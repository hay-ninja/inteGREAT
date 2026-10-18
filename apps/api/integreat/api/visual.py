"""Observation-only visual LED checks, persisted with calibration and evidence."""
import asyncio
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Request

from ..models import (Evidence, EvidenceKind, Epistemic, Provenance, VisualCaptureRequest,
    VisualReference, VisualConfigRequest, VisualConfig, VisualRunRequest, VisualRun, VisualSample)
from ..observations.led_brightness import contrast, evaluate
from ..service import ServiceError

router = APIRouter(prefix="/api/v1/projects/{pid}/visual")


def uid(prefix):
    return f"{prefix}:{uuid.uuid4().hex[:12]}"


def current_frame(service):
    camera = service.devices.camera.source
    frame = camera.latest() if camera and camera.connected else None
    if frame is None or time.monotonic_ns() - frame.monotonic_ns > 500_000_000:
        raise ServiceError(409, "camera_unavailable", "A fresh camera frame is required (less than 500 ms old). Check camera/Wi-Fi.")
    if "sim" in camera.source_id.split(":") or getattr(camera, "synthetic", False):
        raise ServiceError(409, "visual_live_only", "LED checks require a real camera source")
    return camera, frame


@router.post("/references", response_model=VisualReference)
def capture(pid: str, body: VisualCaptureRequest, request: Request):
    s = request.app.state.service
    graph = s.graph(pid)
    if not any(n.id == body.component_id and n.attributes.get("type") == "led" for n in graph.nodes):
        raise ServiceError(422, "invalid_component", "Select an LED component in this project's graph")
    camera, frame = current_frame(s)
    try:
        value, background = contrast(frame.image, body.region)
    except ValueError as exc:
        raise ServiceError(422, "invalid_region", str(exc)) from exc
    eid = uid("evidence:visual_reference")
    ref = VisualReference(id=uid("visual_reference"), project_id=pid, component_id=body.component_id,
        camera_id=camera.source_id, region=body.region, state=body.state, frame_width=frame.image.shape[1],
        frame_height=frame.image.shape[0], contrast=value, background=background, evidence_id=eid)
    s.store.put("evidence", Evidence(id=eid, project_id=pid, kind=EvidenceKind.cv_measurement,
        epistemic=Epistemic.observed, summary=f"LED region contrast {value:.1f}; engineer labeled this {body.state}",
        provenance=Provenance(source_id=camera.source_id, captured_at_utc=frame.host_time_utc, monotonic_ns=frame.monotonic_ns),
        payload={**ref.model_dump(mode="json"), "frame_seq": frame.seq, "raw_frame_saved": False}))
    s.store.put("visual_reference", ref)
    return ref


@router.post("/configs", response_model=VisualConfig)
def configure(pid: str, body: VisualConfigRequest, request: Request):
    s = request.app.state.service
    s.project(pid)
    if not body.confirmed:
        raise ServiceError(409, "confirmation_required", "Confirm the visual expectation before testing")
    refs = [s.store.get("visual_reference", rid, VisualReference) for rid in body.reference_ids]
    if any(r is None or r.project_id != pid for r in refs):
        raise ServiceError(404, "reference_not_found", "Calibration reference not found in this project")
    ids = list(dict.fromkeys(r.component_id for r in refs))
    if len(ids) != 2:
        raise ServiceError(422, "two_leds_required", "Select two separate LED components")
    camera, frame = current_frame(s)
    for cid in ids:
        pair = [r for r in refs if r.component_id == cid]
        if len(pair) != 2 or {r.state for r in pair} != {"on", "off"}:
            raise ServiceError(422, "calibration_invalid", "Each LED needs an off and an on reference")
        off, on = sorted(pair, key=lambda r: r.state)
        if (off.region != on.region or on.contrast - off.contrast < 15
                or abs(on.background - off.background) > 25):
            raise ServiceError(422, "calibration_invalid", "Use the same region and stable lighting; the on reference must be clearly brighter than off")
        if any(r.camera_id != camera.source_id or (r.frame_height, r.frame_width) != frame.image.shape[:2] for r in pair):
            raise ServiceError(409, "calibration_stale", "Camera changed; capture new references")
    regions = [next(r.region for r in refs if r.component_id == cid) for cid in ids]
    a, b = regions
    if max(a.x, b.x) < min(a.x + a.width, b.x + b.width) and max(a.y, b.y) < min(a.y + a.height, b.y + b.height):
        raise ServiceError(422, "overlapping_regions", "LED regions must not overlap")
    eid = uid("evidence:visual_expectation")
    config = VisualConfig(id=uid("visual_config"), project_id=pid, references=refs, duration_ms=body.duration_ms, evidence_id=eid)
    s.store.put("visual_config", config)
    s.store.put("evidence", Evidence(id=eid, project_id=pid, kind=EvidenceKind.engineer_assertion,
        epistemic=Epistemic.verified, summary=f"Engineer confirmed: both LEDs dim and brighten in separate alternating phases within {body.duration_ms} ms",
        provenance=Provenance(source_id="engineer"), payload={"config": config.model_dump(mode="json"),
            "thresholds": {"dim_max": 0.25, "bright_min": 0.75, "min_frames_per_state": 2, "max_gap_ms": 750}}))
    return config


