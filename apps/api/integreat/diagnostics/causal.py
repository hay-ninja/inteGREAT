"""The cyber-physical causal chain for a run, plus counterfactual interrogation.

Fixed chain — software event to physical effect to observation:
    command sent → firmware acknowledged → signal path → physical motion → camera observed

Each link carries the evidence that established it. Links we cannot measure report
"unmeasured" rather than guessing. Counterfactual queries reuse the digital shadow:
do(knob=nominal) re-predicts the signature; if the observed signature no longer
reproduces, that fault is *necessary* to explain the observation — if it still does,
the fault is not required.
"""

from __future__ import annotations

from ..models import CausalStep, Expectation, ExpectationResult


def _fact(result: ExpectationResult, key: str):
    return next((f for f in result.facts if f.key == key), None)


def causal_chain(exp: Expectation, result: ExpectationResult) -> list[CausalStep]:
    sent = _fact(result, "command_sent")
    ack = _fact(result, "command_acknowledged")
    motion = _fact(result, "physical_motion")
    measured = result.valid_samples >= exp.min_valid_samples
    moved = bool(motion and motion.value == "yes")
    return [
        CausalStep(key="command_sent", label="Host sent the command",
                   value=sent.value if sent else "unknown",
                   evidence_ids=sent.evidence_ids if sent else [],
                   breaks_if="command path failed before the board"),
        CausalStep(key="command_acknowledged", label="Firmware acknowledged",
                   value=ack.value if ack else "unknown",
                   evidence_ids=ack.evidence_ids if ack else [],
                   breaks_if="firmware did not receive/handle the command (or does not log an ack)"),
        CausalStep(key="signal_path", label="Signal reached the component",
                   value="yes" if moved else "unmeasured", inferred=moved,
                   evidence_ids=motion.evidence_ids if moved and motion else [],
                   breaks_if="signal lead disconnected, or firmware drives a different pin"),
        CausalStep(key="physical_motion", label="Component physically moved",
                   value=motion.value if motion else "unknown",
                   evidence_ids=motion.evidence_ids if motion else [],
                   breaks_if="power/ground missing, component stalled or failed"),
        CausalStep(key="observed", label="Camera produced usable measurements",
                   value="yes" if measured else "unknown",
                   evidence_ids=[o for f in result.facts for o in f.evidence_ids][:3],
                   breaks_if="marker occluded or camera uncalibrated"),
    ]
