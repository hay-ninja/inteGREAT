"""Remote repair workflow (D-025): Devin session lifecycle, gating, dedup, honest failure states."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from integreat.config import Settings
from integreat.main import create_app
from integreat.repair import FakeDevin, UnavailableDevin

from .conftest import FAULT_A_REPO, FIX, GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


def make_client(devin=None, settings=None):
    app = create_app(settings or Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     devin=devin if devin is not None else FakeDevin())
    return TestClient(app)


def incident(c, repo=FAULT_A_REPO, scenario="fault_a_wrong_gpio"):
    p, exp = import_and_confirm(c, repo)
    run = run_test(c, p["id"], exp["id"], scenario)
    return run["incident_id"]


def test_preflight_reports_prerequisites():
    with make_client() as c:
        iid = incident(c)
        r = c.get(f"{API}/investigations/{iid}/repairs/preflight")
        assert r.status_code == 200, r.text
        pre = r.json()
        assert pre["devin_configured"] is True
        assert pre["software_evidence"] is True  # GPIO mismatch = evidence of a software issue
        assert pre["snapshot"]["base_revision"]  # fixtures live inside the inteGREAT git repo
        assert pre["snapshot"]["repo_ref"] == "hay-ninja/inteGREAT"
        assert pre["snapshot"]["relative_path"] == "fixtures/esp32_servo_demo_fault_a"


def test_no_software_evidence_blocks_repair():
    with make_client() as c:
        iid = incident(c, GOOD_REPO, "fault_b_disconnected")  # power/signal — not a code issue
        pre = c.get(f"{API}/investigations/{iid}/repairs/preflight").json()
        assert pre["software_evidence"] is False
        assert any("software issue" in i for i in pre["issues"])
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 409 and r.json()["error"]["code"] == "no_software_evidence"


def test_devin_unconfigured_is_precise_not_crash():
    with make_client(devin=UnavailableDevin("DEVIN_API_KEY not set")) as c:
        iid = incident(c)
        pre = c.get(f"{API}/investigations/{iid}/repairs/preflight").json()
        assert pre["devin_configured"] is False and "DEVIN_API_KEY" in pre["unavailable_reason"]
        assert pre["ready"] is False
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 503 and r.json()["error"]["code"] == "devin_unavailable"


def test_create_refresh_review_lifecycle():
    devin = FakeDevin(script=[
        {"status": "running", "status_detail": "working"},
        {"status": "running", "status_detail": "working"},
        {"status": "exit", "status_detail": "finished",
         "pull_requests": [{"pr_url": "https://github.com/hay-ninja/inteGREAT/pull/7"}],
         "structured_output": {"summary": "Changed servo pin to GPIO18", "tests_passed": True,
                               "tests_run": ["pio build"], "risks": ["needs hardware verify"],
                               "branch": "devin/fix-gpio"},
         "acus_consumed": 2.5},
    ])
    with make_client(devin=devin) as c:
        iid = incident(c)
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 200, r.text
        job = r.json()
        assert job["state"] in ("queued", "working")
        assert job["devin_session_id"].startswith("devin-")
        assert job["session_url"].startswith("https://app.devin.ai/")
        # the exact brief is persisted for audit, names the base commit, forbids threshold edits
        assert "Base commit" in job["brief_text"] and "do NOT relax" in job["brief_text"]
        assert devin.calls == ["create"]

        r = c.post(f"{API}/repairs/{job['id']}/refresh")
        assert r.json()["state"] == "working"
        r = c.post(f"{API}/repairs/{job['id']}/refresh")
        job = c.post(f"{API}/repairs/{job['id']}/refresh").json()
        assert job["state"] == "ready_for_review"
        assert job["result"]["pull_requests"] == ["https://github.com/hay-ninja/inteGREAT/pull/7"]
        assert job["result"]["structured_output"]["tests_passed"] is True
        assert job["result"]["acus_consumed"] == 2.5
        # polling a finished job does not hit the API again
        calls = list(devin.calls)
        c.post(f"{API}/repairs/{job['id']}/refresh")
        assert devin.calls == calls


def test_one_active_job_per_incident():
    with make_client() as c:
        iid = incident(c)
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 200
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 409 and r.json()["error"]["code"] == "repair_active"


def test_create_timeout_marks_uncertain_never_retried():
    devin = FakeDevin(create_error=asyncio.TimeoutError())
    with make_client(devin=devin) as c:
        iid = incident(c)
        r = c.post(f"{API}/investigations/{iid}/repairs", json={"acknowledge_uncommitted": True})
        assert r.status_code == 200
        job = r.json()
        assert job["state"] == "uncertain" and "NOT retried" in job["error"]
        assert devin.calls == ["create"]  # exactly one create attempt


def test_remote_failure_states_map_to_failed():
    devin = FakeDevin(script=[{"status": "error", "status_detail": "out_of_funds"}])
    with make_client(devin=devin) as c:
        iid = incident(c)
        job = c.post(f"{API}/investigations/{iid}/repairs",
                     json={"acknowledge_uncommitted": True}).json()
        assert job["state"] == "failed"  # error status maps immediately


def test_needs_input_and_audit_evidence():
    devin = FakeDevin(script=[{"status": "running", "status_detail": "waiting_for_user"}])
    with make_client(devin=devin) as c:
        iid = incident(c)
        job = c.post(f"{API}/investigations/{iid}/repairs",
                     json={"acknowledge_uncommitted": True}).json()
        assert job["state"] == "needs_input"
        # audit: the request is recorded as engineer evidence on the investigation
        v = c.get(f"{API}/investigations/{iid}").json()
        assert any(j["id"] == job["id"] for j in v["repair_jobs"])
        assert any("Devin repair session" in e["summary"] for e in v["evidence"])
