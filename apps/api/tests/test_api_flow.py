"""End-to-end loop on SYNTHETIC replays: import -> expectation -> test -> incident -> actions -> verify."""

from .conftest import GOOD_REPO, MANIFEST, import_and_confirm, run_test

API = "/api/v1"


def investigation(client, iid):
    r = client.get(f"{API}/investigations/{iid}")
    assert r.status_code == 200, r.text
    return r.json()


def assert_evidence_resolves(view):
    ids = {e["id"] for e in view["evidence"]}
    for h in view["hypotheses"]:
        assert set(h["supporting_evidence_ids"]) <= ids, h["id"]
        assert set(h["contradicting_evidence_ids"]) <= ids, h["id"]
    assert view["test_run"]["result"]["evidence_id"] in ids


def test_proposal_requires_confirmation(client):
    p = client.post(f"{API}/projects/import", json={"repo_path": str(GOOD_REPO), "manifest_path": str(MANIFEST)}).json()
    exp = client.post(f"{API}/projects/{p['id']}/expectations/propose").json()
    assert exp["confirmed_by_engineer"] is False
    assert exp["trigger"]["value"] == "MOVE 90" and exp["ack_pattern"] == "ACK MOVE"
    r = client.post(f"{API}/projects/{p['id']}/tests",
                    json={"expectation_id": exp["id"], "source": {"kind": "replay", "scenario": "good"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "expectation_unconfirmed"


def test_good_run_passes_without_incident(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    run = run_test(client, p["id"], exp["id"], "good")
    assert run["state"] == "completed" and run["result"]["outcome"] == "pass"
    assert run["incident_id"] is None and run["synthetic"] is True


def test_fault_a_full_loop(client):
    p, exp = import_and_confirm(client)
    run = run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
    assert run["result"]["outcome"] == "fail"
    view = investigation(client, run["incident_id"])
    assert_evidence_resolves(view)
    top = view["hypotheses"][0]
    assert top["fault_code"] == "GPIO_CONFIG_MISMATCH" and top["rank"] == 1
    assert all(h["rank"] > 1 for h in view["hypotheses"][1:])
    styles = {(h["element_id"], h["style"]) for h in view["highlights"]}
    assert ("pin:esp32_gpio19", "conflict") in styles
    assert ("component:servo_1", "failed_expectation") in styles
    assert ("function:servo_control.cpp::moveServoTo", "observed") in styles

    # Inspect GPIO mapping is a real operation that returns the cited source lines
    inspect = next(a for a in view["actions"] if a["label"] == "Inspect GPIO mapping")
    url_inspect = f"{API}/investigations/{run['incident_id']}/actions/{inspect['id']}/execute"
    denied = client.post(url_inspect, json={})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_required"
    assert denied.json()["error"]["details"]["category"] == "repo_read"
    r = client.post(url_inspect, json={"approve_once": True}).json()  # engineer approves this one call
    lines = [line for ex in r["result"]["source_excerpts"] for line in ex["lines"]]
    assert "#define SERVO_PIN 19" in lines
    assert any("GPIO18" in e["summary"] for e in r["result"]["evidence"])

    # Verify fix with a still-failing run keeps the incident open...
    verify = next(a for a in view["actions"] if a["kind"] == "verify_fix")
    url = f"{API}/investigations/{run['incident_id']}/actions/{verify['id']}/execute"
    client.post(url, json={"source": {"kind": "replay", "scenario": "fault_a_wrong_gpio"}})
    assert investigation(client, run["incident_id"])["incident"]["state"] == "awaiting_engineer"
    # ...and a passing run resolves it
    client.post(url, json={"source": {"kind": "replay", "scenario": "good"}})
    view = investigation(client, run["incident_id"])
    inc = view["incident"]
    assert inc["state"] == "resolved" and inc["resolved_by_test_run_id"]
    assert [r["result"]["outcome"] for r in view["followup_runs"]] == ["fail", "pass"]


def test_fault_b_offers_manual_checks_and_records_result(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    run = run_test(client, p["id"], exp["id"], "fault_b_disconnected")
    view = investigation(client, run["incident_id"])
    assert_evidence_resolves(view)
    assert {h["fault_code"] for h in view["hypotheses"]} == {"POSSIBLE_POWER_OR_SIGNAL_FAULT"}
    assert {h["rank"] for h in view["hypotheses"]} == {1}  # signal vs power: tie, not forced
    for h in view["hypotheses"]:  # never claims an electrical measurement
        assert any("not measured" in u for u in h["unknowns"])
    check = next(a for a in view["actions"] if a["label"] == "Check signal connection")
    assert check["result_choices"] == ["Connected", "Disconnected", "Unable to verify"]
    bad = client.post(f"{API}/investigations/{run['incident_id']}/manual-results",
                      json={"action_id": check["id"], "result": "Maybe"})
    assert bad.status_code == 400
    view = client.post(f"{API}/investigations/{run['incident_id']}/manual-results",
                       json={"action_id": check["id"], "result": "Disconnected", "note": "lead off"}).json()
    top = view["hypotheses"][0]
    assert "signal lead" in top["title"] and top["status"] == "supported" and top["rank"] == 1
    assert any(e["kind"] == "engineer_assertion" for e in view["evidence"])


def test_marker_lost_does_not_diagnose_servo(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    run = run_test(client, p["id"], exp["id"], "marker_lost")
    assert run["result"]["outcome"] == "inconclusive"
    view = investigation(client, run["incident_id"])
    assert [h["fault_code"] for h in view["hypotheses"]] == ["CAMERA_MEASUREMENT_UNAVAILABLE"]


def test_missing_ack(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    run = run_test(client, p["id"], exp["id"], "no_ack")
    codes = {h["fault_code"] for h in investigation(client, run["incident_id"])["hypotheses"]}
    assert "MISSING_SERIAL_ACK" in codes and "POSSIBLE_POWER_OR_SIGNAL_FAULT" not in codes


def test_bad_inputs_are_rejected(client):
    p, exp = import_and_confirm(client, GOOD_REPO)
    tests = f"{API}/projects/{p['id']}/tests"
    r = client.post(tests, json={"expectation_id": exp["id"], "source": {"kind": "replay", "scenario": "../etc"}})
    assert r.status_code == 422
    r = client.post(tests, json={"expectation_id": exp["id"], "source": {"kind": "replay", "scenario": "nope"}})
    assert r.status_code == 400
    r = client.post(tests, json={"expectation_id": exp["id"], "source": {"kind": "live"}})
    assert r.status_code == 409 and r.json()["error"]["code"] == "serial_unavailable"  # no device connected
    r = client.post(f"{API}/projects/import", json={"repo_path": "C:/definitely/not/here"})
    assert r.status_code == 400


def test_bad_manifest_does_not_block_import(client, tmp_path):
    f = tmp_path / "m.yaml"
    f.write_text("schema: nope\n")
    p = client.post(f"{API}/projects/import", json={"repo_path": str(GOOD_REPO), "manifest_path": str(f)}).json()
    assert any(i["code"] == "MANIFEST_INVALID" for i in p["issues"])
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    assert any(n["kind"] == "function" for n in g["nodes"])


def test_timeline_and_websocket(client):
    p, exp = import_and_confirm(client)
    run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
    types = [e["type"] for e in client.get(f"{API}/projects/{p['id']}/events").json()]
    for t in ["project.imported", "test.started", "test.observation", "expectation.failed", "incident.created"]:
        assert t in types
    with client.websocket_connect(f"{API}/ws/projects/{p['id']}") as ws:
        assert ws.receive_json()["type"] == "project.imported"
