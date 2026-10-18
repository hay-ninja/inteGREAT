"""Phone camera input boundaries and deterministic stream lifecycle."""
import time
import threading

import cv2
import numpy as np
import pytest

from integreat.observations.camera_adapter import CameraError
from integreat.observations.network_camera import NetworkCamera, validate_camera_url


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/video",
    "http://169.254.169.254/", "http://example.com/video", "http://8.8.8.8/video",
    "http://192.168.1.2/video?token=secret", "http://user:pass@192.168.1.2/video",
    "https://192.168.1.2/video", "http://[::1]/", "http://192.168.1.2:99999/video"])
def test_reject_camera_url(url):
    with pytest.raises(CameraError):
        validate_camera_url(url)


def test_private_camera_url():
    assert validate_camera_url("http://192.168.1.42:8080/video").endswith("/video")


def test_camera_endpoint_rejects_non_lan(client):
    response = client.post("/api/v1/devices/camera/connect", json={"stream_url": "http://127.0.0.1/video"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "camera_error"


def test_camera_endpoint_routes_phone_and_releases(client, monkeypatch):
    from integreat.observations.camera_adapter import Frame
    class Phone:
        source_id = "camera:phone:test"
        connected = True
        fps = 10
        def __init__(self, url): assert url == "http://192.168.1.42:8080/video"
        def latest(self):
            from datetime import UTC, datetime
            return Frame(np.zeros((16, 16, 3), dtype=np.uint8), time.monotonic_ns(), datetime.now(UTC), 1)
        def release(self): self.connected = False
    monkeypatch.setattr("integreat.observations.network_camera.NetworkCamera", Phone)
    response = client.post("/api/v1/devices/camera/connect", json={"stream_url": "http://192.168.1.42:8080/video"})
    assert response.status_code == 200
    assert response.json()["camera"]["source_id"] == "camera:phone:test"
    assert client.get("/api/v1/devices/camera/frame.jpg").status_code == 200
    assert not client.post("/api/v1/devices/camera/release").json()["camera"]["connected"]


def test_stream_decode_and_release(monkeypatch):
    stopped = threading.Event()
    _, jpeg = cv2.imencode(".jpg", np.zeros((16, 16, 3), dtype=np.uint8))
    class Response:
        status_code = 200
        headers = {"content-type": "multipart/x-mixed-replace; boundary=frame"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, **kwargs):
            frame = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
            yield frame[:40]
            yield frame[40:]
            while not stopped.is_set():
                time.sleep(0.01)
                yield b"\r\n"
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args): return Response()
    monkeypatch.setattr("integreat.observations.network_camera.httpx.Client", Client)
    camera = NetworkCamera("http://192.168.1.42:8080/video")
    try:
        assert camera.connected
        assert camera.latest().image.shape == (16, 16, 3)
        assert camera.latest().seq == 1
        camera.latest().monotonic_ns = time.monotonic_ns() - 6_000_000_000
        assert not camera.connected
    finally:
        stopped.set()
        camera.release()
    assert not camera.connected


@pytest.mark.parametrize("status,content,chunks", [
    (302, "multipart/x-mixed-replace", []),
    (200, "text/html", []),
    (200, "multipart/x-mixed-replace", [b"not a frame"]),
    (200, "multipart/x-mixed-replace", [b"x" * 2_000_001]),
    (200, "multipart/x-mixed-replace", [b"\xff\xd8invalid\xff\xd9"]),
])
def test_bad_stream_fails_cleanly(monkeypatch, status, content, chunks):
    class Response:
        status_code = status
        headers = {"content-type": content}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_bytes(self, **kwargs): yield from chunks
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def stream(self, *args): return Response()
    monkeypatch.setattr("integreat.observations.network_camera.httpx.Client", Client)
    with pytest.raises(CameraError):
        NetworkCamera("http://192.168.1.42:8080/video")
