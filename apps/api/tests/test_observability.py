"""Real SDK envelopes captured in memory: no Sentry account or network required."""
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from integreat.config import Settings, load_settings
from integreat.observability import (ObservedProvider, Telemetry, TelemetryMiddleware,
                                    scrub_log, scrub_transaction)
from tests.conftest import FIX, GOOD_REPO, MANIFEST, ROOT, import_and_confirm, run_test

BASE = Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0)
ENABLED = replace(BASE, sentry_dsn="https://public@example.invalid/1", sentry_traces_sample_rate=1)


@pytest.fixture
def recorded():
    pytest.importorskip("sentry_sdk")
    from sentry_sdk.transport import Transport
    class MemoryTransport(Transport):
        def __init__(self, options):
            super().__init__(options)
            self.envelopes = []
        def capture_envelope(self, envelope):
            self.envelopes.append(envelope)
    telemetry = Telemetry(ENABLED, transport=MemoryTransport)
    assert telemetry.client is not None
    yield telemetry
    telemetry.close()


def captured(telemetry, kind):
    telemetry.client.flush(timeout=2)
    return [json.loads(item.get_bytes()) for env in telemetry.client.transport.envelopes
            for item in env.items if item.headers["type"] == kind]


def test_disabled_does_not_import_sdk_or_add_middleware(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    from integreat.main import create_app
    app = create_app(BASE)
    assert app.state.service.telemetry.client is None
    assert not any(m.cls is TelemetryMiddleware for m in app.user_middleware)
    with TestClient(app) as client:
        assert client.get("/api/v1/health").json() == {"ok": True}
        p, exp = import_and_confirm(client)
        run = run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
        assert run["result"]["outcome"] == "fail"


@pytest.mark.parametrize("rate", ["bad", "nan", "inf", "-1", "2"])
def test_bad_optional_rate_does_not_break_startup(monkeypatch, rate):
    monkeypatch.setenv("INTEGREAT_SENTRY_TRACES_SAMPLE_RATE", rate)
    assert load_settings().sentry_traces_sample_rate == 0.1


def test_bad_dsn_is_fail_open(caplog):
    telemetry = Telemetry(replace(ENABLED, sentry_dsn="secret-invalid-dsn"))
    assert telemetry.client is None
    assert "secret-invalid-dsn" not in caplog.text
    with telemetry.operation("project.import"):
        pass


def test_enabled_but_missing_sdk_is_fail_open(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    telemetry = Telemetry(ENABLED)
    assert telemetry.client is None
    assert "public" not in caplog.text


def test_explicit_opt_out_prevents_sdk_initialization_with_a_configured_dsn(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    telemetry = Telemetry(replace(ENABLED, sentry_enabled=False))
    assert telemetry.status == "disabled"
    assert telemetry.client is None
    with telemetry.operation("project.import"):
        pass


@pytest.mark.parametrize("value,expected", [("true", True), ("1", True), ("false", False),
    ("off", False), ("0", False), ("invalid", False)])
def test_environment_switch(monkeypatch, value, expected):
    monkeypatch.setenv("INTEGREAT_SENTRY_ENABLED", value)
    assert load_settings().sentry_enabled is expected


def test_simulation_cannot_export_when_explicitly_disabled(tmp_path):
    report = tmp_path / "must-not-exist.json"
    env = {**os.environ, "INTEGREAT_SENTRY_ENABLED": "false",
           "INTEGREAT_SENTRY_DSN": ENABLED.sentry_dsn}
    result = subprocess.run([sys.executable, str(ROOT / "scripts/sentry_simulation.py"),
                             "--send-live", "--output", str(report)],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert "No data sent" in result.stderr
    assert not report.exists()


def test_enabled_import_and_test_preserve_behavior_without_sending_payloads(recorded, monkeypatch):
    from integreat.main import create_app
    monkeypatch.setattr("integreat.service.Telemetry", lambda settings: recorded)
    app = create_app(ENABLED)
    secret = "PRIVATE-BODY-HEADER-QUERY-12345"
    with TestClient(app) as client:
        p, exp = import_and_confirm(client)
        run = run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
        assert run["result"]["outcome"] == "fail"
        response = client.post("/api/v1/projects/import?token=" + secret,
            headers={"Authorization": "Bearer " + secret, "Cookie": "pair=" + secret},
            json={"repo_path": str(GOOD_REPO), "manifest_path": str(MANIFEST), "name": secret})
        assert response.status_code == 200
        assert client.get("/not-found/" + secret).status_code == 404
        transactions = captured(recorded, "transaction")
        logs = captured(recorded, "log")
        assert transactions and logs
        assert any(s["op"] == "project.build" for t in transactions for s in t["spans"])
        serialized = json.dumps(transactions + logs)
        for private in (secret, str(GOOD_REPO), str(MANIFEST), p["id"], exp["id"]):
            assert private not in serialized
        assert all("request" not in t and "user" not in t and "extra" not in t for t in transactions)


def test_health_camera_and_websocket_are_not_traced(recorded):
    async def app(scope, receive, send):
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"PRIVATE FRAME"})
    async def exercise():
        middleware = TelemetryMiddleware(app, recorded)
        async def receive():
            raise AssertionError("Middleware must not read request body")
        async def send(message):
            pass
        for scope in ({"type": "http", "path": "/api/v1/health"},
                      {"type": "http", "path": "/api/v1/devices/camera/frame"},
                      {"type": "websocket", "path": "/api/v1/ws/private"}):
            await middleware(scope, receive, send)
    asyncio.run(exercise())
    assert not captured(recorded, "transaction")
    assert not captured(recorded, "log")


def test_ai_spans_reveal_slow_call_and_timeout_without_prompts(recorded):
    class SlowProvider:
        name, model, available = "fake", "private-model", True
        async def generate_structured(self, **kwargs):
            await asyncio.sleep(0.025)
            if kwargs.get("fail"):
                raise TimeoutError("SECRET provider response")
            return {"secret_response": "do not collect"}
        async def analyze_image_optional(self, **kwargs):
            return None
    async def exercise():
        provider = ObservedProvider(SlowProvider(), recorded)
        with recorded.operation("diagnosis.run"):
            result = await provider.generate_structured(prompt="SECRET prompt", system="SECRET source")
            assert result == {"secret_response": "do not collect"}
            with pytest.raises(TimeoutError, match="SECRET provider response"):
                await provider.generate_structured(prompt="SECRET prompt", fail=True)
    asyncio.run(exercise())
    transactions = captured(recorded, "transaction")
    calls = [s for t in transactions for s in t["spans"] if s["op"] == "ai.structured"]
    assert len(calls) == 2
    assert all(s["data"]["duration_ms"] >= 20 for s in calls)
    assert {s["data"]["outcome"] for s in calls} == {"ok", "error"}
    assert "SECRET" not in json.dumps(transactions + captured(recorded, "log"))
    assert "secret_response" not in json.dumps(transactions + captured(recorded, "log"))
    assert all(t["contexts"]["trace"]["trace_id"] == s["trace_id"] for t in transactions for s in t["spans"])


def test_telemetry_emission_failure_preserves_result_and_exception(recorded, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("telemetry broke")
    monkeypatch.setattr(recorded, "logger", SimpleNamespace(info=broken, warning=broken))
    with recorded.operation("project.import"):
        result = 42
    assert result == 42
    with pytest.raises(ValueError, match="original"):
        with recorded.operation("project.import"):
            raise ValueError("original")


def test_filters_drop_inherited_scope_and_unapproved_logs():
    assert scrub_log({"body": "SECRET"}, {}) is None
    assert scrub_transaction({"transaction": "SECRET"}, {}) is None
    event = {"transaction": "test.run", "extra": {"secret": "SECRET"}, "user": {"id": "SECRET"},
             "request": {"url": "SECRET"}, "contexts": {"trace": {"trace_id": "abc"}, "private": "SECRET"},
             "spans": [{"op": "test.collect", "description": "SECRET", "data": {"prompt": "SECRET"}}]}
    assert "SECRET" not in json.dumps(scrub_transaction(event, {}))


def test_zero_trace_sampling_still_emits_logs_and_keeps_global_client(recorded):
    import sentry_sdk
    previous = sentry_sdk.get_global_scope().client
    previous_scope = sentry_sdk.get_current_scope()
    recorded.client.options["traces_sample_rate"] = 0
    with recorded.operation("diagnosis.run"):
        with recorded.operation("ai.structured", provider="fake"):
            pass
    assert sentry_sdk.get_global_scope().client is previous
    assert sentry_sdk.get_current_scope() is previous_scope
    assert not captured(recorded, "transaction")
    logs = captured(recorded, "log")
    assert logs and sum(len(batch["items"]) for batch in logs) == 2


def test_history_projection_does_not_export_payload_or_mutate_it(recorded):
    payload = {"source": {"kind": "replay"}, "result": {"outcome": "fail"},
               "raw": "SECRET serial", "message": "SECRET source", "token": "SECRET pairing"}
    before = json.dumps(payload, sort_keys=True)
    recorded.history_event("test.completed", payload)
    recorded.history_event("test.serial", {"raw": "SECRET serial"})
    logs = captured(recorded, "log")
    assert logs
    serialized = json.dumps(logs)
    assert "test.completed" in serialized and "replay" in serialized and "fail" in serialized
    assert "SECRET" not in serialized and "test.serial" not in serialized
    assert before == json.dumps(payload, sort_keys=True)


def test_history_observer_failure_cannot_change_persisted_history_or_run(recorded, monkeypatch):
    from integreat.main import create_app
    monkeypatch.setattr("integreat.service.Telemetry", lambda settings: recorded)
    def broken_observer(*args, **kwargs):
        raise RuntimeError("observer has no authority")
    monkeypatch.setattr(recorded, "history_event", broken_observer)
    with TestClient(create_app(ENABLED)) as client:
        p, exp = import_and_confirm(client)
        run = run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
        assert run["result"]["outcome"] == "fail"
        events = client.get(f"/api/v1/projects/{p['id']}/events").json()
        assert any(e["type"] == "project.imported" for e in events)
        assert any(e["type"] == "test.completed" for e in events)
