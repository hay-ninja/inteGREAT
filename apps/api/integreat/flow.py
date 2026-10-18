"""Event flow projection (D-024): a chronological, lane-based view of ONE persisted test run.

Derived deterministically from persisted records (serial events, observations, run result, timeline
events) — never fabricated, never reordered beyond what timestamps + stable insertion order support.
Cross-source ordering is host-clock correlated, NOT synchronized; ordering alone is not causation.
Aggregated camera segments keep their underlying observation ids so evidence is never hidden.
"""

from __future__ import annotations

from .models import (
    EventFlow,
    Expectation,
    FlowEvent,
    FlowEventKind,
    FlowLane,
    IntegreatEvent,
    Observation,
    SerialEvent,
    TestRun,
)

QUALITY_LABEL = {
    "valid": "valid angle measurement",
    "marker_not_found": "marker not visible",
    "calibration_invalid": "calibration invalid",
    "dropped": "frame dropped",
}


def build_event_flow(run: TestRun, exp: Expectation | None, obs: list[Observation],
                     serial: list[SerialEvent], timeline: list[IntegreatEvent]) -> EventFlow:
    items: list[FlowEvent] = []
    gaps: list[str] = []
    order = 0

    def add(**kw) -> None:
        nonlocal order
        order += 1
        items.append(FlowEvent(id=f"flow:{run.id}:{order}", test_run_id=run.id, order=order, **kw))

    tx = sorted([s for s in serial if s.direction == "tx"], key=lambda s: s.elapsed_ms)
    rx = sorted([s for s in serial if s.direction == "rx"], key=lambda s: s.elapsed_ms)
    obs = sorted(obs, key=lambda o: o.elapsed_ms)

    # ---------------------------------------------------------------- command lane
    if exp is not None and exp.trigger.kind == "configured_serial_command":
        if tx:
            for s in tx:
                add(lane=FlowLane.command, kind=FlowEventKind.command_sent,
                    label=f'Host sent "{s.raw}"', timestamp_utc=s.timestamp_utc, elapsed_ms=s.elapsed_ms,
                    evidence_ids=[s.evidence_id])
        else:
            add(lane=FlowLane.command, kind=FlowEventKind.command_sent, state="expected",
                label=f'Configured command "{exp.trigger.value}" was never recorded as sent',
                elapsed_ms=0,
                note="The run may have been triggered another way, or the send was not captured.")
            gaps.append("no host command recorded for a configured serial command")
    else:
        add(lane=FlowLane.command, kind=FlowEventKind.external_trigger,
            label="Engineer started the motion sequence",
            timestamp_utc=run.started_at_utc, elapsed_ms=None,
            note="External trigger: there is no host command record; t=0 is the run start.")

    # ---------------------------------------------------------------- software lane (serial)
    for s in rx:
        matched = list(s.matched_function_ids)
        add(lane=FlowLane.software, kind=FlowEventKind.serial_rx, label=s.raw,
            detail=f"Firmware serial line at +{s.elapsed_ms} ms",
            timestamp_utc=s.timestamp_utc, elapsed_ms=s.elapsed_ms,
            evidence_ids=[s.evidence_id], related_node_ids=matched,
            note=("matches a Serial.print literal in the listed function(s) — an association with "
                  "the log message, not a complete function execution trace") if matched else None)
    if exp is not None and exp.ack_pattern:
        acked = any(s.raw.startswith(exp.ack_pattern) for s in rx)
        if not acked:
            add(lane=FlowLane.software, kind=FlowEventKind.missing_ack, state="expected",
                label=f'Firmware acknowledgement "{exp.ack_pattern}" not observed',
                elapsed_ms=exp.deadline_ms,
                note="Absence of an ACK is not proof the firmware failed — it may not have logged.")
            gaps.append(f'firmware acknowledgement "{exp.ack_pattern}" not observed')
    elif exp is not None:
        gaps.append("no acknowledgement pattern configured — software acknowledgement is unknown")

    # ---------------------------------------------------------------- hardware lane (camera)
    if not obs:
        gaps.append("no camera observations recorded for this run")
    seg: list[Observation] = []
    for o in obs:
        if seg and o.measurement_quality != seg[-1].measurement_quality:
            _flush_segment(add, seg)
            seg = []
        seg.append(o)
    if seg:
        _flush_segment(add, seg)
    if not any(o.measurement_quality == "valid" for o in obs):
        gaps.append("no valid camera measurements — servo behavior cannot be judged")

    # ---------------------------------------------------------------- result lane
    if run.result is not None:
        r = run.result
        elapsed = None
        if run.started_at_utc and run.ended_at_utc:
            elapsed = int((run.ended_at_utc - run.started_at_utc).total_seconds() * 1000)
        add(lane=FlowLane.result, kind=FlowEventKind.evaluation,
            label=f"Expectation {r.outcome.value.upper()}: {r.reason}",
            timestamp_utc=run.ended_at_utc, elapsed_ms=elapsed, quality=r.outcome.value,
            evidence_ids=[r.evidence_id] + [i for f in r.facts for i in f.evidence_ids][:3],
            related_node_ids=[exp.component_id] if exp else [])
        if r.outcome.value == "inconclusive":
            gaps.append("inconclusive — not enough valid measurements to judge the expectation")

    for ev in timeline:
        if ev.test_run_id != run.id:
            continue
        if ev.type == "incident.created":
            add(lane=FlowLane.result, kind=FlowEventKind.incident_opened,
                label=f"Investigation opened: {ev.payload.get('title', 'incident')}",
                timestamp_utc=ev.timestamp_utc,
                elapsed_ms=_elapsed(run, ev), state="observed")
        elif ev.type == "test.verification_completed":
            add(lane=FlowLane.result, kind=FlowEventKind.run_completed,
                label=f"Verification {ev.payload.get('outcome', '').upper()}: "
                      f"{str(ev.payload.get('reason', ''))[:160]}",
                timestamp_utc=ev.timestamp_utc, elapsed_ms=_elapsed(run, ev))
        elif ev.type == "run.failed" or (ev.type == "error" and ev.test_run_id == run.id):
            add(lane=FlowLane.result, kind=FlowEventKind.run_completed,
                label=f"Run failed: {str(ev.payload.get('message', ''))[:160]}",
                timestamp_utc=ev.timestamp_utc, elapsed_ms=_elapsed(run, ev), quality="fail")

    items.sort(key=lambda e: (e.elapsed_ms is None, e.elapsed_ms if e.elapsed_ms is not None else 0, e.order))
    return EventFlow(
        run_id=run.id, project_id=run.project_id, attempt_kind=run.attempt_kind,
        run_state=run.state, source=run.source, synthetic=run.synthetic,
        correlation="host-clock correlated (not synchronized)",
        deadline_ms=exp.deadline_ms if exp else 0,
        lanes=[FlowLane.command, FlowLane.software, FlowLane.hardware, FlowLane.result],
        events=items, gaps=gaps)


