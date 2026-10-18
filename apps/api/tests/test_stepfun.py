"""StepFun provider + orchestration routing (D-023).

Provider calls are stubbed at the httpx client level — no network. Routing tests inject separate
fakes for the orchestration vs specialist providers and check attribution + prompt routing.
"""

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from integreat.agents.provider import FakeProvider, LLMUnavailable
from integreat.agents.stepfun import StepFunProvider, strict_schema
from integreat.agents.schemas import AgentReportOut, SynthesisOut, TriageOut
from integreat.config import Settings
from integreat.main import create_app

from .conftest import FAULT_A_REPO, FIX, import_and_confirm, run_test

API = "/api/v1"


class _FakeHTTP:
    """Stand-in for httpx.AsyncClient.post: returns queued (status, body) responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.payloads = []

    async def post(self, path, json):
        self.payloads.append((path, json))
        status, body = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        req = httpx.Request("POST", "https://api.stepfun.ai/v1/chat/completions")
        return httpx.Response(status, json=body, request=req)


def make_stepfun(responses):
    p = StepFunProvider("test-key", "step-5-preview")
    p._client = _FakeHTTP(responses)
    return p


def ok(content: dict):
    return (200, {"choices": [{"message": {"content": json.dumps(content)}}]})


def test_strict_schema_inlines_defs_and_marks_required():
    s = strict_schema(AgentReportOut)
    assert "$ref" not in str(s) and "$defs" not in s
    assert s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"])
    finding = s["properties"]["findings"]["items"]
    assert finding["type"] == "object" and finding["additionalProperties"] is False
    assert set(finding["required"]) == set(finding["properties"])


def test_stepfun_posts_openai_compatible_strict_request():
    p = make_stepfun([ok({"agents": ["code"], "rationale": "r", "questions": []})])
    out = asyncio.run(p.generate_structured(system="sys", prompt="p", schema=TriageOut, timeout_s=5))
    assert out.agents == ["code"]
    path, payload = p._client.payloads[0]
    assert path == "/chat/completions"
    assert payload["model"] == "step-5-preview"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True


def test_stepfun_http_error_maps_to_unavailable():
    p = make_stepfun([(429, {"error": "rate limited"})])
    with pytest.raises(LLMUnavailable, match="429"):
        asyncio.run(p.generate_structured(system="s", prompt="p", schema=TriageOut, timeout_s=5))


def incident(c, repo=FAULT_A_REPO, scenario="fault_a_wrong_gpio"):
    p, exp = import_and_confirm(c, repo)
    run = run_test(c, p["id"], exp["id"], scenario)
    return run["incident_id"]


def named(script, name):
    p = FakeProvider(script)
    p.name = name
    return p


def script(schema, prompt):
    if schema == "TriageOut":
        return {"agents": ["code"], "rationale": "only code needed",
                "questions": [{"agent": "code", "question": "Does the configured pin match wiring?"}]}
    if schema == "AgentReportOut":
        return {"findings": [], "unknowns": [], "proposed_action_ids": [], "proposed_hypotheses": []}
    if schema == "SynthesisOut":
        return {"summary": "pin mismatch", "recommended_action_id": "action:nope",
                "contradictions": [], "outcome_explanation": "inspect shows pin difference"}
    raise AssertionError(schema)


def test_routing_orchestrator_stepfun_specialists_gemini():
    orch, spec = named(script, "stepfun"), named(script, "gemini")
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     orchestrator_llm=orch, specialist_llm=spec)
    with TestClient(app) as c:
        st = c.get(f"{API}/agents/status").json()
        assert st["available"] is True and st["provider"] == "stepfun+gemini"
        assert {s["role"]: s["provider"] for s in st["stages"]} == {
            "orchestrator": "stepfun", "specialists": "gemini"}
        iid = incident(c)
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        runs = c.get(f"{API}/investigations/{iid}").json()["agent_runs"]
        triage = next(r for r in runs if r["agent"] == "orchestrator" and r["dispatched"] is not None
                      and r["summary"])
        assert triage["provider"] == "stepfun"
        code = next(r for r in runs if r["agent"] == "code")
        assert code["provider"] == "gemini"
        # the orchestrator's question is passed to the specialist prompt
        agent_prompts = [p for s, p in spec.calls if s == "AgentReportOut"]
        assert any("Does the configured pin match wiring?" in p for p in agent_prompts)
        # StepFun did orchestration only — never the specialist schema
        assert all(s != "AgentReportOut" for s, _ in orch.calls)
        synth = [r for r in runs if r["agent"] == "orchestrator" and r.get("context")][-1]
        assert synth["provider"] == "stepfun"
        # invented action id was dropped; outcome explanation kept
        inc = c.get(f"{API}/investigations/{iid}").json()["incident"]
        assert inc["agent_recommended_action_id"] is None
        assert "pin mismatch" in inc["agent_summary"]


def test_gemini_down_stepfun_still_synthesizes():
    orch, spec = named(script, "stepfun"), None
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     orchestrator_llm=orch)  # specialists provider → unavailable (no key/model)
    with TestClient(app) as c:
        iid = incident(c)
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        runs = c.get(f"{API}/investigations/{iid}").json()["agent_runs"]
        triage = runs[0]
        assert triage["dispatched"] == []  # marked honestly, no fake specialist output
        assert any("specialist provider unavailable" in e for e in triage["validation_errors"])
        inc = c.get(f"{API}/investigations/{iid}").json()["incident"]
        assert "pin mismatch" in (inc["agent_summary"] or "")


def test_stepfun_down_deterministic_still_works():
    spec = named(script, "gemini")
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0),
                     specialist_llm=spec)  # no orchestrator → StepFun unavailable
    with TestClient(app) as c:
        iid = incident(c)
        assert c.post(f"{API}/investigations/{iid}/diagnose").status_code == 200
        runs = c.get(f"{API}/investigations/{iid}").json()["agent_runs"]
        triage = runs[0]
        assert triage["provider"] == "none"
        assert set(triage["dispatched"]) == {"code", "hardware", "runtime_vision"}  # rule plan
        synth = runs[-1]
        assert synth["status"] == "failed" and "rule-based ranking stands" in synth["error"]


def test_both_down_refused_but_rules_work():
    app = create_app(Settings(db_path=":memory:", fixtures_dir=FIX, replay_speed=0))
    with TestClient(app) as c:
        st = c.get(f"{API}/agents/status").json()
        assert st["available"] is False
        assert {s["role"] for s in st["stages"]} == {"orchestrator", "specialists"}
        iid = incident(c)
        r = c.post(f"{API}/investigations/{iid}/diagnose")
        assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
        v = c.get(f"{API}/investigations/{iid}").json()
        assert v["hypotheses"][0]["fault_code"] == "GPIO_CONFIG_MISMATCH"
