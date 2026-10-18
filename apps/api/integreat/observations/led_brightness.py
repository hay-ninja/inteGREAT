"""Deterministic ROI contrast and a narrowly specified two-LED alternation check.

Measures visible image brightness, never voltage, PWM, or electrical connectivity.
"""
import numpy as np

from ..models import VisualRegion, VisualSample


def contrast(image: np.ndarray, region: VisualRegion) -> tuple[float, float]:
    if region.x + region.width > 1.000001 or region.y + region.height > 1.000001:
        raise ValueError("Region must fit inside the camera image")
    height, width = image.shape[:2]
    x, y = int(region.x * width), int(region.y * height)
    right, bottom = int((region.x + region.width) * width), int((region.y + region.height) * height)
    if right - x < 3 or bottom - y < 3:
        raise ValueError("Select a region at least 3x3 pixels around the LED")
    intensity = image.max(axis=2).astype(float)
    # Remove global ambient brightness; residual exposure/occlusion remains an explicit limitation.
    background = float(np.median(intensity))
    value = float(np.percentile(intensity[y:bottom, x:right], 80)) - background
    return value, background


def evaluate(samples: list[VisualSample], component_ids: list[str], duration_ms: int):
    checks = {}
    states = {}
    uncertain = False
    failed = False
    for cid in component_ids:
        valid = sorted([s for s in samples if s.component_id == cid and s.quality == "valid"], key=lambda s: s.elapsed_ms)
        times = [s.elapsed_ms for s in valid]
        # Coverage, not merely sample count: gaps can hide a full phase of the fade.
        gaps = [b - a for a, b in zip([0, *times], [*times, duration_ms])]
        if len(valid) < 12 or max(gaps, default=duration_ms) > 750:
            checks[cid] = "Measurement unavailable or interrupted; LED behavior is unknown."
            uncertain = True
            continue
        low = [s for s in valid if s.brightness <= 0.25]
        high = [s for s in valid if s.brightness >= 0.75]
        # Require at least two distinct frames in both phases to reject a single flash/noisy sample.
        if len(low) < 2 or len(high) < 2:
            checks[cid] = "Selected region did not show both calibrated dim and bright states. Check framing, LED polarity, resistor/jumpers, and source GPIO. Cause is unverified."
            failed = True
        else:
            checks[cid] = "Calibrated dim and bright states both observed."
        states[cid] = valid
    if uncertain:
        return "inconclusive", checks, "Camera coverage was insufficient; no hardware failure is established."
    if failed:
        return "fail", checks, "The confirmed visual fade expectation was not observed. No voltage or PWM was measured."
    # Samples for both regions come from the same frame, so compare at common receive times.
    a, b = ({s.elapsed_ms: s.brightness for s in states[cid]} for cid in component_ids)
    shared = a.keys() & b.keys()
    a_only = sum(a[t] >= 0.75 and b[t] <= 0.25 for t in shared)
    b_only = sum(b[t] >= 0.75 and a[t] <= 0.25 for t in shared)
    overlap = sum(a[t] >= 0.75 and b[t] >= 0.75 for t in shared)
    if a_only < 2 or b_only < 2 or overlap >= 2:
        checks["alternation"] = "Both LEDs changed, but separate bright phases were not observed consistently."
        return "fail", checks, "LED brightness changed but did not match the confirmed alternating pattern."
    checks["alternation"] = "Each LED was bright while the other was dim."
    return "pass", checks, "Both LED regions brightened and dimmed in alternation during the observation window."
