"""A revocable, expiring browser upload source. No cloud or frame persistence."""
import secrets
import threading
import time
from datetime import UTC, datetime

import cv2
import numpy as np

from .camera_adapter import CameraError, Frame

MAX_UPLOAD = 512_000


def jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Read SOF dimensions before allocating a decoded image."""
    if not data.startswith(b"\xff\xd8"):
        raise CameraError("Expected a JPEG frame")
    i = 2
    while i + 4 <= len(data):
        if data[i] != 255:
            break
        marker = data[i + 1]
        i += 2
        if marker == 255:
            i -= 1
            continue
        if marker in (0xD9, 0xDA):
            break
        size = int.from_bytes(data[i:i + 2], "big")
        if size < 2 or i + size > len(data):
            break
        if marker in (0xC0, 0xC1, 0xC2):
            if size < 8:
                break
            height = int.from_bytes(data[i + 3:i + 5], "big")
            width = int.from_bytes(data[i + 5:i + 7], "big")
            if not 0 < width <= 1280 or not 0 < height <= 1280 or width * height > 921600:
                raise CameraError("Use frames no larger than 1280x720")
            return width, height
        i += size
    raise CameraError("Invalid JPEG header")


class BrowserCamera:
    def __init__(self):
        self.source_id = "camera:browser:" + secrets.token_hex(8)
        self.token = secrets.token_urlsafe(32)
        self.expires = time.monotonic() + 7200
        self._released = False
        self._lock = threading.Lock()
        self._latest = None
        self._accepted = 0.0
        self.fps = 0.0
        self.last_error = None

    def authorized(self, token: str) -> bool:
        return (not self._released and time.monotonic() < self.expires
                and secrets.compare_digest(self.token, token))

    @property
    def connected(self):
        frame = self.latest()
        return (self.authorized(self.token) and frame is not None
                and time.monotonic_ns() - frame.monotonic_ns < 5_000_000_000)

    def latest(self):
        with self._lock:
            return self._latest

    def accept(self, data: bytes):
        with self._lock:
            if not self.authorized(self.token):
                raise CameraError("Pairing expired or released")
            now = time.monotonic()
            if now - self._accepted < 0.08:
                return  # bound decoding work to at most 12.5 fps
            if len(data) > MAX_UPLOAD:
                raise CameraError("JPEG frame exceeds 512 KB")
            jpeg_dimensions(data)
            image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise CameraError("Invalid JPEG image")
            seq = self._latest.seq + 1 if self._latest else 1
            self._latest = Frame(image, time.monotonic_ns(), datetime.now(UTC), seq)
            self.fps = 1 / (now - self._accepted) if self._accepted else 0
            self._accepted = now

    def release(self):
        with self._lock:
            self._released = True
            self._latest = None
