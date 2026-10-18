"""The laptop's attached devices: one USB serial port and one camera (PRD §9.1). Global, not per project."""

from __future__ import annotations

from ..models import CameraStatus, DeviceStatus, SerialPortInfo, SerialStatus
from .camera_adapter import CameraManager
from .serial_adapter import SerialDevice, list_ports


class DeviceManager:
    def __init__(self):
        self.serial = SerialDevice()
        self.camera = CameraManager()

    def status(self) -> DeviceStatus:
        try:
            ports = [SerialPortInfo(**p) for p in list_ports()]
        except Exception:  # noqa: BLE001 — port enumeration failing must not break status
            ports = []
        cam = self.camera.source
        est = self.camera.estimators.get(cam.source_id) if cam else None
        return DeviceStatus(
            serial=SerialStatus(connected=self.serial.connected, port=self.serial.port if self.serial.connected else None,
                                baud=self.serial.baud, last_error=self.serial.last_error, ports=ports),
            camera=CameraStatus(connected=self.camera.connected, source_id=cam.source_id if cam else None,
                                fps=round(getattr(cam, "fps", 0.0), 1), calibrated=bool(est and est.calibrated),
                                offset_deg=est.offset_deg if est else None,
                                last_error=getattr(cam, "last_error", None)))

    def shutdown(self) -> None:
        self.serial.release()
        self.camera.release()
