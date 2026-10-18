"""Serial adapter, ArUco angle estimation, and the simulated rig through the live pipeline (M3)."""

import time

import pytest

from integreat.observations.cv_angle import ArucoAngleEstimator, render_scene
from integreat.observations.serial_adapter import SerialDevice, SerialError

from .conftest import FAULT_A_REPO, GOOD_REPO, import_and_confirm

API = "/api/v1"


@pytest.mark.parametrize("angle", [0, 15, 45, 90, 120, 170, 180])
def test_aruco_angle_within_one_degree(angle):
    est = ArucoAngleEstimator()
    est.calibrate(render_scene(0), 0)
    e = est.estimate(render_scene(angle))
    assert e.quality == "valid" and abs(e.angle_deg - angle) <= 1.0


def test_calibration_offset_and_reference_marker():
    est = ArucoAngleEstimator()
    est.calibrate(render_scene(30), 90)  # engineer says "this is 90°"
    assert abs(est.estimate(render_scene(60)).angle_deg - 120) <= 1.0
    assert est.estimate(render_scene(60)).used_reference


def test_missing_marker_and_uncalibrated_are_never_valid():
    est = ArucoAngleEstimator()
    assert est.estimate(render_scene(45)).quality == "calibration_invalid"
    est.calibrate(render_scene(0), 0)
    assert est.estimate(render_scene(None)).quality == "marker_not_found"
    with pytest.raises(ValueError):
        ArucoAngleEstimator().calibrate(render_scene(None), 0)


def test_serial_adapter_loopback_and_port_allowlist():
    d = SerialDevice()
    for bad in ["socket://evil:80", "rfc2217://host:1", "http://x", "COM1; del"]:
        with pytest.raises(SerialError):
            d.connect(bad)
    d.connect("loop://")
    try:
        d.write_line("MOVE 90")
        deadline = time.time() + 2
        while time.time() < deadline and not any(ln.direction == "rx" for ln in d.recent(10)):
            time.sleep(0.02)
        assert [(ln.direction, ln.text) for ln in d.recent(10)] == [("tx", "MOVE 90"), ("rx", "MOVE 90")]
    finally:
        d.release()
    assert not d.connected
    with pytest.raises(SerialError):
        d.write_line("MOVE 0")


def sim(client, repo, scenario):
    p, exp = import_and_confirm(client, repo)
    r = client.post(f"{API}/projects/{p['id']}/tests",
                    json={"expectation_id": exp["id"], "source": {"kind": "sim", "scenario": scenario}})
    assert r.status_code == 200, r.text
    detail = client.get(f"{API}/tests/{r.json()['id']}").json()
    return p, exp, detail


def test_sim_good_firmware_passes_through_real_cv_pipeline(client):
    _, _, d = sim(client, GOOD_REPO, "connected")
    run = d["run"]
    assert run["synthetic"] is True and run["result"]["outcome"] == "pass", run["result"]
    assert d["observations"][0]["source_type"] == "sim_cv"
    assert any(s["raw"] == "ACK MOVE 90" for s in d["serial"])


def test_sim_fault_a_arises_from_source_pin(client):
    _, _, d = sim(client, FAULT_A_REPO, "connected")
    assert d["run"]["result"]["outcome"] == "fail"
    view = client.get(f"{API}/investigations/{d['run']['incident_id']}").json()
    assert view["hypotheses"][0]["fault_code"] == "GPIO_CONFIG_MISMATCH"


def test_sim_disconnected_and_occluded(client):
    _, _, d = sim(client, GOOD_REPO, "signal_disconnected")
    assert d["run"]["result"]["outcome"] == "fail"
    codes = {h["fault_code"] for h in client.get(f"{API}/investigations/{d['run']['incident_id']}").json()["hypotheses"]}
    assert codes == {"POSSIBLE_POWER_OR_SIGNAL_FAULT"}
    _, _, d = sim(client, GOOD_REPO, "marker_occluded")
    assert d["run"]["result"]["outcome"] == "inconclusive"


def test_live_run_requires_devices_and_calibration(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    svc = client.app.state.service
    svc.devices.serial.connect("loop://")
    try:
        r = client.post(f"{API}/projects/{p['id']}/tests",
                        json={"expectation_id": exp["id"], "source": {"kind": "live"}})
        assert r.status_code == 409 and r.json()["error"]["code"] == "camera_unavailable"
    finally:
        svc.devices.serial.release()
    status = client.get(f"{API}/devices").json()
    assert status["serial"]["connected"] is False and status["camera"]["connected"] is False


def test_save_replay_from_sim_run(client, tmp_path):
    _, _, d = sim(client, GOOD_REPO, "connected")
    svc = client.app.state.service
    object.__setattr__(svc.settings, "fixtures_dir", tmp_path)  # don't write into the repo
    r = client.post(f"{API}/tests/{d['run']['id']}/save-replay", json={"name": "sim_good_capture"})
    assert r.status_code == 200 and r.json()["synthetic"] is True
    assert (tmp_path / "recorded" / "synthetic" / "sim_good_capture.jsonl").is_file()
    assert any(x["id"] == "sim_good_capture" for x in client.get(f"{API}/replays").json())
    assert client.post(f"{API}/tests/{d['run']['id']}/save-replay", json={"name": "sim_good_capture"}).status_code == 409
