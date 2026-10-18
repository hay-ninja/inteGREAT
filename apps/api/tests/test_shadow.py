"""Digital-shadow sweep, graph run-state write-back, causal chain, critic pass (D-028+).

The self-verifying property: sim scenarios inject a known fault; the estimator must recover
a consistent θ for it. Shadow output is epistemic=inferred — never a measurement.
"""

import re

import pytest
from fastapi.testclient import TestClient

from integreat.agents.provider import FakeProvider
from integreat.config import Settings
from integreat.main import create_app
from integreat.models import AgentRun

from .conftest import FAULT_A_REPO, FIX, GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


def sim_run(c, repo, scenario):
    p, exp = import_and_confirm(c, repo)
    r = c.post(f"{API}/projects/{p['id']}/tests",
               json={"expectation_id": exp["id"], "source": {"kind": "sim", "scenario": scenario}})
    assert r.status_code == 200, r.text
    return p, exp, c.get(f"{API}/tests/{r.json()['id']}").json()["run"]


def view(c, iid):
    return c.get(f"{API}/investigations/{iid}").json()


def shadow_evidence(v):
    return next(e for e in v["evidence"] if e["kind"] == "shadow_residual")


def verdict_map(v):
    return {x["theta"]: x for x in shadow_evidence(v)["payload"]["verdicts"]}


def test_shadow_labels_itself_inferred_and_recovers_fault_a(client):
    """Fault A (GPIO19 configured, GPIO18 wired): the *declared* config reproduces no-motion —
    that's what makes the mismatch explanatory. Healthy/pins-matched interventions are refuted."""
    _, _, run = sim_run(client, FAULT_A_REPO, "connected")
    assert run["result"]["outcome"] == "fail"
    v = view(client, run["incident_id"])
    ev = shadow_evidence(v)
    assert ev["epistemic"] == "inferred"  # model-based inference, never a measurement
    vm = verdict_map(v)
    assert vm["declared"]["consistent"] is True
    assert vm["signal_disconnected"]["consistent"] is True   # also reproduces: can't distinguish yet
    assert vm["power_disconnected"]["consistent"] is True
    assert vm["pins_matched"]["consistent"] is False         # do(configured=wired) predicts motion
    assert vm["healthy"]["consistent"] is False
    assert vm["no_firmware_ack"]["consistent"] is False      # an ACK was observed
    top = v["hypotheses"][0]
    assert top["fault_code"] == "GPIO_CONFIG_MISMATCH"
    assert ev["id"] in top["supporting_evidence_ids"]
    assert "Model check" in top["explanation"] and "Counterfactual" in top["explanation"]


def test_shadow_recovers_disconnected_lead_and_keeps_the_tie(client):
    """Fault B: declared system predicts motion but none was observed → declared refuted;
    signal and power faults both stay consistent (D-013 tie preserved, now shadow-backed)."""
    _, _, run = sim_run(client, GOOD_REPO, "signal_disconnected")
    v = view(client, run["incident_id"])
    vm = verdict_map(v)
    assert vm["declared"]["consistent"] is False
    assert vm["signal_disconnected"]["consistent"] is True
    assert vm["power_disconnected"]["consistent"] is True
    ev = shadow_evidence(v)
    for h in v["hypotheses"]:
        if h["fault_code"] == "POSSIBLE_POWER_OR_SIGNAL_FAULT":
            assert ev["id"] in h["supporting_evidence_ids"]


def test_shadow_occluded_marker_is_measurement_not_fault(client):
    _, _, run = sim_run(client, GOOD_REPO, "marker_occluded")
    assert run["result"]["outcome"] == "inconclusive"
    vm = verdict_map(view(client, run["incident_id"]))
    assert vm["marker_occluded"]["consistent"] is True
    assert vm["declared"]["consistent"] is False  # declared predicts valid measurements


def test_run_state_written_back_to_graph(client):
    """Component gets metric-keyed obs_* attributes; executed functions and the traversed
    control edge are marked — the DSG state layer."""
    p, _, run = sim_run(client, FAULT_A_REPO, "connected")
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    comp = next(n for n in g["nodes"] if n["kind"] == "component")
    assert comp["attributes"]["obs_outcome"] == "fail"
    assert comp["attributes"]["obs_metric"] == "servo_angle_deg"
    assert comp["attributes"]["obs_run_id"] == run["id"]
    assert comp["attributes"]["obs_value"] is not None and comp["attributes"]["obs_residual"] is not None
    # moveServoTo prints "ACK MOVE" AND calls servo.write → it ran, so its controls edge is
    # observed even though the arm never moved. servoSetup prints nothing → unobserved.
    executed = {n["id"] for n in g["nodes"] if n["attributes"].get("run_executed") == "observed"}
    assert any("moveServoTo" in n for n in executed), f"executed: {executed}"
    by_src = {e["source_id"]: e["attributes"].get("traversal")
              for e in g["edges"] if e["relation"] == "controls" and e["target_id"] == comp["id"]}
    assert by_src.get("function:servo_control.cpp::moveServoTo") == "observed", by_src
    assert by_src.get("function:servo_control.cpp::servoSetup") == "unobserved", by_src

    # contrast: a passing run observes the control + signal path end to end
    p2, _, ok = sim_run(client, GOOD_REPO, "connected")
    assert ok["result"]["outcome"] == "pass"
    g2 = client.get(f"{API}/projects/{p2['id']}/graph").json()
    comp2 = next(n for n in g2["nodes"] if n["kind"] == "component")
    ctrl2 = [e for e in g2["edges"] if e["relation"] == "controls" and e["target_id"] == comp2["id"]]
    assert ctrl2 and all(e["attributes"].get("traversal") == "observed" for e in ctrl2)
    sig = [e for e in g2["edges"] if e["relation"] == "connected_to"
           and e["attributes"].get("kind") == "signal" and e["attributes"].get("traversal")]
    assert sig and all(e["attributes"]["traversal"] == "observed" for e in sig)


