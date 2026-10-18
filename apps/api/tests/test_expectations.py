from datetime import UTC, datetime

import pytest

from integreat.diagnostics.expectations import evaluate
from integreat.models import Expectation, ExpectationTrigger, Observation, SerialEvent

T0 = datetime(2026, 10, 17, tzinfo=UTC)


def exp(**kw):
    base = dict(id="expectation:x", project_id="p", test_definition_id="t", component_id="component:servo_1",
                trigger=ExpectationTrigger(kind="configured_serial_command", value="MOVE 90"),
                target=90, tolerance=8, deadline_ms=2000, ack_pattern="ACK MOVE", confirmed_by_engineer=True)
    return Expectation(**{**base, **kw})


def obs(points, quality="valid"):
    return [Observation(id=f"o{i}", project_id="p", test_run_id="r", source_type="replay_cv", source_id="s",
                        component_id="component:servo_1", timestamp_utc=T0, elapsed_ms=t, metric="servo_angle_deg",
                        value=v if quality == "valid" else None, unit="deg", measurement_quality=quality,
                        evidence_ref="f", evidence_id=f"e{i}") for i, (t, v) in enumerate(points)]


def serial(*lines, tx="MOVE 90"):
    out = [SerialEvent(id="s0", project_id="p", test_run_id="r", direction="tx", timestamp_utc=T0, elapsed_ms=0,
                       raw=tx, evidence_id="ehost")]
    out += [SerialEvent(id=f"s{i + 1}", project_id="p", test_run_id="r", direction="rx", timestamp_utc=T0,
                        elapsed_ms=40, raw=line, evidence_id=f"eser{i}") for i, line in enumerate(lines)]
    return out


def facts(res):
    return {f.key: f.value for f in res.facts}


def test_pass_when_settled_within_tolerance():
    res, ev = evaluate(exp(), obs([(0, 0), (500, 60), (1000, 88), (1500, 89)]), serial("ACK MOVE 90"), "r")
    assert res.outcome.value == "pass"
    f = facts(res)
    assert {k: f[k] for k in ("command_sent", "command_acknowledged", "physical_motion", "physical_state")} == \
        {"command_sent": "yes", "command_acknowledged": "yes",
         "physical_motion": "yes", "physical_state": "yes"}
    assert f["state_transitions"] == "yes" and "3 changes" in res.facts[[x.key for x in res.facts].index("state_transitions")].note
    assert f["first_response"] == "yes"
    assert ev.id == res.evidence_id


def led_exp(**kw):
    base = dict(metric="led_state", unit="state", target=1.0, tolerance=0.0,
                trigger=ExpectationTrigger(kind="configured_serial_command", value="LED ON"),
                ack_pattern="ACK LED ON")
    return exp(**{**base, **kw})


def led_obs(points, quality="valid"):
    return [o.model_copy(update={"metric": "led_state", "unit": "state"})
            for o in obs(points, quality=quality)]


def test_led_on_passes_when_state_reaches_target():
    res, _ = evaluate(led_exp(), led_obs([(0, 0), (500, 1), (1000, 1)]), serial("ACK LED ON", tx="LED ON"), "r")
    assert res.outcome.value == "pass"
    assert facts(res)["physical_motion"] == "yes" and facts(res)["physical_state"] == "yes"


def test_led_off_after_command_is_fail_with_state_change():
    """The inverted-logic signature: state changed, ended wrong (Fault C)."""
    res, _ = evaluate(led_exp(), led_obs([(0, 1), (500, 0), (1000, 0)]), serial("ACK LED ON", tx="LED ON"), "r")
    assert res.outcome.value == "fail"
    assert facts(res)["physical_motion"] == "yes" and facts(res)["physical_state"] == "no"


def test_led_never_changes_is_fail_no_response():
    res, _ = evaluate(led_exp(), led_obs([(0, 0), (500, 0), (1000, 0)]), serial("ACK LED ON", tx="LED ON"), "r")
    assert res.outcome.value == "fail"
    assert facts(res)["physical_motion"] == "no" and facts(res)["physical_state"] == "no"


@pytest.mark.parametrize("final,outcome", [(82.0, "pass"), (81.9, "fail"), (98.0, "pass"), (98.1, "fail")])
def test_tolerance_boundary(final, outcome):
    res, _ = evaluate(exp(), obs([(0, 0), (500, 50), (1000, final)]), serial(), "r")
    assert res.outcome.value == outcome


