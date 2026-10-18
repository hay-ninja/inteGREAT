"""Build the system graph with provenance from parsed source + manifest (PRD FR-03, §9.2 step 1).

Edge semantics stay separate (FR-03): `calls` = static call graph, `configures` = source config,
`connected_to`/`powered_by` = declared wiring, `controls` = inferred dependency. None of these is a
causal claim.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..ingestion.arduino_parser import OBJECT_TYPE_HINTS, WRITE_VALUE_ARG, ParsedProject
from ..ingestion.manifest import Endpoint, Manifest, mcu_pin_node_id, resolve_endpoint
from ..ingestion.manifest import ESP32_INPUT_ONLY
from ..models import (
    EdgeOrigin,
    EdgeRelation,
    Epistemic,
    Evidence,
    EvidenceKind,
    GraphEdge,
    GraphNode,
    ImportIssue,
    NodeKind,
    Provenance,
    Subsystem,
    Verification,
)

UNASSIGNED = "subsystem:unassigned"


@dataclass
class BuildResult:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    issues: list[ImportIssue] = field(default_factory=list)
    subsystems: list[Subsystem] = field(default_factory=list)


def src_evidence_id(file: str, line: int, tag: str) -> str:
    return f"evidence:src:{file}:{line}:{tag}"


def manifest_evidence_id(item_id: str) -> str:
    return f"evidence:manifest:{item_id}"


def endpoint_node_id(ep: Endpoint, board: str) -> str:
    if ep.part_kind == "mcu":
        return mcu_pin_node_id(board, ep.pin)
    if ep.part_kind == "component":
        return f"pin:{ep.part_id}.{ep.pin}"
    return f"power_source:{ep.part_id}"


# Pin apis that drive a physical state (vs. pinMode which only configures).
WRITE_APIS = set(WRITE_VALUE_ARG)

# Symbol-name hints for guessing the kind of an otherwise-unknown output component.
# Matched case-insensitively against the pin symbol/object name. Guesses stay unverified.
_NAME_TYPE_HINTS: list[tuple[str, str]] = [
    ("led", "led"), ("servo", "servo"), ("motor", "motor"), ("fan", "fan"),
    ("relay", "relay"), ("buzz", "buzzer"), ("pump", "pump"), ("heat", "heater"),
]


class _Builder:
    def __init__(self, project_id: str, files: list[str], parsed: ParsedProject,
                 manifest: Manifest | None, manifest_lines: dict[str, int], manifest_rel: str | None,
                 hardware_source: str = "manifest"):
        self.pid = project_id
        self.hw_kind = EvidenceKind.netlist_entry if hardware_source == "netlist" else EvidenceKind.manifest_entry
        self.hw_src = hardware_source
        self.hw_word = "Netlist" if hardware_source == "netlist" else "Manifest"
        self.files = files
        self.p = parsed
        self.m = manifest
        self.mlines = manifest_lines
        self.mrel = manifest_rel
        self.r = BuildResult()
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._evidence: dict[str, Evidence] = {}
        self.board = manifest.board.id if manifest else "esp32"
        self.mcu_id = f"mcu:{self.board}"

    # ---- primitives
    def node(self, id: str, kind: NodeKind, label: str, verification: Verification, **kw) -> GraphNode:
        if id in self._nodes:
            n = self._nodes[id]
            for e in kw.get("evidence_ids", []):
                if e not in n.evidence_ids:
                    n.evidence_ids.append(e)
            return n
        n = GraphNode(id=id, project_id=self.pid, kind=kind, label=label, verification=verification, **kw)
        self._nodes[id] = n
        return n

    def edge(self, src: str, dst: str, rel: EdgeRelation, origin: EdgeOrigin, ver: Verification, **kw) -> GraphEdge:
        eid = f"edge:{rel.value}:{src}->{dst}"
        if eid in self._edges:
            e = self._edges[eid]
            for ev in kw.get("evidence_ids", []):
                if ev not in e.evidence_ids:
                    e.evidence_ids.append(ev)
            return e
        e = GraphEdge(id=eid, project_id=self.pid, source_id=src, target_id=dst, relation=rel,
                      origin=origin, verification=ver, **kw)
        self._edges[eid] = e
        return e

    def evidence(self, id: str, kind: EvidenceKind, epi: Epistemic, summary: str, prov: Provenance,
                 payload: dict | None = None) -> str:
        if id not in self._evidence:
            self._evidence[id] = Evidence(id=id, project_id=self.pid, kind=kind, epistemic=epi,
                                          summary=summary, provenance=prov, payload=payload or {})
        return id

    def src_ev(self, file: str, line: int, tag: str, summary: str, epi=Epistemic.inferred, **payload) -> str:
        return self.evidence(src_evidence_id(file, line, tag), EvidenceKind.source_excerpt, epi, summary,
                             Provenance(source_id="repo", file=file, line_start=line, line_end=line), payload)

    def issue(self, level, code, message, **kw):
        self.r.issues.append(ImportIssue(level=level, code=code, message=message, **kw))

    # ---- build steps
    def build(self) -> BuildResult:
        module_sub = self._subsystems()
        self._source(module_sub)
        self._hardware()          # declared components first — they're authoritative
        self._hardware_inferred() # code-derived components fill gaps, never override
        self._source_hardware_links()
        self._static_consistency()
        for msg, file, line in self.p.warnings:
            self.issue("warning", "PARSER_UNCERTAIN", msg, file=file, line=line)
        self.r.nodes = list(self._nodes.values())
        self.r.edges = list(self._edges.values())
        self.r.evidence = list(self._evidence.values())
        return self.r

    def _subsystems(self) -> dict[str, str]:
        subs = self.m.subsystems if self.m else []
        module_sub: dict[str, str] = {}
        unassigned: list[str] = []
        for rel in self.files:
            name = PurePosixPath(rel).name
            sid = next((f"subsystem:{s.id}" for s in subs
                        if any(fnmatch.fnmatch(name, g) for g in s.source_globs)), None)
            if sid is None:
                unassigned.append(rel)
            module_sub[rel] = sid or UNASSIGNED
        for s in subs:
            ev = manifest_evidence_id(f"subsystem_{s.id}")
            self.evidence(ev, self.hw_kind, Epistemic.verified, f"{self.hw_word} declares subsystem '{s.label}'",
                          Provenance(source_id=self.hw_src, file=self.mrel, line_start=self.mlines.get(s.id)))
            self.node(f"subsystem:{s.id}", NodeKind.subsystem, s.label, Verification.verified, evidence_ids=[ev],
                      subsystem_id=f"subsystem:{s.id}")
        # Files a manifest didn't claim get grouped by filename stem: header+impl pairs and
        # related same-stem files cluster into an inferred subsystem instead of all landing
        # under "Unassigned". Inferred, evidence-cited; declared globs always win.
        by_stem: dict[str, list[str]] = {}
        for rel in unassigned:
            by_stem.setdefault(PurePosixPath(rel).stem.lower(), []).append(rel)
        sketch = [r for r in unassigned if r.endswith(".ino")]
        for stem, members in sorted(by_stem.items()):
            single = len(members) == 1
            if single and members[0] not in sketch:
                continue  # a lone non-sketch file stays Unassigned rather than a 1-file group
            label = "Sketch" if members[0] in sketch and single else stem.replace("_", " ").title()
            sid = f"subsystem:inferred:{stem}"
            self.node(sid, NodeKind.subsystem, label, Verification.inferred, subsystem_id=sid)
            for rel in members:
                module_sub[rel] = sid
            self.issue("info", "SUBSYSTEM_INFERRED",
                       f"'{label}' grouped from filename stem '{stem}' — no manifest declaration")
        if UNASSIGNED in module_sub.values() or not subs:
            self.node(UNASSIGNED, NodeKind.subsystem, "Unassigned", Verification.inferred, subsystem_id=UNASSIGNED)
        return module_sub

    def _source(self, module_sub: dict[str, str]) -> None:
        for rel in self.files:
            sid = module_sub[rel]
            mid = f"module:{rel}"
            self.node(mid, NodeKind.source_module, PurePosixPath(rel).name, Verification.observed,
                      parent_id=sid, subsystem_id=sid, attributes={"path": rel})
            self.edge(sid, mid, EdgeRelation.contains, EdgeOrigin.structural, Verification.inferred)
        for fn in self.p.functions:
            ev = self.src_ev(fn.file, fn.line_start, "def", f"Definition of {fn.name}()", Epistemic.observed)
            mid = f"module:{fn.file}"
            sid = self._nodes[mid].subsystem_id
            self.node(fn.id, NodeKind.function, f"{fn.name}()", Verification.observed, parent_id=mid,
                      subsystem_id=sid, evidence_ids=[ev],
                      attributes={"file": fn.file, "line_start": fn.line_start, "line_end": fn.line_end})
            self.edge(mid, fn.id, EdgeRelation.contains, EdgeOrigin.structural, Verification.observed)
        by_name: dict[str, list[str]] = {}
        for fn in self.p.functions:
            by_name.setdefault(fn.name, []).append(fn.id)
        for c in self.p.calls:
            targets = by_name.get(c.callee_name, [])
            if len(targets) != 1:
                continue  # ambiguous overloads: don't guess
            ev = self.src_ev(c.file, c.line, f"call_{c.callee_name}", f"Static call to {c.callee_name}()")
            self.edge(c.caller_id, targets[0], EdgeRelation.calls, EdgeOrigin.source_call_graph,
                      Verification.inferred, evidence_ids=[ev])

    def _hardware(self) -> list[str]:
        if not self.m:
            self.issue("warning", "NO_HARDWARE_CONTEXT", "No manifest or netlist provided; hardware graph is empty")
            return []
        m = self.m
        sub_of = {cid: f"subsystem:{s.id}" for s in m.subsystems for cid in s.components}
        self.node(self.mcu_id, NodeKind.mcu, m.board.label, Verification.verified,
                  attributes={"board": m.board.id})
        for c in m.components:
            ev = self.evidence(manifest_evidence_id(c.id), self.hw_kind, Epistemic.verified,
                               f"{self.hw_word} declares {c.type} '{c.label}' with pins {', '.join(c.pins)}",
                               Provenance(source_id=self.hw_src, file=self.mrel, line_start=self.mlines.get(c.id)))
            cid = f"component:{c.id}"
            self.node(cid, NodeKind.component, c.label, Verification.verified, subsystem_id=sub_of.get(c.id),
                      attributes={"type": c.type, **c.attributes}, evidence_ids=[ev])
            for pin in c.pins:
                pid = f"pin:{c.id}.{pin}"
                self.node(pid, NodeKind.pin, f"{c.id}.{pin}", Verification.verified, parent_id=cid,
                          subsystem_id=sub_of.get(c.id), attributes={"pin": pin})
                self.edge(cid, pid, EdgeRelation.contains, EdgeOrigin.structural, Verification.verified)
        for ps in m.power_sources:
            ev = self.evidence(manifest_evidence_id(ps.id), self.hw_kind, Epistemic.verified,
                               f"{self.hw_word} declares power source '{ps.label}'",
                               Provenance(source_id=self.hw_src, file=self.mrel, line_start=self.mlines.get(ps.id)))
            self.node(f"power_source:{ps.id}", NodeKind.power_source, ps.label, Verification.verified,
                      subsystem_id=sub_of.get(ps.id), evidence_ids=[ev])

        for conn in m.connections:
            a, b = resolve_endpoint(m, conn.from_), resolve_endpoint(m, conn.to)
            ver = Verification.verified if conn.verification == "verified" else Verification.unverified
            epi = Epistemic.verified if conn.verification == "verified" else Epistemic.inferred
            ev = self.evidence(manifest_evidence_id(conn.id), self.hw_kind, epi,
                               f"{self.hw_word}: {conn.from_} → {conn.to} ({conn.kind}, {conn.verification})"
                               + (f" — {conn.note}" if conn.note else ""),
                               Provenance(source_id=self.hw_src, file=self.mrel, line_start=self.mlines.get(conn.id)),
                               {"connection_id": conn.id, "kind": conn.kind, "verification": conn.verification})
            for ep in (a, b):
                if ep.part_kind == "mcu":
                    self._mcu_pin(ep.pin, ep.gpio)
            attrs = {"kind": conn.kind, "connection_id": conn.id}
            if conn.kind == "power" and b.part_kind == "component" and a.part_kind == "power_source":
                self.edge(f"component:{b.part_id}", f"power_source:{a.part_id}", EdgeRelation.powered_by,
                          EdgeOrigin.declared_wiring, ver, evidence_ids=[ev], label=f"{a.pin}→{b.pin}", attributes=attrs)
            else:
                self.edge(endpoint_node_id(a, self.board), endpoint_node_id(b, self.board),
                          EdgeRelation.connected_to,
                          EdgeOrigin.declared_wiring, ver, evidence_ids=[ev], label=conn.kind, attributes=attrs)
        return

    def _mcu_pin(self, canonical: str, gpio: int | None) -> str:
        pid = mcu_pin_node_id(self.board, canonical)
        attrs = {"gpio": gpio} if gpio is not None else {}
        if gpio in ESP32_INPUT_ONLY:
            attrs["input_only"] = True
        self.node(pid, NodeKind.pin, canonical, Verification.verified, parent_id=self.mcu_id, attributes=attrs)
        self.edge(self.mcu_id, pid, EdgeRelation.contains, EdgeOrigin.structural, Verification.verified)
        return pid

    def _component_for_gpio(self, gpio: int, declared_only: bool = True) -> str | None:
        """Resolve an MCU pin to the component wired to it — the pin-mediated path that makes
        actuation edges work for any component type, not just servo objects. Declared wiring
        wins over inferred wiring: an unverified guess must not outrank a manifest."""
        pin_id = mcu_pin_node_id(self.board, f"GPIO{gpio}")
        comps: list[str] = []
        for e in self._edges.values():
            if e.relation != EdgeRelation.connected_to or e.attributes.get("kind") != "signal":
                continue
            if pin_id not in (e.source_id, e.target_id):
                continue
            other = e.target_id if e.source_id == pin_id else e.source_id
            m = re.match(r"pin:([a-z0-9_]+)\.", other)
            if m:
                comps.append(f"component:{m.group(1)}")
        declared = sorted(c for c in set(comps)
                          if not self._nodes.get(c) or not self._nodes[c].attributes.get("inferred"))
        pool = declared if declared_only else sorted(set(comps))
        if len(pool) > 1:
            self.issue("warning", "AMBIGUOUS_PIN_MAPPING",
                       f"GPIO{gpio} is wired to multiple components {pool}; actuation edges not guessed")
            return None
        return pool[0] if pool else None

    def _subsystem_component(self, function_id: str | None) -> str | None:
        """The sole declared component of the source file's subsystem (`led_control.cpp` in
        `lighting` → its one component). Subsystem attribution is what lets a write to a
        *wrong* pin still attribute to the intended component — exposing the mismatch."""
        fn = self._nodes.get(function_id) if function_id else None
        sub = fn.subsystem_id if fn else None
        if not sub:
            return None
        comps = [n.id for n in self._nodes.values()
                 if n.kind == NodeKind.component and n.subsystem_id == sub
                 and not n.attributes.get("inferred")]
        return comps[0] if len(comps) == 1 else None

    def _resolve_component(self, gpio: int, object_type: str | None,
                           function_id: str | None = None) -> str | None:
        """Component attribution, in precedence order: declared wiring on the pin → sole
        declared component matching the object's type → sole declared component of the
        file's subsystem → inferred wiring on the pin."""
        comp = self._component_for_gpio(gpio, declared_only=True)
        if comp:
            return comp
        if object_type:
            ctype = OBJECT_TYPE_HINTS.get(object_type)
            cands = [n.id for n in self._nodes.values()
                     if n.kind == NodeKind.component and n.attributes.get("type") == ctype
                     and not n.attributes.get("inferred")]
            if len(cands) == 1:
                return cands[0]
        comp = self._subsystem_component(function_id)
        return comp or self._component_for_gpio(gpio, declared_only=False)

    def _ensure_mcu(self) -> bool:
        """Create an inferred MCU node when source uses GPIO pins but no manifest declared a
        board. The pin model is still esp32; the node is marked inferred, never verified."""
        if self.mcu_id in self._nodes:
            return True
        if not self.p.pin_uses:
            return False
        self.node(self.mcu_id, NodeKind.mcu, f"MCU (assumed {self.board} — no manifest)",
                  Verification.inferred, attributes={"board": self.board, "inferred": True})
        self.issue("info", "MCU_INFERRED",
                   f"No manifest declared a board; assumed {self.board} from source GPIO usage")
        return True

    def _inferred_component(self, name: str, gpio: int | None, type_hint: str | None,
                            ev_ids: list[str]) -> str:
        """Create (or return) an inferred component for something the code drives but no
        manifest declared. Unverified — hardware existence is never claimed from code alone."""
        cid = f"component:{name}"
        if cid in self._nodes:
            return cid
        label = f"{type_hint or 'output'} '{name}'" + (f" on GPIO{gpio}" if gpio is not None else "")
        self.node(cid, NodeKind.component, label, Verification.unverified,
                  attributes={"type": type_hint or "output", "inferred": True},
                  evidence_ids=ev_ids)
        self.issue("info", "COMPONENT_INFERRED",
                   f"'{label}' inferred from source — confirm hardware in a manifest")
        if gpio is not None and self._ensure_mcu():
            pid = self._mcu_pin(f"GPIO{gpio}", gpio)
            self._nodes[pid].verification = Verification.inferred
            ppin = f"pin:{name}.signal"
            self.node(ppin, NodeKind.pin, f"{name}.signal", Verification.unverified,
                      parent_id=cid, attributes={"pin": "signal", "inferred": True})
            self.edge(cid, ppin, EdgeRelation.contains, EdgeOrigin.structural, Verification.unverified)
            self.edge(pid, ppin, EdgeRelation.connected_to, EdgeOrigin.inferred_dependency,
                      Verification.unverified, evidence_ids=ev_ids, label="signal",
                      attributes={"kind": "signal", "inferred": True})
        return cid

    def _hardware_inferred(self) -> None:
        """Code-derived hardware: declared objects (Servo myservo) and name-hinted pin symbols
        (LED_PIN) become unverified component nodes when the manifest didn't declare them.
        Inferred wiring only materializes when no declared component already covers the pin."""
        for name, (otype, file, line) in self.p.objects.items():
            ev = [self.src_ev(file, line, f"obj_{name}", f"Declaration of {otype} {name}",
                              Epistemic.observed, object_name=name, object_type=otype)]
            declared = [n for n in self._nodes.values() if n.kind == NodeKind.component
                        and n.attributes.get("type") == OBJECT_TYPE_HINTS.get(otype)
                        and not n.attributes.get("inferred")]
            if declared:
                # declared wins: the object is evidence FOR the manifest component, not a new one
                for e in ev:
                    if e not in declared[0].evidence_ids:
                        declared[0].evidence_ids.append(e)
                continue
            self._inferred_component(name, None, OBJECT_TYPE_HINTS.get(otype), ev)
        for pu in self.p.pin_uses:
            if pu.gpio is None or pu.api not in WRITE_APIS:
                continue
            if self._component_for_gpio(pu.gpio):
                continue  # declared (or already-inferred) component covers this pin
            if self._subsystem_component(pu.function_id):
                continue  # the file's subsystem attributes this write to a declared
                # component — inventing a twin here would hide wrong-pin mismatches
            sym = pu.symbol.name if pu.symbol else None
            if sym is None:
                continue  # anonymous literal pins don't justify inventing hardware
            hint = next((t for key, t in _NAME_TYPE_HINTS if key in sym.lower()), None)
            ev = [self.src_ev(pu.file, pu.line, f"pin_{pu.api}", f"`{pu.call_text}` drives GPIO{pu.gpio}",
                              api=pu.api, gpio=pu.gpio)]
            self._inferred_component(sym.lower(), pu.gpio, hint, ev)

    def _source_hardware_links(self) -> None:
        """Actuation resolves THROUGH THE PIN: a write on GPIO n controls whatever component's
        declared/inferred signal wiring lands on pin:{board}_gpio{n}. Object-type knowledge
        (servo.attach → object→pin binding, obj.write() → actuation) feeds the same path."""
        has_mcu = self._ensure_mcu()
        obj_pin: dict[str, int] = {}  # object name -> bound gpio (from .attach etc.)

        for pu in self.p.pin_uses:
            if pu.gpio is None or pu.function_id is None:
                continue
            if pu.object_name is not None:
                obj_pin[pu.object_name] = pu.gpio
            tag = f"pin_{pu.api}"
            via = f" via {pu.symbol.name} ({pu.symbol.file}:{pu.symbol.line})" if pu.symbol else ""
            ev = [self.src_ev(pu.file, pu.line, tag, f"`{pu.call_text}` configures GPIO{pu.gpio}{via}",
                              api=pu.api, gpio=pu.gpio, raw_arg=pu.raw_arg, resolution=pu.resolution,
                              level=pu.level, object_name=pu.object_name, object_type=pu.object_type)]
            if pu.symbol:
                ev.append(self.src_ev(pu.symbol.file, pu.symbol.line, "symbol",
                                      f"{pu.symbol.kind} {pu.symbol.name} = {pu.symbol.raw_value}",
                                      Epistemic.observed, name=pu.symbol.name, value=pu.symbol.raw_value))
            if not has_mcu:
                continue
            canonical = f"GPIO{pu.gpio}"
            pid = self._mcu_pin(canonical, pu.gpio)
            if self._nodes[pid].verification == Verification.verified and not any(
                e.target_id == pid or e.source_id == pid for e in self._edges.values() if e.relation == EdgeRelation.connected_to
            ):
                self._nodes[pid].verification = Verification.inferred  # only known from source
            comp = self._resolve_component(pu.gpio, pu.object_type, pu.function_id)
            attrs = {"api": pu.api, "gpio": pu.gpio}
            if pu.level is not None:
                attrs["level"] = pu.level
            if comp:
                attrs["for_component"] = comp
            self.edge(pu.function_id, pid, EdgeRelation.configures, EdgeOrigin.source_config, Verification.inferred,
                      evidence_ids=ev, label=pu.api, attributes=attrs)
            if comp and (pu.api in WRITE_APIS or pu.object_type):
                # a pin write actuates the wired component; .attach binds a servo object to it
                lbl = f"via {pu.object_name}" if pu.object_name else pu.api
                self.edge(pu.function_id, comp, EdgeRelation.controls, EdgeOrigin.inferred_dependency,
                          Verification.inferred, evidence_ids=ev, label=lbl)

        for ac in self.p.actuator_calls:
            if ac.function_id is None:
                continue
            comp = (self._component_for_gpio(obj_pin[ac.object_name])
                    if ac.object_name in obj_pin else None)
            if comp is None:
                # object not bound to a pin — fall back to the sole declared/inferred
                # component of the object's type, if unambiguous
                ctype = OBJECT_TYPE_HINTS.get(ac.object_type or "")
                cands = [n.id for n in self._nodes.values()
                         if n.kind == NodeKind.component and n.attributes.get("type") == ctype]
                comp = cands[0] if len(cands) == 1 else None
            if comp is None:
                continue
            ev = self.src_ev(ac.file, ac.line, f"act_{ac.method}", f"`{ac.call_text}` commands {ac.object_name}")
            self.edge(ac.function_id, comp, EdgeRelation.controls, EdgeOrigin.inferred_dependency,
                      Verification.inferred, evidence_ids=[ev], label=f"{ac.object_name}.{ac.method}")

        for lit in self.p.command_literals:
            self.src_ev(lit.file, lit.line, "cmd", f"Firmware matches serial command prefix \"{lit.text}\"",
                        Epistemic.observed, literal=lit.text)

    def _static_consistency(self) -> None:
        self.r.issues += consistency_issues(list(self._nodes.values()), list(self._edges.values()))


