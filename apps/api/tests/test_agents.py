"""Bounded multi-agent diagnosis with a scripted model (AC-06, AC-08, PRD §11)."""

import re

import pytest
from fastapi.testclient import TestClient

from integreat.agents.provider import FakeProvider, LLMUnavailable
from integreat.config import Settings
from integreat.main import create_app

from .conftest import FAULT_A_REPO, FIX, GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


def ids(prefix, text):
    return re.findall(rf"({prefix}:[^\s|,\]\)']+)", text)


def make_script(**over):
    def script(schema, prompt):
        if schema in over:
            v = over[schema]
            return v(prompt) if callable(v) else v
        if schema == "TriageOut":
            return {"agents": ["code", "hardware", "runtime_vision"], "rationale": "check config, wiring, observations"}
        if schema == "AgentReportOut":
            cat = prompt.split("## EVIDENCE CATALOG")[1].split("##")[0]
            ev = ids("evidence", cat)
            acts = ids("action", prompt.split("## ACTION CATALOG")[1].split("##")[0])
            return {"findings": [
                        {"statement": "Configured pin differs from wiring", "supporting_evidence_ids": ev[:2],
                         "contradicting_evidence_ids": [], "epistemic_status": "inferred"},
                        {"statement": "Voltage measured at 4.9 V", "supporting_evidence_ids": ["evidence:made_up"],
                         "contradicting_evidence_ids": [], "epistemic_status": "inferred"}],
                    "unknowns": ["PWM not measured"], "proposed_action_ids": acts[:1] + ["action:rm_rf"],
                    "proposed_hypotheses": [
                        {"title": "Brown-out on servo start", "explanation": "plausible", "supporting_evidence_ids": ev[:1]},
                        {"title": "Cosmic rays", "explanation": "x", "supporting_evidence_ids": ["evidence:nope"]}]}
        if schema == "SynthesisOut":
            return {"summary": "Most consistent: GPIO mismatch.", "recommended_action_id": ids("action", prompt)[0],
                    "contradictions": []}
        raise AssertionError(schema)
    return script


@pytest.fixture
def agent_client():
    provider = FakeProvider(make_script())
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0, agent_timeout_s=2), llm=provider)
    with TestClient(app) as c:
        c.provider = provider
        yield c


def incident(c, repo=FAULT_A_REPO, scenario="fault_a_wrong_gpio", grant=("repo_read", "netlist_read", "serial_read", "camera_observe")):
    p, exp = import_and_confirm(c, repo)
    iid = run_test(c, p["id"], exp["id"], scenario)["incident_id"]
    for cat in grant:
        c.post(f"{API}/investigations/{iid}/permissions", json={"category": cat, "granted": True})
    return iid


def test_round_produces_validated_reports(agent_client):
    c = agent_client
    iid = incident(c)
    r = c.post(f"{API}/investigations/{iid}/diagnose")
    assert r.status_code == 200
    v = c.get(f"{API}/investigations/{iid}").json()
    runs = v["agent_runs"]
    specialists = [x for x in runs if x["agent"] in ("code", "hardware", "runtime_vision")]
    assert len(specialists) == 3 and all(x["status"] == "completed" for x in specialists)
    ev_ids = {e["id"] for e in v["evidence"]}
    for x in specialists:
        # invented evidence and actions were dropped and logged, never shown as findings
        assert [f["statement"] for f in x["report"]["findings"]] == ["Configured pin differs from wiring"]
        assert all(i in ev_ids for f in x["report"]["findings"] for i in f["supporting_evidence_ids"])
        assert "action:rm_rf" not in x["report"]["proposed_action_ids"]
        assert any("made_up" in e for e in x["validation_errors"])
    # agent hypotheses are unverified, origin=agent, and never outrank rule hypotheses
    agent_h = [h for h in v["hypotheses"] if h["origin"] == "agent"]
    assert {h["title"] for h in agent_h} == {"Brown-out on servo start"}
    assert all(h["status"] == "unverified" for h in agent_h)
    assert v["hypotheses"][0]["fault_code"] == "GPIO_CONFIG_MISMATCH"
    assert v["incident"]["agent_summary"].startswith("Most consistent")
    assert v["incident"]["state"] == "awaiting_engineer" and v["incident"]["agent_rounds_used"] == 1