def _elapsed(run: TestRun, ev: IntegreatEvent) -> int | None:
    if run.started_at_utc is None:
        return None
    return max(0, int((ev.timestamp_utc - run.started_at_utc).total_seconds() * 1000))


def _flush_segment(add, seg: list[Observation]) -> None:
    """Aggregate consecutive same-quality camera samples into ONE flow event. Underlying
    observation ids are preserved in `aggregated_ids` — aggregation never deletes evidence."""
    q = seg[-1].measurement_quality
    first, last = seg[0], seg[-1]
    if q == "valid":
        label = (f"Marker angle {first.value:g}° → {last.value:g}° "
                 f"({len(seg)} valid sample{'s' if len(seg) != 1 else ''})")
    else:
        label = f"{QUALITY_LABEL.get(q, q).capitalize()} ({len(seg)} sample{'s' if len(seg) != 1 else ''})"
    add(lane=FlowLane.hardware, kind=FlowEventKind.cv_segment, label=label,
        detail=f"Frames covering +{first.elapsed_ms}–{last.elapsed_ms} ms",
        timestamp_utc=first.timestamp_utc, elapsed_ms=first.elapsed_ms, elapsed_end_ms=last.elapsed_ms,
        quality=q, state="observed",
        evidence_ids=list(dict.fromkeys([first.evidence_id, last.evidence_id])),
        related_node_ids=[first.component_id],
        aggregated_ids=[o.id for o in seg],
        note="aggregated consecutive camera samples; individual measurements remain stored" if len(seg) > 1 else None)
