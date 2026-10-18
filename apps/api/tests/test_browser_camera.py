import time
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from integreat.api.phone import create_phone_app
from integreat.observations.browser_camera import BrowserCamera, MAX_UPLOAD, jpeg_dimensions
from integreat.observations.camera_adapter import CameraError, CameraManager


def jpeg():
    return cv2.imencode(".jpg", np.zeros((48, 64, 3), dtype=np.uint8))[1].tobytes()


@pytest.fixture
def paired():
    manager = CameraManager()
    manager.source = BrowserCamera()
    with TestClient(create_phone_app(manager)) as client:
        yield client, manager, {"Authorization": f"Bearer {manager.source.token}", "Content-Type": "image/jpeg"}
    manager.release()


def test_pairing_requires_https_gateway(client):
    assert client.post("/api/v1/devices/camera/browser/pair").status_code == 409
    client.app.state.phone_camera_url = "https://192.168.1.2:8443"
    first = client.post("/api/v1/devices/camera/browser/pair").json()
    old = client.app.state.service.devices.camera.source
    second = client.post("/api/v1/devices/camera/browser/pair").json()
    assert first["url"] != second["url"]
    assert first["expires_in_seconds"] == 7200
    assert not old.authorized(first["url"].split("#")[1])


def test_upload_preview_and_revoke(paired):
    client, manager, headers = paired
    assert not manager.connected
    assert client.post("/phone/frame", content=jpeg(), headers=headers).status_code == 204
    assert manager.connected and manager.source.latest().image.shape == (48, 64, 3)
    manager.source.latest().monotonic_ns = time.monotonic_ns() - 6_000_000_000
    assert not manager.connected
    assert client.delete("/phone/session", headers=headers).status_code == 204
    assert client.post("/phone/frame", content=jpeg(), headers=headers).status_code == 401
    assert manager.source.latest() is None


def test_expired_or_unpaired_cannot_upload(paired):
    client, manager, headers = paired
    assert client.post("/phone/frame", content=jpeg()).status_code == 401
    assert client.delete("/phone/session").status_code == 401
    manager.source.expires = 0
    assert client.post("/phone/frame", content=jpeg(), headers=headers).status_code == 401


def test_invalid_and_oversized_inputs(paired):
    client, manager, headers = paired
    assert client.post("/phone/frame", content=b"bad", headers=headers).status_code == 422
    assert client.post("/phone/frame", content=b"x" * (MAX_UPLOAD + 1), headers=headers).status_code == 413
    assert client.post("/phone/frame", content=jpeg(), headers={**headers, "Content-Type": "text/plain"}).status_code == 415
    assert not manager.connected


def test_jpeg_dimensions_before_decode():
    assert jpeg_dimensions(jpeg()) == (64, 48)
    # SOF declares massive dimensions despite a tiny compressed input.
    with pytest.raises(CameraError):
        jpeg_dimensions(b"\xff\xd8\xff\xc0\x00\x08\x08\xff\xff\xff\xff\x01")


def test_gateway_does_not_expose_project_api(paired):
    client, _, _ = paired
    for path in ("/api/v1/projects", "/docs", "/openapi.json"):
        assert client.get(path).status_code == 404
    response = client.get("/phone")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/phone/capture.js").status_code == 200


def test_decoding_rate_limit(paired):
    client, manager, headers = paired
    client.post("/phone/frame", content=jpeg(), headers=headers)
    client.post("/phone/frame", content=jpeg(), headers=headers)
    assert manager.source.latest().seq == 1
