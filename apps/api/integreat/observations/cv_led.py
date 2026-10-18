"""Deterministic LED on/off measurement in an ArUco-anchored region (same trust model as
cv_angle.py: deterministic, calibrated, honest invalid states).

Setup: marker id 0 fixed next to the LED. The LED region of interest sits at a fixed offset
beside the marker, so the camera never has to "find" the LED — calibration records the marker's
position and the off-state brightness, and state is the mean ROI brightness vs. that baseline.

The estimator never guesses: no anchor marker → `marker_not_found`; not calibrated →
`calibration_invalid`. An *off* LED is a valid 0, not a missing measurement.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .cv_angle import ARUCO_DICT, REFERENCE_ID

# ROI placement relative to the anchor marker's bounding box: a square of `roi_size` px whose
# centre sits `roi_offset` marker-widths to the right of the marker centre. Chosen once for the
# rig layout (LED beside the marker); not per-frame.
ROI_SIZE = 28
ROI_OFFSET_MW = 1.4
# ON if the mean ROI brightness exceeds the off-baseline by more than this delta. Lighting is
# rig-dependent; calibration captures the baseline, this is the margin above it.
ON_DELTA = 40.0


@dataclass
class LedEstimate:
    quality: str  # "valid" | "marker_not_found" | "calibration_invalid"
    state: int | None  # 0 | 1
    brightness: float | None  # mean ROI gray level — kept for evidence even when invalid
    roi: list[int] | None = None  # [x, y, w, h] for debug overlay

    @property
    def value(self) -> float | None:
        return float(self.state) if self.state is not None else None


class LedStateEstimator:
    def __init__(self, marker_id: int = REFERENCE_ID):
        self.marker_id = marker_id
        self._detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(ARUCO_DICT),
                                                 cv2.aruco.DetectorParameters())
        self.baseline: float | None = None  # off-state ROI brightness, set by calibrate()

    @property
    def calibrated(self) -> bool:
        return self.baseline is not None

    def _marker(self, frame: np.ndarray) -> np.ndarray | None:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        if ids is None:
            return None
        found = {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}
        return found.get(self.marker_id)

    def _roi(self, marker: np.ndarray, shape: tuple[int, ...]) -> list[int]:
        cx, cy = marker.mean(axis=0)
        mw = float(np.ptp(marker[:, 0]))  # marker width in px
        rx, ry = int(cx + ROI_OFFSET_MW * mw - ROI_SIZE / 2), int(cy - ROI_SIZE / 2)
        rx = max(0, min(rx, shape[1] - ROI_SIZE))
        ry = max(0, min(ry, shape[0] - ROI_SIZE))
        return [rx, ry, ROI_SIZE, ROI_SIZE]

    def _brightness(self, frame: np.ndarray, marker: np.ndarray) -> tuple[float, list[int]]:
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        x, y, w, h = self._roi(marker, gray.shape)
        return float(gray[y:y + h, x:x + w].mean()), [x, y, w, h]

    def calibrate(self, frame: np.ndarray) -> float:
        """Record the off-state baseline. Call with the marker visible and the LED OFF —
        like the angle calibrate(), the engineer asserts the known state."""
        m = self._marker(frame)
        if m is None:
            raise ValueError("anchor marker not visible; cannot calibrate LED baseline")
        self.baseline, _ = self._brightness(frame, m)
        return self.baseline

    def estimate(self, frame: np.ndarray) -> LedEstimate:
        m = self._marker(frame)
        if m is None:
            return LedEstimate("marker_not_found", None, None)
        b, roi = self._brightness(frame, m)
        if self.baseline is None:
            return LedEstimate("calibration_invalid", None, round(b, 1), roi)
        return LedEstimate("valid", int(b > self.baseline + ON_DELTA), round(b, 1), roi)


# ---------------------------------------------------------------- rendering (sim camera)


def render_led_scene(lit: bool, width: int = 480, height: int = 300,
                     marker_visible: bool = True) -> np.ndarray:
    """Synthetic camera frame: anchor marker on the left, LED blob in the ROI position beside it.
    lit=False renders the LED dark — a valid 0, not a missing measurement."""
    from .cv_angle import marker_image

    frame = np.full((height, width), 200, np.uint8)
    roi_center: tuple[float, float] | None = None
    if marker_visible:
        ref = marker_image(REFERENCE_ID)
        frame[60:60 + ref.shape[0], 40:40 + ref.shape[1]] = ref
        # marker_image has a white border; the marker square is `size` wide inside it
        cx = 40 + ref.shape[1] / 2
        cy = 60 + ref.shape[0] / 2
        mw = ref.shape[1] - 2 * 24  # border=24
        roi_center = (cx + ROI_OFFSET_MW * mw, cy)
    if lit and roi_center is not None:
        cv2.circle(frame, (int(roi_center[0]), int(roi_center[1])), ROI_SIZE // 2, 255, -1)
    elif not lit and roi_center is not None:
        # LED visible but dark — sits at baseline so "off" is a measurement, not an absence
        cv2.circle(frame, (int(roi_center[0]), int(roi_center[1])), ROI_SIZE // 2, 120, -1)
    return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