@router.get("/configs", response_model=list[VisualConfig])
def configs(pid: str, request: Request):
    s = request.app.state.service
    s.project(pid)
    return s.store.list("visual_config", VisualConfig, project_id=pid)


@router.get("/runs", response_model=list[VisualRun])
def runs(pid: str, request: Request):
    s = request.app.state.service
    s.project(pid)
    history = s.store.list("visual_run", VisualRun, project_id=pid)
    for run in history:
        if run.state == "running" and not getattr(s, "visual_active", False):
            run.state, run.outcome = "failed", "inconclusive"
            run.summary = "Observation interrupted by server restart; no hardware conclusion. Start a new observation."
            s.store.put("visual_run", run)
    return history


@router.post("/runs", response_model=VisualRun)
async def start(pid: str, body: VisualRunRequest, request: Request, bg: BackgroundTasks):
    s = request.app.state.service
    s.project(pid)
    config = s.store.get("visual_config", body.config_id, VisualConfig)
    if config is None or config.project_id != pid:
        raise ServiceError(404, "config_not_found", "Visual configuration not found")
    camera, frame = current_frame(s)
    if any(r.camera_id != camera.source_id or (r.frame_height, r.frame_width) != frame.image.shape[:2] for r in config.references):
        raise ServiceError(409, "calibration_stale", "Camera changed; recalibrate before testing")
    prior = None
    if body.verifies_run_id:
        prior = s.store.get("visual_run", body.verifies_run_id, VisualRun)
        if prior is None or prior.project_id != pid or prior.config_id != config.id or prior.state != "completed" or prior.outcome != "fail" or prior.resolved_by_run_id:
            raise ServiceError(409, "verification_invalid", "Verify an unresolved failed run using the same confirmed configuration")
    if getattr(s, "visual_active", False):
        raise ServiceError(409, "visual_busy", "A visual observation is already running")
    s.visual_active = True
    graph = s.graph(pid)
    selected = {r.component_id for r in config.references}
    context_ids = [eid for n in graph.nodes if n.id in selected for eid in n.evidence_ids]
    context_ids += [eid for edge in graph.edges if edge.relation.value in ("configures", "connected_to") for eid in edge.evidence_ids]
    context_ids = [e.id for e in s.evidence(context_ids) if e.kind in
        (EvidenceKind.source_excerpt, EvidenceKind.manifest_entry, EvidenceKind.netlist_entry, EvidenceKind.engineer_assertion)]
    run = VisualRun(id=uid("visual_run"), project_id=pid, config_id=config.id, source_id=camera.source_id,
        verifies_run_id=prior.id if prior else None, evidence_ids=list(dict.fromkeys([config.evidence_id,
            *[r.evidence_id for r in config.references], *context_ids])))
    s.store.put("visual_run", run)
    s._emit("visual.started", pid, {"run_id": run.id})
    bg.add_task(observe, s, config, run, camera)
    return run