def signal_wiring_for(component_id: str, edges: list[GraphEdge]) -> tuple[GraphEdge, str] | None:
    """Return (connected_to edge, mcu pin node id) for the component's signal wiring, if declared."""
    prefix = f"pin:{component_id.removeprefix('component:')}."
    for e in edges:
        if e.relation != EdgeRelation.connected_to or e.attributes.get("kind") != "signal":
            continue
        ends = {e.source_id, e.target_id}
        comp_pin = next((x for x in ends if x.startswith(prefix)), None)
        # MCU pins are pin:{board}_* (no dot); component pins are pin:{comp}.{pin} (dotted)
        mcu_pin = next((x for x in ends if x.startswith("pin:") and "." not in x), None)
        if comp_pin and mcu_pin:
            return e, mcu_pin
    return None


def consistency_issues(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[ImportIssue]:
    """Flag source pin config that contradicts declared wiring (visible before any test). Mutates the
    verification of `configures` edges: conflicting when mismatched, inferred otherwise."""
    labels = {n.id: n.label for n in nodes}
    issues = []
    flagged: set[tuple[str, str]] = set()  # one issue per (configured pin, component) pair
    for e in edges:
        comp = e.attributes.get("for_component")
        if e.relation != EdgeRelation.configures or not comp:
            continue
        e.verification = Verification.inferred
        wired = signal_wiring_for(comp, edges)
        if not wired or wired[1] == e.target_id:
            continue
        wire_edge, mcu_pin_id = wired
        e.verification = Verification.conflicting
        if (e.target_id, comp) in flagged:
            continue
        flagged.add((e.target_id, comp))
        issues.append(ImportIssue(
            level="warning", code="GPIO_CONFIG_MISMATCH",
            message=(f"Source configures {labels[e.target_id]} for {labels[comp]}, but "
                     f"{wire_edge.verification.value} wiring connects it to {labels[mcu_pin_id]}"),
            evidence_ids=e.evidence_ids + wire_edge.evidence_ids,
            related_node_ids=[e.target_id, mcu_pin_id, comp], related_edge_ids=[e.id, wire_edge.id]))
    return issues


def build_graph(project_id: str, files: list[str], parsed: ParsedProject, manifest: Manifest | None,
                manifest_lines: dict[str, int] | None = None, manifest_rel: str | None = None,
                hardware_source: str = "manifest") -> BuildResult:
    r = _Builder(project_id, files, parsed, manifest, manifest_lines or {}, manifest_rel, hardware_source).build()
    module_ids = [n.id for n in r.nodes if n.kind == NodeKind.source_module]
    comp_ids = [n.id for n in r.nodes if n.kind in (NodeKind.component, NodeKind.power_source)]
    for n in r.nodes:
        if n.kind == NodeKind.subsystem:
            r.subsystems.append(Subsystem(
                id=n.id, label=n.label,
                module_ids=[m for m in module_ids if next(x for x in r.nodes if x.id == m).subsystem_id == n.id],
                component_ids=[c for c in comp_ids if next(x for x in r.nodes if x.id == c).subsystem_id == n.id],
            ))
    return r
