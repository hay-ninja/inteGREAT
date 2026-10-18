"""REST + WebSocket routes under /api/v1 (PRD §15). Thin: all logic lives in the service layer."""

from __future__ import annotations

import asyncio

import cv2
from fastapi import APIRouter, BackgroundTasks, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse

from ..models import (
    ActionResult,
    AgentStatus,
    CalibrateRequest,
    CameraConnectRequest,
    DemoFixture,
    DeviceStatus,
    EventFlow,
    Evidence,
    ExecuteActionRequest,
    Expectation,
    ExpectationEdit,
    GraphSnapshot,
    ImportRequest,
    Incident,
    IntegreatEvent,
    InvestigationView,
    ManualResultRequest,
    MessageRequest,
    Model,
    NetlistPreview,
    NetlistPreviewRequest,
    Observation,
    PermissionGrant,
    PermissionUpdate,
    Project,
    ProjectUpdate,
    ReplayInfo,
    RepairJob,
    RepairPreflight,
    RepairRequest,
    SaveReplayRequest,
    SerialConnectRequest,
    SerialEvent,
    StartTestRequest,
    Subsystem,
    TestRun,
    ToolInfo,
    WiringVerificationRequest,
)
from ..observations.camera_adapter import CameraError, probe_cameras
from ..observations.cv_angle import annotate
from ..observations.serial_adapter import SerialError
from ..service import Service, ServiceError
from ..tools.registry import RISKY_CATEGORIES, list_tools

router = APIRouter(prefix="/api/v1")


def svc(request: Request) -> Service:
    return request.app.state.service


class TestRunDetail(Model):
    __test__ = False
    run: TestRun
    observations: list[Observation]
    serial: list[SerialEvent]


class ActionExecution(Model):
    result: ActionResult


class SourceOptions(Model):
    replays: list[ReplayInfo]
    sim: list[ReplayInfo]


class DemoInfo(Model):
    fixtures: list[DemoFixture]
    netlist_path: str


# ---------------------------------------------------------------- meta


@router.get("/demo-fixtures", response_model=list[DemoFixture])
def demo_fixtures(request: Request):
    return svc(request).demo_fixtures()


@router.get("/demo", response_model=DemoInfo)
def demo_info(request: Request):
    s = svc(request)
    return DemoInfo(fixtures=s.demo_fixtures(), netlist_path=s.demo_netlist())


@router.get("/replays", response_model=list[ReplayInfo])
def replays(request: Request):
    return svc(request).replays()


@router.get("/sources", response_model=SourceOptions)
def sources(request: Request):
    s = svc(request)
    return SourceOptions(replays=s.replays(), sim=s.sim_scenarios())


@router.get("/tools", response_model=list[ToolInfo])
def tools():
    return [ToolInfo(name=t.name, permission_category=t.permission_category, is_read_only=t.is_read_only,
                     available=t.available and t.is_read_only and t.permission_category not in RISKY_CATEGORIES,
                     description=t.description, args_schema=t.args_model.model_json_schema()) for t in list_tools()]


@router.get("/agents/status", response_model=AgentStatus)
def agents_status(request: Request):
    return svc(request).agent_status()


# ---------------------------------------------------------------- projects


@router.post("/netlist/preview", response_model=NetlistPreview)
def netlist_preview(req: NetlistPreviewRequest, request: Request):
    return svc(request).netlist_preview(req)


@router.post("/projects/import", response_model=Project)
def import_project(req: ImportRequest, request: Request):
    return svc(request).import_project(req)


@router.get("/projects", response_model=list[Project])
def list_projects(request: Request):
    return svc(request).list_projects()


@router.get("/projects/{pid}", response_model=Project)
def get_project(pid: str, request: Request):
    return svc(request).project(pid)


@router.post("/projects/{pid}/rescan", response_model=Project)
def rescan(pid: str, request: Request):
    return svc(request).rescan(pid)


@router.patch("/projects/{pid}", response_model=Project)
def update_project(pid: str, req: ProjectUpdate, request: Request):
    return svc(request).update_project(pid, req)


@router.delete("/projects/{pid}", status_code=204)
def delete_project(pid: str, request: Request):
    svc(request).delete_project(pid)
    return Response(status_code=204)


@router.get("/projects/{pid}/graph", response_model=GraphSnapshot)
def get_graph(pid: str, request: Request, scope_node_id: str | None = None, depth: int = Query(2, ge=0, le=5)):
    return svc(request).graph(pid, scope_node_id, depth)


@router.patch("/projects/{pid}/graph/verification", response_model=Project)
def verify_wiring(pid: str, req: WiringVerificationRequest, request: Request):
    return svc(request).verify_wiring(pid, req)


