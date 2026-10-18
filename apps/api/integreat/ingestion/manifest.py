"""Hardware manifest loader (PRD FR-02 fallback) and ESP32 pin normalization.

Pin normalization is deliberately narrow: we accept GPIO numbers ("GPIO18", "IO18", "G18", "18")
and power names. Board silkscreen labels like "D18" are board-specific and are NOT guessed
(PRD §6 Fault A note) — they produce a validation error.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ESP32 (classic) GPIOs that exist on the chip. 6-11 are flash pins; 34-39 are input-only.
ESP32_GPIOS = set(range(0, 6)) | set(range(12, 20)) | {21, 22, 23, 25, 26, 27} | set(range(32, 40))
ESP32_FLASH_GPIOS = set(range(6, 12))
ESP32_INPUT_ONLY = set(range(34, 40))
POWER_PINS = {"GND", "3V3", "5V", "VIN", "EN"}

_GPIO_RE = re.compile(r"^(?:GPIO|IO|G)?\s*(\d{1,2})$", re.I)


class ManifestError(ValueError):
    pass


def normalize_mcu_pin(label: str) -> tuple[str, int | None]:
    """Return (canonical_name, gpio_number). Raise ManifestError for unknown/ambiguous labels."""
    s = label.strip().upper()
    if s in POWER_PINS:
        return s, None
    m = _GPIO_RE.match(s)
    if not m:
        raise ManifestError(
            f"unrecognized ESP32 pin label {label!r}; use GPIO numbers (e.g. GPIO18) — "
            "board silkscreen labels are not mapped automatically"
        )
    n = int(m.group(1))
    if n in ESP32_FLASH_GPIOS:
        raise ManifestError(f"GPIO{n} is connected to SPI flash on ESP32 modules and cannot be used")
    if n not in ESP32_GPIOS:
        raise ManifestError(f"GPIO{n} does not exist on ESP32")
    return f"GPIO{n}", n


def mcu_pin_node_id(board: str, canonical: str) -> str:
    """Pin node ids are keyed by the declared board id, so `pin:esp32_gpio18` stays stable
    for esp32 manifests while other boards get their own namespace."""
    return f"pin:{board}_{canonical.lower()}"


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestBoard(_M):
    id: str
    label: str
    mcu: Literal["esp32"]


class ManifestSubsystem(_M):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    source_globs: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)


class ManifestComponent(_M):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    type: str
    label: str
    pins: list[str]
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)


class ManifestPowerSource(_M):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    terminals: list[str]


class ManifestConnection(_M):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    from_: str = Field(alias="from")
    to: str
    kind: Literal["signal", "power", "ground"]
    verification: Literal["verified", "unverified"] = "unverified"
    note: str | None = None

    @field_validator("from_", "to")
    @classmethod
    def _endpoint(cls, v: str) -> str:
        if v.count(".") != 1:
            raise ValueError(f"endpoint must be '<part>.<pin>': {v!r}")
        return v


class Manifest(_M):
    schema_: Literal["integreat-manifest/v1"] = Field(alias="schema")
    board: ManifestBoard
    subsystems: list[ManifestSubsystem]
    components: list[ManifestComponent]
    power_sources: list[ManifestPowerSource] = Field(default_factory=list)
    connections: list[ManifestConnection]


class Endpoint(BaseModel):
    part_kind: Literal["mcu", "component", "power_source"]
    part_id: str
    pin: str  # canonical
    gpio: int | None = None


def resolve_endpoint(m: Manifest, ref: str) -> Endpoint:
    part, pin = ref.split(".")
    if part == "mcu":
        canon, gpio = normalize_mcu_pin(pin)
        return Endpoint(part_kind="mcu", part_id="mcu", pin=canon, gpio=gpio)
    for c in m.components:
        if c.id == part:
            if pin not in c.pins:
                raise ManifestError(f"component {part!r} has no pin {pin!r} (declared: {c.pins})")
            return Endpoint(part_kind="component", part_id=part, pin=pin)
    for p in m.power_sources:
        if p.id == part:
            if pin not in p.terminals:
                raise ManifestError(f"power source {part!r} has no terminal {pin!r}")
            return Endpoint(part_kind="power_source", part_id=part, pin=pin)
    raise ManifestError(f"unknown part {part!r} in connection endpoint {ref!r}")


def load_manifest(path: str | Path) -> tuple[Manifest, str, dict[str, int]]:
    """Return (manifest, raw_text, connection_id -> line number) so evidence can cite lines."""
    p = Path(path)
    if not p.is_file():
        raise ManifestError(f"manifest not found: {path}")
    text = p.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ManifestError(f"manifest is not valid YAML: {e}") from e
    try:
        m = Manifest.model_validate(data)
    except Exception as e:  # pydantic ValidationError -> readable message
        raise ManifestError(f"manifest failed validation: {e}") from e
    for conn in m.connections:  # validate endpoints eagerly; fail import loudly, never guess
        resolve_endpoint(m, conn.from_)
        resolve_endpoint(m, conn.to)
    lines: dict[str, int] = {}
    for i, line in enumerate(text.splitlines(), start=1):
        mm = re.match(r"^\s*-\s*id:\s*([a-z0-9_]+)\s*$", line)
        if mm and mm.group(1) not in lines:
            lines[mm.group(1)] = i
    return m, text, lines
