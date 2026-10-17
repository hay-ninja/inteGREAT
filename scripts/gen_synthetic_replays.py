"""Generate SYNTHETIC replay streams for development without hardware.

These are not recordings. Every file carries a `_meta.synthetic = true` header and the UI must
label them as replay/synthetic. Replace with real captures once the rig is available (H0).

Format (JSONL): first line `{"_meta": {...}}`, then events with `t_ms` relative to the moment the
host sent the configured test command:
  {"t_ms": 0,   "source": "host",   "raw": "MOVE 90"}
  {"t_ms": 38,  "source": "serial", "raw": "ACK MOVE 90"}
  {"t_ms": 66,  "source": "cv",     "frame": 1, "angle_deg": 4.2, "quality": "valid"}
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "fixtures" / "recorded" / "synthetic"
FRAME_MS = 66  # ~15 fps
DURATION_MS = 2600


def frames(angle_at, quality_at=lambda t: "valid", seed=0):
    rng = random.Random(seed)
    out = []
    for i, t in enumerate(range(0, DURATION_MS, FRAME_MS)):
        q = quality_at(t)
        ev = {"t_ms": t, "source": "cv", "frame": i, "quality": q}
        ev["angle_deg"] = round(angle_at(t) + rng.uniform(-0.8, 0.8), 1) if q == "valid" else None
        out.append(ev)
    return out


def moving(t):  # 0 -> 90 deg over ~450 ms after ~120 ms command latency
    if t < 120:
        return 0.0
    return min(90.0, (t - 120) / 450 * 90.0)


def still(t):
    return 0.0


SCENARIOS = {
    "good": dict(
        desc="Servo reaches 90 deg; firmware ACKs. Expected: PASS.",
        serial=[(38, "ACK MOVE 90")],
        cv=frames(moving, seed=1),
    ),
    "fault_a_wrong_gpio": dict(
        desc="Firmware drives GPIO19 but servo is wired to GPIO18: ACK present, no motion.",
        serial=[(38, "ACK MOVE 90")],
        cv=frames(still, seed=2),
    ),
    "fault_b_disconnected": dict(
        desc="Config consistent, servo signal/power lead unplugged: ACK present, no motion.",
        serial=[(41, "ACK MOVE 90")],
        cv=frames(still, seed=3),
    ),
    "marker_lost": dict(
        desc="Marker occluded for the whole window: measurement unavailable (not a servo fault).",
        serial=[(40, "ACK MOVE 90")],
        cv=frames(moving, quality_at=lambda t: "marker_not_found", seed=4),
    ),
    "no_ack": dict(
        desc="No serial acknowledgement and no motion.",
        serial=[],
        cv=frames(still, seed=5),
    ),
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, sc in SCENARIOS.items():
        events = [{"t_ms": 0, "source": "host", "raw": "MOVE 90"}]
        events += [{"t_ms": t, "source": "serial", "raw": raw} for t, raw in sc["serial"]]
        events += sc["cv"]
        events.sort(key=lambda e: (e["t_ms"], e["source"] != "host"))
        meta = {"_meta": {"synthetic": True, "scenario": name, "description": sc["desc"],
                          "command": "MOVE 90", "generated_by": "scripts/gen_synthetic_replays.py"}}
        path = OUT / f"{name}.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in [meta, *events]) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(OUT.parents[2])} ({len(events)} events)")


if __name__ == "__main__":
    main()
