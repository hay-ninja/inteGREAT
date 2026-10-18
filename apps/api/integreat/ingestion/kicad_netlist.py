"""Narrow KiCad netlist importer (PRD FR-02, M6).

Supported input: KiCad **XML** netlist ("kicadxml"), e.g.
    kicad-cli sch export netlist --format kicadxml -o board.xml board.kicad_sch
The KiCad 6+ default `.net` (S-expression) format is detected and rejected with that hint.

Netlists describe *electrical connectivity of the designed schematic*, not physical wiring and not
application roles. So:
  1. parse → components + nets (no interpretation),
  2. propose a mapping (MCU ref, which ref is the servo, pin roles) — labelled as a PROPOSAL,
  3. the engineer confirms/edits the mapping,
  4. convert to the same Manifest model the YAML path uses, with every connection `unverified`.
Untrusted XML is parsed with defusedxml (no entity expansion / external entities).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from defusedxml import ElementTree as SafeET
from pydantic import BaseModel, ConfigDict, Field

from .manifest import (
    Manifest,
    ManifestBoard,
    ManifestComponent,
    ManifestConnection,
    ManifestError,
    ManifestPowerSource,
    ManifestSubsystem,
    normalize_mcu_pin,
)

MAX_NETLIST_BYTES = 5 * 1024 * 1024
_GPIO_FUNC = re.compile(r"^(?:GPIO|IO)(\d{1,2})\b", re.I)
_POWER_NAMES = {"GND": "GND", "3V3": "3V3", "+3V3": "3V3", "3.3V": "3V3", "5V": "5V", "+5V": "5V", "VIN": "VIN"}


class NetlistError(ValueError):
    pass


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NetNode(_M):
    ref: str
    pin: str
    pinfunction: str | None = None


class Net(_M):
    code: str
    name: str
    nodes: list[NetNode]


class NetComponent(_M):
    ref: str
    value: str
    part: str | None = None


class NetlistParse(_M):
    file: str
    components: list[NetComponent]
    nets: list[Net]


class ComponentMapping(_M):
    ref: str
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    type: str
    label: str
    pins: dict[str, str]  # netlist pin number → role name (e.g. "1" → "signal")


class PowerMapping(_M):
    ref: str
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    terminals: dict[str, Literal["pos", "neg"]]


class NetlistMapping(_M):
    """Engineer-confirmed interpretation of the netlist. `proposed=True` means nobody has confirmed it."""

    mcu_ref: str
    board_label: str = "ESP32 (from netlist)"
    components: list[ComponentMapping]
    power_sources: list[PowerMapping] = Field(default_factory=list)
    subsystems: list[ManifestSubsystem] = Field(default_factory=list)
    proposed: bool = True
    notes: list[str] = Field(default_factory=list)


def parse_netlist(path: str | Path) -> NetlistParse:
    p = Path(path)
    if not p.is_file():
        raise NetlistError(f"netlist not found: {path}")
    if p.stat().st_size > MAX_NETLIST_BYTES:
        raise NetlistError("netlist too large")
    text = p.read_text(encoding="utf-8", errors="replace").lstrip()
    if text.startswith("(export"):
        raise NetlistError("this is a KiCad S-expression netlist; export XML instead: "
                           "kicad-cli sch export netlist --format kicadxml -o board.xml board.kicad_sch")
    try:
        root = SafeET.fromstring(text)
    except Exception as e:  # defusedxml raises on entities/DTDs; ParseError on garbage
        raise NetlistError(f"not a valid KiCad XML netlist: {e}") from e
    if root.tag != "export":
        raise NetlistError(f"unexpected root element <{root.tag}>, expected <export>")
    comps = []
    for c in root.iter("comp"):
        ls = c.find("libsource")
        comps.append(NetComponent(ref=c.get("ref", "?"), value=(c.findtext("value") or "").strip(),
                                  part=ls.get("part") if ls is not None else None))
    nets = []
    for n in root.iter("net"):
        nodes = [NetNode(ref=x.get("ref", "?"), pin=x.get("pin", "?"), pinfunction=x.get("pinfunction"))
                 for x in n.iter("node")]
        nets.append(Net(code=n.get("code", "?"), name=n.get("name", ""), nodes=nodes))
    if not comps or not nets:
        raise NetlistError("netlist has no components or no nets")
    return NetlistParse(file=p.name, components=comps, nets=nets)


def _net_short(name: str) -> str:
    return name.rsplit("/", 1)[-1].strip()


def mcu_pin_from_node(node: NetNode, net_name: str) -> str | None:
    """Canonical MCU pin name from the symbol's pin function (e.g. IO18 → GPIO18); None if unknown.
    Physical module pin NUMBERS are never treated as GPIO numbers."""
    fn = (node.pinfunction or "").strip()
    m = _GPIO_FUNC.match(fn)
    if m:
        try:
            return normalize_mcu_pin(f"GPIO{m.group(1)}")[0]
        except ManifestError:
            return None
    for cand in (fn.upper(), _net_short(net_name).upper()):
        if cand in _POWER_NAMES:
            return _POWER_NAMES[cand]
    return None


def propose_mapping(nl: NetlistParse, source_stems: list[str]) -> NetlistMapping:
    notes: list[str] = []
    mcu = next((c for c in nl.components if "ESP32" in (c.value + (c.part or "")).upper()), None)
    if mcu is None:
        raise NetlistError("no ESP32 component found (value/part containing 'ESP32'); map the MCU manually")
    pins_by_ref: dict[str, dict[str, str]] = {}
    for net in nl.nets:
        short = _net_short(net.name).upper()
        touches_mcu_gpio = any(n.ref == mcu.ref and _GPIO_FUNC.match(n.pinfunction or "") for n in net.nodes)
        role = ("gnd" if "GND" in short else "vcc" if short in _POWER_NAMES or short.startswith("+") or "VCC" in short
                else "signal" if touches_mcu_gpio else re.sub(r"[^a-z0-9_]", "_", short.lower()) or "net")
        for n in net.nodes:
            if n.ref != mcu.ref:
                pins_by_ref.setdefault(n.ref, {})[n.pin] = role

    components, powers = [], []
    for c in nl.components:
        if c.ref == mcu.ref or c.ref not in pins_by_ref:
            continue
        v = (c.value + " " + (c.part or "")).lower()
        pins = pins_by_ref[c.ref]
        roles = set(pins.values())
        if any(k in v for k in ("power", "pwr", "barrel", "supply", "battery")) or (roles <= {"vcc", "gnd"} and len(pins) == 2):
            powers.append(PowerMapping(ref=c.ref, id=f"psu_{c.ref.lower()}", label=f"{c.value} ({c.ref})",
                                       terminals={p: ("neg" if r == "gnd" else "pos") for p, r in pins.items()}))
            continue
        ctype = "servo" if any(k in v for k in ("servo", "sg90", "mg90")) else "led" if "led" in v else "other"
        components.append(ComponentMapping(ref=c.ref, id=f"{ctype}_{c.ref.lower()}" if ctype != "other" else c.ref.lower(),
                                           type=ctype, label=f"{c.value} ({c.ref})", pins=pins))
    if not any(c.type == "servo" for c in components):
        notes.append("No component looks like a servo; set the servo's type manually.")

    keywords = {"servo": ("servo", "motor"), "led": ("led", "status", "wifi")}
    subsystems: list[ManifestSubsystem] = []
    used: set[str] = set()
    for stem in source_stems:
        sid = re.sub(r"[^a-z0-9_]", "_", stem.lower())
        comps = [c.id for c in components if c.id not in used and c.type in keywords
                 and any(k in stem.lower() for k in keywords[c.type])]
        if not comps:
            continue
        if any(c.type == "servo" for c in components if c.id in comps):
            comps += [p.id for p in powers if p.id not in used]
        used |= set(comps)
        subsystems.append(ManifestSubsystem(id=sid, label=stem.replace("_", " ").title(), source_globs=[f"{stem}.*"],
                                            components=comps))
    if subsystems:
        subsystems[0].source_globs.append("*.ino")
    leftovers = [c.id for c in components if c.id not in used] + [p.id for p in powers if p.id not in used]
    if leftovers:
        subsystems.append(ManifestSubsystem(id="hardware", label="Other hardware", components=leftovers))
    notes.append("Proposed from net names and component values; confirm before relying on it.")
    return NetlistMapping(mcu_ref=mcu.ref, board_label=f"{mcu.value} ({mcu.ref})", components=components,
                          power_sources=powers, subsystems=subsystems, proposed=True, notes=notes)


def to_manifest(nl: NetlistParse, mp: NetlistMapping) -> tuple[Manifest, dict[str, int], list[str]]:
    """Convert to the shared Manifest model. All connections are `unverified` (declared design only)."""
    warnings: list[str] = []
    comp_by_ref = {c.ref: c for c in mp.components}
    psu_by_ref = {p.ref: p for p in mp.power_sources}
    known = {mp.mcu_ref, *comp_by_ref, *psu_by_ref}
    connections: list[ManifestConnection] = []
    for net in nl.nets:
        endpoints: list[tuple[str, str]] = []  # (endpoint ref, role kind hint)
        for n in net.nodes:
            if n.ref == mp.mcu_ref:
                pin = mcu_pin_from_node(n, net.name)
                if pin is None:
                    warnings.append(f"net {net.name}: MCU pin {n.pin} ({n.pinfunction}) not mappable to a GPIO; skipped")
                    continue
                endpoints.append((f"mcu.{pin}", "mcu"))
            elif n.ref in comp_by_ref:
                role = comp_by_ref[n.ref].pins.get(n.pin)
                if role:
                    endpoints.append((f"{comp_by_ref[n.ref].id}.{role}", "comp"))
            elif n.ref in psu_by_ref:
                term = psu_by_ref[n.ref].terminals.get(n.pin)
                if term:
                    endpoints.append((f"{psu_by_ref[n.ref].id}.{term}", "psu"))
            elif n.ref not in known:
                warnings.append(f"net {net.name}: component {n.ref} is not mapped; ignored")
        if len(endpoints) < 2:
            continue
        short = _net_short(net.name).upper()
        is_gnd = "GND" in short or any(e.endswith(".neg") or e.endswith(".GND") for e, _ in endpoints)
        is_pwr = not is_gnd and (short in _POWER_NAMES or short.startswith("+")
                                 or any(e.endswith(".pos") for e, _ in endpoints))
        kind = "ground" if is_gnd else "power" if is_pwr else "signal"
        # Star from the driver (power source first, else MCU) to every other endpoint.
        endpoints.sort(key=lambda e: {"psu": 0, "mcu": 1, "comp": 2}[e[1]])
        hub = endpoints[0][0]
        for other, _ in endpoints[1:]:
            cid = re.sub(r"[^a-z0-9_]", "_", f"net{net.code}_{other}".lower())
            connections.append(ManifestConnection.model_validate(
                {"id": cid, "from": hub, "to": other, "kind": kind, "verification": "unverified",
                 "note": f"KiCad net {net.name} (schematic; not physically verified)"}))
    m = Manifest.model_validate({
        "schema": "integreat-manifest/v1",
        "board": ManifestBoard(id="esp32", label=mp.board_label, mcu="esp32").model_dump(),
        "subsystems": [s.model_dump() for s in mp.subsystems],
        "components": [ManifestComponent(id=c.id, type=c.type, label=c.label, pins=sorted(set(c.pins.values())),
                                         attributes={"netlist_ref": c.ref}).model_dump() for c in mp.components],
        "power_sources": [ManifestPowerSource(id=p.id, label=p.label, terminals=sorted(set(p.terminals.values())))
                          .model_dump() for p in mp.power_sources],
        "connections": [c.model_dump(by_alias=True) for c in connections],
    })
    return m, {}, warnings
