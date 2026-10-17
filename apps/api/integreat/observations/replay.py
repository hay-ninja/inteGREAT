"""Replay observation source: streams recorded (or SYNTHETIC) serial/CV events (PRD §8 Reproducibility).

Replay is a first-class source so the whole loop can be developed and demoed honestly without
hardware. Every run from replay is marked `synthetic`/`replay` and the UI must label it.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import ReplayInfo

_NAME = re.compile(r"^[a-z0-9_]+$")


class ReplayError(ValueError):
    pass


@dataclass
class ReplayEvent:
    t_ms: int
    source: str  # "host" | "serial" | "cv"
    data: dict[str, Any]


@dataclass
class ReplayStream:
    scenario: str
    synthetic: bool
    description: str
    command: str | None
    events: list[ReplayEvent]

    async def play(self, speed: float) -> AsyncIterator[ReplayEvent]:
        """Yield events, pacing in real time / speed. speed <= 0 means as fast as possible."""
        last = 0
        for ev in self.events:
            if speed > 0 and ev.t_ms > last:
                await asyncio.sleep((ev.t_ms - last) / 1000 / speed)
            last = ev.t_ms
            yield ev


def _dirs(root: Path) -> list[Path]:
    return [root / "synthetic", root / "real"]


def list_replays(root: Path) -> list[ReplayInfo]:
    out = []
    for d in _dirs(root):
        for p in sorted(d.glob("*.jsonl")) if d.is_dir() else []:
            try:
                s = load_replay(root, p.stem)
            except ReplayError:
                continue
            out.append(ReplayInfo(id=p.stem, description=s.description, synthetic=s.synthetic))
    return out


def load_replay(root: Path, scenario: str) -> ReplayStream:
    if not _NAME.match(scenario):
        raise ReplayError(f"invalid scenario name: {scenario!r}")
    path = next((d / f"{scenario}.jsonl" for d in _dirs(root) if (d / f"{scenario}.jsonl").is_file()), None)
    if path is None:
        raise ReplayError(f"unknown replay scenario: {scenario}")
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ReplayError(f"empty replay: {scenario}")
    meta = json.loads(lines[0]).get("_meta")
    if not isinstance(meta, dict):
        raise ReplayError(f"replay {scenario} is missing its _meta header")
    events = []
    for ln in lines[1:]:
        d = json.loads(ln)
        events.append(ReplayEvent(t_ms=int(d.pop("t_ms")), source=str(d.pop("source")), data=d))
    events.sort(key=lambda e: e.t_ms)
    # Anything not explicitly marked real is treated as synthetic.
    synthetic = path.parent.name == "synthetic" or bool(meta.get("synthetic", True))
    return ReplayStream(scenario, synthetic, str(meta.get("description", "")), meta.get("command"), events)
