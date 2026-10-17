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


def serial(*lines):
    out = [SerialEvent(id="s0", project_id="p", test_run_id="r", direction="tx", timestamp_utc=T0, elapsed_ms=0,
                       raw="MOVE 90", evidence_id="ehost")]
    out += [SerialEvent(id=f"s{i + 1}", project_id="p", test_run_id="r", direction="rx", timestamp_utc=T0,
                        elapsed_ms=40, raw=line, evidence_id=f"eser{i}") for i, line in enumerate(lines)]
    return out


def facts(res):
    return {f.key: f.value for f in res.facts}


def test_pass_when_settled_within_tolerance():
    res, ev = evaluate(exp(), obs([(0, 0), (500, 60), (1000, 88), (1500, 89)]), serial("ACK MOVE 90"), "r")
    assert res.outcome.value == "pass"
    assert facts(res) == {"command_sent": "yes", "command_acknowledged": "yes", "physical_motion": "yes"}
    assert ev.id == res.evidence_id


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
