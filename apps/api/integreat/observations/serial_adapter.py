"""USB serial adapter for an ESP32 running existing firmware (PRD FR-06, D-005).

- Opens the port ONCE with DTR/RTS deasserted, so the dev board's auto-reset circuit isn't triggered.
- A background thread reads lines into a ring buffer with host monotonic + UTC timestamps (D-006).
- Tools read the buffer; only the configured test runner may write (write_line is not a tool).
- release() frees the COM port so the engineer can reflash with the Arduino IDE (Windows ports are exclusive).
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import serial
import serial.tools.list_ports

# Physical ports only (plus pyserial's in-memory loopback for tests). No network URLs (rfc2217://, socket://).
_ALLOWED_PORT = re.compile(r"^(COM\d{1,3}|/dev/(tty|cu)[A-Za-z0-9._-]+|loop://)$")


class SerialError(RuntimeError):
    pass


@dataclass
class SerialLine:
    text: str
    direction: str  # "rx" | "tx"
    monotonic_ns: int
    host_time_utc: datetime


def list_ports() -> list[dict[str, str]]:
    return [{"port": p.device, "description": p.description or "", "hwid": p.hwid or ""}
            for p in serial.tools.list_ports.comports()]


class SerialDevice:
    def __init__(self, maxlen: int = 2000):
        self._buf: deque[SerialLine] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._ser: serial.SerialBase | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._listeners: list[Callable[[SerialLine], None]] = []
        self.port: str | None = None
        self.baud: int = 115200
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def add_listener(self, fn: Callable[[SerialLine], None]) -> None:
        self._listeners.append(fn)

    def connect(self, port: str, baud: int = 115200) -> None:
        if not _ALLOWED_PORT.match(port):
            raise SerialError(f"refusing port {port!r}: only local serial devices are allowed")
        self.release()
        try:
            s = serial.serial_for_url(port, baudrate=baud, timeout=0.1, do_not_open=True)
            s.dtr = False  # deassert BEFORE open: avoids the ESP32 auto-reset pulse
            s.rts = False
            s.open()
        except (serial.SerialException, OSError, ValueError) as e:
            self.last_error = str(e)
            raise SerialError(f"could not open {port}: {e}") from e
        self._ser, self.port, self.baud, self.last_error = s, port, baud, None
        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, name=f"serial-{port}", daemon=True)
        self._thread.start()

    def release(self) -> None:
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:  # noqa: BLE001
                pass
        self._ser, self._thread = None, None

    def _append(self, text: str, direction: str) -> SerialLine:
        line = SerialLine(text=text, direction=direction, monotonic_ns=time.monotonic_ns(),
                          host_time_utc=datetime.now(UTC))
        with self._lock:
            self._buf.append(line)
        for fn in list(self._listeners):
            try:
                fn(line)
            except Exception:  # noqa: BLE001
                pass
        return line

    def _read_loop(self) -> None:
        pending = b""
        while not self._stop.is_set():
            ser = self._ser
            if ser is None:
                return
            try:
                chunk = ser.read(256)
            except (serial.SerialException, OSError) as e:
                self.last_error = f"read failed: {e}"
                self._ser = None  # device unplugged: surface as disconnected
                return
            if not chunk:
                continue
            pending += chunk
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                text = raw.decode("utf-8", "replace").rstrip("\r")
                if text:
                    self._append(text, "rx")

    def write_line(self, text: str) -> SerialLine:
        """Used ONLY by the configured test runner (PRD §13.1). Not exposed as a tool."""
        if not self.connected:
            raise SerialError("serial device not connected")
        self._ser.write((text + "\n").encode("utf-8"))
        self._ser.flush()
        return self._append(text, "tx")

    def recent(self, n: int) -> list[SerialLine]:
        with self._lock:
            return list(self._buf)[-n:]

    def since(self, monotonic_ns: int) -> list[SerialLine]:
        with self._lock:
            return [ln for ln in self._buf if ln.monotonic_ns >= monotonic_ns]
