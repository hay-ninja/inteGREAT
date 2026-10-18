"""Deterministic servo angle measurement with ArUco markers (PRD §3.7, FR-06, AC-03, D-008).

Setup: marker id 1 on the servo horn, optional marker id 0 fixed next to the servo as a reference.
Angle = horn marker orientation (relative to the reference marker if visible, else to the image),
minus a calibration offset recorded when the engineer tells us the current true angle.

The estimator never guesses: no horn marker → `marker_not_found`; not calibrated → `calibration_invalid`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

ARUCO_DICT = cv2.aruco.DICT_4X4_50
HORN_ID = 1
REFERENCE_ID = 0


@dataclass
class AngleEstimate:
    quality: str  # "valid" | "marker_not_found" | "calibration_invalid"
    angle_deg: float | None
    raw_deg: float | None  # uncalibrated relative orientation
    used_reference: bool
    corners: list | None = None


def _wrap(a: float) -> float:
    """Wrap to [-180, 180)."""
    return (a + 180.0) % 360.0 - 180.0


def _wrap_servo(a: float) -> float:
    """Wrap calibrated angles to [-90, 270) so the whole 0–180° servo range is continuous."""
    return (a + 90.0) % 360.0 - 90.0


def _orientation(c: np.ndarray) -> float:
    """Marker orientation in degrees, counter-clockwise positive (image y axis points down)."""
    p0, p1 = c[0], c[1]  # top-left → top-right edge of the marker
    return math.degrees(math.atan2(-(p1[1] - p0[1]), p1[0] - p0[0]))


class ArucoAngleEstimator:
    def __init__(self, horn_id: int = HORN_ID, reference_id: int = REFERENCE_ID):
        self.horn_id, self.reference_id = horn_id, reference_id
        self._detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT),
                                                 cv2.aruco.DetectorParameters())
        self.offset_deg: float | None = None  # set by calibrate()

    @property
    def calibrated(self) -> bool:
        return self.offset_deg is not None

    def raw(self, frame: np.ndarray) -> tuple[float | None, bool, list | None]:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return None, False, None
        found = {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}
        horn = found.get(self.horn_id)
        if horn is None:
            return None, False, None
        ref = found.get(self.reference_id)
        raw = _orientation(horn) - (_orientation(ref) if ref is not None else 0.0)
        return _wrap(raw), ref is not None, [c.tolist() for c in found.values()]

    def calibrate(self, frame: np.ndarray, known_angle_deg: float) -> float:
        raw, _, _ = self.raw(frame)
        if raw is None:
            raise ValueError("horn marker not visible; cannot calibrate")
        self.offset_deg = _wrap(raw - known_angle_deg)
        return self.offset_deg

    def estimate(self, frame: np.ndarray) -> AngleEstimate:
        raw, used_ref, corners = self.raw(frame)
        if raw is None:
            return AngleEstimate("marker_not_found", None, None, False)
        if self.offset_deg is None:
            return AngleEstimate("calibration_invalid", None, round(raw, 1), used_ref, corners)
        return AngleEstimate("valid", round(_wrap_servo(raw - self.offset_deg), 1), round(raw, 1), used_ref, corners)


# ---------------------------------------------------------------- rendering (sim camera, printable markers)


def marker_image(marker_id: int, size: int = 120, border: int = 24) -> np.ndarray:
    img = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(ARUCO_DICT), marker_id, size)
    return cv2.copyMakeBorder(img, border, border, border, border, cv2.BORDER_CONSTANT, value=255)


def render_scene(horn_angle_deg: float | None, width: int = 480, height: int = 300,
                 with_reference: bool = True) -> np.ndarray:
    """Synthetic camera frame: reference marker on the left, horn marker rotated by the servo angle.
    horn_angle_deg=None renders the horn occluded."""
    frame = np.full((height, width), 200, np.uint8)
    if with_reference:
        ref = marker_image(REFERENCE_ID)
        frame[60:60 + ref.shape[0], 40:40 + ref.shape[1]] = ref
    if horn_angle_deg is not None:
        horn = marker_image(HORN_ID)
        h, w = horn.shape
        canvas = np.full((int(h * 1.5), int(w * 1.5)), 200, np.uint8)
        oy, ox = (canvas.shape[0] - h) // 2, (canvas.shape[1] - w) // 2
        canvas[oy:oy + h, ox:ox + w] = horn
        m = cv2.getRotationMatrix2D((canvas.shape[1] / 2, canvas.shape[0] / 2), horn_angle_deg, 1.0)
        rot = cv2.warpAffine(canvas, m, (canvas.shape[1], canvas.shape[0]), borderValue=200)
        y0, x0 = 30, width - canvas.shape[1] - 30
        frame[y0:y0 + canvas.shape[0], x0:x0 + canvas.shape[1]] = rot
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)


def annotate(frame: np.ndarray, est: AngleEstimate | None) -> np.ndarray:
    out = frame.copy()
    if est and est.corners:
        for c in est.corners:
            pts = np.array(c, np.int32).reshape(-1, 1, 2)
            cv2.polylines(out, [pts], True, (0, 200, 255), 2)
    label = ("no marker" if not est else
             f"{est.angle_deg:.1f} deg" if est.quality == "valid" else est.quality.replace("_", " "))
    cv2.putText(out, label, (10, out.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out
