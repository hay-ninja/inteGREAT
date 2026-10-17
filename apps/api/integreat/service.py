"""Application service: the import → test → evaluate → incident → action loop.

Routes stay thin; all orchestration and state transitions live here so they are testable without HTTP.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path

from .api.ws import Hub
from .config import Settings
from .diagnostics import expectations as expmod
from .diagnostics import hypotheses as hypmod
from .diagnostics.rules import config_vs_wiring, run_rules
from .diagnostics.state_machine import check_incident, check_test
from .graph.builder import build_graph, src_evidence_id
from .graph.query import scope as scope_graph
from .ingestion.arduino_parser import parse_project
from .ingestion.manifest import ManifestError, load_manifest
from .ingestion.repository import RepoError, resolve_inside, scan_repository
from .models import (
    ActionKind,
    ActionResult,
    DemoFixture,
    DiagnosticAction,
    Epistemic,
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
    Observation,
    ObservationSourceSpec,
    Project,
    ProjectAnalysis,
    Provenance,
    ReplayInfo,
    SerialEvent,
    SourceExcerpt,
    StartTestRequest,
    Subsystem,
    TestRun,
    TestRunState,
    utcnow,
)
from .observations.replay import ReplayError, list_replays, load_replay
from .storage.db import Store


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _id(prefix: str) -> str:
    return f"{prefix}:{uuid.uuid4().hex[:10]}"


# Document kinds in the store
K_PROJECT, K_GRAPH, K_SUBSYS, K_EVIDENCE, K_ANALYSIS = "project", "graph", "subsystem", "evidence", "analysis"
K_EXPECT, K_RUN, K_OBS, K_SERIAL = "expectation", "test_run", "observation", "serial_event"
K_INCIDENT, K_HYP, K_ACTION = "incident", "hypothesis", "action"


class Service:
    def __init__(self, store: Store, settings: Settings, hub: Hub):
        self.store, self.settings, self.hub = store, settings, hub

    def _emit(self, type: str, project_id: str, payload: dict | None = None, **kw) -> None:
        self.hub.publish(IntegreatEvent(type=type, project_id=project_id, payload=payload or {}, **kw))

    # ------------------------------------------------------------------ projects & graph

    def import_project(self, req: ImportRequest) -> Project:
        try:
            scan = scan_repository(req.repo_path)
        except RepoError as e:
            raise ServiceError(400, "repo_invalid", str(e)) from e
        pid = _id("project")
        parsed = parse_project(scan.files)
        issues: list[ImportIssue] = [ImportIssue(level="info", code="FILE_SKIPPED", message=f"{rel}: {why}", file=rel)
                                     for rel, why in scan.skipped]
        manifest = lines = mrel = None
        if req.manifest_path:
            try:
                manifest, _, lines = load_manifest(req.manifest_path)
                mrel = Path(req.manifest_path).name
            except ManifestError as e:
                issues.append(ImportIssue(level="error", code="MANIFEST_INVALID", message=str(e)))
        built = build_graph(pid, [f.rel for f in scan.files], parsed, manifest, lines, mrel)
        issues += built.issues

        lit_ev = []
        literals = []
        for lit in parsed.log_literals:
            eid = src_evidence_id(lit.file, lit.line, "log")
            lit_ev.append(Evidence(id=eid, project_id=pid, kind=EvidenceKind.source_excerpt, epistemic=Epistemic.observed,
                                   summary=f'Firmware prints "{lit.text}"',
                                   provenance=Provenance(source_id="repo", file=lit.file, line_start=lit.line, line_end=lit.line),
                                   payload={"literal": lit.text}))
            literals.append(LogLiteral(function_id=lit.function_id, text=lit.text, evidence_id=eid))

        project = Project(id=pid, name=req.name or scan.root.name, repo_root=str(scan.root),
                          manifest_path=req.manifest_path, issues=issues, file_count=len(scan.files))
        self.store.put(K_PROJECT, project)
        self.store.put(K_GRAPH, GraphSnapshot(project_id=pid, version=1, nodes=built.nodes, edges=built.edges))
        self.store.put_many(K_SUBSYS, built.subsystems, parent_id=pid)
        self.store.put_many(K_EVIDENCE, built.evidence + lit_ev)
        self.store.put(K_ANALYSIS, ProjectAnalysis(id=pid, project_id=pid, log_literals=literals))
        self._emit("project.imported", pid, {"name": project.name, "issues": len(issues)})
        return project

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

    def subsystems(self, pid: str) -> list[Subsystem]:
        self.project(pid)
        return self.store.list(K_SUBSYS, Subsystem, parent_id=pid)

    def evidence(self, ids: list[str]) -> list[Evidence]:
        return self.store.get_many(K_EVIDENCE, list(dict.fromkeys(ids)), Evidence)

    def demo_fixtures(self) -> list[DemoFixture]:
        f = self.settings.fixtures_dir
        manifest = str(f / "manifests" / "esp32_servo_demo.yaml")
        return [DemoFixture(label="Fault A firmware (servo pin set to GPIO19)",
                            repo_path=str(f / "esp32_servo_demo_fault_a"), manifest_path=manifest),
                DemoFixture(label="Correct firmware (GPIO18) — use for Fault B",
                            repo_path=str(f / "esp32_servo_demo"), manifest_path=manifest)]

    def replays(self) -> list[ReplayInfo]:
        return list_replays(self.settings.replay_dir)

    # ------------------------------------------------------------------ expectations

    def propose_expectation(self, pid: str) -> Expectation:
        g = self.graph(pid)
        analysis = self.store.get(K_ANALYSIS, pid, ProjectAnalysis)
        evs = self.store.list(K_EVIDENCE, Evidence, project_id=pid)
        exp = expmod.propose_expectation(pid, g.nodes, evs, [lit.text for lit in analysis.log_literals])
        if exp is None:
            raise ServiceError(422, "no_testable_component", "No servo component in the hardware graph to test")
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
        exp = exp.model_copy(update={**upd, "confirmed_by_engineer": True})
        exp = Expectation.model_validate(exp.model_dump())
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
        synthetic = False
        if req.source.kind == "replay":
            try:
                synthetic = load_replay(self.settings.replay_dir, req.source.scenario or "").synthetic
            except ReplayError as e:
                raise ServiceError(400, "replay_invalid", str(e)) from e
        else:
            raise ServiceError(501, "live_unavailable",
                               "Live serial/camera adapters are not implemented yet (milestone M3). Use a replay.")
        run = TestRun(id=_id("test"), project_id=pid, expectation_id=exp.id, attempt_kind=attempt_kind,
                      verifies_test_run_id=verifies, source=req.source, synthetic=synthetic, incident_id=incident_id)
        self.store.put(K_RUN, run)
        return run

    def test_run(self, run_id: str) -> TestRun:
        r = self.store.get(K_RUN, run_id, TestRun)
        if r is None:
            raise ServiceError(404, "not_found", f"test run {run_id} not found")
        return r

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
            obs, serial, evs = await self._collect(run, exp)
        except Exception as e:  # adapter failure: record honestly, never fabricate a result
            run.state = check_test(run.state, TestRunState.failed)
            run.error = f"{type(e).__name__}: {e}"
            run.ended_at_utc = utcnow()
            self.store.put(K_RUN, run)
            self._emit("error", pid, {"message": run.error}, test_run_id=run.id)
            return run

        result, rev = expmod.evaluate(exp, obs, serial, run.id)
        self.store.put(K_EVIDENCE, rev)
        run.result = result
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

    async def _collect(self, run: TestRun, exp: Expectation):
        stream = load_replay(self.settings.replay_dir, run.source.scenario or "")
        analysis = self.store.get(K_ANALYSIS, run.project_id, ProjectAnalysis)
        src = f"replay:{stream.scenario}"
        obs: list[Observation] = []
        serial: list[SerialEvent] = []
        evs: list[Evidence] = []
        t0 = run.started_at_utc
        n = 0
        async for ev in stream.play(self.settings.replay_speed):
            n += 1
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
                val = ev.data.get("angle_deg")
                eid = f"evidence:cv:{run.id}:{ev.data.get('frame', n)}"
                evs.append(Evidence(
                    id=eid, project_id=run.project_id, kind=EvidenceKind.cv_measurement,
                    epistemic=Epistemic.observed if q == "valid" else Epistemic.unknown, test_run_id=run.id,
                    provenance=prov, raw_ref=f"{src}#frame{ev.data.get('frame')}",
                    summary=(f"Servo angle {val}° at {ev.t_ms} ms" if q == "valid" else f"No valid angle at {ev.t_ms} ms ({q})"),
                    payload={"value": val, "quality": q, "elapsed_ms": ev.t_ms}))
                o = Observation(id=f"obs:{run.id}:{n}", project_id=run.project_id, test_run_id=run.id,
                                source_type="replay_cv", source_id=src, component_id=exp.component_id,
                                timestamp_utc=ts, elapsed_ms=ev.t_ms, metric="servo_angle_deg",
                                value=val if q == "valid" else None, unit="deg", measurement_quality=q,
                                evidence_ref=f"frame:{ev.data.get('frame')}", evidence_id=eid)
                obs.append(o)
                self.store.put(K_OBS, o, parent_id=run.id)
                self._emit("test.observation", run.project_id, o.model_dump(mode="json"), test_run_id=run.id)
        self.store.put_many(K_EVIDENCE, evs)
        return obs, serial, evs

    # ------------------------------------------------------------------ incidents

    def _create_incident(self, run: TestRun, exp: Expectation) -> str:
        g = self.graph(run.project_id)
        findings, new_ev = run_rules(exp, run.result, g.nodes, g.edges, run.id)
        self.store.put_many(K_EVIDENCE, new_ev)
        iid = _id("incident")
        _, _, wired_pin = config_vs_wiring(exp.component_id, g.nodes, g.edges)
        wired_label = next((n.label for n in g.nodes if n.id == wired_pin), None)
        hyps, actions = hypmod.build(iid, findings, wired_label, exp.component_id)
        codes = [f.code for f in findings]
        title = ("Measurement unavailable" if FaultCode.CAMERA_MEASUREMENT_UNAVAILABLE in codes
                 else f"Servo did not reach {exp.target:g}°")
        inc = Incident(id=iid, project_id=run.project_id, test_run_id=run.id, expectation_id=exp.id,
                       state=IncidentState.open, title=title, fault_codes=codes,
                       hypothesis_ids=[h.id for h in hyps], action_ids=[a.id for a in actions])
        inc.state = check_incident(inc.state, IncidentState.awaiting_engineer)
        self.store.put_many(K_HYP, hyps)
        self.store.put_many(K_ACTION, actions)
        self.store.put(K_INCIDENT, inc)
        self._emit("incident.created", run.project_id, {"incident_id": iid, "title": title,
                   "fault_codes": [c.value for c in codes]}, investigation_id=iid, test_run_id=run.id)
        self._emit("hypotheses.updated", run.project_id, {"hypothesis_ids": inc.hypothesis_ids}, investigation_id=iid)
        return iid

    def _attach_followup_run(self, run: TestRun) -> None:
        inc = self.incident(run.incident_id)
        outcome = run.result.outcome
        if run.attempt_kind == "verify":
            if outcome == ExpectationOutcome.passed:
                inc.state = check_incident(inc.state, IncidentState.resolved)
                inc.resolved_by_test_run_id = run.id
                self._emit("incident.resolved", inc.project_id, {"test_run_id": run.id},
                           investigation_id=inc.id, test_run_id=run.id)
            else:
                inc.state = check_incident(inc.state, IncidentState.awaiting_engineer)
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
        followups = [r for r in self.store.list(K_RUN, TestRun, project_id=inc.project_id) if r.incident_id == iid and r.id != run.id]
        ev_ids = [i for h in hyps for i in h.supporting_evidence_ids + h.contradicting_evidence_ids]
        ev_ids += [i for a in actions for i in a.evidence_ids]
        ev_ids += [run.result.evidence_id] + [i for f in run.result.facts for i in f.evidence_ids] if run.result else []
        ev_ids += [r.result.evidence_id for r in followups if r.result]
        ev_ids += [e.id for e in self.store.list(K_EVIDENCE, Evidence, project_id=inc.project_id)
                   if e.kind == EvidenceKind.engineer_assertion and e.payload.get("incident_id") == iid]
        followups.sort(key=lambda r: r.started_at_utc or r.ended_at_utc or utcnow())
        return InvestigationView(incident=inc, test_run=run, followup_runs=followups, hypotheses=hyps, actions=actions,
                                 evidence=self.evidence(ev_ids), highlights=self._highlights(inc, run, hyps))

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

    # ------------------------------------------------------------------ actions

    def execute_action(self, iid: str, action_id: str, source: ObservationSourceSpec | None) -> tuple[ActionResult, TestRun | None]:
        inc = self.incident(iid)
        action = self.store.get(K_ACTION, action_id, DiagnosticAction)
        if action is None or action.incident_id != iid:
            raise ServiceError(404, "not_found", f"action {action_id} not found")
        if inc.state in (IncidentState.resolved, IncidentState.inconclusive):
            raise ServiceError(409, "incident_closed", f"incident is {inc.state.value}")
        self._emit("action.started", inc.project_id, {"action_id": action_id}, investigation_id=iid)

        if action.kind == ActionKind.inspect_source and action.tool_name == "inspect_gpio_config":
            result = self._inspect_gpio(inc, action)
            run = None
        elif action.kind in (ActionKind.repeat_test, ActionKind.verify_fix):
            original = self.test_run(inc.test_run_id)
            kind = "verify" if action.kind == ActionKind.verify_fix else "repeat"
            run = self.create_test_run(inc.project_id, StartTestRequest(
                expectation_id=inc.expectation_id, source=source or original.source),
                attempt_kind=kind, verifies=original.id, incident_id=iid)
            if kind == "verify":
                inc.state = check_incident(inc.state, IncidentState.verifying)
                self.store.put(K_INCIDENT, inc)
            result = ActionResult(action_id=action_id, status="completed", test_run_id=run.id,
                                  summary=f"{'Verification' if kind == 'verify' else 'Repeat'} test {run.id} started "
                                          f"with the same confirmed expectation.")
        elif action.kind == ActionKind.request_manual_check:
            raise ServiceError(400, "manual_action", "Manual checks are recorded via /manual-results")
        else:
            raise ServiceError(400, "unsupported_action", f"action kind {action.kind.value} not executable yet")

        action.status = "completed"
        self.store.put(K_ACTION, action)
        self._emit("action.completed", inc.project_id, result.model_dump(mode="json"), investigation_id=iid)
        return result, run

    def _inspect_gpio(self, inc: Incident, action: DiagnosticAction) -> ActionResult:
        """Read-only: bounded source excerpts for the cited pin evidence + the manifest wiring entry."""
        project = self.project(inc.project_id)
        root = Path(project.repo_root)
        cited = self.evidence(action.evidence_ids)
        excerpts: list[SourceExcerpt] = []
        for ev in cited:
            if ev.kind != EvidenceKind.source_excerpt or not ev.provenance.file:
                continue
            path = resolve_inside(root, ev.provenance.file)
            lines = path.read_text(encoding="utf-8").splitlines()
            ln = ev.provenance.line_start or 1
            start = max(1, ln - 3)
            excerpts.append(SourceExcerpt(file=ev.provenance.file, line_start=start, lines=lines[start - 1: ln + 3],
                                          highlight_lines=[ln], evidence_id=ev.id))
        wiring = [ev for ev in cited if ev.kind == EvidenceKind.manifest_entry]
        out_ev = Evidence(id=f"evidence:tool:{action.id}:{uuid.uuid4().hex[:6]}", project_id=inc.project_id,
                          kind=EvidenceKind.tool_output, epistemic=Epistemic.observed,
                          summary=f"inspect_gpio_config: {len(excerpts)} source excerpt(s), {len(wiring)} wiring entr(y/ies)",
                          provenance=Provenance(source_id="tool:inspect_gpio_config"),
                          payload={"incident_id": inc.id, "action_id": action.id,
                                   "excerpts": [e.evidence_id for e in excerpts]})
        self.store.put(K_EVIDENCE, out_ev)
        summary = "; ".join(ev.summary for ev in cited if ev.kind in (EvidenceKind.source_excerpt, EvidenceKind.manifest_entry))
        return ActionResult(action_id=action.id, status="completed", summary=summary,
                            source_excerpts=excerpts, evidence=[*wiring, out_ev])

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
