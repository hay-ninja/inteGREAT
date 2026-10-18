"""P0 fault library (PRD §12). Deterministic, no LLM. Each finding cites evidence that exists."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..graph.builder import signal_wiring_for
from ..models import (
    EdgeRelation,
    Epistemic,
    Evidence,
    EvidenceKind,
    Expectation,
    ExpectationOutcome,
    ExpectationResult,
    FaultCode,
    GraphEdge,
    GraphNode,
    Provenance,
    Verification,
)


@dataclass
class RuleFinding:
    code: FaultCode
    supporting: list[str] = field(default_factory=list)
    contradicting: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    nodes: list[str] = field(default_factory=list)
    edges: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def _fact(result: ExpectationResult, key: str):
    return next(f for f in result.facts if f.key == key)


def config_vs_wiring(component_id: str, nodes: list[GraphNode], edges: list[GraphEdge]):
    """Return (configures_edges_for_component, wiring_edge, wired_pin_id)."""
    cfg = [e for e in edges if e.relation == EdgeRelation.configures and e.attributes.get("for_component") == component_id]
    wired = signal_wiring_for(component_id, edges)
    return cfg, (wired[0] if wired else None), (wired[1] if wired else None)


def run_rules(exp: Expectation, result: ExpectationResult, nodes: list[GraphNode], edges: list[GraphEdge],
              test_run_id: str) -> tuple[list[RuleFinding], list[Evidence]]:
    findings: list[RuleFinding] = []
    new_ev: list[Evidence] = []
    comp = exp.component_id
    label = {n.id: n.label for n in nodes}
    comp_node = next((n for n in nodes if n.id == comp), None)
    comp_label = comp_node.label if comp_node else comp
    active_low = bool(comp_node and comp_node.attributes.get("active_low"))
    details_common = {"component_label": comp_label, "metric": exp.metric}

    if result.outcome == ExpectationOutcome.inconclusive:
        motion = _fact(result, "physical_motion")
        findings.append(RuleFinding(
            FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE, supporting=[result.evidence_id, *motion.evidence_ids],
            unknowns=[f"Whether {comp_label} responded (no valid measurement)"], nodes=[comp],
            details=dict(details_common)))
        return findings, new_ev  # never diagnose the component from missing frames (AC-03)

    if result.outcome == ExpectationOutcome.passed:
        return findings, new_ev

    motion = _fact(result, "physical_motion")
    ack = _fact(result, "command_acknowledged")
    sent = _fact(result, "command_sent")
    state = next((f for f in result.facts if f.key == "physical_state"), None)
    no_motion = motion.value == "no"

    # Binary outputs: the state changed but ended wrong → the code's on-level doesn't match
    # the declared wiring polarity. When the on-level resolved at proposal and is *consistent*
    # with the wiring, this is not inverted logic — the symptom lies elsewhere, so we stay silent.
    if exp.unit == "state" and motion.value == "yes" and state and state.value == "no":
        polarity_wrong = (exp.on_level is not None
                          and active_low == (exp.on_level == "HIGH"))
        if polarity_wrong or exp.on_level is None:
            findings.append(RuleFinding(
                FaultCode.INVERTED_LOGIC,
                supporting=[result.evidence_id, *motion.evidence_ids,
                            *(comp_node.evidence_ids if comp_node else [])],
                unknowns=[] if polarity_wrong else
                        ["The level the code drives for 'on' could not be resolved statically"],
                nodes=[comp],
                details={**details_common, "on_level": exp.on_level, "active_low": active_low,
                         "polarity_confirmed": polarity_wrong}))

    cfg, wire, wired_pin = config_vs_wiring(comp, nodes, edges)
    mismatched = [e for e in cfg if wired_pin and e.target_id != wired_pin]
    consistent = [e for e in cfg if wired_pin and e.target_id == wired_pin]

    if mismatched and wire:
        f = RuleFinding(
            FaultCode.GPIO_CONFIG_MISMATCH,
            supporting=[ev for e in mismatched for ev in e.evidence_ids] + wire.evidence_ids + [result.evidence_id],
            nodes=[comp, wired_pin, *[e.target_id for e in mismatched], *[e.source_id for e in mismatched]],
            edges=[wire.id, *[e.id for e in mismatched]],
            details={**details_common,
                     "configured": [label[e.target_id] for e in mismatched], "wired": label[wired_pin]},
        )
        if wire.verification != Verification.verified:
            f.unknowns.append("Signal wiring is declared but not engineer-verified")
        f.unknowns.append("Whether the firmware running on the board was built from this source revision")
        findings.append(f)

    if no_motion:
        findings.append(RuleFinding(
            FaultCode.NO_PHYSICAL_MOTION, supporting=[result.evidence_id, *motion.evidence_ids], nodes=[comp]))

    if ack.value == "no":
        findings.append(RuleFinding(
            FaultCode.MISSING_SERIAL_ACK, supporting=[result.evidence_id, *sent.evidence_ids],
            unknowns=["Whether the firmware received the command (absent ACK is not proof of failure)"],
            nodes=[comp]))

    if no_motion and ack.value != "no":
        f = RuleFinding(
            FaultCode.POSSIBLE_POWER_OR_SIGNAL_FAULT,
            supporting=[result.evidence_id, *ack.evidence_ids],
            unknowns=["The drive signal at the component pin was not measured",
                      f"Supply voltage to {comp_label} was not measured"],
            nodes=[comp],
            details=dict(details_common),
            edges=[e.id for e in edges if e.source_id == comp and e.relation == EdgeRelation.powered_by]
            + ([wire.id] if wire else []),
        )
        if consistent:
            cid = f"evidence:rule:{test_run_id}:config_consistent"
            new_ev.append(Evidence(
                id=cid, project_id=exp.project_id, kind=EvidenceKind.rule_result, epistemic=Epistemic.inferred,
                summary=f"Source configures {label[consistent[0].target_id]}, matching declared signal wiring "
                        f"({wire.verification.value}).",
                provenance=Provenance(source_id="rules"), test_run_id=test_run_id,
                payload={"edge_ids": [consistent[0].id, wire.id]}))
            f.supporting.append(cid)
        if mismatched:
            f.details["secondary"] = True  # a config mismatch already explains no motion better
        findings.append(f)

    return findings, new_ev