@router.get("/projects/{pid}/subsystems", response_model=list[Subsystem])
def get_subsystems(pid: str, request: Request):
    return svc(request).subsystems(pid)


@router.get("/projects/{pid}/evidence", response_model=list[Evidence])
def get_evidence(pid: str, request: Request, ids: list[str] = Query(default=[], max_length=200)):
    s = svc(request)
    s.project(pid)
    return [e for e in s.evidence(ids) if e.project_id == pid]


@router.get("/projects/{pid}/devices", response_model=DeviceStatus)
def project_devices(pid: str, request: Request):
    s = svc(request)
    s.project(pid)
    return s.devices.status()


@router.get("/projects/{pid}/expectations", response_model=list[Expectation])
def list_expectations(pid: str, request: Request):
    return svc(request).list_expectations(pid)


@router.post("/projects/{pid}/expectations/propose", response_model=Expectation)
def propose_expectation(pid: str, request: Request):
    return svc(request).propose_expectation(pid)


@router.post("/projects/{pid}/expectations/{eid}/confirm", response_model=Expectation)
def confirm_expectation(pid: str, eid: str, edit: ExpectationEdit, request: Request):
    return svc(request).confirm_expectation(pid, eid, edit)


@router.post("/projects/{pid}/tests", response_model=TestRun)
def start_test(pid: str, req: StartTestRequest, request: Request, bg: BackgroundTasks):
    s = svc(request)
    run = s.create_test_run(pid, req)
    bg.add_task(s.execute_test_run, run.id)
    return run


@router.get("/projects/{pid}/incidents", response_model=list[Incident])
def list_incidents(pid: str, request: Request):
    return svc(request).list_incidents(pid)


@router.get("/projects/{pid}/events", response_model=list[IntegreatEvent])
def list_events(pid: str, request: Request, after_seq: int = 0):
    s = svc(request)
    s.project(pid)
    return s.store.events(pid, after_seq)


# ---------------------------------------------------------------- tests


@router.get("/tests/{run_id}", response_model=TestRunDetail)
def get_test(run_id: str, request: Request):
    s = svc(request)
    obs, serial = s.test_data(run_id)
    return TestRunDetail(run=s.test_run(run_id), observations=obs, serial=serial)


@router.post("/tests/{run_id}/verify", response_model=TestRun)
async def verify_test(run_id: str, request: Request, bg: BackgroundTasks):
    """PRD §15 alias: rerun the incident's verify action for the incident this run opened."""
    s = svc(request)
    run = s.test_run(run_id)
    if not run.incident_id:
        raise ServiceError(409, "no_incident", "this run did not open an incident")
    inc = s.incident(run.incident_id)
    action_id = next(a for a in inc.action_ids if a.endswith(":verify_fix"))
    _, new_run = await s.execute_action(inc.id, action_id, None)
    bg.add_task(s.execute_test_run, new_run.id)
    return new_run


@router.post("/tests/{run_id}/save-replay", response_model=ReplayInfo)
def save_replay(run_id: str, req: SaveReplayRequest, request: Request):
    return svc(request).save_replay(run_id, req.name)


@router.get("/tests/{run_id}/flow", response_model=EventFlow)
def test_flow(run_id: str, request: Request):
    """Chronological hardware/software event flow for one persisted run (D-024)."""
    return svc(request).event_flow(run_id)


# ---------------------------------------------------------------- investigations


@router.get("/investigations/{iid}", response_model=InvestigationView)
def get_investigation(iid: str, request: Request):
    return svc(request).investigation(iid)


@router.post("/investigations/{iid}/actions/{action_id}/execute", response_model=ActionExecution)
async def execute_action(iid: str, action_id: str, body: ExecuteActionRequest, request: Request, bg: BackgroundTasks):
    s = svc(request)
    result, run = await s.execute_action(iid, action_id, body.source, body.approve_once)
    if run is not None:
        bg.add_task(s.execute_test_run, run.id)
    return ActionExecution(result=result)


@router.post("/investigations/{iid}/manual-results", response_model=InvestigationView)
def manual_result(iid: str, req: ManualResultRequest, request: Request):
    return svc(request).record_manual_result(iid, req)


@router.post("/investigations/{iid}/messages", response_model=InvestigationView)
def add_message(iid: str, req: MessageRequest, request: Request):
    return svc(request).add_message(iid, req.text)


@router.get("/investigations/{iid}/permissions", response_model=list[PermissionGrant])
def get_permissions(iid: str, request: Request):
    s = svc(request)
    s.incident(iid)
    return s.tools.permissions.active(iid)


@router.post("/investigations/{iid}/permissions", response_model=list[PermissionGrant])
def set_permission(iid: str, req: PermissionUpdate, request: Request):
    return svc(request).set_permission(iid, req.category, req.granted)


