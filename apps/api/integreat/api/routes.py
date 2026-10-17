"""REST + WebSocket routes under /api/v1 (PRD §15). Thin: all logic is in service.py."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query, Request, WebSocket, WebSocketDisconnect

from ..models import (
    ActionResult,
    ExecuteActionRequest,
    Expectation,
    ExpectationEdit,
    GraphSnapshot,
    ImportRequest,
    Incident,
    IntegreatEvent,
    InvestigationView,
    ManualResultRequest,
    DemoFixture,
    Evidence,
    Model,
    Observation,
    Project,
    ReplayInfo,
    SerialEvent,
    StartTestRequest,
    Subsystem,
    TestRun,
)
from ..service import Service

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


@router.get("/demo-fixtures", response_model=list[DemoFixture])
def demo_fixtures(request: Request):
    return svc(request).demo_fixtures()


@router.get("/projects/{pid}/evidence", response_model=list[Evidence])
def get_evidence(pid: str, request: Request, ids: list[str] = Query(default=[], max_length=200)):
    s = svc(request)
    s.project(pid)
    return [e for e in s.evidence(ids) if e.project_id == pid]


@router.get("/replays", response_model=list[ReplayInfo])
def replays(request: Request):
    return svc(request).replays()


@router.post("/projects/import", response_model=Project)
def import_project(req: ImportRequest, request: Request):
    return svc(request).import_project(req)


@router.get("/projects", response_model=list[Project])
def list_projects(request: Request):
    return svc(request).list_projects()


@router.get("/projects/{pid}", response_model=Project)
def get_project(pid: str, request: Request):
    return svc(request).project(pid)


@router.get("/projects/{pid}/graph", response_model=GraphSnapshot)
def get_graph(pid: str, request: Request, scope_node_id: str | None = None, depth: int = Query(2, ge=0, le=5)):
    return svc(request).graph(pid, scope_node_id, depth)


@router.get("/projects/{pid}/subsystems", response_model=list[Subsystem])
def get_subsystems(pid: str, request: Request):
    return svc(request).subsystems(pid)


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


@router.get("/tests/{run_id}", response_model=TestRunDetail)
def get_test(run_id: str, request: Request):
    s = svc(request)
    obs, serial = s.test_data(run_id)
    return TestRunDetail(run=s.test_run(run_id), observations=obs, serial=serial)


@router.get("/investigations/{iid}", response_model=InvestigationView)
def get_investigation(iid: str, request: Request):
    return svc(request).investigation(iid)


@router.post("/investigations/{iid}/actions/{action_id}/execute", response_model=ActionExecution)
def execute_action(iid: str, action_id: str, body: ExecuteActionRequest, request: Request, bg: BackgroundTasks):
    s = svc(request)
    result, run = s.execute_action(iid, action_id, body.source)
    if run is not None:
        bg.add_task(s.execute_test_run, run.id)
    return ActionExecution(result=result)


@router.post("/investigations/{iid}/manual-results", response_model=InvestigationView)
def manual_result(iid: str, req: ManualResultRequest, request: Request):
    return svc(request).record_manual_result(iid, req)


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
