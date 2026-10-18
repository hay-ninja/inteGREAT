"""Camera sources behind one interface (PRD FR-06): local OpenCV webcam now, Pi camera bridge later.

A background thread keeps only the latest frame (+ host timestamps); the test runner samples it at
~15 fps and the preview endpoint streams it as MJPEG. Raw frames are not persisted (PRD §10 notes).
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import cv2
import numpy as np

from .cv_angle import ArucoAngleEstimator


@dataclass
class Frame:
    image: np.ndarray
    monotonic_ns: int
    host_time_utc: datetime
    seq: int


class CameraSource(Protocol):
    source_id: str

    @property
    def connected(self) -> bool: ...
    def latest(self) -> Frame | None: ...
    def release(self) -> None: ...


class CameraError(RuntimeError):
    pass


def _backend() -> int:
    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def probe_cameras(max_index: int = 4) -> list[int]:
    """Indices that open and return a frame. Slow-ish (~0.5 s per index on Windows); call on demand."""
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, _backend())
        try:
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
        finally:
            cap.release()
    return found


class OpenCVCamera:
    def __init__(self, index: int):
        if not 0 <= index <= 16:
            raise CameraError("camera index must be 0..16")
        self.source_id = f"camera:{index}"
        self._cap = cv2.VideoCapture(index, _backend())
        if not self._cap.isOpened():
            self._cap.release()
            raise CameraError(f"camera {index} could not be opened (is it in use or not a capture device?)")
        self._latest: Frame | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._seq = 0
        self.fps = 0.0
        self.last_error: str | None = None
        self._thread = threading.Thread(target=self._loop, name=self.source_id, daemon=True)
        self._thread.start()

    @property
    def connected(self) -> bool:
        return self._cap is not None and self._cap.isOpened() and self.last_error is None

    def _loop(self) -> None:
        t_last, n = time.monotonic(), 0
        fails = 0
        while not self._stop.is_set():
            ok, img = self._cap.read()
            if not ok:
                fails += 1
                if fails > 30:
                    self.last_error = "camera stopped delivering frames"
                    return
                time.sleep(0.03)
                continue
            fails = 0
            self._seq += 1
            f = Frame(img, time.monotonic_ns(), datetime.now(UTC), self._seq)
            with self._lock:
                self._latest = f
            n += 1
            if time.monotonic() - t_last >= 1.0:
                self.fps, n, t_last = n / (time.monotonic() - t_last), 0, time.monotonic()

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def release(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._cap.release()


class CameraManager:
    """The one active camera plus its calibrated estimator (calibration is per camera source)."""

    def __init__(self):
        self.source: CameraSource | None = None
        self.estimators: dict[str, ArucoAngleEstimator] = {}

    @property
    def connected(self) -> bool:
        return self.source is not None and self.source.connected

    def connect(self, index: int) -> None:
        self.release()
        self.source = OpenCVCamera(index)

    def connect_phone(self, url: str) -> None:
        from .network_camera import NetworkCamera
        candidate = NetworkCamera(url)
        self.release()
        self.source = candidate

    def release(self) -> None:
        if self.source is not None:
            self.source.release()
        self.source = None

    def estimator(self, source_id: str | None = None) -> ArucoAngleEstimator:
        sid = source_id or (self.source.source_id if self.source else "none")
        return self.estimators.setdefault(sid, ArucoAngleEstimator())

    def calibrate(self, known_angle_deg: float) -> float:
        if not self.connected:
            raise CameraError("no camera connected")
        f = self.source.latest()
        if f is None:
            raise CameraError("no frame yet")
        return self.estimator().calibrate(f.image, known_angle_deg)
