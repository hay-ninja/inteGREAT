from integreat.graph.builder import build_graph
from integreat.graph.query import scope
from integreat.ingestion.arduino_parser import parse_project
from integreat.ingestion.manifest import load_manifest
from integreat.ingestion.repository import scan_repository
from integreat.models import EdgeOrigin, EdgeRelation, GraphSnapshot, Verification

from .conftest import FAULT_A_REPO, GOOD_REPO, MANIFEST


def build(repo):
    s = scan_repository(repo)
    m, _, lines = load_manifest(MANIFEST)
    return build_graph("p", [f.rel for f in s.files], parse_project(s.files), m, lines, "m.yaml")


def test_every_reference_resolves():
    r = build(FAULT_A_REPO)
    node_ids = {n.id for n in r.nodes}
    ev_ids = {e.id for e in r.evidence}
    for e in r.edges:
        assert e.source_id in node_ids and e.target_id in node_ids, e.id
        assert set(e.evidence_ids) <= ev_ids, e.id
    for n in r.nodes:
        assert set(n.evidence_ids) <= ev_ids, n.id
        assert n.parent_id is None or n.parent_id in node_ids


def test_edge_semantics_are_distinct():
    r = build(GOOD_REPO)
    by_rel = {e.relation: e for e in r.edges}
    assert by_rel[EdgeRelation.calls].origin == EdgeOrigin.source_call_graph
    assert by_rel[EdgeRelation.configures].origin == EdgeOrigin.source_config
    assert by_rel[EdgeRelation.connected_to].origin == EdgeOrigin.declared_wiring
    assert by_rel[EdgeRelation.controls].origin == EdgeOrigin.inferred_dependency
    # static analysis is never "verified"
    assert all(e.verification != Verification.verified for e in r.edges
               if e.origin in (EdgeOrigin.source_config, EdgeOrigin.source_call_graph, EdgeOrigin.inferred_dependency))


def test_good_repo_is_consistent_fault_a_conflicts():
    good = build(GOOD_REPO)
    assert not [i for i in good.issues if i.code == "GPIO_CONFIG_MISMATCH"]
    bad = build(FAULT_A_REPO)
    issue = next(i for i in bad.issues if i.code == "GPIO_CONFIG_MISMATCH")
    assert "GPIO19" in issue.message and "GPIO18" in issue.message
    cfg = next(e for e in bad.edges if e.relation == EdgeRelation.configures and e.target_id == "pin:esp32_gpio19")
    assert cfg.verification == Verification.conflicting


def test_scope_excludes_unrelated_subsystem():
    r = build(GOOD_REPO)
    snap = GraphSnapshot(project_id="p", version=1, nodes=r.nodes, edges=r.edges)
    s = scope(snap, "subsystem:motor_control")
    ids = {n.id for n in s.nodes}
    assert "component:servo_1" in ids and "power_source:psu_5v" in ids and "pin:esp32_gpio18" in ids
    assert not any("wifi_status" in i for i in ids)
    assert "component:status_led" not in ids


# ---- dynamic graph inference (D-034) ----------------------------------------------

from integreat.ingestion.repository import RepoFile
from integreat.models import NodeKind

LED_SRC = """\
#include "led_control.h"
#define LED_PIN 4
void ledOn() { digitalWrite(LED_PIN, HIGH); }
void setup() { pinMode(LED_PIN, OUTPUT); }
"""


def build_mem(files: list[tuple[str, str]], manifest=None):
    rf = [RepoFile(rel=r, text=t) for r, t in files]
    return build_graph("p", [f.rel for f in rf], parse_project(rf), manifest)


def test_no_manifest_groups_by_filename_stem():
    r = build_mem([("led_demo.ino", LED_SRC), ("led_control.cpp", "// impl"), ("led_control.h", "// hdr"),
                   ("wifi_check.cpp", "// w"), ("wifi_check.h", "// wh")])
    subs = {n.id: n for n in r.nodes if n.kind == NodeKind.subsystem}
    assert "subsystem:inferred:led_control" in subs and "subsystem:inferred:wifi_check" in subs
    assert subs["subsystem:inferred:led_control"].verification == Verification.inferred
    assert any(i.code == "SUBSYSTEM_INFERRED" for i in r.issues)


def test_no_manifest_infers_component_from_name_hint():
    r = build_mem([("led_demo.ino", LED_SRC)])
    comp = next((n for n in r.nodes if n.id == "component:led_pin"), None)
    assert comp is not None and comp.attributes["inferred"] is True and comp.attributes["type"] == "led"
    assert comp.verification == Verification.unverified
    # inferred wiring: component pin -> mcu pin, so downstream rules/shadow can use it
    assert any(e.relation == EdgeRelation.connected_to and "led_pin" in (e.source_id + e.target_id)
               for e in r.edges)


def test_pin_mediated_controls_for_digitalwrite():
    # declared LED wired to GPIO4; code writes that pin -> controls edge resolves through the pin
    from integreat.ingestion.manifest import Manifest
    m = Manifest.model_validate({
        "schema": "integreat-manifest/v1",
        "board": {"id": "esp32", "label": "ESP32", "mcu": "esp32"},
        "subsystems": [], "components": [
            {"id": "led_1", "type": "led", "label": "Status LED", "pins": ["anode"]}],
        "connections": [
            {"id": "led_sig", "from": "mcu.GPIO4", "to": "led_1.anode", "kind": "signal",
             "verification": "verified"}]})
    r = build_mem([("led_demo.ino", LED_SRC)], manifest=m)
    fn = "function:led_demo.ino::ledOn"
    assert any(e.relation == EdgeRelation.controls and e.source_id == fn
               and e.target_id == "component:led_1" for e in r.edges)
    cfg = next(e for e in r.edges if e.relation == EdgeRelation.configures
               and e.target_id == "pin:esp32_gpio4")
    assert cfg.attributes["for_component"] == "component:led_1"
    assert cfg.attributes["level"] == "HIGH"


def test_declared_component_wins_over_object_inference():
    # `Servo myservo` + declared servo_1 → evidence folds into servo_1, no component:myservo
    src = "#include <Servo.h>\nServo myservo;\nvoid s() { myservo.attach(18); }\n"
    r = build_mem([("x.ino", src)], manifest=load_manifest(MANIFEST)[0])
    assert "component:myservo" not in {n.id for n in r.nodes}
    assert "component:servo_1" in {n.id for n in r.nodes}


def test_inferred_mcu_when_no_manifest_but_pins_used():
    r = build_mem([("led_demo.ino", LED_SRC)])
    mcu = next(n for n in r.nodes if n.kind == NodeKind.mcu)
    assert mcu.id == "mcu:esp32" and mcu.verification == Verification.inferred
