"""Expectation proposal and deterministic evaluation (PRD FR-05, AC-03).

Rules of evaluation:
- Fewer than `min_valid_samples` valid measurements → INCONCLUSIVE. Missing marker never becomes a
  servo failure.
- Pass iff the last valid measurement inside the deadline is within tolerance of target.
- "Physical motion" = displacement from first valid sample ≥ min_motion_deg.
- Command sent / acknowledged / physical motion are reported as three separate facts (PRD §5.3).
"""

from __future__ import annotations

import uuid

from ..models import (
    Epistemic,
    Evidence,
    EvidenceKind,
    Expectation,
    ExpectationOutcome,
    ExpectationResult,
    ExpectationTrigger,
    Fact,
    GraphNode,
    NodeKind,
    Observation,
    Provenance,
    SerialEvent,
)


def propose_expectation(project_id: str, nodes: list[GraphNode], evidence: list[Evidence],
                        log_literals: list[str]) -> Expectation | None:
    """Deterministic proposal from source evidence. Engineer must confirm before use."""
    servo = next((n for n in nodes if n.kind == NodeKind.component and n.attributes.get("type") == "servo"), None)
    if servo is None:
        return None
    cmd = next((e for e in evidence if e.id.endswith(":cmd") and str(e.payload.get("literal", "")).strip()), None)
    trigger_prefix = str(cmd.payload["literal"]).strip() if cmd else None
    if trigger_prefix is None:
        trigger = ExpectationTrigger(kind="external_sequence", value="Engineer starts the motion sequence")
        rationale = "No serial command handler found in source; requires an engineer-initiated sequence."
    else:
        trigger = ExpectationTrigger(kind="configured_serial_command", value=f"{trigger_prefix} 90")
        rationale = f'Firmware parses serial commands starting with "{trigger_prefix}" ({cmd.provenance.file}:{cmd.provenance.line_start}).'
    # Only expect an ACK if the firmware itself prints one that echoes the command (no instrumentation).
    ack_pattern = None
    if trigger_prefix:
        ack_pattern = next((lit.strip() for lit in log_literals if lit.strip().endswith(trigger_prefix)
                            and lit.strip() != trigger_prefix), None)
    test_id = uuid.uuid4().hex[:8]
    return Expectation(
        id=f"expectation:{test_id}", project_id=project_id, test_definition_id=f"testdef:{test_id}",
        component_id=servo.id, trigger=trigger, target=90, tolerance=8, deadline_ms=2000,
        ack_pattern=ack_pattern,
        confirmed_by_engineer=False,
        proposed_from_evidence_ids=[e.id for e in (cmd,) if e] + servo.evidence_ids,
        rationale=rationale,
    )


def evaluate(exp: Expectation, observations: list[Observation], serial: list[SerialEvent],
             test_run_id: str) -> tuple[ExpectationResult, Evidence]:
    window = [o for o in observations if o.elapsed_ms <= exp.deadline_ms and o.metric == exp.metric]
    valid = [o for o in window if o.measurement_quality == "valid" and o.value is not None]
    invalid = [o for o in window if o not in valid]

    tx = [s for s in serial if s.direction == "tx"]
    rx = [s for s in serial if s.direction == "rx"]
    facts = [Fact(key="command_sent", label="Test command sent by host",
                  value="yes" if tx else ("unknown" if exp.trigger.kind == "external_sequence" else "no"),
                  evidence_ids=[s.evidence_id for s in tx][:1])]
    if exp.ack_pattern:
        acks = [s for s in rx if s.raw.startswith(exp.ack_pattern)]
        facts.append(Fact(key="command_acknowledged", label="Firmware acknowledged command in serial log",
                          value="yes" if acks else "no", evidence_ids=[s.evidence_id for s in acks][:1],
                          note=None if acks else "Absence of an ACK is not proof the firmware failed."))
    else:
        facts.append(Fact(key="command_acknowledged", label="Firmware acknowledged command in serial log",
                          value="unknown", note="No acknowledgement pattern configured."))

    if len(valid) < exp.min_valid_samples:
        outcome = ExpectationOutcome.inconclusive
        final = valid[-1].value if valid else None
        disp = None
        reason = (f"Only {len(valid)} valid camera measurements in the {exp.deadline_ms} ms window "
                  f"({len(invalid)} invalid). Servo behavior cannot be judged from missing measurements.")
        facts.append(Fact(key="physical_motion", label="Physical motion observed by camera", value="unknown",
                          evidence_ids=[o.evidence_id for o in invalid][:3], note="Measurement unavailable."))
    else:
        base = valid[0].value
        disp = round(max(abs(o.value - base) for o in valid), 1)
        final = valid[-1].value
        moved = disp >= exp.min_motion_deg
        facts.append(Fact(key="physical_motion", label="Physical motion observed by camera",
                          value="yes" if moved else "no",
                          evidence_ids=[valid[0].evidence_id, valid[-1].evidence_id],
                          note=f"Max displacement {disp}° (threshold {exp.min_motion_deg}°)."))
        if abs(final - exp.target) <= exp.tolerance:
            outcome = ExpectationOutcome.passed
            reason = (f"Angle reached {final}° (target {exp.target}° ± {exp.tolerance}°) "
                      f"within {exp.deadline_ms} ms.")
        else:
            outcome = ExpectationOutcome.failed
            reason = (f"Final valid angle {final}° is outside {exp.target}° ± {exp.tolerance}° at "
                      f"{exp.deadline_ms} ms; max displacement {disp}°.")

    ev = Evidence(
        id=f"evidence:rule:{test_run_id}:expectation", project_id=exp.project_id, kind=EvidenceKind.rule_result,
        epistemic=Epistemic.observed, summary=f"Expectation {outcome.value.upper()}: {reason}",
        provenance=Provenance(source_id="expectation_evaluator"), test_run_id=test_run_id,
        payload={"expectation_id": exp.id, "valid_samples": len(valid), "invalid_samples": len(invalid),
                 "final_valid_value": final, "max_displacement": disp,
                 "observation_ids": [o.id for o in valid[:1] + valid[-1:]]},
    )
    result = ExpectationResult(outcome=outcome, reason=reason, final_valid_value=final, max_displacement=disp,
                               valid_samples=len(valid), invalid_samples=len(invalid), facts=facts,
                               evidence_id=ev.id)
    return result, ev
