"""Application service: import → test → evaluate → incident → tools/actions → agents → verify.

Routes stay thin; orchestration and state transitions live here (and in tools/, agents/, observations/)
so they're testable without HTTP.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import timedelta
from pathlib import Path

from .agents.orchestrator import DiagnosisRefused, Orchestrator
from .agents.provider import GeminiProvider, LLMProvider, UnavailableProvider
from .agents.stepfun import StepFunProvider
from .api.ws import Hub
from .config import Settings
from .diagnostics import expectations as expmod
from .diagnostics import hypotheses as hypmod
from .diagnostics.causal import causal_chain
from .diagnostics.estimate import assess as shadow_assess, attach_verdicts
from .diagnostics.graph_state import reapply_run_state, record_run_state
from .diagnostics.rules import config_vs_wiring, run_rules
from .diagnostics.state_machine import InvalidTransition, check_incident, check_test
from .flow import build_event_flow
from .graph.builder import build_graph, consistency_issues, src_evidence_id
from .graph.query import scope as scope_graph
from .ingestion.arduino_parser import parse_project
from .ingestion.kicad_netlist import NetlistError, NetlistMapping, parse_netlist, propose_mapping, to_manifest
from .ingestion.manifest import ManifestError, load_manifest
from .ingestion.repository import RepoError, scan_repository
from .models import (
    ActionKind,
    ActionResult,
    AgentRun,
    AgentStatus,
    DemoFixture,
    DiagnosticAction,
    EdgeOrigin,
    Epistemic,
    EventFlow,
    Evidence,
    EvidenceKind,
    Expectation,
    ExpectationEdit,
    ExpectationOutcome,
    FaultCode,
    GraphSnapshot,
    Highlight,
    Hypothesis,
    HypothesisStatus,
    ImportIssue,
    ImportRequest,
    Incident,
    IncidentState,
    IntegreatEvent,
    InvestigationView,
    LogLiteral,
    ManualResultRequest,
    NetlistPreview,
    NetlistPreviewRequest,
    Observation,
    ObservationSourceSpec,
    Project,
    ProjectAnalysis,
    Provenance,
    ProviderStatus,
    ReplayInfo,
    RepairJob,
    RepairPreflight,
    RepairRequest,
    RepairResult,
    RepairState,
    RunRecording,
    SerialEvent,
    StartTestRequest,
    Subsystem,
    TestRun,
    TestRunState,
    Verification,
    WiringVerificationRequest,
    utcnow,
)
from .repair import (REPAIR_OUTPUT_SCHEMA, DevinClientProtocol, DevinUnavailable, SessionGone,
                     build_brief,
                     make_devin, map_remote_state, repo_snapshot)
from .observations.cv_angle import ArucoAngleEstimator, render_scene
from .observations.cv_led import render_led_scene
from .observations.devices import DeviceManager
from .observations.live import LiveStream
from .observations.replay import ReplayError, ReplayEvent, list_replays, load_replay
from .observations.sim import SIM_SCENARIOS, SimCamera, SimRig, SimSerial, conditions_for
from .storage.db import Store
from .tools.executor import ToolDenied, ToolExecutor, ToolFailed
from .tools.registry import tool_args


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def _id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


# Document kinds in the store
K_PROJECT, K_GRAPH, K_SUBSYS, K_EVIDENCE, K_ANALYSIS = "project", "graph", "subsystem", "evidence", "analysis"
K_EXPECT, K_RUN, K_OBS, K_SERIAL = "expectation", "test_run", "observation", "serial_event"
K_INCIDENT, K_HYP, K_ACTION, K_RECORDING = "incident", "hypothesis", "action", "run_recording"
K_REPAIR = "repair_job"
MAX_REPAIR_ATTEMPTS = 5


def make_specialist_provider(settings: Settings) -> LLMProvider:
    """Gemini supplies the Code / Hardware / Runtime-Vision specialists (D-023)."""
    if not settings.gemini_api_key:
        return UnavailableProvider("GEMINI_API_KEY not set")
    if not settings.gemini_model:
        return UnavailableProvider("INTEGREAT_GEMINI_MODEL not set (no model id is hardcoded)")
    try:
        return GeminiProvider(settings.gemini_api_key, settings.gemini_model)
    except Exception as e:  # noqa: BLE001
        return UnavailableProvider(f"Gemini client failed to start: {e}")


def make_orchestrator_provider(settings: Settings) -> LLMProvider:
    """StepFun performs triage + synthesis — the orchestration roles (D-023)."""
    if not settings.stepfun_api_key:
        return UnavailableProvider("STEP_API_KEY not set")
    try:
        return StepFunProvider(settings.stepfun_api_key, settings.stepfun_model, settings.stepfun_base_url)
    except Exception as e:  # noqa: BLE001
        return UnavailableProvider(f"StepFun client failed to start: {e}")


# Backwards-compat alias used by tests/scripts that build the old single-provider service.
make_provider = make_specialist_provider


class Service:
    def __init__(self, store: Store, settings: Settings, hub: Hub, llm: LLMProvider | None = None,
                 devices: DeviceManager | None = None,
                 orchestrator_llm: LLMProvider | None = None,
                 specialist_llm: LLMProvider | None = None,
                 devin: DevinClientProtocol | None = None):
        self.store, self.settings, self.hub = store, settings, hub
        self.devices = devices or DeviceManager()
        self.tools = ToolExecutor(self)
        # `llm` fills BOTH roles (test fakes); explicit role providers win (D-023).
        self.specialist_llm = specialist_llm or llm or make_specialist_provider(settings)
        self.orchestrator_llm = orchestrator_llm or llm or make_orchestrator_provider(settings)
        self.llm = self.specialist_llm  # compat for older callers
        self.devin = devin or make_devin(settings)
        self.orchestrator = Orchestrator(self)

    def _emit(self, type: str, project_id: str, payload: dict | None = None, **kw) -> None:
        self.hub.publish(IntegreatEvent(type=type, project_id=project_id, payload=payload or {}, **kw))

    def transition(self, inc: Incident, new: IncidentState) -> IncidentState:
        try:
            return check_incident(inc.state, new)
        except InvalidTransition as e:
            raise ServiceError(409, "invalid_state", str(e)) from e

    # ------------------------------------------------------------------ projects & graph

    def import_project(self, req: ImportRequest) -> Project:
        project = self._build(_id("project"), req, version=1, overrides={})
        self._emit("project.imported", project.id, {"name": project.name, "issues": len(project.issues)})
        return project

    def rescan(self, pid: str) -> Project:
        """Re-read the repository (e.g. after the engineer fixed firmware) into the SAME project.
        Graph version increments; engineer wiring confirmations are re-applied."""
        old = self.project(pid)
        req = ImportRequest(repo_path=old.repo_root, manifest_path=old.manifest_path, netlist_path=old.netlist_path,
                            netlist_mapping=old.netlist_mapping, name=old.name)
        project = self._build(pid, req, version=old.graph_version + 1, overrides=old.wiring_overrides,
                              created_at=old.created_at_utc)
        self._emit("graph.updated", pid, {"version": project.graph_version, "reason": "rescan"})
        return project

    def _load_hardware(self, req: ImportRequest, issues: list[ImportIssue]):
        """Returns (manifest, line map, file label, source kind). Netlist first if given; manifest fallback."""
        if req.netlist_path:
            try:
                nl = parse_netlist(req.netlist_path)
                if not req.netlist_mapping:
                    raise NetlistError("netlist mapping not confirmed; use /netlist/preview and confirm the mapping")
                mapping = NetlistMapping.model_validate(req.netlist_mapping)
                manifest, lines, warns = to_manifest(nl, mapping)
                issues += [ImportIssue(level="warning", code="NETLIST_WARNING", message=w) for w in warns]
                if mapping.proposed:
                    issues.append(ImportIssue(level="warning", code="NETLIST_MAPPING_UNCONFIRMED",
                                              message="Netlist role mapping was not confirmed by the engineer"))
                issues.append(ImportIssue(level="info", code="NETLIST_DECLARED_ONLY",
                                          message="Netlist connections describe the schematic, not verified wiring"))
                return manifest, lines, Path(req.netlist_path).name, "netlist"
            except (NetlistError, ManifestError, ValueError) as e:
                issues.append(ImportIssue(level="error", code="NETLIST_UNSUPPORTED",
                                          message=f"{e}" + (" — falling back to manifest" if req.manifest_path else "")))
        if req.manifest_path:
            try:
                manifest, _, lines = load_manifest(req.manifest_path)
                return manifest, lines, Path(req.manifest_path).name, "manifest"
            except ManifestError as e:
                issues.append(ImportIssue(level="error", code="MANIFEST_INVALID", message=str(e)))
        return None, {}, None, "none"

    def _build(self, pid: str, req: ImportRequest, version: int, overrides: dict, created_at=None) -> Project:
        try:
            scan = scan_repository(req.repo_path)
        except RepoError as e:
            raise ServiceError(400, "repo_invalid", str(e)) from e
        parsed = parse_project(scan.files)
        issues: list[ImportIssue] = [ImportIssue(level="info", code="FILE_SKIPPED", message=f"{rel}: {why}", file=rel)
                                     for rel, why in scan.skipped]
        manifest, lines, hw_file, hw_source = self._load_hardware(req, issues)
        built = build_graph(pid, [f.rel for f in scan.files], parsed, manifest, lines, hw_file, hardware_source=hw_source)

        # Rescan keeps identity: carry the latest run state forward onto rebuilt elements (D-019).
        old_g = self.store.get(K_GRAPH, pid, GraphSnapshot)
        if old_g is not None:
            reapply_run_state(old_g, built.nodes, built.edges)

        # Re-apply engineer wiring confirmations from earlier versions.
        if overrides:
            by_id = {e.id: e for e in built.edges}
            for eid, state in overrides.items():
                if eid in by_id and by_id[eid].origin == EdgeOrigin.declared_wiring:
                    by_id[eid].verification = Verification(state)
            built.issues = [i for i in built.issues if i.code != "GPIO_CONFIG_MISMATCH"]
            built.issues += consistency_issues(built.nodes, built.edges)
        issues += built.issues

        lit_ev, literals = [], []
        for lit in parsed.log_literals:
            eid = src_evidence_id(lit.file, lit.line, "log")
            lit_ev.append(Evidence(id=eid, project_id=pid, kind=EvidenceKind.source_excerpt, epistemic=Epistemic.observed,
                                   summary=f'Firmware prints "{lit.text}"',
                                   provenance=Provenance(source_id="repo", file=lit.file, line_start=lit.line, line_end=lit.line),
                                   payload={"literal": lit.text}))
            literals.append(LogLiteral(function_id=lit.function_id, text=lit.text, evidence_id=eid))

        project = Project(id=pid, name=req.name or scan.root.name, repo_root=str(scan.root),
                          manifest_path=req.manifest_path, issues=issues, file_count=len(scan.files),
                          graph_version=version, hardware_source=hw_source, netlist_path=req.netlist_path,
                          netlist_mapping=req.netlist_mapping, wiring_overrides=dict(overrides))
        if created_at:
            project.created_at_utc = created_at
        self.store.put(K_PROJECT, project)
        self.store.put(K_GRAPH, GraphSnapshot(project_id=pid, version=version, nodes=built.nodes, edges=built.edges))
        self.store.put(f"{K_GRAPH}_v{version}", GraphSnapshot(project_id=pid, version=version, nodes=built.nodes,
                                                            edges=built.edges))
        self.store.put_many(K_SUBSYS, built.subsystems, parent_id=pid)
        self.store.put_many(K_EVIDENCE, built.evidence + lit_ev)
        self.store.put(K_ANALYSIS, ProjectAnalysis(id=pid, project_id=pid, log_literals=literals))
        return project

    def netlist_preview(self, req: NetlistPreviewRequest) -> NetlistPreview:
        try:
            nl = parse_netlist(req.netlist_path)
            stems = []
            if req.repo_path:
                try:
                    stems = sorted({Path(f.rel).stem for f in scan_repository(req.repo_path).files
                                    if not f.rel.endswith(".ino")})
                except RepoError:
                    stems = []
            mapping = propose_mapping(nl, stems)
            _, _, warns = to_manifest(nl, mapping)
        except (NetlistError, ManifestError, ValueError) as e:
            raise ServiceError(400, "netlist_unsupported", str(e)) from e
        return NetlistPreview(file=nl.file, components=[c.model_dump() for c in nl.components],
                              nets=[n.model_dump() for n in nl.nets], proposed_mapping=mapping.model_dump(),
                              warnings=warns)

    def project(self, pid: str) -> Project:
        p = self.store.get(K_PROJECT, pid, Project)
        if p is None:
            raise ServiceError(404, "not_found", f"project {pid} not found")
        return p

    def list_projects(self) -> list[Project]:
        return self.store.list(K_PROJECT, Project)

    def graph(self, pid: str, scope_node_id: str | None = None, depth: int = 2) -> GraphSnapshot:
        self.project(pid)
        g = self.store.get(K_GRAPH, pid, GraphSnapshot)
        if scope_node_id:
            try:
                return scope_graph(g, scope_node_id, depth)
            except KeyError as e:
                raise ServiceError(404, "not_found", f"node {scope_node_id} not in graph") from e
        return g

    def verify_wiring(self, pid: str, req: WiringVerificationRequest) -> Project:
        """Engineer confirms/un-confirms a declared connection (PRD §5.1 step 5, FR-02)."""
        project = self.project(pid)
        g = self.store.get(K_GRAPH, pid, GraphSnapshot)
        edge = next((e for e in g.edges if e.id == req.edge_id), None)
        if edge is None:
            raise ServiceError(404, "not_found", f"edge {req.edge_id} not found")
        if edge.origin != EdgeOrigin.declared_wiring:
            raise ServiceError(400, "not_wiring", "only declared wiring/power connections can be physically verified")
        edge.verification = Verification(req.verification)
        ev = Evidence(id=f"evidence:engineer:wiring:{uuid.uuid4().hex[:8]}", project_id=pid,
                      kind=EvidenceKind.engineer_assertion, epistemic=Epistemic.verified,
                      summary=f"Engineer marked connection {edge.label or edge.relation.value} "
                              f"({edge.source_id} → {edge.target_id}) as {req.verification}"
                              + (f": {req.note}" if req.note else ""),
                      provenance=Provenance(source_id="engineer", captured_at_utc=utcnow()),
                      payload={"edge_id": edge.id, "verification": req.verification, "note": req.note})
        self.store.put(K_EVIDENCE, ev)
        if ev.id not in edge.evidence_ids:
            edge.evidence_ids.append(ev.id)
        project.issues = [i for i in project.issues if i.code != "GPIO_CONFIG_MISMATCH"]
        project.issues += consistency_issues(g.nodes, g.edges)
        project.graph_version += 1
        project.wiring_overrides[edge.id] = req.verification
        g.version = project.graph_version
        self.store.put(K_GRAPH, g)
        self.store.put(f"{K_GRAPH}_v{g.version}", g)
        self.store.put(K_PROJECT, project)
        self._emit("graph.updated", pid, {"version": g.version, "edge_id": edge.id, "verification": req.verification})
        return project

    def subsystems(self, pid: str) -> list[Subsystem]:
        self.project(pid)
        return self.store.list(K_SUBSYS, Subsystem, parent_id=pid)

    def evidence(self, ids: list[str]) -> list[Evidence]:
        return self.store.get_many(K_EVIDENCE, list(dict.fromkeys(ids)), Evidence)

    def demo_fixtures(self) -> list[DemoFixture]:
        f = self.settings.fixtures_dir
        led = str(f / "manifests" / "esp32_led_demo.yaml")
        led_low = str(f / "manifests" / "esp32_led_demo_active_low.yaml")
        servo = str(f / "manifests" / "esp32_servo_demo.yaml")
        return [DemoFixture(label="LED demo — code drives the wrong pin",
                            repo_path=str(f / "esp32_led_demo_fault_a"), manifest_path=led),
                DemoFixture(label="LED demo — correct firmware (pairs with signal/power faults)",
                            repo_path=str(f / "esp32_led_demo"), manifest_path=led),
                DemoFixture(label="LED demo — active-low wiring, active-high code",
                            repo_path=str(f / "esp32_led_demo"), manifest_path=led_low),
                DemoFixture(label="Servo — wrong pin (legacy demo)",
                            repo_path=str(f / "esp32_servo_demo_fault_a"), manifest_path=servo),
                DemoFixture(label="Servo — correct firmware (legacy demo)",
                            repo_path=str(f / "esp32_servo_demo"), manifest_path=servo)]

    def demo_netlist(self) -> str:
        return str(self.settings.fixtures_dir / "kicad" / "esp32_servo_demo.xml")

    def replays(self) -> list[ReplayInfo]:
        return list_replays(self.settings.replay_dir)

    def sim_scenarios(self) -> list[ReplayInfo]:
        return [ReplayInfo(id=k, description=v, synthetic=True) for k, v in SIM_SCENARIOS.items()]

    # ------------------------------------------------------------------ expectations

    def propose_expectation(self, pid: str) -> Expectation:
        g = self.graph(pid)
        analysis = self.store.get(K_ANALYSIS, pid, ProjectAnalysis)
        evs = self.store.list(K_EVIDENCE, Evidence, project_id=pid)
        exp = expmod.propose_expectation(pid, g.nodes, g.edges, evs,
                                         [lit.text for lit in analysis.log_literals])
        if exp is None:
            raise ServiceError(422, "no_testable_component",
                               "No testable component (servo, led) in the hardware graph")
        self.store.put(K_EXPECT, exp)
        return exp

    def list_expectations(self, pid: str) -> list[Expectation]:
        return self.store.list(K_EXPECT, Expectation, project_id=pid)

    def confirm_expectation(self, pid: str, eid: str, edit: ExpectationEdit) -> Expectation:
        exp = self.store.get(K_EXPECT, eid, Expectation)
        if exp is None or exp.project_id != pid:
            raise ServiceError(404, "not_found", f"expectation {eid} not found")
        upd = {k: v for k, v in edit.model_dump().items() if v is not None and k != "trigger_value"}
        if edit.trigger_value is not None:
            upd["trigger"] = exp.trigger.model_copy(update={"value": edit.trigger_value})
        ev = Evidence(id=f"evidence:engineer:{eid}:confirm:{uuid.uuid4().hex[:6]}", project_id=pid,
                      kind=EvidenceKind.engineer_assertion, epistemic=Epistemic.verified,
                      summary="Engineer confirmed expectation", provenance=Provenance(source_id="engineer"),
                      payload={"expectation_id": eid, "edits": edit.model_dump(exclude_none=True)})
        self.store.put(K_EVIDENCE, ev)
        exp = Expectation.model_validate({**exp.model_dump(), **{k: (v.model_dump() if hasattr(v, "model_dump") else v)
                                                                 for k, v in upd.items()},
                                          "confirmed_by_engineer": True})
        self.store.put(K_EXPECT, exp)
        self._emit("expectation.confirmed", pid, {"expectation_id": eid})
        return exp

    # ------------------------------------------------------------------ test runs

    def create_test_run(self, pid: str, req: StartTestRequest, attempt_kind="initial",
                        verifies: str | None = None, incident_id: str | None = None) -> TestRun:
        self.project(pid)
        exp = self.store.get(K_EXPECT, req.expectation_id, Expectation)
        if exp is None or exp.project_id != pid:
            raise ServiceError(404, "not_found", f"expectation {req.expectation_id} not found")
        if not exp.confirmed_by_engineer:
            raise ServiceError(409, "expectation_unconfirmed", "Engineer must confirm the expectation before running it")
        src = req.source
        if src.kind == "replay":
            try:
                synthetic = load_replay(self.settings.replay_dir, src.scenario or "").synthetic
            except ReplayError as e:
                raise ServiceError(400, "replay_invalid", str(e)) from e
        elif src.kind == "sim":
            if (src.scenario or "connected") not in SIM_SCENARIOS:
                raise ServiceError(400, "sim_invalid", f"unknown sim scenario; one of {sorted(SIM_SCENARIOS)}")
            synthetic = True
        else:
            synthetic = False
            d = self.devices
            if exp.trigger.kind == "configured_serial_command" and not d.serial.connected:
                raise ServiceError(409, "serial_unavailable", "Connect the ESP32 serial port before a live test")
            if not d.camera.connected:
                raise ServiceError(409, "camera_unavailable", "Connect a camera before a live test")
            if not d.camera.estimator().calibrated:
                raise ServiceError(409, "camera_uncalibrated",
                                   "Calibrate the camera (servo at a known angle) before a live test")
        run = TestRun(id=_id("test"), project_id=pid, expectation_id=exp.id, attempt_kind=attempt_kind,
                      verifies_test_run_id=verifies, source=src, synthetic=synthetic, incident_id=incident_id)
        self.store.put(K_RUN, run)
        return run

    def test_run(self, run_id: str) -> TestRun:
        r = self.store.get(K_RUN, run_id, TestRun)
        if r is None:
            raise ServiceError(404, "not_found", f"test run {run_id} not found")
        return r

    def runs_for_incident(self, iid: str) -> list[TestRun]:
        inc = self.incident(iid)
        runs = [r for r in self.store.list(K_RUN, TestRun, project_id=inc.project_id)
                if r.incident_id == iid or r.id == inc.test_run_id]
        return sorted(runs, key=lambda r: r.started_at_utc or utcnow())

    def test_data(self, run_id: str) -> tuple[list[Observation], list[SerialEvent]]:
        return (self.store.list(K_OBS, Observation, parent_id=run_id),
                self.store.list(K_SERIAL, SerialEvent, parent_id=run_id))

    async def execute_test_run(self, run_id: str) -> TestRun:
        run = self.test_run(run_id)
        pid = run.project_id
        exp = self.store.get(K_EXPECT, run.expectation_id, Expectation)
        run.state = check_test(run.state, TestRunState.running)
        run.started_at_utc = utcnow()
        self.store.put(K_RUN, run)
        self._emit("test.started", pid, run.model_dump(mode="json"), test_run_id=run.id)
        try:
            obs, serial = await self._collect(run, exp)
        except Exception as e:  # adapter failure: record honestly, never fabricate a result
            run.state = check_test(run.state, TestRunState.failed)
            run.error = f"{type(e).__name__}: {e}"
            run.ended_at_utc = utcnow()
            self.store.put(K_RUN, run)
            self._emit("error", pid, {"message": f"Test run failed: {run.error}"}, test_run_id=run.id)
            if run.incident_id:  # a failed verify attempt returns the incident to the engineer
                inc = self.incident(run.incident_id)
                if inc.state == IncidentState.verifying:
                    inc.state = self.transition(inc, IncidentState.awaiting_engineer)
                    self.store.put(K_INCIDENT, inc)
            return run

        result, rev = expmod.evaluate(exp, obs, serial, run.id)
        self.store.put(K_EVIDENCE, rev)
        run.result = result

        # Write observed state back onto the canonical graph (residuals on the component,
        # traversal on edges) so agents/inspectors see it anchored to structure.
        g = self.store.get(K_GRAPH, pid, GraphSnapshot)
        if g is not None and record_run_state(g, exp, result, run.id, serial):
            self.store.put(K_GRAPH, g)
            self.store.put(f"{K_GRAPH}_v{g.version}", g)
            self._emit("graph.updated", pid, {"version": g.version, "reason": "run_state"})
        run.state = check_test(run.state, TestRunState.completed)
        run.ended_at_utc = utcnow()

        if run.attempt_kind == "initial" and result.outcome != ExpectationOutcome.passed:
            run.incident_id = self._create_incident(run, exp)
            self._emit("expectation.failed", pid, {"reason": result.reason, "outcome": result.outcome.value},
                       test_run_id=run.id, investigation_id=run.incident_id)
        elif run.incident_id:
            self._attach_followup_run(run)
        self.store.put(K_RUN, run)
        self._emit("test.completed", pid, run.model_dump(mode="json"), test_run_id=run.id,
                   investigation_id=run.incident_id)
        return run

    def _stream(self, run: TestRun, exp: Expectation):
        src = run.source
        if src.kind == "replay":
            return load_replay(self.settings.replay_dir, src.scenario or ""), "replay_cv", f"replay:{src.scenario}"
        command = exp.trigger.value if exp.trigger.kind == "configured_serial_command" else None
        if src.kind == "sim":
            g = self.graph(run.project_id)
            cfg, _, wired = config_vs_wiring(exp.component_id, g.nodes, g.edges)
            gpio = {n.id: n.attributes.get("gpio") for n in g.nodes}
            configured = gpio.get(cfg[0].target_id) if cfg else None
            comp_node = next((n for n in g.nodes if n.id == exp.component_id), None)
            active_low = bool(comp_node and comp_node.attributes.get("active_low"))
            rig = SimRig(conditions_for(src.scenario or "connected", configured,
                                        gpio.get(wired) if wired else None,
                                        active_low=active_low,
                                        code_on_high=exp.on_level != "LOW"))
            cam = SimCamera(rig, metric=exp.metric)
            if exp.unit == "state":
                from .observations.cv_led import LedStateEstimator
                est = LedStateEstimator()
                est.calibrate(render_led_scene(False))  # engineer records the LED-off baseline
            else:
                est = ArucoAngleEstimator()
                # Calibrate like an engineer would before the run: marker visible at a known angle.
                est.calibrate(render_scene(rig.angle()), rig.angle())
            return (LiveStream(scenario=src.scenario or "connected", synthetic=True,
                               description=SIM_SCENARIOS[src.scenario or "connected"], command=command,
                               serial=SimSerial(rig), camera=cam, estimator=est, window_ms=exp.deadline_ms),
                    "sim_cv", "sim:rig")
        d = self.devices
        return (LiveStream(scenario="live", synthetic=False, description="live devices", command=command,
                           serial=d.serial if command else None, camera=d.camera.source,
                           estimator=d.camera.estimator(), window_ms=exp.deadline_ms),
                "opencv", d.camera.source.source_id)

    async def _collect(self, run: TestRun, exp: Expectation):
        stream, cv_type, src = self._stream(run, exp)
        analysis = self.store.get(K_ANALYSIS, run.project_id, ProjectAnalysis)
        obs: list[Observation] = []
        serial: list[SerialEvent] = []
        evs: list[Evidence] = []
        recorded: list[dict] = []
        t0 = run.started_at_utc
        n = 0
        async for ev in stream.play(self.settings.replay_speed):
            n += 1
            recorded.append({"t_ms": ev.t_ms, "source": ev.source, **ev.data})
            ts = t0 + timedelta(milliseconds=ev.t_ms)
            prov = Provenance(source_id=src, captured_at_utc=ts)
            if ev.source in ("host", "serial"):
                raw = str(ev.data.get("raw", ""))
                tx = ev.source == "host"
                eid = f"evidence:{'host' if tx else 'serial'}:{run.id}:{n}"
                matched = [] if tx else [lit.function_id for lit in analysis.log_literals
                                         if lit.function_id and len(lit.text.strip()) >= 3
                                         and raw.startswith(lit.text.strip())]
                evs.append(Evidence(
                    id=eid, project_id=run.project_id, kind=EvidenceKind.host_command if tx else EvidenceKind.serial_line,
                    epistemic=Epistemic.observed, test_run_id=run.id, provenance=prov, raw_ref=f"{src}#{n}",
                    summary=(f"Host sent configured command: {raw}" if tx else f"Serial RX: {raw}"),
                    payload={"raw": raw, "elapsed_ms": ev.t_ms, "matched_function_ids": matched}))
                se = SerialEvent(id=f"serial:{run.id}:{n}", project_id=run.project_id, test_run_id=run.id,
                                 direction="tx" if tx else "rx", timestamp_utc=ts, elapsed_ms=ev.t_ms, raw=raw,
                                 evidence_id=eid, matched_function_ids=matched)
                serial.append(se)
                self.store.put(K_SERIAL, se, parent_id=run.id)
                self._emit("test.serial", run.project_id, se.model_dump(mode="json"), test_run_id=run.id)
            elif ev.source == "cv":
                q = ev.data.get("quality", "valid")
                val = ev.data.get("value", ev.data.get("angle_deg"))  # old replays used angle_deg
                eid = f"evidence:cv:{run.id}:{n}"
                evs.append(Evidence(
                    id=eid, project_id=run.project_id, kind=EvidenceKind.cv_measurement,
                    epistemic=Epistemic.observed if q == "valid" else Epistemic.unknown, test_run_id=run.id,
                    provenance=prov, raw_ref=f"{src}#frame{ev.data.get('frame')}",
                    summary=(f"{exp.metric} {val}{exp.unit if exp.unit != 'state' else ''} at {ev.t_ms} ms"
                             if q == "valid" else f"No valid measurement at {ev.t_ms} ms ({q})"),
                    payload={"value": val, "quality": q, "elapsed_ms": ev.t_ms, "metric": exp.metric}))
                o = Observation(id=f"obs:{run.id}:{n}", project_id=run.project_id, test_run_id=run.id,
                                source_type=cv_type, source_id=src, component_id=exp.component_id,
                                timestamp_utc=ts, elapsed_ms=ev.t_ms, metric=exp.metric,
                                value=val if q == "valid" else None, unit=exp.unit, measurement_quality=q,
                                evidence_ref=f"frame:{ev.data.get('frame')}", evidence_id=eid)
                obs.append(o)
                self.store.put(K_OBS, o, parent_id=run.id)
                self._emit("test.observation", run.project_id, o.model_dump(mode="json"), test_run_id=run.id)
        self.store.put_many(K_EVIDENCE, evs)
        self.store.put(K_RECORDING, RunRecording(id=run.id, project_id=run.project_id, events=recorded,
                                               command=getattr(stream, "command", None)))
        return obs, serial

    def save_replay(self, run_id: str, name: str) -> ReplayInfo:
        """Persist a completed run as a replay fixture (PRD §8 reproducibility, M7 fallback demo).
        Live runs go to recorded/real/, sim/replay-derived ones to recorded/synthetic/."""
        run = self.test_run(run_id)
        rec = self.store.get(K_RECORDING, run_id, RunRecording)
        if rec is None or run.state != TestRunState.completed:
            raise ServiceError(409, "no_recording", "only completed runs can be saved as replays")
        folder = "real" if run.source.kind == "live" else "synthetic"
        out = self.settings.replay_dir / folder / f"{name}.jsonl"
        if out.exists():
            raise ServiceError(409, "exists", f"replay {name} already exists")
        out.parent.mkdir(parents=True, exist_ok=True)
        meta = {"_meta": {"synthetic": run.synthetic, "scenario": name, "command": rec.command,
                          "description": f"Recorded from {run.source.kind} run {run.id}"
                                         + (f" ({run.source.scenario})" if run.source.scenario else "")
                                         + (f"; result {run.result.outcome.value}" if run.result else ""),
                          "recorded_at_utc": (run.started_at_utc or utcnow()).isoformat()}}
        out.write_text("\n".join(json.dumps(x) for x in [meta, *rec.events]) + "\n", encoding="utf-8")
        return ReplayInfo(id=name, description=meta["_meta"]["description"], synthetic=run.synthetic)

    # ------------------------------------------------------------------ incidents

    def _create_incident(self, run: TestRun, exp: Expectation) -> str:
        g = self.graph(run.project_id)
        findings, new_ev = run_rules(exp, run.result, g.nodes, g.edges, run.id)
        self.store.put_many(K_EVIDENCE, new_ev)
        iid = _id("incident")
        _, _, wired_pin = config_vs_wiring(exp.component_id, g.nodes, g.edges)
        wired_label = next((n.label for n in g.nodes if n.id == wired_pin), None)
        hyps, actions = hypmod.build(iid, findings, wired_label, exp.component_id)
        # Digital-shadow sweep: which fault-knob settings reproduce the observed signature.
        # Adds inferred evidence/counter-evidence to hypotheses; rules keep the ranking.
        if run.result is not None:
            verdicts, shev = shadow_assess(exp, g.nodes, g.edges, run.result, run.id)
            obs = {f.key: f.value for f in run.result.facts}
            attach_verdicts(hyps, verdicts, shev.id,
                            f"sent={obs.get('command_sent')} ack={obs.get('command_acknowledged')} "
                            f"motion={obs.get('physical_motion')} valid={run.result.valid_samples}")
            self.store.put(K_EVIDENCE, shev)
        codes = [f.code for f in findings]
        comp_label = next((n.label for n in g.nodes if n.id == exp.component_id), "component")
        if FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE in codes:
            title = "Measurement unavailable"
        elif exp.unit == "state":
            title = f"{comp_label} did not reach expected state {exp.target:g}"
        else:
            title = f"{comp_label} did not reach {exp.target:g}°"
        inc = Incident(id=iid, project_id=run.project_id, test_run_id=run.id, expectation_id=exp.id,
                       state=IncidentState.open, title=title, fault_codes=codes,
                       hypothesis_ids=[h.id for h in hyps], action_ids=[a.id for a in actions])
        inc.state = check_incident(inc.state, IncidentState.awaiting_engineer)
        self.store.put_many(K_HYP, hyps)
        self.store.put_many(K_ACTION, actions)
        self.store.put(K_INCIDENT, inc)
        self._emit("incident.created", run.project_id, {"incident_id": iid, "title": title,
                   "fault_codes": [c.value for c in codes]}, investigation_id=iid, test_run_id=run.id)
        for a in actions:
            self._emit("action.proposed", run.project_id, {"action_id": a.id, "label": a.label}, investigation_id=iid)
        self._emit("hypotheses.updated", run.project_id, {"hypothesis_ids": inc.hypothesis_ids}, investigation_id=iid)
        return iid

    def _attach_followup_run(self, run: TestRun) -> None:
        inc = self.incident(run.incident_id)
        outcome = run.result.outcome
        if run.attempt_kind == "verify":
            if outcome == ExpectationOutcome.passed:
                inc.state = self.transition(inc, IncidentState.resolved)
                inc.resolved_by_test_run_id = run.id
                self._emit("incident.resolved", inc.project_id, {"test_run_id": run.id},
                           investigation_id=inc.id, test_run_id=run.id)
            elif inc.state == IncidentState.verifying:
                inc.state = self.transition(inc, IncidentState.awaiting_engineer)
            self._emit("test.verification_completed", inc.project_id,
                       {"outcome": outcome.value, "reason": run.result.reason}, investigation_id=inc.id, test_run_id=run.id)
        self.store.put(K_INCIDENT, inc)

    def incident(self, iid: str) -> Incident:
        inc = self.store.get(K_INCIDENT, iid, Incident)
        if inc is None:
            raise ServiceError(404, "not_found", f"investigation {iid} not found")
        return inc

    def list_incidents(self, pid: str) -> list[Incident]:
        return self.store.list(K_INCIDENT, Incident, project_id=pid)

    def investigation(self, iid: str) -> InvestigationView:
        inc = self.incident(iid)
        run = self.test_run(inc.test_run_id)
        hyps = hypmod.rerank(self.store.get_many(K_HYP, inc.hypothesis_ids, Hypothesis))
        actions = self.store.get_many(K_ACTION, inc.action_ids, DiagnosticAction)
        followups = [r for r in self.runs_for_incident(iid) if r.id != run.id]
        agent_runs = self.orchestrator.runs(iid)
        engineer = [e for e in self.store.list(K_EVIDENCE, Evidence, project_id=inc.project_id)
                    if e.kind == EvidenceKind.engineer_assertion and e.payload.get("incident_id") == iid]
        ev_ids = [i for h in hyps for i in h.supporting_evidence_ids + h.contradicting_evidence_ids]
        ev_ids += [i for a in actions for i in a.evidence_ids]
        if run.result:
            ev_ids += [run.result.evidence_id] + [i for f in run.result.facts for i in f.evidence_ids]
        ev_ids += [r.result.evidence_id for r in followups if r.result]
        ev_ids += [e.id for e in engineer]
        ev_ids += [i for ar in agent_runs if ar.report for f in ar.report.findings
                   for i in f.supporting_evidence_ids + f.contradicting_evidence_ids]
        calls = self.tools.calls(iid)
        ev_ids += [i for c in calls for i in c.evidence_ids]
        exp = self.store.get(K_EXPECT, inc.expectation_id, Expectation)
        causal = causal_chain(exp, run.result) if run.result else []
        return InvestigationView(
            incident=inc, test_run=run, followup_runs=followups, hypotheses=hyps, actions=actions,
            evidence=self.evidence(ev_ids), highlights=self._highlights(inc, run, hyps),
            permissions=self.tools.permissions.active(iid), tool_calls=calls,
            messages=[e for e in engineer if e.payload.get("message")], agent_runs=agent_runs,
            repair_jobs=self.store.list(K_REPAIR, RepairJob, parent_id=iid), causal_chain=causal)

    def _highlights(self, inc: Incident, run: TestRun, hyps: list[Hypothesis]) -> list[Highlight]:
        out: dict[str, Highlight] = {}
        exp = self.store.get(K_EXPECT, inc.expectation_id, Expectation)
        if inc.state == IncidentState.resolved:
            out[exp.component_id] = Highlight(element_id=exp.component_id, style="observed",
                                              reason="Verified: expectation passed after repair")
        elif run.result and run.result.outcome == ExpectationOutcome.failed:
            out[exp.component_id] = Highlight(element_id=exp.component_id, style="failed_expectation",
                                              reason=run.result.reason)
        for h in hyps:
            if h.status in (HypothesisStatus.ruled_out, HypothesisStatus.weakened) or inc.state == IncidentState.resolved:
                continue
            style = {FaultCode.GPIO_CONFIG_MISMATCH: "conflict",
                     FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE: "unknown"}.get(h.fault_code, "suspect")
            for el in h.related_edge_ids + [n for n in h.related_node_ids if n != exp.component_id]:
                out.setdefault(el, Highlight(element_id=el, style=style, reason=h.title))
        _, serial = self.test_data(run.id)
        for se in serial:
            for fid in se.matched_function_ids:
                out.setdefault(fid, Highlight(element_id=fid, style="observed",
                                              reason=f'Serial log line "{se.raw}" matches a print in this function'))
        return list(out.values())

    # ------------------------------------------------------------------ actions & tools

    async def execute_action(self, iid: str, action_id: str, source: ObservationSourceSpec | None,
                             approve_once: bool = False) -> tuple[ActionResult, TestRun | None]:
        inc = self.incident(iid)
        action = self.store.get(K_ACTION, action_id, DiagnosticAction)
        if action is None or action.incident_id != iid:
            raise ServiceError(404, "not_found", f"action {action_id} not found")
        if inc.state in (IncidentState.resolved, IncidentState.inconclusive):
            raise ServiceError(409, "incident_closed", f"incident is {inc.state.value}")
        if inc.state == IncidentState.investigating and action.kind in (ActionKind.verify_fix, ActionKind.repeat_test):
            raise ServiceError(409, "agents_running", "wait for the agent round to finish")
        self._emit("action.started", inc.project_id, {"action_id": action_id}, investigation_id=iid)
        run = None

        if action.tool_name:
            result = await self._run_tool_action(inc, action, approve_once)
        elif action.kind in (ActionKind.repeat_test, ActionKind.verify_fix):
            original = self.test_run(inc.test_run_id)
            kind = "verify" if action.kind == ActionKind.verify_fix else "repeat"
            run = self.create_test_run(inc.project_id, StartTestRequest(
                expectation_id=inc.expectation_id, source=source or original.source),
                attempt_kind=kind, verifies=original.id, incident_id=iid)
            if kind == "verify":
                inc.state = self.transition(inc, IncidentState.verifying)
                self.store.put(K_INCIDENT, inc)
            result = ActionResult(action_id=action_id, status="completed", test_run_id=run.id,
                                  summary=f"{'Verification' if kind == 'verify' else 'Repeat'} test {run.id} started "
                                          f"with the same confirmed expectation.")
        elif action.kind == ActionKind.request_manual_check:
            raise ServiceError(400, "manual_action", "Manual checks are recorded via /manual-results")
        else:
            raise ServiceError(400, "unsupported_action", f"action kind {action.kind.value} is not executable")

        action.status = "completed"
        self.store.put(K_ACTION, action)
        self._emit("action.completed", inc.project_id, result.model_dump(mode="json"), investigation_id=iid)
        return result, run

    async def _run_tool_action(self, inc: Incident, action: DiagnosticAction, approve_once: bool) -> ActionResult:
        project = self.project(inc.project_id)
        try:
            call, out = await self.tools.execute(project, inc, action.tool_name, tool_args(action.tool_name, action.arguments),
                                                 caller="engineer", approve_once=approve_once)
        except ToolDenied as e:
            self._emit("action.denied", inc.project_id, {"action_id": action.id, "reason": e.reason,
                       "category": e.category}, investigation_id=inc.id)
            code = "permission_required" if e.call.decision == "denied" else "tool_unavailable"
            raise ServiceError(403, code, e.reason, {"category": e.category, "tool": action.tool_name,
                                                     "tool_call_id": e.call.id}) from e
        except ToolFailed as e:
            raise ServiceError(502, "tool_failed", e.reason, {"tool_call_id": e.call.id}) from e

        self._update_hypotheses_from_tool(inc, action, call.evidence_ids[0], out.data)
        return ActionResult(action_id=action.id, status="completed", summary=out.summary,
                            source_excerpts=out.source_excerpts,
                            evidence=out.cited_evidence + self.evidence(call.evidence_ids),
                            tool_call_id=call.id, node_ids=out.node_ids, lines=out.lines)

    def _update_hypotheses_from_tool(self, inc: Incident, action: DiagnosticAction, ev_id: str, data: dict) -> None:
        """Deterministic: Inspect GPIO either confirms or rules out the mismatch hypothesis."""
        if action.tool_name != "inspect_gpio_config" or not data.get("wired") or not data.get("configured"):
            return
        for h in self.store.get_many(K_HYP, inc.hypothesis_ids, Hypothesis):
            if h.fault_code != FaultCode.GPIO_CONFIG_MISMATCH:
                continue
            if data["configured"] != [data["wired"]]:
                h.status = HypothesisStatus.supported
                h.supporting_evidence_ids.append(ev_id)
            else:
                h.status = HypothesisStatus.ruled_out
                h.contradicting_evidence_ids.append(ev_id)
            self.store.put(K_HYP, h)
            self._emit("hypotheses.updated", inc.project_id, {"hypothesis_ids": [h.id]}, investigation_id=inc.id)

    def set_permission(self, iid: str, category: str, granted: bool):
        inc = self.incident(iid)
        if inc.state in (IncidentState.resolved, IncidentState.inconclusive):
            raise ServiceError(409, "incident_closed", "grants end when the investigation ends")
        return self.tools.permissions.set(inc, category, granted)

    def record_manual_result(self, iid: str, req: ManualResultRequest) -> InvestigationView:
        inc = self.incident(iid)
        action = self.store.get(K_ACTION, req.action_id, DiagnosticAction)
        if action is None or action.incident_id != iid or action.kind != ActionKind.request_manual_check:
            raise ServiceError(404, "not_found", f"manual check {req.action_id} not found")
        if req.result not in action.result_choices:
            raise ServiceError(400, "invalid_result", f"result must be one of {action.result_choices}")
        ev = Evidence(id=f"evidence:engineer:{iid}:{uuid.uuid4().hex[:8]}", project_id=inc.project_id,
                      kind=EvidenceKind.engineer_assertion, epistemic=Epistemic.observed,
                      summary=f"Engineer check — {action.label}: {req.result}" + (f" ({req.note})" if req.note else ""),
                      provenance=Provenance(source_id="engineer", captured_at_utc=utcnow()),
                      payload={"incident_id": iid, "action_id": action.id, "result": req.result, "note": req.note})
        self.store.put(K_EVIDENCE, ev)
        hid = action.arguments.get("hypothesis_id")
        new_status = action.arguments.get("status_on_result", {}).get(req.result)
        h = self.store.get(K_HYP, hid, Hypothesis) if hid else None
        if h is not None:
            if new_status == "supported":
                h.supporting_evidence_ids.append(ev.id)
                h.status = HypothesisStatus.supported
            elif new_status == "weakened":
                h.contradicting_evidence_ids.append(ev.id)
                h.status = HypothesisStatus.weakened
            else:
                h.unknowns.append(f"{action.label}: engineer was unable to verify")
            self.store.put(K_HYP, h)
        action.status = "completed"
        self.store.put(K_ACTION, action)
        self._emit("action.completed", inc.project_id, {"action_id": action.id, "result": req.result},
                   investigation_id=iid)
        self._emit("hypotheses.updated", inc.project_id, {"hypothesis_ids": inc.hypothesis_ids}, investigation_id=iid)
        return self.investigation(iid)

    def add_message(self, iid: str, text: str) -> InvestigationView:
        """Contextual free text (PRD FR-08). Stored as an engineer statement; never changes permissions."""
        inc = self.incident(iid)
        ev = Evidence(id=f"evidence:engineer:{iid}:msg:{uuid.uuid4().hex[:8]}", project_id=inc.project_id,
                      kind=EvidenceKind.engineer_assertion, epistemic=Epistemic.observed,
                      summary=f"Engineer note: {text}", provenance=Provenance(source_id="engineer", captured_at_utc=utcnow()),
                      payload={"incident_id": iid, "message": True, "text": text})
        self.store.put(K_EVIDENCE, ev)
        self._emit("message.added", inc.project_id, {"text": text[:200]}, investigation_id=iid)
        return self.investigation(iid)

    # ------------------------------------------------------------------ agents

    def agent_status(self) -> AgentStatus:
        """Per-stage provider attribution (D-023): orchestration vs specialists are different providers."""
        stages = [
            ProviderStatus(role="orchestrator", provider=self.orchestrator_llm.name,
                           model=self.orchestrator_llm.model, available=self.orchestrator_llm.available,
                           reason=getattr(self.orchestrator_llm, "reason", None)),
            ProviderStatus(role="specialists", provider=self.specialist_llm.name,
                           model=self.specialist_llm.model, available=self.specialist_llm.available,
                           reason=getattr(self.specialist_llm, "reason", None)),
        ]
        avail = [s for s in stages if s.available]
        if len(avail) == 2:
            provider = f"{stages[0].provider}+{stages[1].provider}"
        elif avail:
            provider = f"{avail[0].provider} only ({avail[0].role})"
        else:
            provider = "none (deterministic only)"
        reason = None if len(avail) == 2 else "; ".join(
            f"{s.role}: {s.reason}" for s in stages if not s.available and s.reason) or None
        return AgentStatus(available=bool(avail), provider=provider,
                           model="/".join(s.model or "?" for s in avail) or None,
                           reason=reason, stages=stages)

    def begin_diagnosis(self, iid: str) -> Incident:
        try:
            return self.orchestrator.begin(self.incident(iid))
        except DiagnosisRefused as e:
            raise ServiceError(e.status, e.code, e.message) from e

    async def run_diagnosis(self, iid: str) -> list[AgentRun]:
        return await self.orchestrator.run_round(iid)

    # ------------------------------------------------------------------ event flow (D-024)

    def event_flow(self, run_id: str) -> EventFlow:
        """Chronological lanes for one persisted run. Deterministic projection — reload-safe,
        duplicate-safe (ids derived from underlying records), and honest about missing data."""
        run = self.test_run(run_id)
        exp = self.store.get(K_EXPECT, run.expectation_id, Expectation)
        obs, serial = self.test_data(run_id)
        timeline = self.store.events(run.project_id)
        return build_event_flow(run, exp, obs, serial, timeline)

    # ------------------------------------------------------------------ remote repair (D-025)

    def _repair_jobs(self, iid: str) -> list[RepairJob]:
        return self.store.list(K_REPAIR, RepairJob, parent_id=iid)

    def _software_evidence(self, inc: Incident) -> bool:
        """A remote code fix is only offered when the incident has evidence of a software issue —
        never as a remedy for an unverified power/signal problem."""
        if FaultCode.GPIO_CONFIG_MISMATCH not in inc.fault_codes:
            return False
        hyps = self.store.get_many(K_HYP, inc.hypothesis_ids, Hypothesis)
        return any(h.fault_code == FaultCode.GPIO_CONFIG_MISMATCH
                   and h.status != HypothesisStatus.ruled_out for h in hyps)

    def repair_preflight(self, iid: str) -> RepairPreflight:
        inc = self.incident(iid)
        project = self.project(inc.project_id)
        snap = repo_snapshot(project.repo_root)
        issues: list[str] = []
        warnings: list[str] = []
        if not self._software_evidence(inc):
            issues.append("this incident has no evidence of a software issue — a remote code fix "
                          "is not offered for unverified power/signal problems")
        if inc.state in (IncidentState.resolved, IncidentState.inconclusive):
            issues.append(f"incident is {inc.state.value}")
        if snap.base_revision is None:
            issues.append("the project is not inside a git repository — Devin needs an accessible "
                          "repository and a base commit")
        repo_ref = self.settings.devin_repo or snap.repo_ref
        if snap.base_revision is not None and not repo_ref:
            issues.append("no usable git remote — Devin Cloud cannot reach a local path. Add a remote "
                          "(e.g. origin on GitHub) or set INTEGREAT_DEVIN_REPO=owner/name")
        if snap.dirty_files:
            warnings.append(f"{len(snap.dirty_files)} uncommitted file(s) will NOT be visible to Devin — "
                            "the session works from the committed base commit")
        if snap.relative_path:
            warnings.append(f"firmware lives in subdirectory '{snap.relative_path}' of the git repo; "
                            "the brief tells Devin where to look")
        if snap.git_toplevel and Path(snap.git_toplevel) != Path(project.repo_root):
            pass  # nested repo is fine; relative_path is recorded in the snapshot
        active = next((j for j in self._repair_jobs(iid)
                       if j.state in (RepairState.preparing, RepairState.queued, RepairState.working,
                                      RepairState.needs_input, RepairState.uncertain)), None)
        if active is not None:
            issues.append(f"a repair job is already {active.state.value} for this incident ({active.id})")
        jobs = self._repair_jobs(iid)
        if len(jobs) >= MAX_REPAIR_ATTEMPTS:
            issues.append(f"repair request budget exhausted ({MAX_REPAIR_ATTEMPTS} attempts per incident)")
        configured = self.devin.available
        return RepairPreflight(
            ready=bool(issues == [] and configured),
            devin_configured=configured,
            unavailable_reason=None if configured else getattr(self.devin, "reason", "not configured"),
            issues=issues, warnings=warnings, snapshot=snap,
            software_evidence=self._software_evidence(inc),
            active_job_id=active.id if active else None)

    async def request_repair(self, iid: str, req: RepairRequest) -> RepairJob:
        """Create ONE remote Devin session for this incident. Engineer-initiated only; session
        creation is non-idempotent so we never retry automatically."""
        inc = self.incident(iid)
        project = self.project(inc.project_id)
        pre = self.repair_preflight(iid)
        if not pre.devin_configured:
            raise ServiceError(503, "devin_unavailable",
                               f"Devin is not configured: {pre.unavailable_reason}")
        if not self._software_evidence(inc):
            raise ServiceError(409, "no_software_evidence",
                               "a remote code fix needs evidence of a software issue — "
                               "unverified power/signal problems are diagnosed on the bench")
        if pre.active_job_id:
            raise ServiceError(409, "repair_active",
                               f"a repair job is already active ({pre.active_job_id}); "
                               "wait for it or deliberately request a new attempt after it ends")
        blocking = [i for i in pre.issues if "uncommitted" not in i]
        if blocking:
            raise ServiceError(409, "repair_unavailable", "; ".join(blocking),
                             {"issues": pre.issues, "warnings": pre.warnings})
        if pre.snapshot and pre.snapshot.dirty_files and not req.acknowledge_uncommitted:
            raise ServiceError(409, "uncommitted_changes",
                               "uncommitted changes are not visible to Devin — acknowledge that the "
                               "session works from the committed base revision")
        snap = pre.snapshot
        repo_ref = self.settings.devin_repo or snap.repo_ref
        hyps = hypmod.rerank(self.store.get_many(K_HYP, inc.hypothesis_ids, Hypothesis))
        run = self.test_run(inc.test_run_id)
        exp = self.store.get(K_EXPECT, inc.expectation_id, Expectation)
        ev_ids = sorted({i for h in hyps for i in h.supporting_evidence_ids})
        evidence_lines = [f"{e.id} [{e.kind.value}/{e.epistemic.value}] {e.summary[:180]}"
                          for e in self.evidence(ev_ids)]
        brief = build_brief(project, inc, exp, run, hyps, evidence_lines, snap, repo_ref)
        job = RepairJob(id=_id("repair"), project_id=inc.project_id, incident_id=iid,
                        attempt=len(self._repair_jobs(iid)) + 1, snapshot=snap,
                        brief_text=brief, brief_evidence_ids=ev_ids, warnings=list(pre.warnings))
        self.store.put(K_REPAIR, job, parent_id=iid)
        self._emit("repair.requested", inc.project_id,
                   {"job_id": job.id, "repo_ref": repo_ref, "base_revision": snap.base_revision,
                    "attempt": job.attempt}, investigation_id=iid)
        # Audit: who requested it and what was sent (PRD §13 audit; no secrets in the brief).
        self.store.put(K_EVIDENCE, Evidence(
            id=f"evidence:engineer:{iid}:repair:{job.id}", project_id=inc.project_id,
            kind=EvidenceKind.engineer_assertion, epistemic=Epistemic.observed,
            summary=(f"Engineer requested a Devin repair session for {repo_ref} "
                     f"@ {str(snap.base_revision)[:8]} (brief {len(brief)} chars, "
                     f"{len(ev_ids)} evidence refs)"),
            provenance=Provenance(source_id="engineer", captured_at_utc=utcnow()),
            payload={"incident_id": iid, "job_id": job.id, "repo_ref": repo_ref,
                     "base_revision": snap.base_revision}))
        try:
            session = await self.devin.create_session(
                prompt=brief, repos=[repo_ref] if repo_ref else [],
                title=f"inteGREAT repair: {inc.title[:80]}",
                tags=["integreat", f"incident:{iid[-8:]}", f"job:{job.id[-8:]}"],
                max_acu_limit=self.settings.devin_max_acu,
                structured_output_schema=REPAIR_OUTPUT_SCHEMA, timeout_s=45.0)
            job.devin_session_id = session.session_id or None
            job.session_url = session.url or None
            job.state = map_remote_state(session.status, session.status_detail)
        except asyncio.TimeoutError:
            job.state = RepairState.uncertain
            job.error = ("Session creation timed out — the session may exist in Devin Cloud but we "
                         "have no session id. It is NOT retried automatically; check the Devin "
                         "dashboard, then request a new attempt deliberately.")
        except DevinUnavailable as e:
            job.state = RepairState.failed
            job.error = str(e)
        job.updated_at_utc = utcnow()
        self.store.put(K_REPAIR, job, parent_id=iid)
        self._emit("repair.updated", inc.project_id,
                   {"job_id": job.id, "state": job.state.value, "session_url": job.session_url},
                   investigation_id=iid)
        return job

    async def refresh_repair(self, job_id: str) -> RepairJob:
        """Poll remote status. GET only — polling NEVER creates a session."""
        job = self.store.get(K_REPAIR, job_id, RepairJob)
        if job is None:
            raise ServiceError(404, "not_found", f"repair job {job_id} not found")
        terminal = (RepairState.ready_for_review, RepairState.failed)
        if job.state in terminal or not job.devin_session_id:
            return job
        try:
            session = await self.devin.get_session(job.devin_session_id)
        except asyncio.TimeoutError:
            job.error = "status check timed out; will retry on next refresh"
            job.updated_at_utc = utcnow()
            self.store.put(K_REPAIR, job, parent_id=job.incident_id)
            return job
        except SessionGone as e:
            job.state = RepairState.failed
            job.error = (f"{e} — the session is gone in Devin Cloud, so this attempt is "
                         "closed; request a new attempt if still needed")
            job.updated_at_utc = utcnow()
            self.store.put(K_REPAIR, job, parent_id=job.incident_id)
            self._emit("repair.updated", job.project_id,
                       {"job_id": job.id, "state": job.state.value}, investigation_id=job.incident_id)
            return job
        except DevinUnavailable as e:
            job.error = str(e)
            job.updated_at_utc = utcnow()
            self.store.put(K_REPAIR, job, parent_id=job.incident_id)
            return job
        job.state = map_remote_state(session.status, session.status_detail)
        job.session_url = job.session_url or session.url or None
        job.error = None
        if job.state == RepairState.ready_for_review:
            job.result = RepairResult(pull_requests=session.pull_requests,
                                      structured_output=session.structured_output,
                                      acus_consumed=session.acus_consumed,
                                      session_status_detail=session.status_detail)
        job.updated_at_utc = utcnow()
        self.store.put(K_REPAIR, job, parent_id=job.incident_id)
        self._emit("repair.updated", job.project_id,
                   {"job_id": job.id, "state": job.state.value,
                    "prs": len(job.result.pull_requests) if job.result else 0},
                   investigation_id=job.incident_id)
        return job

    def repair_jobs(self, iid: str) -> list[RepairJob]:
        self.incident(iid)
        return self._repair_jobs(iid)
