"""Synthetic images/time series only; not validation of physical LEDs."""
import time
from datetime import UTC, datetime

import numpy as np
import pytest

from integreat.models import VisualRegion, VisualSample
from integreat.observations.camera_adapter import Frame
from integreat.observations.led_brightness import contrast, evaluate


def sample(cid, t, value, quality="valid"):
    return VisualSample(component_id=cid, elapsed_ms=t, brightness=value, quality=quality, evidence_id=f"e:{cid}:{t}")


def series(mode="alternating"):
    out = []
    for t in range(0, 6001, 150):
        a = 1.0 if 1000 <= t <= 2000 else 0.0
        b = 1.0 if 4000 <= t <= 5000 else 0.0
        if mode == "dark": b = 0.0
        if mode == "together": b = a
        out += [sample("a", t, a), sample("b", t, b)]
    return out


def test_contrast_and_bounds():
    image = np.full((100, 100, 3), 20, dtype=np.uint8)
    image[10:20, 10:20, 2] = 220
    region = VisualRegion(x=.1, y=.1, width=.1, height=.1)
    assert contrast(image, region) == (200, 20)
    with pytest.raises(ValueError):
        contrast(image, VisualRegion(x=.9, y=.1, width=.2, height=.1))
    with pytest.raises(ValueError):
        contrast(image, VisualRegion(x=.1, y=.1, width=.001, height=.001))


@pytest.mark.parametrize("mode,outcome", [("alternating", "pass"), ("dark", "fail"), ("together", "fail")])
def test_pattern_rules(mode, outcome):
    assert evaluate(series(mode), ["a", "b"], 6000)[0] == outcome


def test_missing_or_gapped_frames_are_unknown():
    assert evaluate([], ["a", "b"], 6000)[0] == "inconclusive"
    interrupted = [s for s in series() if not 1000 < s.elapsed_ms < 2500]
    assert evaluate(interrupted, ["a", "b"], 6000)[0] == "inconclusive"
    invalid = [s.model_copy(update={"quality": "unavailable"}) for s in series()]
    assert evaluate(invalid, ["a", "b"], 6000)[0] == "inconclusive"


class Camera:
    source_id = "camera:test-only-synthetic-images"
    connected = True
    seq = 0
    mode = "reference"
    level = 0
    started = 0
    missing = False
    def latest(self):
        if self.missing: return None
        self.seq += 1
        image = np.full((100, 100, 3), 10, dtype=np.uint8)
        levels = [self.level, self.level]
        if self.mode != "reference":
            t = time.monotonic() - self.started
            levels = [max(0, 1 - abs(t - 1.5) / 1.5), max(0, 1 - abs(t - 4.5) / 1.5)]
            if self.mode == "fault": levels[1] = 0
        image[10:20, 10:20] = int(10 + levels[0] * 200)
        image[60:70, 60:70] = int(10 + levels[1] * 200)
        return Frame(image, time.monotonic_ns(), datetime.now(UTC), self.seq)
    def release(self): self.connected = False


@pytest.fixture
def led_project(client):
    from .conftest import FIX
    project = client.post("/api/v1/projects/import", json={"repo_path": str(FIX / "esp32_led_fade"),
        "manifest_path": str(FIX / "manifests/esp32_led_fade.yaml")}).json()
    camera = Camera()
    client.app.state.service.devices.camera.source = camera
    base = f"/api/v1/projects/{project['id']}/visual"
    refs = []
    for cid, pos in [("component:led_1", .1), ("component:led_2", .6)]:
        for state, level in [("off", 0), ("on", 1)]:
            camera.level = level
            response = client.post(base + "/references", json={"component_id": cid, "state": state,
                "region": {"x": pos, "y": pos, "width": .1, "height": .1}})
            assert response.status_code == 200, response.text
            refs.append(response.json()["id"])
    return base, project, camera, refs


