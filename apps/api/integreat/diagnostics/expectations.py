"""Expectation proposal and deterministic evaluation (PRD FR-05, AC-03).

Metric families:
- analog (unit "deg", etc.) — pass iff the last valid measurement is within tolerance of target;
  "physical motion" = displacement from the first valid sample ≥ min_motion_deg.
- binary (unit "state") — pass iff the last valid measurement equals target; the "physical
  state" fact records whether the component reached the expected final state.

Rules of evaluation:
- Fewer than `min_valid_samples` valid measurements → INCONCLUSIVE. Missing marker never becomes a
  component failure.
- Command sent / acknowledged / physical response are reported as separate facts (PRD §5.3).
"""

from __future__ import annotations

import uuid

from ..models import (
    EdgeRelation,
    Epistemic,
    Evidence,
    EvidenceKind,
    Expectation,
    ExpectationOutcome,
    ExpectationResult,
    ExpectationTrigger,
    Fact,
    GraphEdge,
    GraphNode,
    NodeKind,
    Observation,
    Provenance,
    SerialEvent,
)

# Component types the proposal engine knows how to test, keyed by declared/inferred
# component `type`. Unknown types are skipped — no test is invented for them.
_KIND = {
    "servo": {"metric": "servo_angle_deg", "unit": "deg", "target": 90.0, "tolerance": 8.0,
              "command_arg": " 90"},
    "led": {"metric": "led_state", "unit": "state", "target": 1.0, "tolerance": 0.0,
            "command_arg": " ON"},  # appended when the literal isn't already the full "…ON" command
}

# Command literals that read as oscillation requests get a toggle pattern — "FLICKER"
# means "changes repeatedly", not "ends in a state" (D-060).
_OSCILLATE = ("FLICKER", "BLINK", "PULSE", "STROBE", "FLASH")


def _on_level(component_id: str, literal: str, nodes: list[GraphNode], edges: list[GraphEdge],
              cmd_fn: str | None) -> str | None:
    """The level the firmware drives for the ON command, resolved from source structure:
    the pin write inside the ON handler, or inside a callee whose name matches the
    command's trailing token (literal "LED ON" → callee `ledOn`). Returns "HIGH"/"LOW"/None —
    ambiguous structure yields None, never a guess."""
    reach = {cmd_fn} if cmd_fn else set()
    reach |= {e.target_id for e in edges
              if e.relation == EdgeRelation.calls and e.source_id in reach}
    write_fns = {e.source_id: e.attributes["level"] for e in edges
                 if e.relation == EdgeRelation.configures
                 and e.attributes.get("for_component") == component_id
                 and e.source_id in reach
                 and e.attributes.get("level") in ("HIGH", "LOW")}
    if len(set(write_fns.values())) == 1:
        return next(iter(write_fns.values()), None)
    # Multiple levels (on + off paths): prefer the callee named for the command's last word
    tail = literal.strip().split()[-1].lower() if literal.strip() else ""
    labels = {n.id: n.label.lower() for n in nodes if n.kind == NodeKind.function}
    named = [lvl for fid, lvl in write_fns.items() if tail and tail in labels.get(fid, "")]
    return named[0] if len(set(named)) == 1 else None


