"""Live test stream: send the configured command, then sample camera + serial until the window ends.

Yields the same `ReplayEvent`s as replay, so evaluation, rules and storage are identical for replay,
simulated and real runs. Times are host-clock correlated (D-006), relative to the command write.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from .cv_angle import ArucoAngleEstimator
from .replay import ReplayEvent

SAMPLE_INTERVAL_S = 1 / 15


@dataclass
class LiveStream:
    scenario: str
    synthetic: bool
    description: str
    command: str | None
    serial: object  # SerialDevice | SimSerial
    camera: object  # CameraSource
    estimator: ArucoAngleEstimator
    window_ms: int
    camera_id: str = "camera"
    recorded: list[ReplayEvent] = field(default_factory=list)

    async def play(self, speed: float = 1.0) -> AsyncIterator[ReplayEvent]:  # speed ignored: real time
        # Baseline frame just before the command (t=0).
        t0 = time.monotonic_ns()
        rx_seen = 0
        frame_seq = -1

        def cv_event(frame) -> ReplayEvent:
            est = self.estimator.estimate(frame.image)
            return ReplayEvent(t_ms=max(0, (frame.monotonic_ns - t0) // 1_000_000), source="cv",
                               data={"frame": frame.seq, "angle_deg": est.angle_deg, "quality": est.quality,
                                     "raw_deg": est.raw_deg})

        first = self.camera.latest() if self.camera is not None else None
        if first is not None:
            frame_seq = first.seq
            ev = cv_event(first)
            ev.t_ms = 0
            yield self._rec(ev)
        if self.command:
            tx = await asyncio.to_thread(self.serial.write_line, self.command)
            t0 = tx.monotonic_ns
            yield self._rec(ReplayEvent(t_ms=0, source="host", data={"raw": self.command}))

        deadline = t0 + (self.window_ms + 300) * 1_000_000
        while time.monotonic_ns() < deadline:
            await asyncio.sleep(SAMPLE_INTERVAL_S)
            if self.serial is not None:
                rx = [ln for ln in self.serial.since(t0) if ln.direction == "rx"]
                new, rx_seen = rx[rx_seen:], len(rx)
                for ln in new:
                    yield self._rec(ReplayEvent(t_ms=(ln.monotonic_ns - t0) // 1_000_000, source="serial",
                                                data={"raw": ln.text}))
            if self.camera is not None:
                f = self.camera.latest()
                if f is not None and f.seq != frame_seq:
                    frame_seq = f.seq
                    yield self._rec(cv_event(f))

    def _rec(self, ev: ReplayEvent) -> ReplayEvent:
        self.recorded.append(ev)
        return ev
