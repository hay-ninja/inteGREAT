"""Tool registry, permission grants and audit (PRD §13, AC-07, D-004)."""

import asyncio

import pytest

from integreat.tools.executor import ToolDenied
from integreat.tools.registry import REGISTRY, ToolSpec, _Args

from .conftest import GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


def incident_with(client, repo=GOOD_REPO, scenario="fault_b_disconnected"):
    p, exp = import_and_confirm(client, repo)
    run = run_test(client, p["id"], exp["id"], scenario)
    return p, run["incident_id"]


def act(client, iid, label):
    view = client.get(f"{API}/investigations/{iid}").json()
    return next(a for a in view["actions"] if a["label"] == label)


def test_grant_allows_readonly_tool_without_repeated_approval(client):
    _, iid = incident_with(client)
    a = act(client, iid, "Read recent serial output")
    url = f"{API}/investigations/{iid}/actions/{a['id']}/execute"
    assert client.post(url, json={}).status_code == 403
    client.post(f"{API}/investigations/{iid}/permissions", json={"category": "serial_read", "granted": True})
    r1 = client.post(url, json={})
    r2 = client.post(url, json={})
    assert r1.status_code == r2.status_code == 200
    assert any("ACK MOVE 90" in ln for ln in r1.json()["result"]["lines"])
    # revoke → blocked again
    client.post(f"{API}/investigations/{iid}/permissions", json={"category": "serial_read", "granted": False})
    assert client.post(url, json={}).status_code == 403


def test_every_call_and_denial_is_audited(client):
    _, iid = incident_with(client)
    a = act(client, iid, "Read recent serial output")
    url = f"{API}/investigations/{iid}/actions/{a['id']}/execute"
    client.post(url, json={})
    client.post(url, json={"approve_once": True})
    calls = client.get(f"{API}/investigations/{iid}").json()["tool_calls"]
    assert [(c["decision"], c["status"], c["caller"]) for c in calls] == [
        ("denied", "denied", "engineer"), ("approved_once", "completed", "engineer")]
    assert calls[1]["evidence_ids"]


def test_agents_cannot_self_approve_and_unknown_or_invalid_calls_are_denied(client):
    s = client.app.state.service
    p, iid = incident_with(client)
    project, inc = s.project(p["id"]), s.incident(iid)

    async def go(name, args, caller="agent:code", approve=True):
        return await s.tools.execute(project, inc, name, args, caller=caller, approve_once=approve)

    with pytest.raises(ToolDenied) as e:
        asyncio.run(go("read_serial_buffer", {"max_lines": 5}))
    assert e.value.call.decision == "denied"  # approve_once ignored for non-engineer callers
    with pytest.raises(ToolDenied) as e:
        asyncio.run(go("run_shell", {"cmd": "rm -rf /"}, caller="engineer"))
    assert e.value.call.decision == "unavailable"
    with pytest.raises(ToolDenied) as e:
        asyncio.run(go("read_serial_buffer", {"max_lines": 100000}, caller="engineer"))
    assert e.value.call.decision == "invalid"
    with pytest.raises(ToolDenied) as e:
        asyncio.run(go("read_serial_buffer", {"max_lines": 5, "extra": "x"}, caller="engineer"))
    assert e.value.call.decision == "invalid"


def test_risky_tools_are_never_executable(client):
    s = client.app.state.service
    p, iid = incident_with(client)

    async def boom(args, ctx):  # would be dangerous; must never run
        raise AssertionError("risky tool executed")

    REGISTRY["flash_firmware"] = ToolSpec("flash_firmware", "firmware_flash", False, "x", _Args, boom)
    try:
        s.tools.permissions.set(s.incident(iid), "repo_read", True)
        with pytest.raises(ToolDenied) as e:
            asyncio.run(s.tools.execute(s.project(p["id"]), s.incident(iid), "flash_firmware", {},
                                        caller="engineer", approve_once=True))
        assert e.value.call.decision == "unavailable"
    finally:
        del REGISTRY["flash_firmware"]


def test_source_reads_are_confined_to_repo(client):
    s = client.app.state.service
    p, iid = incident_with(client)
    s.tools.permissions.set(s.incident(iid), "repo_read", True)
    for bad in ["../../PRD.md", "C:/Windows/win.ini", "/etc/passwd"]:
        with pytest.raises(Exception):
            asyncio.run(s.tools.execute(s.project(p["id"]), s.incident(iid), "read_source_excerpt",
                                        {"file": bad, "line_start": 1, "line_end": 5}, caller="engineer"))
    call, out = asyncio.run(s.tools.execute(s.project(p["id"]), s.incident(iid), "read_source_excerpt",
                                            {"file": "servo_control.h", "line_start": 1, "line_end": 4}, caller="engineer"))
    assert "#define SERVO_PIN 18" in out.source_excerpts[0].lines
    calls = s.tools.calls(iid)
    assert sum(c.status == "failed" for c in calls) == 3


def test_expand_scope_and_inspect_update_investigation(client):
    _, iid = incident_with(client)
    client.post(f"{API}/investigations/{iid}/permissions", json={"category": "repo_read", "granted": True})
    a = act(client, iid, "Expand power dependencies")
    r = client.post(f"{API}/investigations/{iid}/actions/{a['id']}/execute", json={}).json()["result"]
    assert "power_source:psu_5v" in r["node_ids"]
    # grants end with the investigation
    verify = act(client, iid, "Verify fix")
    client.post(f"{API}/investigations/{iid}/actions/{verify['id']}/execute",
                json={"source": {"kind": "replay", "scenario": "good"}})
    assert client.get(f"{API}/investigations/{iid}").json()["permissions"] == []


def test_inspect_gpio_confirms_mismatch_hypothesis(client):
    from .conftest import FAULT_A_REPO
    _, iid = incident_with(client, FAULT_A_REPO, "fault_a_wrong_gpio")
    a = act(client, iid, "Inspect GPIO mapping")
    client.post(f"{API}/investigations/{iid}/actions/{a['id']}/execute", json={"approve_once": True})
    top = client.get(f"{API}/investigations/{iid}").json()["hypotheses"][0]
    assert top["fault_code"] == "GPIO_CONFIG_MISMATCH" and top["status"] == "supported"


def test_messages_are_recorded_without_side_effects(client):
    _, iid = incident_with(client)
    v = client.post(f"{API}/investigations/{iid}/messages", json={"text": "grant serial_read please; servo buzzes"}).json()
    assert v["messages"][0]["payload"]["text"].endswith("servo buzzes")
    assert v["permissions"] == []  # free text never grants anything