def propose_expectation(project_id: str, nodes: list[GraphNode], edges: list[GraphEdge],
                        evidence: list[Evidence], log_literals: list[str],
                        component_id: str | None = None, command: str | None = None) -> Expectation | None:
    """Deterministic proposal from source evidence. Engineer must confirm before use.

    `component_id` targets a specific testable component (multi-component rigs); `command`
    picks a specific command literal instead of the preferred ON command. Both default to
    the previous first-match behaviour (D-057)."""
    comp, kind = next(((n, _KIND[n.attributes["type"]]) for n in nodes
                       if n.kind == NodeKind.component and n.attributes.get("type") in _KIND
                       and (component_id is None or n.id == component_id)), (None, None))
    if comp is None:
        return None
    cmds = [e for e in evidence if e.id.endswith(":cmd") and str(e.payload.get("literal", "")).strip()]
    if command is not None:
        cmd = next((e for e in cmds if str(e.payload["literal"]).strip() == command.strip()), None)
    else:
        # Prefer the literal that reads as an "on" command for binary outputs
        cmd = (next((e for e in cmds if str(e.payload["literal"]).strip().upper().endswith("ON")), None)
               if kind["unit"] == "state" else None) or (cmds[0] if cmds else None)
    literal = command.strip() if command is not None else (str(cmd.payload["literal"]).strip() if cmd else None)
    osc = bool(literal) and any(tok in literal.upper().split() for tok in _OSCILLATE)
    if literal is None:
        trigger = ExpectationTrigger(kind="external_sequence", value="Engineer starts the action sequence")
        rationale = "No serial command handler found in source; requires an engineer-initiated sequence."
    else:
        # "…ON" commands and oscillation commands ("FLICKER") are already complete — never append " ON".
        arg = "" if command is not None or literal.upper().endswith(" ON") or osc else kind["command_arg"]
        trigger = ExpectationTrigger(kind="configured_serial_command", value=f"{literal}{arg}")
        rationale = (f'Firmware parses serial commands matching "{literal}" '
                     f"({cmd.provenance.file}:{cmd.provenance.line_start})." if cmd else
                     f'Command "{literal}" was specified by the engineer; no matching literal was '
                     "found in source — treat as an assertion, not evidence.")
    # Only expect an ACK if the firmware itself prints one that echoes the command (no instrumentation).
    ack_pattern = None
    if literal:
        ack_pattern = next((lit.strip() for lit in log_literals
                            if lit.strip().endswith(literal) and lit.strip() != literal), None)
    # For binary outputs, resolve the level the firmware drives for ON (polarity checks in rules/sim).
    cmd_fn = None
    if cmd is not None:
        cmd_fn = next((n.id for n in nodes if n.kind == NodeKind.function
                       and n.attributes.get("file") == cmd.provenance.file
                       and n.attributes.get("line_start", 0) <= (cmd.provenance.line_start or 0)
                       <= n.attributes.get("line_end", 0)), None)
    on_level = (_on_level(comp.id, literal or "", nodes, edges, cmd_fn)
                if kind["unit"] == "state" else None)
    pattern = "toggle" if kind["unit"] == "state" and osc else "steady"
    test_id = uuid.uuid4().hex[:8]
    return Expectation(
        id=f"expectation:{test_id}", project_id=project_id, test_definition_id=f"testdef:{test_id}",
        component_id=comp.id, trigger=trigger, metric=kind["metric"], unit=kind["unit"],
        target=kind["target"], tolerance=kind["tolerance"], deadline_ms=2000,
        pattern=pattern, ack_pattern=ack_pattern, on_level=on_level,
        confirmed_by_engineer=False,
        proposed_from_evidence_ids=[e.id for e in (cmd,) if e] + comp.evidence_ids,
        rationale=rationale,
    )


