"""KiCad netlist import (M6), engineer wiring verification, rescan after a firmware fix."""

import shutil

import pytest

from integreat.ingestion.kicad_netlist import NetlistError, parse_netlist, propose_mapping, to_manifest

from .conftest import FAULT_A_REPO, FIX, GOOD_REPO, MANIFEST

API = "/api/v1"
NETLIST = FIX / "kicad" / "esp32_servo_demo.xml"


def test_netlist_parse_and_proposal():
    nl = parse_netlist(NETLIST)
    assert {c.ref for c in nl.components} == {"U1", "J1", "J2", "D1"}
    mp = propose_mapping(nl, ["servo_control", "wifi_status"])
    assert mp.mcu_ref == "U1" and mp.proposed is True
    servo = next(c for c in mp.components if c.type == "servo")
    assert servo.pins == {"1": "signal", "2": "vcc", "3": "gnd"}
    m, _, warnings = to_manifest(nl, mp)
    sig = next(c for c in m.connections if c.to.endswith(".signal") and c.from_.startswith("mcu."))
    assert sig.from_ == "mcu.GPIO18"  # from pinfunction IO18, NOT module pin number 25
    assert all(c.verification == "unverified" for c in m.connections)
    assert not warnings


def test_netlist_rejects_sexpr_and_xml_attacks(tmp_path):
    f = tmp_path / "a.net"
    f.write_text('(export (version "E") (components))')
    with pytest.raises(NetlistError, match="kicadxml"):
        parse_netlist(f)
    f.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><export>&b;</export>')
    with pytest.raises(NetlistError):
        parse_netlist(f)
    f.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><export>&e;</export>')
    with pytest.raises(NetlistError):
        parse_netlist(f)


def test_import_with_confirmed_netlist(client):
    prev = client.post(f"{API}/netlist/preview", json={"netlist_path": str(NETLIST), "repo_path": str(FAULT_A_REPO)}).json()
    mapping = {**prev["proposed_mapping"], "proposed": False}
    p = client.post(f"{API}/projects/import", json={"repo_path": str(FAULT_A_REPO), "netlist_path": str(NETLIST),
                                                    "netlist_mapping": mapping}).json()
    assert p["hardware_source"] == "netlist"
    assert any(i["code"] == "GPIO_CONFIG_MISMATCH" for i in p["issues"])
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    wiring = [e for e in g["edges"] if e["origin"] == "declared_wiring"]
    assert wiring and all(e["verification"] == "unverified" for e in wiring)
    ev = client.get(f"{API}/projects/{p['id']}/evidence", params={"ids": wiring[0]["evidence_ids"]}).json()
    assert ev[0]["kind"] == "netlist_entry"


def test_unsupported_netlist_falls_back_to_manifest(client, tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<nope/>")
    p = client.post(f"{API}/projects/import", json={"repo_path": str(GOOD_REPO), "netlist_path": str(bad),
                                                    "manifest_path": str(MANIFEST)}).json()
    assert p["hardware_source"] == "manifest"
    assert any(i["code"] == "NETLIST_UNSUPPORTED" and "falling back" in i["message"] for i in p["issues"])
    # mapping missing → also falls back, never guesses
    p = client.post(f"{API}/projects/import", json={"repo_path": str(GOOD_REPO), "netlist_path": str(NETLIST),
                                                    "manifest_path": str(MANIFEST)}).json()
    assert p["hardware_source"] == "manifest"


def test_engineer_wiring_verification(client):
    p = client.post(f"{API}/projects/import", json={"repo_path": str(GOOD_REPO), "manifest_path": str(MANIFEST)}).json()
    g = client.get(f"{API}/projects/{p['id']}/graph").json()
    led = next(e for e in g["edges"] if e["attributes"].get("connection_id") == "led_signal")
    assert led["verification"] == "unverified"
    r = client.patch(f"{API}/projects/{p['id']}/graph/verification",
                     json={"edge_id": led["id"], "verification": "verified", "note": "checked with meter"})
    assert r.status_code == 200 and r.json()["graph_version"] == 2
    g2 = client.get(f"{API}/projects/{p['id']}/graph").json()
    led2 = next(e for e in g2["edges"] if e["id"] == led["id"])
    assert led2["verification"] == "verified" and any("engineer" in i for i in led2["evidence_ids"])
    code_edge = next(e for e in g["edges"] if e["origin"] == "source_config")
    bad = client.patch(f"{API}/projects/{p['id']}/graph/verification",
                       json={"edge_id": code_edge["id"], "verification": "verified"})
    assert bad.status_code == 400  # static-analysis edges can't be "physically verified"


def test_fault_a_fix_rescan_and_sim_verify(client, tmp_path):
    """Full Fault A loop with no hardware: fail → engineer edits firmware → rescan → verify passes."""
    repo = tmp_path / "fw"
    shutil.copytree(FAULT_A_REPO, repo)
    p = client.post(f"{API}/projects/import", json={"repo_path": str(repo), "manifest_path": str(MANIFEST)}).json()
    exp = client.post(f"{API}/projects/{p['id']}/expectations/propose").json()
    client.post(f"{API}/projects/{p['id']}/expectations/{exp['id']}/confirm", json={})
    run = client.post(f"{API}/projects/{p['id']}/tests",
                      json={"expectation_id": exp["id"], "source": {"kind": "sim", "scenario": "connected"}}).json()
    iid = client.get(f"{API}/tests/{run['id']}").json()["run"]["incident_id"]
    assert iid

    h = repo / "servo_control.h"
    h.write_text(h.read_text().replace("#define SERVO_PIN 19", "#define SERVO_PIN 18"))
    p2 = client.post(f"{API}/projects/{p['id']}/rescan").json()
    assert p2["graph_version"] == 2 and not any(i["code"] == "GPIO_CONFIG_MISMATCH" for i in p2["issues"])

    view = client.get(f"{API}/investigations/{iid}").json()
    verify = next(a for a in view["actions"] if a["kind"] == "verify_fix")
    client.post(f"{API}/investigations/{iid}/actions/{verify['id']}/execute",
                json={"source": {"kind": "sim", "scenario": "connected"}})
    assert client.get(f"{API}/investigations/{iid}").json()["incident"]["state"] == "resolved"