async def observe(s, config, run, camera):
    with s.telemetry.operation("visual.observe") as state:
        await _observe(s, config, run, camera)
        state["outcome"] = run.outcome


async def _observe(s, config, run, camera):
    ids = list(dict.fromkeys(r.component_id for r in config.references))
    pairs = {cid: {r.state: r for r in config.references if r.component_id == cid} for cid in ids}
    t0, seq = time.monotonic_ns(), -1
    try:
        while (elapsed := (time.monotonic_ns() - t0) // 1_000_000) <= config.duration_ms:
            frame = camera.latest() if camera.connected and s.devices.camera.source is camera else None
            if frame is not None and frame.seq != seq and time.monotonic_ns() - frame.monotonic_ns < 500_000_000:
                seq = frame.seq
                for cid in ids:
                    off, on = pairs[cid]["off"], pairs[cid]["on"]
                    value, quality = None, "unavailable"
                    if frame.image.shape[:2] == (off.frame_height, off.frame_width):
                        contrast_value, background = contrast(frame.image, off.region)
                        if abs(background - off.background) <= 25:
                            value = round((contrast_value - off.contrast) / (on.contrast - off.contrast), 3)
                            quality = "valid"
                    eid = uid("evidence:led_brightness")
                    sample = VisualSample(component_id=cid, elapsed_ms=elapsed, brightness=value, quality=quality, evidence_id=eid)
                    run.samples.append(sample)
                    run.evidence_ids.append(eid)
                    s.store.put("evidence", Evidence(id=eid, project_id=run.project_id, kind=EvidenceKind.cv_measurement,
                        epistemic=Epistemic.observed if quality == "valid" else Epistemic.unknown,
                        summary=f"{cid}: normalized visible brightness {value} ({quality})",
                        provenance=Provenance(source_id=camera.source_id, captured_at_utc=frame.host_time_utc, monotonic_ns=frame.monotonic_ns),
                        payload={**sample.model_dump(mode="json"), "frame_seq": frame.seq, "raw_frame_saved": False}))
            await asyncio.sleep(0.15)
        run.outcome, run.checks, run.summary = evaluate(run.samples, ids, config.duration_ms)
        run.state = "completed"
        eid = uid("evidence:visual_result")
        s.store.put("evidence", Evidence(id=eid, project_id=run.project_id, kind=EvidenceKind.rule_result,
            epistemic=Epistemic.inferred, summary=run.summary, provenance=Provenance(source_id="led_visual_evaluator"),
            payload={"run_id": run.id, "outcome": run.outcome, "checks": run.checks, "supporting_evidence_ids": list(run.evidence_ids)}))
        run.evidence_ids.append(eid)
        graph = s.graph(run.project_id)
        for node in graph.nodes:
            if node.id in ids:
                values = [v.brightness for v in run.samples if v.component_id == node.id and v.brightness is not None]
                check = run.checks[node.id]
                node_outcome = ("inconclusive" if check.startswith("Measurement unavailable") else
                    "pass" if check.startswith("Calibrated dim") else "fail")
                node.attributes.update({"obs_metric": "led_brightness", "obs_value": values[-1] if values else None,
                    "obs_outcome": node_outcome, "obs_quality": check, "obs_run_id": run.id, "obs_evidence_id": eid})
                node.evidence_ids.append(eid)
        s.store.put("graph", graph)
        s._emit("graph.updated", run.project_id, {"visual_run_id": run.id})
        if run.verifies_run_id and run.outcome == "pass":
            original = s.store.get("visual_run", run.verifies_run_id, VisualRun)
            original.resolved_by_run_id = run.id
            s.store.put("visual_run", original)
    except Exception as exc:
        run.state, run.outcome = "failed", "inconclusive"
        run.summary = f"Visual observation interrupted ({type(exc).__name__}); no hardware conclusion."
    finally:
        s.store.put("visual_run", run)
        s.visual_active = False
        s._emit("visual.completed", run.project_id, {"run_id": run.id, "outcome": run.outcome})