def configure(client, base, refs):
    response = client.post(base + "/configs", json={"reference_ids": refs, "duration_ms": 6000, "confirmed": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_confirmation_and_project_boundaries(client, led_project):
    base, project, camera, refs = led_project
    assert client.post(base + "/configs", json={"reference_ids": refs, "confirmed": False}).status_code == 409
    assert client.post(base + "/configs", json={"reference_ids": [refs[0]] * 4, "confirmed": True}).status_code == 422
    other = "/api/v1/projects/project:missing/visual"
    assert client.post(other + "/configs", json={"reference_ids": refs, "confirmed": True}).status_code == 404
    assert client.post(base + "/configs", json={"reference_ids": [refs[1], refs[0], refs[2], refs[2]], "confirmed": True}).status_code == 422
    config = configure(client, base, refs)
    assert len(client.get(base + "/configs").json()) == 1
    camera.source_id = "camera:changed"
    assert client.post(base + "/runs", json={"config_id": config["id"]}).status_code == 409


def test_capture_and_calibration_reject_bad_regions_and_simulation(client, led_project):
    base, _, camera, refs = led_project
    body = {"component_id": "component:led_1", "state": "on", "region": {"x": .95, "y": .1, "width": .2, "height": .1}}
    assert client.post(base + "/references", json=body).status_code == 422
    body["region"] = {"x": .1, "y": .1, "width": .1, "height": .1}
    body["component_id"] = "component:resistor_1"
    assert client.post(base + "/references", json=body).status_code == 422
    body["component_id"] = "component:led_1"
    camera.source_id = "camera:sim"
    assert client.post(base + "/references", json=body).status_code == 409


def test_ambient_change_is_not_judged_as_led_fault(client, led_project):
    from integreat.models import VisualReference
    base, _, camera, refs = led_project
    service = client.app.state.service
    ref = service.store.get("visual_reference", refs[1], VisualReference)
    ref.background += 40
    service.store.put("visual_reference", ref)
    assert client.post(base + "/configs", json={"reference_ids": refs, "confirmed": True}).status_code == 422


def test_fault_then_verify_with_evidence_and_graph(client, led_project):
    base, project, camera, refs = led_project
    config = configure(client, base, refs)
    camera.mode, camera.started = "fault", time.monotonic()
    response = client.post(base + "/runs", json={"config_id": config["id"]})
    assert response.status_code == 200
    failed = client.get(base + "/runs").json()[-1]
    assert failed["outcome"] == "fail" and failed["state"] == "completed"
    camera.mode, camera.started = "good", time.monotonic()
    response = client.post(base + "/runs", json={"config_id": config["id"], "verifies_run_id": failed["id"]})
    assert response.status_code == 200
    runs = client.get(base + "/runs").json()
    assert runs[-1]["outcome"] == "pass"
    assert runs[0]["resolved_by_run_id"] == runs[-1]["id"]
    service = client.app.state.service
    assert len(service.evidence(runs[-1]["evidence_ids"])) == len(runs[-1]["evidence_ids"])
    graph = client.get(f"/api/v1/projects/{project['id']}/graph").json()
    led = next(n for n in graph["nodes"] if n["id"] == "component:led_1")
    assert led["attributes"]["obs_metric"] == "led_brightness"
    assert led["attributes"]["obs_outcome"] == "pass"
    assert client.post(base + "/runs", json={"config_id": config["id"], "verifies_run_id": failed["id"]}).status_code == 409


def test_camera_loss_does_not_become_led_failure(client, led_project):
    base, _, camera, refs = led_project
    config = configure(client, base, refs)
    camera.missing = True
    assert client.post(base + "/runs", json={"config_id": config["id"]}).status_code == 409


def test_preview_supports_raw_calibration_and_component_overlays(client, led_project, monkeypatch):
    """Merged camera workflows share one endpoint without contaminating raw references."""
    import cv2

    adapter = client.app.state.service.devices.camera
    calls = []

    def overlay(image, metric, component_id):
        calls.append((metric, component_id))
        return np.full_like(image, 240)

    monkeypatch.setattr(adapter, "annotate", overlay)
    url = "/api/v1/devices/camera/frame.jpg"
    raw = client.get(url + "?raw=true&metric=led_state&component=component:led_1")
    assert raw.status_code == 200
    image = cv2.imdecode(np.frombuffer(raw.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image[90, 90, 0] < 20
    assert calls == []

    annotated = client.get(url + "?metric=led_state&component=component:led_2")
    assert annotated.status_code == 200
    image = cv2.imdecode(np.frombuffer(annotated.content, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert image[90, 90, 0] > 230
    assert calls == [("led_state", "component:led_2")]
