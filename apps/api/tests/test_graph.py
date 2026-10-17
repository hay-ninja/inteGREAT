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