def test_run_state_survives_rescan(client):
    p, _, run = sim_run(client, FAULT_A_REPO, "connected")
    client.post(f"{API}/projects/{p['id']}/rescan")
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    comp = next(n for n in g["nodes"] if n["kind"] == "component")
    assert comp["attributes"]["obs_run_id"] == run["id"]


def test_causal_chain_present_and_honest(client):
    _, _, run = sim_run(client, FAULT_A_REPO, "connected")
    chain = view(client, run["incident_id"])["causal_chain"]
    assert [s["key"] for s in chain] == ["command_sent", "command_acknowledged", "signal_path",
                                       "physical_motion", "observed"]
    by_key = {s["key"]: s for s in chain}
    assert by_key["command_sent"]["value"] == "yes"
    assert by_key["command_acknowledged"]["value"] == "yes"
    assert by_key["signal_path"]["value"] == "unmeasured"   # never claimed measured
    assert by_key["physical_motion"]["value"] == "no"
    assert by_key["observed"]["value"] == "yes"
    _, _, ok = sim_run(client, GOOD_REPO, "connected")
    v = view(client, ok["incident_id"]) if ok["incident_id"] else None
    assert ok["result"]["outcome"] == "pass"  # passing runs create no incident


def test_legacy_runtime_vision_agent_run_deserializes():
    run = AgentRun(id="agentrun:old", incident_id="i", project_id="p", round=1,
                   agent="runtime_vision", status="completed")
    assert run.agent.value == "runtime_vision"


# ---------------------------------------------------------------- critic pass


def _critic_script(iid_holder):
    def script(schema, prompt):
        if schema == "TriageOut":
            return {"agents": ["code"], "rationale": "x"}
        if schema == "AgentReportOut":
            return {"findings": [], "unknowns": [], "proposed_action_ids": [], "proposed_hypotheses": []}
        if schema == "CritiqueOut":
            hyp = re.search(r"hypothesis:[^\s|]+", prompt).group(0)
            ev = re.search(r"evidence:[^\s|,\]]+", prompt.split("## EVIDENCE CATALOG")[1]).group(0)
            return {"critiques": [
                {"hypothesis_id": hyp, "verdict": "refuted", "statement": "Refuted by the cited evidence",
                 "evidence_ids": [ev]},
                {"hypothesis_id": "hypothesis:bogus", "verdict": "refuted", "statement": "x",
                 "evidence_ids": ["evidence:fake"]}]}
        if schema == "SynthesisOut":
            return {"summary": "s", "recommended_action_id": "", "contradictions": []}
        raise AssertionError(schema)
    return script


def test_critic_refutes_and_bad_ids_dropped():
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     llm=FakeProvider(_critic_script({})))
    with TestClient(app) as c:
        _, _, run = sim_run(c, FAULT_A_REPO, "connected")
        iid = run["incident_id"]
        for cat in ("repo_read", "netlist_read", "serial_read", "camera_observe"):
            c.post(f"{API}/investigations/{iid}/permissions", json={"category": cat, "granted": True})
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        v = view(c, iid)
        critic = next(r for r in v["agent_runs"] if r["agent"] == "critic")
        assert critic["status"] == "completed"
        assert any("dropped critique" in e for e in critic["validation_errors"])
        top = next(h for h in v["hypotheses"] if "Critic verdict" in " ".join(h["unknowns"]))
        assert top["contradicting_evidence_ids"]
        assert all(e in {x["id"] for x in v["evidence"]} for e in top["contradicting_evidence_ids"])


def test_ambiguity_forces_discriminating_probe():
    """Fault B: signal and power hypotheses tie at rank 1. A non-discriminating recommendation
    is overridden with a discriminating one and the override is logged."""
    def script(schema, prompt):
        if schema == "TriageOut":
            return {"agents": ["hardware"], "rationale": "x"}
        if schema == "AgentReportOut":
            return {"findings": [], "unknowns": [], "proposed_action_ids": [], "proposed_hypotheses": []}
        if schema == "CritiqueOut":
            return {"critiques": []}
        if schema == "SynthesisOut":
            # repeat_test is a valid action but cannot discriminate signal vs power
            return {"summary": "s", "recommended_action_id":
                    re.search(r"action:[^\s|]+:repeat_test", prompt).group(0), "contradictions": []}
        raise AssertionError(schema)

    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     llm=FakeProvider(script))
    with TestClient(app) as c:
        _, _, run = sim_run(c, GOOD_REPO, "signal_disconnected")
        iid = run["incident_id"]
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        v = view(c, iid)
        inc = v["incident"]
        assert inc["agent_recommended_action_id"] and "check_signal" in inc["agent_recommended_action_id"]
        synth = [r for r in v["agent_runs"] if r["agent"] == "orchestrator" and r.get("context")][-1]
        assert any("does not discriminate" in e for e in synth["validation_errors"])