def test_samples_after_deadline_ignored():
    res, _ = evaluate(exp(), obs([(0, 0), (500, 1), (1000, 1), (2500, 90)]), serial("ACK MOVE 90"), "r")
    assert res.outcome.value == "fail"
    assert facts(res)["physical_motion"] == "no"


def test_missing_marker_is_inconclusive_not_failure():
    res, _ = evaluate(exp(), obs([(0, 0), (100, 0), (200, 0)], quality="marker_not_found"), serial(), "r")
    assert res.outcome.value == "inconclusive"
    assert facts(res)["physical_motion"] == "unknown"


def test_no_ack_pattern_means_ack_unknown():
    res, _ = evaluate(exp(ack_pattern=None), obs([(0, 0), (500, 0), (900, 0)]), serial(), "r")
    assert facts(res)["command_acknowledged"] == "unknown"


def toggle_exp(**kw):
    return led_exp(trigger=ExpectationTrigger(kind="configured_serial_command", value="FLICKER"),
                   pattern="toggle", min_transitions=4, **kw)


def test_toggle_passes_when_led_oscillates():
    """A flickering LED fails a steady check but passes a toggle check (D-053)."""
    points = [(0, 0), (200, 1), (400, 0), (600, 1), (800, 0), (1000, 1)]
    res, _ = evaluate(toggle_exp(), led_obs(points), serial("ACK FLICKER", tx="FLICKER"), "r")
    assert res.outcome.value == "pass"
    f = facts(res)
    assert f["state_transitions"] == "yes" and f["physical_state"] == "yes"
    # the same stream under a steady expectation ends at 1 — but a flicker that dies
    # mid-window must not read as "the light is on": these semantics differ by design


def test_toggle_fails_when_led_stays_on():
    """Stuck-on is not flicker — the command implied oscillation."""
    res, _ = evaluate(toggle_exp(), led_obs([(0, 0), (300, 1), (600, 1), (900, 1)]), serial("ACK FLICKER", tx="FLICKER"), "r")
    assert res.outcome.value == "fail"
    f = facts(res)
    assert f["state_transitions"] == "yes" and "1 change" in \
        res.facts[[x.key for x in res.facts].index("state_transitions")].note


def test_toggle_fails_when_led_never_moves():
    res, _ = evaluate(toggle_exp(), led_obs([(0, 0), (500, 0), (1000, 0)]), serial("ACK FLICKER", tx="FLICKER"), "r")
    assert res.outcome.value == "fail"
    assert facts(res)["first_response"] == "no"


def test_proposal_marks_oscillate_commands_toggle():
    """Command literals like FLICKER/BLINK get a toggle pattern at proposal time."""
    from integreat.diagnostics.expectations import propose_expectation
    from integreat.models import Evidence, EvidenceKind, Epistemic, GraphNode, NodeKind, Provenance, Verification
    nodes = [GraphNode(id="component:l1", project_id="p", kind=NodeKind.component, label="L1",
                       verification=Verification.verified, attributes={"type": "led"})]
    ev = Evidence(id="e:1:cmd", project_id="p", kind=EvidenceKind.source_excerpt, epistemic=Epistemic.observed,
                  summary="serial literal", provenance=Provenance(source_id="x", file="a.ino", line_start=1),
                  payload={"literal": "FLICKER"})
    e = propose_expectation("p", nodes, [], [ev], ["ACK FLICKER"], component_id="component:l1")
    assert e is not None and e.pattern == "toggle" and e.trigger.value == "FLICKER"


def test_proposal_stays_steady_for_on_command():
    from integreat.diagnostics.expectations import propose_expectation
    from integreat.models import Evidence, EvidenceKind, Epistemic, GraphNode, NodeKind, Provenance, Verification
    nodes = [GraphNode(id="component:l1", project_id="p", kind=NodeKind.component, label="L1",
                       verification=Verification.verified, attributes={"type": "led"})]
    ev = Evidence(id="e:1:cmd", project_id="p", kind=EvidenceKind.source_excerpt, epistemic=Epistemic.observed,
                  summary="serial literal", provenance=Provenance(source_id="x", file="a.ino", line_start=1),
                  payload={"literal": "LED ON"})
    e = propose_expectation("p", nodes, [], [ev], ["ACK LED ON"], component_id="component:l1")
    assert e is not None and e.pattern == "steady"
