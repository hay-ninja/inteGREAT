"""Bounded HTTP MJPEG input for an explicitly selected LAN phone camera."""
import ipaddress
import threading
import time
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit

import cv2
import httpx
import numpy as np

from .camera_adapter import CameraError, Frame

MAX_FRAME_BYTES = 2_000_000
MAX_PIXELS = 4_000_000


def validate_camera_url(url: str) -> str:
    try:
        parsed = urlsplit(url)
        address = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except ValueError as exc:
        raise CameraError("Use an HTTP URL with the phone's private IPv4 address and port") from exc
    allowed = any(address in ipaddress.ip_network(net) for net in
                  ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")) if address.version == 4 else False
    if (parsed.scheme != "http" or not allowed or parsed.username or parsed.password
            or parsed.fragment or parsed.query or (port is not None and not 1 <= port <= 65535)):
        raise CameraError("Use a private LAN HTTP stream URL without credentials, query, or fragment")
    return url


class NetworkCamera:
    def __init__(self, url: str):
        self.url = validate_camera_url(url)
        self.source_id = f"camera:phone:{uuid.uuid4().hex[:12]}"
        self._latest = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.last_error = None
        self.fps = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True, name=self.source_id)
        self._thread.start()
        if not self._ready.wait(7) or self._latest is None:
            self.release()
            raise CameraError(self.last_error or "Phone sent no JPEG frame within 7 seconds")

    @property
    def connected(self):
        frame = self.latest()
        return (not self._stop.is_set() and self.last_error is None and frame is not None
                and time.monotonic_ns() - frame.monotonic_ns < 5_000_000_000)

    def latest(self):
        with self._lock:
            return self._latest

    def _loop(self):
        try:
            # No redirects, environment proxies, DNS resolution, or automatic reconnect.
            with httpx.Client(timeout=httpx.Timeout(5), trust_env=False, follow_redirects=False) as client:
                with client.stream("GET", self.url) as response:
                    if response.status_code != 200:
                        raise CameraError("Phone stream returned an error or redirect")
                    if not response.headers.get("content-type", "").lower().startswith("multipart/x-mixed-replace"):
                        raise CameraError("URL must return an MJPEG stream, not a camera web page")
                    buffer = bytearray()
                    seq, started = 0, time.monotonic()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if self._stop.is_set():
                            break
                        buffer.extend(chunk)
                        while True:
                            start = buffer.find(b"\xff\xd8")
                            end = buffer.find(b"\xff\xd9", max(start, 0) + 2)
                            if start < 0 or end < 0:
                                break
                            jpeg = bytes(buffer[start:end + 2])
                            del buffer[:end + 2]
                            if len(jpeg) > MAX_FRAME_BYTES:
                                raise CameraError("Phone frame exceeds 2 MB; lower stream resolution")
                            image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                            if image is None or image.shape[0] * image.shape[1] > MAX_PIXELS:
                                raise CameraError("Invalid or oversized phone image; use 640x480 or 1280x720")
                            seq += 1
                            frame = Frame(image, time.monotonic_ns(), datetime.now(UTC), seq)
                            with self._lock:
                                self._latest = frame
                            self.fps = seq / max(time.monotonic() - started, 0.001)
                            self._ready.set()
                        if len(buffer) > MAX_FRAME_BYTES:
                            raise CameraError("Phone stream exceeded the frame buffer limit")
                    if not self._stop.is_set():
                        raise CameraError("Phone stream ended; reconnect in rig setup")
        except Exception as exc:
            self.last_error = str(exc) if isinstance(exc, CameraError) else "Phone stream unavailable; check Wi-Fi and reconnect"
        finally:
            self._ready.set()

    def release(self):
        self._stop.set()
        self._thread.join(timeout=5.5)
