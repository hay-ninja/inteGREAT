"""Live LED CV slice (D-045): blink-to-find locator, fixed-ROI estimation, keyed
estimators/calibration, locate/ROI routes, and the live run gate."""

from datetime import UTC, datetime

import cv2
import numpy as np
import pytest

from integreat.observations.camera_adapter import Frame
from integreat.observations.cv_angle import render_scene
from integreat.observations.cv_led import (LedStateEstimator, annotate, locate_candidates,
                                           render_led_scene)

from .conftest import LED_REPO, LED_MANIFEST, GOOD_REPO, import_and_confirm

API = "/api/v1"


class FakeCam:
    """Static camera source returning queued frames (latest() pops the next)."""
    source_id = "camera:fake"
    connected = True
    fps = 10.0

    def __init__(self, frames):
        self._frames = list(frames)
        self._i = 0

    def latest(self):
        f = self._frames[min(self._i, len(self._frames) - 1)]
        self._i += 1
        return Frame(f, 0, datetime.now(UTC), self._i)

    def release(self):
        self.connected = False


def _blob_frame(lit, lit2=False, w=320, h=200):
    f = np.full((h, w, 3), 40, np.uint8)
    if lit:
        cv2.circle(f, (200, 80), 12, (255, 255, 255), -1)
    if lit2:
        cv2.circle(f, (60, 150), 12, (255, 255, 255), -1)
    return f


# ---------------------------------------------------------------- locator + estimator units

def test_locate_candidates_finds_the_changed_blob():
    off = [_blob_frame(False) for _ in range(2)]
    on = [_blob_frame(True) for _ in range(2)]
    rois = locate_candidates(off, on)
    assert len(rois) == 1
    x, y, w, h = rois[0]
    assert x <= 200 <= x + w and y <= 80 <= y + h  # contains the LED


def test_locate_candidates_multiple_leds_and_no_change():
    off = [_blob_frame(False)]
    both = [_blob_frame(True, lit2=True)]
    rois = locate_candidates(off, both)
    assert len(rois) == 2  # multi-LED: engineer picks, locator never guesses
    assert locate_candidates(off, [_blob_frame(False)]) == []
    assert locate_candidates([], on_frames=[_blob_frame(True)]) == []


def test_fixed_roi_estimator_needs_no_marker():
    est = LedStateEstimator()
    est.roi = [188, 68, 24, 24]
    est.calibrate(_blob_frame(False))
    assert est.estimate(_blob_frame(False)).state == 0
    e = est.estimate(_blob_frame(True))
    assert e.quality == "valid" and e.state == 1


def test_led_uncalibrated_and_annotate():
    est = LedStateEstimator()
    est.roi = [188, 68, 24, 24]
    e = est.estimate(_blob_frame(True))
    assert e.quality == "calibration_invalid" and e.state is None
    out = annotate(_blob_frame(True), e)
    assert out.shape == (200, 320, 3)


# ---------------------------------------------------------------- manager + routes

def _connect_fake(client, frames):
    svc = client.app.state.service
    svc.devices.camera.source = FakeCam(frames)
    return svc


def test_keyed_estimators_and_calibrate_modes(client):
    svc = _connect_fake(client, [render_led_scene(False)])
    cam = svc.devices.camera
    a = cam.estimator("led_state", "component:led_a")
    b = cam.estimator("led_state", "component:led_b")
    ang = cam.estimator("servo_angle_deg")
    assert a is not b and a is not ang  # per-component keys

    r = client.post(f"{API}/devices/camera/calibrate",
                    json={"mode": "led_baseline", "component_id": "component:led_a"})
    assert r.status_code == 409  # no ROI yet — honest failure, no guessing

    a.roi = [10, 10, 20, 20]
    r = client.post(f"{API}/devices/camera/calibrate",
                    json={"mode": "led_baseline", "component_id": "component:led_a"})
    assert r.status_code == 200
    cams = r.json()["camera"]["calibrations"]
    assert "led_state:component:led_a" in cams
    assert "led_state:component:led_b" not in cams  # per-component state

    # angle mode stays backward-compatible
    svc.devices.camera.source = FakeCam([render_scene(0)])
    r = client.post(f"{API}/devices/camera/calibrate", json={"known_angle_deg": 0})
    assert r.status_code == 200
    assert "servo_angle_deg" in r.json()["camera"]["calibrations"]
    assert r.json()["camera"]["calibrated"] is True  # legacy flag = any angle estimator