@router.post("/investigations/{iid}/diagnose", response_model=Incident)
def diagnose(iid: str, request: Request, bg: BackgroundTasks):
    s = svc(request)
    inc = s.begin_diagnosis(iid)
    bg.add_task(s.run_diagnosis, iid)
    return inc


# ---------------------------------------------------------------- remote repair (D-025)


@router.get("/investigations/{iid}/repairs/preflight", response_model=RepairPreflight)
def repair_preflight(iid: str, request: Request):
    """What a repair request would need — precise missing prerequisites, never a guess."""
    return svc(request).repair_preflight(iid)


@router.get("/investigations/{iid}/repairs", response_model=list[RepairJob])
def repair_jobs(iid: str, request: Request):
    return svc(request).repair_jobs(iid)


@router.post("/investigations/{iid}/repairs", response_model=RepairJob)
async def request_repair(iid: str, req: RepairRequest, request: Request):
    """Engineer-initiated remote repair request (Devin). Non-idempotent: never auto-retried."""
    return await svc(request).request_repair(iid, req)


@router.post("/repairs/{job_id}/refresh", response_model=RepairJob)
async def refresh_repair(job_id: str, request: Request):
    """Poll remote status (GET only — polling never creates a session)."""
    return await svc(request).refresh_repair(job_id)


# ---------------------------------------------------------------- devices (global: the laptop's ports)


@router.get("/devices", response_model=DeviceStatus)
def devices(request: Request):
    return svc(request).devices.status()


@router.post("/devices/serial/connect", response_model=DeviceStatus)
async def serial_connect(req: SerialConnectRequest, request: Request):
    d = svc(request).devices
    try:
        await asyncio.to_thread(d.serial.connect, req.port, req.baud)
    except SerialError as e:
        raise ServiceError(409, "serial_error", str(e)) from e
    return d.status()


@router.post("/devices/serial/release", response_model=DeviceStatus)
async def serial_release(request: Request):
    d = svc(request).devices
    await asyncio.to_thread(d.serial.release)
    return d.status()


@router.get("/devices/camera/probe", response_model=list[int])
async def camera_probe():
    return await asyncio.to_thread(probe_cameras)


@router.post("/devices/camera/connect", response_model=DeviceStatus)
async def camera_connect(req: CameraConnectRequest, request: Request):
    d = svc(request).devices
    try:
        await asyncio.to_thread(d.camera.connect, req.index)
    except CameraError as e:
        raise ServiceError(409, "camera_error", str(e)) from e
    return d.status()


@router.post("/devices/camera/release", response_model=DeviceStatus)
async def camera_release(request: Request):
    d = svc(request).devices
    await asyncio.to_thread(d.camera.release)
    return d.status()


@router.post("/devices/camera/calibrate", response_model=DeviceStatus)
def camera_calibrate(req: CalibrateRequest, request: Request):
    d = svc(request).devices
    try:
        d.camera.calibrate(req.known_angle_deg)
    except (CameraError, ValueError) as e:
        raise ServiceError(409, "calibration_failed", str(e)) from e
    return d.status()


def _jpeg(d) -> bytes | None:
    f = d.camera.source.latest() if d.camera.connected else None
    if f is None:
        return None
    est = d.camera.estimator().estimate(f.image)
    ok, buf = cv2.imencode(".jpg", annotate(f.image, est), [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ok else None


@router.get("/devices/camera/frame.jpg")
def camera_frame(request: Request):
    data = _jpeg(svc(request).devices)
    if data is None:
        raise ServiceError(409, "camera_unavailable", "no camera frame available")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/devices/camera/stream.mjpg")
async def camera_stream(request: Request):
    d = svc(request).devices
    if not d.camera.connected:
        raise ServiceError(409, "camera_unavailable", "no camera connected")

    async def gen():
        while not await request.is_disconnected() and d.camera.connected:
            data = await asyncio.to_thread(_jpeg, d)
            if data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
            await asyncio.sleep(1 / 12)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------------------------------------------------------------- websocket


@router.websocket("/ws/projects/{pid}")
async def ws_project(ws: WebSocket, pid: str, after_seq: int = 0):
    s: Service = ws.app.state.service
    await ws.accept()
    q = s.hub.subscribe(pid)
    try:
        last = after_seq
        for ev in s.store.events(pid, after_seq):  # catch up from the persisted timeline
            await ws.send_text(ev.model_dump_json())
            last = ev.seq
        while True:
            ev = await q.get()
            if ev.seq > last:
                await ws.send_text(ev.model_dump_json())
                last = ev.seq
    except WebSocketDisconnect:
        pass
    finally:
        s.hub.unsubscribe(pid, q)
