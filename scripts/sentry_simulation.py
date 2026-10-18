"""Exercise Sentry with synthetic replay, isolated storage, and no hardware/AI access.

Default: capture real SDK envelopes in memory, save a sanitized report locally.
--send-live: additionally exercise the configured Sentry project (requires a DSN).
Neither mode opens devices, calls AI providers, runs tools, or changes user projects.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from integreat.agents.provider import UnavailableProvider
from integreat.config import Settings, load_settings
from integreat.main import create_app
from integreat.observability import Telemetry


class MemoryTransport(Transport):
    def __init__(self, options):
        super().__init__(options)
        self.items = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            if item.headers["type"] in {"transaction", "log"}:
                self.items.append({"type": item.headers["type"], "data": json.loads(item.get_bytes())})


class NoHardware:
    """Deliberately has no serial/camera interfaces to accidentally connect."""
    def shutdown(self):
        pass


def exercise(settings, transport=None):
    # Use the real app, persistence, rules and replay pipeline. No .env provider keys
    # are copied into settings. The optional transport observes only export envelopes.
    app = create_app(settings, devices=NoHardware(), llm=UnavailableProvider("Simulation: AI disabled"))
    telemetry = app.state.service.telemetry
    if transport is not None:
        # Replace the disabled observer before the first request; middleware is unnecessary
        # for this workflow-level comparison and can't influence the replay outcome.
        telemetry = Telemetry(replace(settings, sentry_dsn="https://public@example.invalid/1"), transport=transport)
        app.state.service.telemetry = telemetry
    with TestClient(app) as client:
        p = client.post("/api/v1/projects/import", json={
            "repo_path": str(ROOT / "fixtures/esp32_servo_demo_fault_a"),
            "manifest_path": str(ROOT / "fixtures/manifests/esp32_servo_demo.yaml")})
        p.raise_for_status()
        pid = p.json()["id"]
        exp = client.post(f"/api/v1/projects/{pid}/expectations/propose")
        exp.raise_for_status()
        eid = exp.json()["id"]
        client.post(f"/api/v1/projects/{pid}/expectations/{eid}/confirm", json={}).raise_for_status()
        outcomes = []
        for scenario in ("fault_a_wrong_gpio", "good"):
            response = client.post(f"/api/v1/projects/{pid}/tests", json={
                "expectation_id": eid, "source": {"kind": "replay", "scenario": scenario}})
            response.raise_for_status()
            rid = response.json()["id"]
            run = client.get(f"/api/v1/tests/{rid}").json()["run"]
            outcomes.append({"scenario": scenario, "state": run["state"],
                "outcome": run["result"]["outcome"], "synthetic": run["synthetic"]})
        events = client.get(f"/api/v1/projects/{pid}/events").json()
        # Compare lifecycle event types, not generated IDs, timestamps or timings.
        history_types = [event["type"] for event in events]
        telemetry.client.flush(timeout=2) if telemetry.client else None
        items = telemetry.client.transport.items if transport is not None else []
    return {"outcomes": outcomes, "history_types": history_types}, items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send-live", action="store_true", help="Send synthetic telemetry to the configured Sentry project")
    parser.add_argument("--output", type=Path, default=ROOT / "apps/api/.data/sentry-simulation.json")
    args = parser.parse_args()
    configured = load_settings()
    if args.send_live and not configured.sentry_enabled:
        parser.error("Sentry is disabled by INTEGREAT_SENTRY_ENABLED. No data sent.")
    if args.send_live and not configured.sentry_dsn:
        parser.error("Set INTEGREAT_SENTRY_DSN in .env first. No data sent.")
    base = Settings(db_path=":memory:", fixtures_dir=ROOT / "fixtures", replay_speed=0,
                    sentry_environment="simulation", sentry_release="integreat@sentry-simulation",
                    sentry_traces_sample_rate=1)
    baseline, _ = exercise(base)
    observed, items = exercise(base, MemoryTransport)
    assert baseline == observed, "Observer changed workflow outputs or history"
    assert [v["outcome"] for v in observed["outcomes"]] == ["fail", "pass"]
    assert all(v["synthetic"] for v in observed["outcomes"])
    assert {item["type"] for item in items} == {"transaction", "log"}
    report = {"synthetic": True, "hardware_access": False, "ai_provider_calls": False,
              "observer_changed_results": False, "workflow": observed, "sentry_envelopes": items,
              "live_export_attempted": False, "live_ingestion_verified": False}
    if args.send_live:
        live = replace(base, sentry_dsn=configured.sentry_dsn)
        sent, _ = exercise(live)
        assert sent == baseline
        report["live_export_attempted"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS: synthetic failure/pass replay has identical outcomes and history with Sentry off/on.")
    print("PASS: real SDK Tracing + Logs envelopes captured; no hardware/tools/AI provider access.")
    print(f"Report: {args.output}")
    if args.send_live:
        print("Synthetic export attempted. Confirm Traces and Logs in Sentry, environment=simulation.")
        print("SDK export alone does not prove Sentry ingestion.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