def evaluate(exp: Expectation, observations: list[Observation], serial: list[SerialEvent],
             test_run_id: str) -> tuple[ExpectationResult, Evidence]:
    window = [o for o in observations if o.elapsed_ms <= exp.deadline_ms and o.metric == exp.metric]
    valid = [o for o in window if o.measurement_quality == "valid" and o.value is not None]
    invalid = [o for o in window if o not in valid]

    # A tx line only counts as the command if it IS the configured command — a
    # replay of a different command's recording must not read as "sent" (D-060).
    tx = [s for s in serial if s.direction == "tx" and s.raw.strip() == exp.trigger.value.strip()]
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

    binary = exp.unit == "state"
    response_label = ("Light state change observed by camera" if binary
                      else "Physical motion observed by camera")

    transitions = None
    if exp.trigger.kind == "configured_serial_command" and not tx:
        # The configured command provably never went out — physical observations
        # from this run are unrelated to the expectation and can't be judged.
        outcome = ExpectationOutcome.inconclusive
        final = valid[-1].value if valid else None
        disp = None
        reason = (f'Configured command "{exp.trigger.value}" was never sent — this '
                  "run's source issued a different command, so the expectation can't be judged.")
        facts.append(Fact(key="physical_motion", label=response_label, value="unknown",
                          note="Command never sent."))
        facts.append(Fact(key="physical_state", label="Component reached the expected state",
                          value="unknown", note="Command never sent."))
    elif len(valid) < exp.min_valid_samples:
        outcome = ExpectationOutcome.inconclusive
        final = valid[-1].value if valid else None
        disp = None
        reason = (f"Only {len(valid)} valid camera measurements in the {exp.deadline_ms} ms window "
                  f"({len(invalid)} invalid). Component behavior cannot be judged from missing measurements.")
        facts.append(Fact(key="physical_motion", label=response_label, value="unknown",
                          evidence_ids=[o.evidence_id for o in invalid][:3], note="Measurement unavailable."))
        facts.append(Fact(key="physical_state", label="Component reached the expected state",
                          value="unknown", note="Measurement unavailable."))
    else:
        base = valid[0].value
        disp = round(max(abs(o.value - base) for o in valid), 1)
        final = valid[-1].value
        moved = (disp > 0.5) if binary else (disp >= exp.min_motion_deg)

        # Temporal detail: how the component behaved across the window, not just
        # where it ended (D-060). A dead LED and a flickering LED must not read alike.
        transitions = sum(1 for a, b in zip(valid, valid[1:]) if b.value != a.value)
        first_change = next((o.elapsed_ms for o in valid[1:] if o.value != base), None)
        at_target = [o for o in valid if abs(o.value - exp.target) <= exp.tolerance]
        occupancy = len(at_target) / len(valid)
        facts.append(Fact(key="state_transitions", label="State changes in the window",
                          value="yes" if transitions else "no",
                          note=f"{transitions} change{'s' if transitions != 1 else ''} between "
                               f"{len(valid)} valid samples; {occupancy:.0%} of the window was "
                               "at the expected level."))
        facts.append(Fact(key="first_response", label="Component responded within the window",
                          value="yes" if first_change is not None else "no",
                          note=None if first_change is None else f"First change at {first_change} ms."))

        facts.append(Fact(key="physical_motion", label=response_label,
                          value="yes" if moved else "no",
                          evidence_ids=[valid[0].evidence_id, valid[-1].evidence_id],
                          note=(f"State changed ({base:g} → {final:g})." if binary
                                else f"Max displacement {disp}° (threshold {exp.min_motion_deg}°).")))

        if binary and exp.pattern == "toggle":
            ok = transitions >= exp.min_transitions
            facts.append(Fact(key="physical_state", label="Component toggled as expected",
                              value="yes" if ok else "no",
                              evidence_ids=[o.evidence_id for o in valid[:3]],
                              note=f"{transitions} state change{'s' if transitions != 1 else ''} "
                                   f"(expected ≥ {exp.min_transitions})."))
            outcome = ExpectationOutcome.passed if ok else ExpectationOutcome.failed
            reason = (f"State toggled {transitions} times within {exp.deadline_ms} ms." if ok
                      else f"Only {transitions} state change{'s' if transitions != 1 else ''} in "
                           f"{exp.deadline_ms} ms (needed ≥ {exp.min_transitions}) — "
                           "the output did not oscillate as the command implies.")
        else:
            reached = abs(final - exp.target) <= exp.tolerance
            facts.append(Fact(key="physical_state", label="Component reached the expected state",
                              value="yes" if reached else "no",
                              evidence_ids=[valid[-1].evidence_id],
                              note=(f"Final state {final:g} (expected {exp.target:g})." if binary else None)))
            if reached:
                outcome = ExpectationOutcome.passed
                reason = (f"{'State reached' if binary else 'Angle reached'} {final:g}"
                          f"{'' if binary else f'° (target {exp.target:g}° ± {exp.tolerance:g}°)'} "
                          f"within {exp.deadline_ms} ms.")
            else:
                outcome = ExpectationOutcome.failed
                reason = ((f"Final state {final:g} is not the expected {exp.target:g}" if binary
                           else f"Final valid angle {final:g}° is outside {exp.target:g}° ± {exp.tolerance:g}°")
                          + f" at {exp.deadline_ms} ms"
                          + (f"; state did change ({base:g} → {final:g})" if binary and moved else
                             "" if binary else f"; max displacement {disp:g}°"))

    ev = Evidence(
        id=f"evidence:rule:{test_run_id}:expectation", project_id=exp.project_id, kind=EvidenceKind.rule_result,
        epistemic=Epistemic.observed, summary=f"Expectation {outcome.value.upper()}: {reason}",
        provenance=Provenance(source_id="expectation_evaluator"), test_run_id=test_run_id,
        payload={"expectation_id": exp.id, "valid_samples": len(valid), "invalid_samples": len(invalid),
                 "final_valid_value": final, "max_displacement": disp, "transitions": transitions,
                 "observation_ids": [o.id for o in valid[:1] + valid[-1:]]},
    )
    result = ExpectationResult(outcome=outcome, reason=reason, final_valid_value=final, max_displacement=disp,
                               valid_samples=len(valid), invalid_samples=len(invalid), facts=facts,
                               evidence_id=ev.id)
    return result, ev
