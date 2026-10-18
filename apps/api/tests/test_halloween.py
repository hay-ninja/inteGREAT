"""Halloween demo rig: two LEDs, targeted expectation proposals, inverted logic,
and software-evidence for Devin after engineer-verified bench checks (D-045)."""

import time
from pathlib import Path

from .conftest import FIX, run_test

API = "/api/v1"
REPO = FIX / "esp32_halloween"
MANIFEST = FIX / "manifests" / "esp32_halloween.yaml"


def import_halloween(client):
    p = client.post(f"{API}/projects/import",
                    json={"repo_path": str(REPO), "manifest_path": str(MANIFEST)}).json()
    return p


def propose(client, pid, **body):
    r = client.post(f"{API}/projects/{pid}/expectations/propose", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client, pid, exp, **edits):
    r = client.post(f"{API}/projects/{pid}/expectations/{exp['id']}/confirm",
                    json={"trigger_value": exp["trigger"]["value"], **edits})
    assert r.status_code == 200, r.text
    return r.json()


def wait_verify(client, res):
    """Action execute returns while the verification run is still queued — poll it
    to a terminal state before reading the incident (flaky under suite load)."""
    tid = res.json()["result"]["test_run_id"]
    for _ in range(100):
        run = client.get(f"{API}/tests/{tid}").json()["run"]
        if run["state"] in ("completed", "failed", "error"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"verify run {tid} never finished")


def test_targeted_proposals(client):
    p = import_halloween(client)
    ghost = propose(client, p["id"], component_id="component:ghost_led", command="GHOST ON")
    assert ghost["component_id"] == "component:ghost_led"
    assert ghost["trigger"]["value"] == "GHOST ON" and ghost["unit"] == "state"
    assert ghost["ack_pattern"] == "ACK GHOST ON"
    assert ghost["on_level"] == "HIGH"  # ghostOn() writes HIGH — resolvable, and wrong vs active-low
    pumpkin = propose(client, p["id"], component_id="component:pumpkin_led", command="FLICKER")
    assert pumpkin["component_id"] == "component:pumpkin_led"
    assert pumpkin["trigger"]["value"] == "FLICKER" and pumpkin["ack_pattern"] == "ACK FLICKER"
    assert pumpkin["on_level"] is None  # PWM duty is variable — honestly unresolved
    # component filtering: an untestable id still 422s, not a wrong-component proposal
    r = client.post(f"{API}/projects/{p['id']}/expectations/propose",
                    json={"component_id": "component:nobody"})
    assert r.status_code == 422


def test_inverted_ghost_diagnosis_and_repair_gate(client):
    p = import_halloween(client)
    exp = confirm(client, p["id"], propose(client, p["id"],
                                         component_id="component:ghost_led", command="GHOST ON"))
    run = run_test(client, p["id"], exp["id"], "halloween_inverted")
    assert run["result"]["outcome"] == "fail"
    view = client.get(f"{API}/investigations/{run['incident_id']}").json()
    top = view["hypotheses"][0]
    assert top["fault_code"] == "INVERTED_LOGIC" and top["status"] == "plausible"
    assert any(a["kind"] == "prepare_software_fix" for a in view["actions"])
    # Inverted logic is software evidence — the repair gate opens without bench checks.
    pre = client.get(f"{API}/investigations/{run['incident_id']}/repairs/preflight").json()
    assert pre["software_evidence"] is True
    # Polarity check records the engineer's observation and supports the hypothesis.
    check = next(a for a in view["actions"] if a["label"] == "Check LED wiring polarity")
    r = client.post(f"{API}/investigations/{run['incident_id']}/manual-results",
                    json={"action_id": check["id"], "result": "Wiring is active-low"})
    assert r.json()["hypotheses"][0]["status"] == "supported"
    # Verification with the fixed-firmware replay resolves it.
    verify = next(a for a in view["actions"] if a["kind"] == "verify_fix")
    res = client.post(f"{API}/investigations/{run['incident_id']}/actions/{verify['id']}/execute",
                      json={"source": {"kind": "replay", "scenario": "halloween_ghost_good"}})
    wait_verify(client, res)
    assert client.get(f"{API}/investigations/{run['incident_id']}").json()["incident"]["state"] == "resolved"


def test_flicker_bug_unlocks_repair_after_bench_checks(client):
    p = import_halloween(client)
    # FLICKER is a one-shot candle ramp (32 analogWrite steps, ends held ON) — one
    # binary transition by design. min_transitions=1 asserts "responded at least
    # once", which is what separates it from the dead loop in the buggy firmware.
    exp = confirm(client, p["id"], propose(client, p["id"],
                                         component_id="component:pumpkin_led", command="FLICKER"),
                  min_transitions=1)
    run = run_test(client, p["id"], exp["id"], "halloween_flicker_dark")
    assert run["result"]["outcome"] == "fail"
    iid = run["incident_id"]
    view = client.get(f"{API}/investigations/{iid}").json()
    codes = {h["fault_code"] for h in view["hypotheses"]}
    assert codes == {"POSSIBLE_POWER_OR_SIGNAL_FAULT"}  # config is consistent; no inversion fired
    assert any(a["kind"] == "prepare_software_fix" for a in view["actions"])
    pre = client.get(f"{API}/investigations/{iid}/repairs/preflight").json()
    assert pre["software_evidence"] is False  # unverified power/signal — gate stays shut
    # Engineer checks both physical paths — the suspicion shifts to firmware.
    for label in ("Check signal connection", "Check Pumpkin candle LED (GPIO18) power & ground"):
        check = next(a for a in view["actions"] if a["label"] == label)
        client.post(f"{API}/investigations/{iid}/manual-results",
                    json={"action_id": check["id"], "result": "Connected"})
    pre = client.get(f"{API}/investigations/{iid}/repairs/preflight").json()
    assert pre["software_evidence"] is True
    # Verify with the fixed-firmware replay resolves it.
    verify = next(a for a in view["actions"] if a["kind"] == "verify_fix")
    res = client.post(f"{API}/investigations/{iid}/actions/{verify['id']}/execute",
                      json={"source": {"kind": "replay", "scenario": "halloween_flicker_good"}})
    wait_verify(client, res)
    assert client.get(f"{API}/investigations/{iid}").json()["incident"]["state"] == "resolved"