def test_context_is_scoped_bounded_and_marked_untrusted(agent_client):
    c = agent_client
    iid = incident(c)
    c.post(f"{API}/investigations/{iid}/diagnose")
    prompts = [p for s, p in c.provider.calls if s == "AgentReportOut"]
    assert prompts and all("<data>" in p and "UNTRUSTED" in p for p in prompts)
    for p in prompts:
        data = p.split("<data>", 1)[1]
        assert "wifi_status" not in data and "Status LED" not in data  # AC-08: unrelated subsystem excluded
    runs = c.get(f"{API}/investigations/{iid}").json()["agent_runs"]
    ctx = next(x["context"] for x in runs if x["agent"] == "code")
    assert ctx["estimated_tokens"] <= ctx["max_token_budget"]
    assert "component:status_led" not in ctx["included_node_ids"]


def test_ungranted_categories_are_omitted_not_bypassed(agent_client):
    c = agent_client
    iid = incident(c, grant=())
    c.post(f"{API}/investigations/{iid}/diagnose")
    v = c.get(f"{API}/investigations/{iid}").json()
    code = next(x for x in v["agent_runs"] if x["agent"] == "code")
    assert "not granted" in code["context"]["omitted_context_summary"]
    assert all(t["decision"] == "denied" for t in v["tool_calls"] if t["caller"] == "context_engine")


def test_round_budget_and_new_evidence_rule(agent_client):
    c = agent_client
    iid = incident(c, GOOD_REPO, "fault_b_disconnected")
    assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
    r = c.post(f"{API}/investigations/{iid}/diagnose")
    assert r.status_code == 409 and r.json()["error"]["code"] == "no_new_evidence"
    v = c.get(f"{API}/investigations/{iid}").json()
    check = next(a for a in v["actions"] if a["label"] == "Check signal connection")
    c.post(f"{API}/investigations/{iid}/manual-results", json={"action_id": check["id"], "result": "Disconnected"})
    assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
    r = c.post(f"{API}/investigations/{iid}/diagnose")
    assert r.status_code == 409 and r.json()["error"]["code"] == "round_budget_exhausted"


def test_model_unavailable_degrades_gracefully():
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0))  # no API key
    with TestClient(app) as c:
        assert c.get(f"{API}/agents/status").json()["available"] is False
        iid = incident(c)
        r = c.post(f"{API}/investigations/{iid}/diagnose")
        assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
        v = c.get(f"{API}/investigations/{iid}").json()
        assert v["hypotheses"][0]["fault_code"] == "GPIO_CONFIG_MISMATCH"  # rules still work


def test_agent_timeout_and_failures_are_isolated():
    calls = {"n": 0}

    def script(schema, prompt):
        if schema == "TriageOut":
            return {"agents": ["code", "runtime_vision"], "rationale": "x"}
        if schema == "AgentReportOut":
            calls["n"] += 1
            if calls["n"] == 1:
                return 10  # first agent: too slow → timeout
            return LLMUnavailable("quota exceeded")
        if schema == "SynthesisOut":
            return {"summary": "s", "recommended_action_id": "x"}

    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0, agent_timeout_s=0.3),
                     llm=FakeProvider(script))
    with TestClient(app) as c:
        iid = incident(c)
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        v = c.get(f"{API}/investigations/{iid}").json()
        statuses = sorted(x["status"] for x in v["agent_runs"] if x["agent"] != "orchestrator")
        assert statuses == ["failed", "timeout"]
        assert v["incident"]["state"] == "awaiting_engineer"  # investigation continues
        # D-023: the orchestrator still synthesizes the deterministic evidence when every
        # specialist fails — specialist failures stay isolated, never crash the round.
        assert v["incident"]["agent_summary"] == "s"


def test_invalid_triage_falls_back_to_rules(agent_client):
    c = agent_client
    c.provider.script = make_script(TriageOut={"agents": ["shell_agent"], "rationale": "x"})
    iid = incident(c)
    c.post(f"{API}/investigations/{iid}/diagnose")
    runs = c.get(f"{API}/investigations/{iid}").json()["agent_runs"]
    triage = runs[0]
    # Fault A fires mismatch + no-motion + power/signal codes → rule-based plan uses all three specialists
    assert triage["agent"] == "orchestrator" and triage["dispatched"] == ["code", "hardware", "runtime_vision"]
    assert any("fell back" in e for e in triage["validation_errors"])
