"""Build the system graph with provenance from parsed source + manifest (PRD FR-03, §9.2 step 1).

Edge semantics stay separate (FR-03): `calls` = static call graph, `configures` = source config,
`connected_to`/`powered_by` = declared wiring, `controls` = inferred dependency. None of these is a
causal claim.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..ingestion.arduino_parser import ParsedProject
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


def endpoint_node_id(ep: Endpoint) -> str:
    if ep.part_kind == "mcu":
        return mcu_pin_node_id(ep.pin)
    if ep.part_kind == "component":
        return f"pin:{ep.part_id}.{ep.pin}"
    return f"power_source:{ep.part_id}"


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
        servo_components = self._hardware()
        self._source_hardware_links(servo_components)
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
        for rel in self.files:
            name = PurePosixPath(rel).name
            sid = next((f"subsystem:{s.id}" for s in subs if any(fnmatch.fnmatch(name, g) for g in s.source_globs)), UNASSIGNED)
            module_sub[rel] = sid
        for s in subs:
            ev = manifest_evidence_id(f"subsystem_{s.id}")
            self.evidence(ev, self.hw_kind, Epistemic.verified, f"{self.hw_word} declares subsystem '{s.label}'",
                          Provenance(source_id=self.hw_src, file=self.mrel, line_start=self.mlines.get(s.id)))
            self.node(f"subsystem:{s.id}", NodeKind.subsystem, s.label, Verification.verified, evidence_ids=[ev],
                      subsystem_id=f"subsystem:{s.id}")
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
        self.node("mcu:esp32", NodeKind.mcu, m.board.label, Verification.verified, attributes={"board": m.board.id})
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
                self.edge(endpoint_node_id(a), endpoint_node_id(b), EdgeRelation.connected_to,
                          EdgeOrigin.declared_wiring, ver, evidence_ids=[ev], label=conn.kind, attributes=attrs)
        return [f"component:{c.id}" for c in m.components if c.type == "servo"]

    def _mcu_pin(self, canonical: str, gpio: int | None) -> str:
        pid = mcu_pin_node_id(canonical)
        attrs = {"gpio": gpio} if gpio is not None else {}
        if gpio in ESP32_INPUT_ONLY:
            attrs["input_only"] = True
        self.node(pid, NodeKind.pin, canonical, Verification.verified, parent_id="mcu:esp32", attributes=attrs)
        self.edge("mcu:esp32", pid, EdgeRelation.contains, EdgeOrigin.structural, Verification.verified)
        return pid

    def _source_hardware_links(self, servo_components: list[str]) -> None:
        has_mcu = "mcu:esp32" in self._nodes
        servo_target = servo_components[0] if len(servo_components) == 1 else None
        if len(servo_components) > 1 and self.p.objects:
            self.issue("warning", "AMBIGUOUS_SERVO_MAPPING",
                       "Multiple servo components declared; source servo objects are not auto-mapped")

        for pu in self.p.pin_uses:
            if pu.gpio is None or pu.function_id is None:
                continue
            tag = f"pin_{pu.api}"
            via = f" via {pu.symbol.name} ({pu.symbol.file}:{pu.symbol.line})" if pu.symbol else ""
            ev = [self.src_ev(pu.file, pu.line, tag, f"`{pu.call_text}` configures GPIO{pu.gpio}{via}",
                              api=pu.api, gpio=pu.gpio, raw_arg=pu.raw_arg, resolution=pu.resolution,
                              object_name=pu.object_name, object_type=pu.object_type)]
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
            attrs = {"api": pu.api, "gpio": pu.gpio}
            if pu.object_type and servo_target:
                attrs["for_component"] = servo_target
            self.edge(pu.function_id, pid, EdgeRelation.configures, EdgeOrigin.source_config, Verification.inferred,
                      evidence_ids=ev, label=pu.api, attributes=attrs)
            if pu.object_type and servo_target:
                self.edge(pu.function_id, servo_target, EdgeRelation.controls, EdgeOrigin.inferred_dependency,
                          Verification.inferred, evidence_ids=ev, label=f"via {pu.object_name}")

        for ac in self.p.actuator_calls:
            if ac.function_id is None or not servo_target:
                continue
            ev = self.src_ev(ac.file, ac.line, f"act_{ac.method}", f"`{ac.call_text}` commands {ac.object_name}")
            self.edge(ac.function_id, servo_target, EdgeRelation.controls, EdgeOrigin.inferred_dependency,
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
        mcu_pin = next((x for x in ends if x.startswith("pin:esp32_")), None)
        if comp_pin and mcu_pin:
            return e, mcu_pin
    return None


def consistency_issues(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[ImportIssue]:
    """Flag source pin config that contradicts declared wiring (visible before any test). Mutates the
    verification of `configures` edges: conflicting when mismatched, inferred otherwise."""
    labels = {n.id: n.label for n in nodes}
    issues = []
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
