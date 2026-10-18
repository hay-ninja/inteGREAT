"""Turn rule findings into ranked hypotheses + action cards (PRD §12, FR-08).

Ranking is qualitative (rank integers, ties allowed), never probabilities. Every action listed here
must be executable — no inert buttons (PRD §14).
"""

from __future__ import annotations

from ..models import (
    ActionKind,
    DiagnosticAction,
    ExpectedOutcome,
    FaultCode,
    Hypothesis,
    HypothesisStatus,
)
from .rules import RuleFinding

# Status ordering used for re-ranking after new evidence.
_STATUS_ORDER = {
    HypothesisStatus.supported: 0,
    HypothesisStatus.plausible: 1,
    HypothesisStatus.unverified: 2,
    HypothesisStatus.weakened: 3,
    HypothesisStatus.ruled_out: 4,
}


def build(incident_id: str, findings: list[RuleFinding], wired_pin_label: str | None,
          component_id: str) -> tuple[list[Hypothesis], list[DiagnosticAction]]:
    hyps: list[Hypothesis] = []
    actions: dict[str, DiagnosticAction] = {}
    codes = {f.code for f in findings}
    pin = wired_pin_label or "the declared signal pin"

    def act(a: DiagnosticAction) -> str:
        actions.setdefault(a.id, a)
        return a.id

    repeat = act(DiagnosticAction(
        id=f"action:{incident_id}:repeat_test", incident_id=incident_id, kind=ActionKind.repeat_test,
        label="Repeat motion test", rationale="Re-run the same confirmed expectation to check the result is repeatable.",
        expected_outcomes=[ExpectedOutcome(result="Same failure", interpretation="Fault is persistent, not transient"),
                           ExpectedOutcome(result="Passes", interpretation="Intermittent fault or setup issue")]))
    verify = act(DiagnosticAction(
        id=f"action:{incident_id}:verify_fix", incident_id=incident_id, kind=ActionKind.verify_fix,
        label="Verify fix", rationale="After repairing outside inteGREAT, re-run the same test with the same thresholds.",
        expected_outcomes=[ExpectedOutcome(result="Pass", interpretation="Incident resolved with measured evidence"),
                           ExpectedOutcome(result="Fail / inconclusive", interpretation="Incident stays open")]))

    read_serial = act(DiagnosticAction(
        id=f"action:{incident_id}:read_serial", incident_id=incident_id, kind=ActionKind.run_readonly_tool,
        label="Read recent serial output", tool_name="read_serial_buffer", arguments={"max_lines": 100},
        permission_category="serial_read",
        rationale="Check what the firmware printed around the test (live buffer if connected, else recorded runs).",
        expected_outcomes=[ExpectedOutcome(result="ACK present", interpretation="Firmware received and handled the command"),
                           ExpectedOutcome(result="Errors / resets", interpretation="Firmware-side problem; inspect source"),
                           ExpectedOutcome(result="Silence", interpretation="Not proof of failure; firmware may not log")]))

    for f in findings:
        hid = f"hypothesis:{incident_id}:{f.code.value.lower()}"
        common = dict(incident_id=incident_id, fault_code=f.code, supporting_evidence_ids=f.supporting,
                      contradicting_evidence_ids=f.contradicting, unknowns=list(f.unknowns),
                      related_node_ids=f.nodes, related_edge_ids=f.edges)

        if f.code == FaultCode.GPIO_CONFIG_MISMATCH:
            a = act(DiagnosticAction(
                id=f"action:{incident_id}:inspect_gpio_mapping", incident_id=incident_id,
                kind=ActionKind.inspect_source, label="Inspect GPIO mapping",
                rationale=f"Source configures {', '.join(f.details['configured'])} but wiring uses {f.details['wired']}.",
                tool_name="inspect_gpio_config", arguments={"component_id": component_id},
                permission_category="repo_read", recommended=True, evidence_ids=f.supporting,
                related_node_ids=f.nodes,
                expected_outcomes=[
                    ExpectedOutcome(result="Pins differ", interpretation="Fix the pin in firmware (or rewire), reflash, then Verify fix"),
                    ExpectedOutcome(result="Pins match", interpretation="Mismatch ruled out; check physical connection")]))
            fix = act(DiagnosticAction(
                id=f"action:{incident_id}:prepare_fix", incident_id=incident_id,
                kind=ActionKind.prepare_software_fix, label="Prepare software fix with Devin",
                rationale=("Evidence points at firmware configuration. Devin Cloud can prepare a "
                           "reviewable fix on an isolated branch — nothing is applied locally, "
                           "merged, or flashed. Remote test results are software-only evidence."),
                related_node_ids=f.nodes,
                expected_outcomes=[
                    ExpectedOutcome(result="Reviewable diff/PR", interpretation="Engineer reviews, applies it by hand, reflashes, then Verify fix"),
                    ExpectedOutcome(result="No result / failed job", interpretation="Incident unchanged; fix the pin by hand")]))
            hyps.append(Hypothesis(
                id=hid, title="Incorrect GPIO mapping", rank=1, status=HypothesisStatus.plausible,
                explanation=(f"Firmware configures the servo on {', '.join(f.details['configured'])}, but the "
                             f"engineer-confirmed wiring connects the servo signal to {f.details['wired']}. "
                             "Commands would drive a pin the servo isn't connected to."),
                recommended_action_ids=[a, fix, verify], **common))

        elif f.code == FaultCode.POSSIBLE_POWER_OR_SIGNAL_FAULT:
            secondary = bool(f.details.get("secondary"))
            rank = 2 if secondary else 1
            sig = act(DiagnosticAction(
                id=f"action:{incident_id}:check_signal", incident_id=incident_id,
                kind=ActionKind.request_manual_check, label="Check signal connection",
                rationale="Cannot measure PWM; a visual check of the signal lead distinguishes signal vs power faults.",
                recommended=not secondary, related_node_ids=f.nodes,
                manual_instructions=[f"Power down the servo supply before touching wiring.",
                                     f"Check the signal jumper from {pin} to the servo signal lead (orange/yellow) is seated at both ends.",
                                     "Record what you find."],
                result_choices=["Connected", "Disconnected", "Unable to verify"],
                arguments={"hypothesis_id": f"{hid}_signal",
                           "status_on_result": {"Disconnected": "supported", "Connected": "weakened"}},
                expected_outcomes=[ExpectedOutcome(result="Disconnected", interpretation="Supports signal-lead fault; reconnect and Verify fix"),
                                   ExpectedOutcome(result="Connected", interpretation="Weakens signal-lead fault; check power")]))
            pwr = act(DiagnosticAction(
                id=f"action:{incident_id}:check_power", incident_id=incident_id,
                kind=ActionKind.request_manual_check, label="Check servo power & ground",
                rationale="Servo supply voltage is not measured by inteGREAT; confirm power and common ground by hand.",
                related_node_ids=f.nodes,
                manual_instructions=["Confirm the external supply is on and set for the servo's rated voltage.",
                                     "Check servo V+ and GND leads are seated, and supply GND is common with ESP32 GND.",
                                     "Do not power the servo from the ESP32 3.3 V pin."],
                result_choices=["Connected", "Disconnected", "Unable to verify"],
                arguments={"hypothesis_id": f"{hid}_power",
                           "status_on_result": {"Disconnected": "supported", "Connected": "weakened"}},
                expected_outcomes=[ExpectedOutcome(result="Disconnected", interpretation="Supports power fault; reconnect and Verify fix"),
                                   ExpectedOutcome(result="Connected", interpretation="Weakens power fault")]))
            expand = act(DiagnosticAction(
                id=f"action:{incident_id}:expand_power", incident_id=incident_id, kind=ActionKind.expand_scope,
                label="Expand power dependencies", tool_name="expand_scope",
                arguments={"scope_node_id": component_id, "depth": 3}, permission_category="repo_read",
                rationale="Show the declared supply, ground and signal path around the servo in the graph.",
                related_node_ids=f.nodes,
                expected_outcomes=[ExpectedOutcome(result="Supply/ground declared", interpretation="Check those connections by hand"),
                                   ExpectedOutcome(result="Missing in graph", interpretation="Hardware context incomplete; update manifest/netlist")]))
            note = " A GPIO mismatch was also found and explains the symptom more directly." if secondary else ""
            hyps.append(Hypothesis(
                id=f"{hid}_signal", title="Servo signal lead disconnected or faulty", rank=rank,
                status=HypothesisStatus.unverified,
                explanation=("The firmware appears to have handled the command but the camera saw no motion. "
                             "inteGREAT cannot observe whether a PWM signal reached the servo." + note),
                recommended_action_ids=[sig, verify], **common))
            hyps.append(Hypothesis(
                id=f"{hid}_power", title="Servo power or ground not reaching servo", rank=rank,
                status=HypothesisStatus.unverified,
                explanation=("No motion is also consistent with missing servo power or a missing common ground. "
                             "Supply voltage is not measured." + note),
                recommended_action_ids=[pwr, expand, verify], **common))

        elif f.code == FaultCode.MISSING_SERIAL_ACK:
            hyps.append(Hypothesis(
                id=hid, title="Firmware did not acknowledge the command", rank=1 if len(codes) <= 2 else 2,
                status=HypothesisStatus.plausible,
                explanation=("No acknowledgement line appeared in serial output. The firmware may not have received "
                             "or handled the command — or it may simply not have logged it."),
                recommended_action_ids=[read_serial, repeat], **common))

        elif f.code == FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE:
            hyps.append(Hypothesis(
                id=hid, title="Camera measurement unavailable", rank=1, status=HypothesisStatus.supported,
                explanation=("The marker was not detected in enough frames to judge servo motion. This is a "
                             "measurement problem, not evidence of a servo fault. Check camera view and marker, then repeat."),
                recommended_action_ids=[repeat], **common))
        # NO_PHYSICAL_MOTION is a symptom, not a cause: it supports the hypotheses above, no card of its own.

    if not hyps:
        return [], [actions[repeat]]
    return rerank(hyps), list(actions.values())


def rerank(hyps: list[Hypothesis]) -> list[Hypothesis]:
    ordered = sorted(hyps, key=lambda h: (_STATUS_ORDER[h.status], h.rank))
    out, rank, prev = [], 0, None
    for h in ordered:
        key = (_STATUS_ORDER[h.status], h.rank)
        if key != prev:
            rank += 1
            prev = key
        out.append(h.model_copy(update={"rank": rank}))
    return out