def test_locate_led_route_finds_roi(client):
    svc = _connect_fake(client, [_blob_frame(False), _blob_frame(True),
                               _blob_frame(False), _blob_frame(True), _blob_frame(False)])
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/devices/camera/locate-led",
                        json={"component_id": "component:led_a",
                              "on_command": "LED ON", "off_command": "LED OFF", "cycles": 2})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["found"] is True and body["roi"]
        est = svc.devices.camera.estimator("led_state", "component:led_a")
        assert est.roi == body["roi"] and est.calibrated  # auto-baseline from last off frame
    finally:
        svc.devices.serial.release()


def test_locate_led_ambiguous_returns_candidates(client):
    frames = [_blob_frame(False), _blob_frame(True, True), _blob_frame(False),
              _blob_frame(True, True), _blob_frame(False)]
    svc = _connect_fake(client, frames)
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/devices/camera/locate-led",
                        json={"component_id": "component:led_a",
                              "on_command": "LED ON", "off_command": "LED OFF", "cycles": 2})
        body = r.json()
        assert body["found"] is False and len(body["candidates"]) == 2
        assert svc.devices.camera.estimator("led_state", "component:led_a").roi is None
    finally:
        svc.devices.serial.release()


def test_locate_led_requires_devices(client):
    r = client.post(f"{API}/devices/camera/locate-led",
                    json={"component_id": "x", "on_command": "A", "off_command": "B"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "serial_unavailable"
    svc = _connect_fake(client, [_blob_frame(False)] * 6)
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/devices/camera/locate-led",
                        json={"component_id": "x", "on_command": "A", "off_command": "B"})
        assert r.status_code == 200 and r.json()["found"] is False  # static scene: honest empty
        # loop:// echoes everything, so "board silence" doesn't fire here
        assert "printed nothing" not in r.json()["message"]
    finally:
        svc.devices.serial.release()


def test_locate_led_reports_board_silence(client):
    """Commands that don't match the firmware must surface as 'board printed nothing',
    not just 'nothing changed' — a silent board can't be blinked (D-047)."""
    class SilentSerial:
        connected = True
        written: list[str] = []
        def write_line(self, text):
            self.written.append(text)
        def recent(self, n):
            return []
    svc = _connect_fake(client, [_blob_frame(False)] * 8)
    real_serial = svc.devices.serial
    fake_serial = SilentSerial()
    try:
        svc.devices.serial = fake_serial
        r = client.post(f"{API}/devices/camera/locate-led",
                        json={"component_id": "x", "on_command": "LED ON", "off_command": "LED OFF"})
        assert r.status_code == 200
        assert r.json()["found"] is False and "printed nothing" in r.json()["message"]
        assert fake_serial.written[0] == "LED OFF"  # off first so the baseline frame is dark
    finally:
        svc.devices.serial = real_serial


def test_led_roi_route_and_validation(client):
    svc = _connect_fake(client, [_blob_frame(False)])
    r = client.post(f"{API}/devices/camera/led-roi",
                    json={"component_id": "component:led_a", "roi": [188, 68, 24, 24]})
    assert r.status_code == 200
    est = svc.devices.camera.estimator("led_state", "component:led_a")
    assert est.roi == [188, 68, 24, 24] and est.calibrated  # baseline recorded by default
    assert "led_state:component:led_a" in r.json()["camera"]["calibrations"]
    assert client.post(f"{API}/devices/camera/led-roi",
                       json={"component_id": "x", "roi": [1, 2, 3]}).status_code == 422


def test_live_led_run_gated_on_led_calibration(client):
    """An led_state expectation needs an LED baseline — the angle estimator's
    calibration must not satisfy it."""
    p, exp = import_and_confirm(client, LED_REPO, LED_MANIFEST)
    assert exp["metric"] == "led_state"
    svc = _connect_fake(client, [_blob_frame(True)] * 200)
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/projects/{p['id']}/tests",
                        json={"expectation_id": exp["id"], "source": {"kind": "live"}})
        assert r.status_code == 409 and r.json()["error"]["code"] == "camera_uncalibrated"
        # calibrate the LED → gate opens (run itself may still be inconclusive;
        # the fake cam can't actually blink)
        client.post(f"{API}/devices/camera/led-roi",
                    json={"component_id": exp["component_id"], "roi": [188, 68, 24, 24]})
        r = client.post(f"{API}/projects/{p['id']}/tests",
                        json={"expectation_id": exp["id"], "source": {"kind": "live"}})
        assert r.status_code == 200, r.text
    finally:
        svc.devices.serial.release()


def test_live_servo_run_still_gated_on_angle(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    assert exp["metric"] == "servo_angle_deg"
    svc = _connect_fake(client, [_blob_frame(True)] * 10)
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/projects/{p['id']}/tests",
                        json={"expectation_id": exp["id"], "source": {"kind": "live"}})
        assert r.status_code == 409 and r.json()["error"]["code"] == "camera_uncalibrated"
    finally:
        svc.devices.serial.release()
