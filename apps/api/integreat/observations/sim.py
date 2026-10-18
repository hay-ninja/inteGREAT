"""Simulated rig: fake firmware on a fake serial port + rendered ArUco camera frames.

Purpose: exercise the REAL live pipeline (serial line handling, frame sampling, ArUco estimation,
evaluation) without hardware. Results are always labeled synthetic. The physics are honest to the
fault model: the servo moves only if the firmware's configured pin equals the wired pin AND the
simulated signal + power leads are connected.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

from .camera_adapter import Frame
from .cv_angle import render_scene
from .serial_adapter import SerialLine

SLEW_DEG_PER_S = 200.0
ACK_DELAY_S = 0.04
MOTION_DELAY_S = 0.12


@dataclass
class SimConditions:
    configured_gpio: int | None
    wired_gpio: int | None
    signal_connected: bool = True
    power_connected: bool = True
    marker_visible: bool = True
    firmware_acks: bool = True


class SimRig:
    def __init__(self, cond: SimConditions, start_angle: float = 0.0):
        self.cond = cond
        self._angle0 = start_angle
        self._target = start_angle
        self._t_move: float | None = None
        self._lock = threading.Lock()

    @property
    def servo_driven(self) -> bool:
        c = self.cond
        return (c.configured_gpio is not None and c.configured_gpio == c.wired_gpio
                and c.signal_connected and c.power_connected)

    def angle(self) -> float:
        with self._lock:
            return self.angle_unlocked()

    def command(self, target: float) -> None:
        if not self.servo_driven:
            return
        with self._lock:
            cur = self.angle_unlocked()
            self._angle0, self._target = cur, max(0.0, min(180.0, target))
            self._t_move = time.monotonic() + MOTION_DELAY_S

    def angle_unlocked(self) -> float:
        if self._t_move is None:
            return self._angle0
        dt = max(0.0, time.monotonic() - self._t_move)
        span = self._target - self._angle0
        step = min(abs(span), SLEW_DEG_PER_S * dt)
        return self._angle0 + (step if span >= 0 else -step)


class SimSerial:
    """Same surface as SerialDevice for what the test runner needs."""

    port = "sim://rig"

    def __init__(self, rig: SimRig):
        self.rig = rig
        self._buf: deque[SerialLine] = deque(maxlen=500)
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        return True

    def _append(self, text: str, direction: str) -> SerialLine:
        ln = SerialLine(text, direction, time.monotonic_ns(), datetime.now(UTC))
        with self._lock:
            self._buf.append(ln)
        return ln

    def write_line(self, text: str) -> SerialLine:
        ln = self._append(text, "tx")
        if text.startswith("MOVE "):
            try:
                target = int(text.split()[1])
            except (IndexError, ValueError):
                threading.Timer(ACK_DELAY_S, self._append, (f"ERR unknown command: {text}", "rx")).start()
                return ln
            clamped = max(0, min(180, target))
            self.rig.command(clamped)
            if self.rig.cond.firmware_acks:
                threading.Timer(ACK_DELAY_S, self._append, (f"ACK MOVE {clamped}", "rx")).start()
        return ln

    def since(self, monotonic_ns: int) -> list[SerialLine]:
        with self._lock:
            return [ln for ln in self._buf if ln.monotonic_ns >= monotonic_ns]

    def recent(self, n: int) -> list[SerialLine]:
        with self._lock:
            return list(self._buf)[-n:]


class SimCamera:
    source_id = "camera:sim"

    def __init__(self, rig: SimRig):
        self.rig = rig
        self._seq = 0

    @property
    def connected(self) -> bool:
        return True

    def latest(self) -> Frame:
        self._seq += 1
        angle = self.rig.angle() if self.rig.cond.marker_visible else None
        return Frame(render_scene(angle), time.monotonic_ns(), datetime.now(UTC), self._seq)

    def release(self) -> None:
        pass


SIM_SCENARIOS = {
    "connected": "Wiring as declared; servo moves iff firmware pin matches wiring.",
    "signal_disconnected": "Servo signal lead unplugged.",
    "power_disconnected": "Servo power lead unplugged.",
    "marker_occluded": "Camera marker hidden for the whole run.",
}


def conditions_for(scenario: str, configured_gpio: int | None, wired_gpio: int | None) -> SimConditions:
    if scenario not in SIM_SCENARIOS:
        raise ValueError(f"unknown sim scenario {scenario!r}; one of {sorted(SIM_SCENARIOS)}")
    return SimConditions(configured_gpio=configured_gpio, wired_gpio=wired_gpio,
                         signal_connected=scenario != "signal_disconnected",
                         power_connected=scenario != "power_disconnected",
                         marker_visible=scenario != "marker_occluded")
