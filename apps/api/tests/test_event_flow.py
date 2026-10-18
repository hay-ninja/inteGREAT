"""Event flow projection (D-024): chronological lanes derived from persisted records."""

import pytest
from fastapi.testclient import TestClient

from integreat.config import Settings
from integreat.main import create_app

from .conftest import FAULT_A_REPO, FIX, GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


@pytest.fixture
def client():
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0))
    with TestClient(app) as c:
        yield c


def flow(c, pid, exp, scenario):
    run = run_test(c, pid, exp["id"], scenario)
    r = c.get(f"{API}/tests/{run['id']}/flow")
    assert r.status_code == 200, r.text
    return run, r.json()


def test_fault_a_flow_lanes_and_order(client):
    c = client
    p, exp = import_and_confirm(c, FAULT_A_REPO)
    run, f = flow(c, p["id"], exp, "fault_a_wrong_gpio")
    assert f["run_id"] == run["id"] and f["synthetic"] is True
    assert f["source"]["kind"] == "replay"
    assert f["correlation"] == "host-clock correlated (not synchronized)"
    lanes = {e["lane"] for e in f["events"]}
    assert lanes == {"command", "software", "hardware", "result"}

    cmd = next(e for e in f["events"] if e["kind"] == "command_sent")
    assert cmd["state"] == "observed" and 'MOVE 90' in cmd["label"]
    assert cmd["elapsed_ms"] == 0 and cmd["evidence_ids"]

    rx = [e for e in f["events"] if e["kind"] == "serial_rx"]
    assert rx and all(e["elapsed_ms"] is not None for e in rx)
    # serial line matched to a source function is an association, not an execution trace
    assert any(e["related_node_ids"] for e in rx)

    segs = [e for e in f["events"] if e["kind"] == "cv_segment"]
    assert segs and all(e["quality"] == "valid" for e in segs)
    # aggregation preserves the underlying observation ids — evidence is never deleted
    assert all(e["aggregated_ids"] for e in segs)

    ev = next(e for e in f["events"] if e["kind"] == "evaluation")
    assert ev["quality"] == "fail" and ev["evidence_ids"]

    # chronological: every observed event's elapsed time is non-decreasing in emitted order
    times = [e["elapsed_ms"] for e in f["events"] if e["elapsed_ms"] is not None]
    assert times == sorted(times)


def test_missing_ack_is_expected_not_absent(client):
    c = client
    p, exp = import_and_confirm(c, FAULT_A_REPO)
    _, f = flow(c, p["id"], exp, "no_ack")
    ack = next((e for e in f["events"] if e["kind"] == "missing_ack"), None)
    assert ack is not None and ack["state"] == "expected"
    assert "not proof" in ack["note"]
    assert any("acknowledgement" in g for g in f["gaps"])


def test_marker_lost_is_measurement_gap_not_servo_fault(client):
    c = client
    p, exp = import_and_confirm(c, FAULT_A_REPO)
    _, f = flow(c, p["id"], exp, "marker_lost")
    segs = [e for e in f["events"] if e["kind"] == "cv_segment"]
    assert segs and all(e["quality"] == "marker_not_found" for e in segs)
    assert any("no valid camera measurements" in g for g in f["gaps"])
    ev = next(e for e in f["events"] if e["kind"] == "evaluation")
    assert ev["quality"] == "inconclusive"


def test_verification_run_shows_verification_outcome(client):
    c = client
    p, exp = import_and_confirm(c, GOOD_REPO)
    # initial run fails (disconnected) → incident; verify run against the good replay passes
    run = run_test(c, p["id"], exp["id"], "fault_b_disconnected")
    iid = run["incident_id"]
    v = c.get(f"{API}/investigations/{iid}").json()
    verify = next(a for a in v["actions"] if a["kind"] == "verify_fix")
    r = c.post(f"{API}/investigations/{iid}/actions/{verify['id']}/execute",
               json={"source": {"kind": "replay", "scenario": "good"}})
    assert r.status_code == 200, r.text
    run_id = r.json()["result"]["test_run_id"]
    f = c.get(f"{API}/tests/{run_id}/flow").json()
    assert f["attempt_kind"] == "verify"
    ev = next(e for e in f["events"] if e["kind"] == "evaluation")
    assert ev["quality"] == "pass"
    done = next((e for e in f["events"] if e["kind"] == "run_completed"), None)
    assert done is not None and "PASS" in done["label"]


def test_flow_ids_stable_across_requests(client):
    c = client
    p, exp = import_and_confirm(c, FAULT_A_REPO)
    run = run_test(c, p["id"], exp["id"], "fault_a_wrong_gpio")
    a = c.get(f"{API}/tests/{run['id']}/flow").json()
    b = c.get(f"{API}/tests/{run['id']}/flow").json()
    assert [e["id"] for e in a["events"]] == [e["id"] for e in b["events"]]
