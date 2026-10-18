"""Project management: rename, context notes, subsystem display names, file updates, delete (D-039)."""

from fastapi.testclient import TestClient

from .conftest import FAULT_A_REPO, GOOD_REPO, import_and_confirm, run_test

API = "/api/v1"


def test_rename_and_context(client: TestClient):
    p, _ = import_and_confirm(client)
    r = client.patch(f"{API}/projects/{p['id']}",
                     json={"name": "Bench rig 2", "context": "PWM cap is 10% during bench tests."})
    assert r.status_code == 200, r.text
    got = client.get(f"{API}/projects/{p['id']}").json()
    assert got["name"] == "Bench rig 2"
    assert got["context"] == "PWM cap is 10% during bench tests."
    # Notes survive a rescan rebuild
    rescanned = client.post(f"{API}/projects/{p['id']}/rescan").json()
    assert rescanned["context"] == "PWM cap is 10% during bench tests."
    assert rescanned["name"] == "Bench rig 2"


def test_subsystem_rename(client: TestClient):
    p, _ = import_and_confirm(client)
    subs = client.get(f"{API}/projects/{p['id']}/subsystems").json()
    assert subs
    sid = subs[0]["id"]
    r = client.patch(f"{API}/projects/{p['id']}",
                     json={"subsystem_names": {sid: "Arm drive chain"}})
    assert r.status_code == 200, r.text
    renamed = {s["id"]: s["label"] for s in client.get(f"{API}/projects/{p['id']}/subsystems").json()}
    assert renamed[sid] == "Arm drive chain"
    # Empty string clears the override
    client.patch(f"{API}/projects/{p['id']}", json={"subsystem_names": {sid: ""}})
    reverted = {s["id"]: s["label"] for s in client.get(f"{API}/projects/{p['id']}/subsystems").json()}
    assert reverted[sid] == subs[0]["label"]


def test_update_paths_rebuilds_and_preserves(client: TestClient):
    p, exp = import_and_confirm(client, FAULT_A_REPO)
    run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
    client.patch(f"{API}/projects/{p['id']}", json={"context": "keep me"})
    r = client.patch(f"{API}/projects/{p['id']}", json={"repo_path": str(GOOD_REPO)})
    assert r.status_code == 200, r.text
    assert r.json()["graph_version"] == p["graph_version"] + 1
    assert r.json()["repo_root"] == str(GOOD_REPO)
    assert r.json()["context"] == "keep me"  # carried across rebuild
    # Graph reflects the new repo (fault fixture drives the wrong pin; good repo doesn't)
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    assert g["nodes"]


def test_delete_project(client: TestClient):
    p, exp = import_and_confirm(client)
    run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
    r = client.delete(f"{API}/projects/{p['id']}")
    assert r.status_code == 204
    assert client.get(f"{API}/projects/{p['id']}").status_code == 404
    assert client.get(f"{API}/projects/{p['id']}/graph").status_code == 404
    assert client.get(f"{API}/projects/{p['id']}/subsystems").status_code == 404
    assert client.get(f"{API}/projects/{p['id']}/events").status_code == 404
    ids = {q["id"] for q in client.get(f"{API}/projects").json()}
    assert p["id"] not in ids


def test_engineer_context_reaches_agent_packet(client: TestClient):
    p, exp = import_and_confirm(client, FAULT_A_REPO)
    run_test(client, p["id"], exp["id"], "fault_a_wrong_gpio")
    inc = client.get(f"{API}/projects/{p['id']}/incidents").json()[0]
    client.patch(f"{API}/projects/{p['id']}", json={"context": "Arm stalls above 60 degrees on USB power."})
    import asyncio
    from integreat.context.packet import build_packet
    from integreat.models import AgentName, Incident
    svc = client.app.state.service
    incident = svc.store.get("incident", inc["id"], Incident)
    packet = asyncio.run(build_packet(svc, incident, AgentName.code, 4000))
    assert "ENGINEER NOTES" in packet.text
    assert "Arm stalls above 60 degrees" in packet.text
