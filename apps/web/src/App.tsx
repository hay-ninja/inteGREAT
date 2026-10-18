import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  api,
  subscribeProject,
  type ActionResult,
  type AgentStatus,
  type DeviceStatus,
  type DiagnosticAction,
  type Evidence,
  type Expectation,
  type GraphSnapshot,
  type Highlight,
  type IntegreatEvent,
  type InvestigationView,
  type Observation,
  type ObservationSourceSpec,
  type PermissionCategory,
  type Project,
  type SerialEvent,
  type SourceOptions,
  type Subsystem,
  type TestRun,
} from "./lib/api";
import { GraphView, Legend } from "./components/graph/GraphView";
import { breadcrumb } from "./components/graph/visibleGraph";
import {
  EvidenceList,
  InspectResultModal,
  InvestigationPanel,
  ManualCheckModal,
} from "./components/investigation/InvestigationPanel";
import {
  AgentsPanel,
  ApprovalModal,
  AuditLog,
  MessageBox,
  PermissionsPanel,
  ToolOutputModal,
} from "./components/investigation/Extras";
import { BottomPanel, type Tab } from "./components/observability/BottomPanel";
import { DevicesPanel } from "./components/observability/DevicesPanel";
import { ExpectationCard, ImportScreen, type ImportArgs } from "./components/onboarding/Onboarding";

const LAST_PROJECT = "integreat.lastProject";
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => {
    try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* private mode */ }
  },
};

function parseSource(v: string): ObservationSourceSpec {
  const [kind, scenario] = v.split(":");
  return kind === "live" ? { kind: "live" } : { kind: kind as "replay" | "sim", scenario };
}

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [subsystems, setSubsystems] = useState<Subsystem[]>([]);
  const [sources, setSources] = useState<SourceOptions>({ replays: [], sim: [] });
  const [source, setSource] = useState("sim:connected");
  const [expectation, setExpectation] = useState<Expectation | null>(null);
  const [run, setRun] = useState<TestRun | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [serial, setSerial] = useState<SerialEvent[]>([]);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [view, setView] = useState<InvestigationView | null>(null);
  const [events, setEvents] = useState<IntegreatEvent[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [focusSub, setFocusSub] = useState<string>("");
  const [focusIds, setFocusIds] = useState<Set<string> | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [inspectResult, setInspectResult] = useState<ActionResult | null>(null);
  const [toolOutput, setToolOutput] = useState<ActionResult | null>(null);
  const [manualAction, setManualAction] = useState<DiagnosticAction | null>(null);
  const [approval, setApproval] = useState<{ action: DiagnosticAction; category: string; tool: string } | null>(null);
  const [devices, setDevices] = useState<DeviceStatus | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [tab, setTab] = useState<Tab>("plot");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fitKey, setFitKey] = useState("init");
  const runRef = useRef<string | null>(null);
  const incidentRef = useRef<string | null>(null);
  incidentRef.current = incidentId;

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);

  useEffect(() => {
    api.sources().then(setSources).catch(() => undefined);
    api.agentStatus().then(setAgentStatus).catch(() => undefined);
  }, []);

  // Device status: poll gently (ports appear/disappear when boards are plugged in).
  useEffect(() => {
    const tick = () => api.devices().then(setDevices).catch(() => undefined);
    tick();
    const t = window.setInterval(tick, 4000);
    return () => window.clearInterval(t);
  }, []);

  const refreshView = useCallback((iid: string) => {
    api.investigation(iid).then(setView).catch(fail);
  }, [fail]);

  const loadProject = useCallback(async (p: Project, fresh: boolean) => {
    const [g, subs, exps, incs] = await Promise.all([
      api.graph(p.id), api.subsystems(p.id), api.expectations(p.id), api.incidents(p.id)]);
    setProject(p);
    setGraph(g);
    setSubsystems(subs);
    setEvents([]);
    setRun(null);
    setObservations([]);
    setSerial([]);
    setExpectation([...exps].reverse().find((e) => e.confirmed_by_engineer) ?? exps[exps.length - 1] ?? null);
    const lastInc = fresh ? null : incs[incs.length - 1] ?? null;
    setIncidentId(lastInc?.id ?? null);
    setView(null);
    if (lastInc) refreshView(lastInc.id);
    setExpanded(new Set());
    setFocusIds(null);
    setFocusSub("");
    setFitKey(`${p.id}-${Date.now()}`);
    store.set(LAST_PROJECT, p.id);
  }, [refreshView]);

  // Restore the last project after a reload.
  useEffect(() => {
    const pid = store.get(LAST_PROJECT);
    if (pid) api.project(pid).then((p) => loadProject(p, false)).catch(() => store.set(LAST_PROJECT, null));
  }, [loadProject]);

  const reloadGraph = useCallback(async (pid: string) => {
    const [p, g, subs] = await Promise.all([api.project(pid), api.graph(pid), api.subsystems(pid)]);
    setProject(p);
    setGraph(g);
    setSubsystems(subs);
  }, []);

  // Live event stream → state
  useEffect(() => {
    if (!project) return;
    const pid = project.id;
    return subscribeProject(pid, (ev) => {
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      const p = ev.payload as Record<string, unknown>;
      const mine = ev.investigation_id && ev.investigation_id === incidentRef.current;
      switch (ev.type) {
        case "test.started":
          runRef.current = ev.test_run_id ?? null;
          setRun(p as unknown as TestRun);
          setObservations([]);
          setSerial([]);
          break;
        case "test.observation":
          if (ev.test_run_id === runRef.current) setObservations((o) => [...o, p as unknown as Observation]);
          break;
        case "test.serial":
          if (ev.test_run_id === runRef.current) setSerial((s) => [...s, p as unknown as SerialEvent]);
          break;
        case "test.completed": {
          const r = p as unknown as TestRun;
          if (r.id === runRef.current) setRun(r);
          if (r.incident_id) {
            setIncidentId(r.incident_id);
            refreshView(r.incident_id);
          }
          setBusy(false);
          break;
        }
        case "graph.updated":
          reloadGraph(pid).catch(fail);
          break;
        case "hypotheses.updated":
          if (mine) {
            refreshView(ev.investigation_id!);
            if (p.round !== undefined) setDiagnosing(false);
          }
          break;
        case "incident.resolved":
        case "action.completed":
        case "agent.reported":
        case "agent.started":
        case "permissions.updated":
        case "message.added":
          if (mine) refreshView(ev.investigation_id!);
          break;
        case "error":
          setError(String(p.message));
          setBusy(false);
          break;
      }
    });
  }, [project, refreshView, reloadGraph, fail]);

  // When a run completes, make sure we have its full data (e.g. after reconnect).
  useEffect(() => {
    if (run && run.state === "completed") {
      api.test(run.id).then((d) => { setObservations(d.observations); setSerial(d.serial); }).catch(() => undefined);
    }
  }, [run?.id, run?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const doImport = async (args: ImportArgs) => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.importProject(args);
      await loadProject(p, true);
      setSource(args.repo_path.includes("fault_a") ? "sim:connected" : "sim:signal_disconnected");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const rescan = async () => {
    if (!project) return;
    try {
      const p = await api.rescan(project.id);
      await reloadGraph(p.id);
      setNotice(`Rescanned repository → graph v${p.graph_version}`);
    } catch (e) {
      fail(e);
    }
  };

  const selectSubsystem = async (sid: string) => {
    setFocusSub(sid);
    if (!project) return;
    if (!sid) {
      setFocusIds(null);
      setFitKey(`all-${Date.now()}`);
      return;
    }
    setExpanded((e) => new Set([...e, sid]));
    try {
      const scoped = await api.graph(project.id, sid);
      setFocusIds(new Set(scoped.nodes.map((n) => n.id)));
      setSelectedId(sid);
      setFitKey(`${sid}-${Date.now()}`);
    } catch (e) {
      fail(e);
    }
  };

  const toggle = useCallback((id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    }), []);

  const revealNodes = (ids: string[], focus = false) => {
    if (!graph || !ids.length) return;
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const exp = new Set(expanded);
    for (const id of ids) {
      let cur = byId.get(id);
      while (cur?.parent_id) {
        exp.add(cur.parent_id);
        cur = byId.get(cur.parent_id);
      }
    }
    setExpanded(exp);
    setSelectedId(ids[0]);
    if (focus) {
      setFocusIds(new Set(ids));
      setFitKey(`focus-${Date.now()}`);
    }
  };

  const runTest = async () => {
    if (!project || !expectation) return;
    setBusy(true);
    setError(null);
    setIncidentId(null);
    setView(null);
    setTab("plot");
    try {
      const r = await api.startTest(project.id, expectation.id, parseSource(source));
      runRef.current = r.id;
      setRun(r);
      setObservations([]);
      setSerial([]);
    } catch (e) {
      fail(e);
      setBusy(false);
    }
  };

  const runAction = async (a: DiagnosticAction, approveOnce = false) => {
    if (!incidentId) return;
    if (a.kind === "request_manual_check") {
      setManualAction(a);
      return;
    }
    setBusyAction(a.id);
    try {
      const needsSource = a.kind === "repeat_test" || a.kind === "verify_fix";
      const { result } = await api.executeAction(incidentId, a.id, needsSource ? parseSource(source) : undefined, approveOnce);
      if (result.source_excerpts.length) setInspectResult(result);
      else if (result.node_ids.length) {
        revealNodes(result.node_ids, true);
        setNotice(result.summary);
      } else if (result.lines.length || a.kind === "run_readonly_tool") setToolOutput(result);
      refreshView(incidentId);
    } catch (e) {
      if (e instanceof ApiError && e.code === "permission_required") {
        setApproval({ action: a, category: String(e.details.category), tool: String(e.details.tool) });
      } else fail(e);
    } finally {
      setBusyAction(null);
    }
  };

  const setPermission = async (c: PermissionCategory, granted: boolean) => {
    if (!incidentId) return;
    try {
      await api.setPermission(incidentId, c, granted);
      refreshView(incidentId);
    } catch (e) {
      fail(e);
    }
  };

  const diagnose = async () => {
    if (!incidentId) return;
    setDiagnosing(true);
    try {
      await api.diagnose(incidentId);
      refreshView(incidentId);
    } catch (e) {
      setDiagnosing(false);
      fail(e);
    }
  };

  const submitManual = async (result: string, note: string) => {
    if (!incidentId || !manualAction) return;
    try {
      setView(await api.manualResult(incidentId, manualAction.id, result, note || undefined));
      setManualAction(null);
    } catch (e) {
      fail(e);
    }
  };

  const saveReplay = async (runId: string) => {
    const name = `capture_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
    try {
      const r = await api.saveReplay(runId, name);
      setNotice(`Saved replay "${r.id}"${r.synthetic ? " (synthetic)" : ""}`);
      api.sources().then(setSources).catch(() => undefined);
    } catch (e) {
      fail(e);
    }
  };

  // Before any test, still show static conflicts found at import (e.g. GPIO mismatch).
  const highlights: Highlight[] = useMemo(() => {
    if (view) return view.highlights;
    if (!project) return [];
    return project.issues
      .filter((i) => i.code === "GPIO_CONFIG_MISMATCH")
      .flatMap((i) => [...i.related_edge_ids, ...i.related_node_ids].map((id) => ({
        element_id: id, style: "conflict" as const, reason: i.message })));
  }, [view, project]);

  const selectedNode = graph?.nodes.find((n) => n.id === selectedId) ?? null;
  const selectedEdges = graph?.edges.filter((e) => selectedEdgeIds.includes(e.id)) ?? [];
  useEffect(() => {
    if (!project) return;
    const ids = selectedEdges.length ? selectedEdges.flatMap((e) => e.evidence_ids) : selectedNode?.evidence_ids ?? [];
    api.evidence(project.id, ids).then(setSelectedEvidence).catch(() => setSelectedEvidence([]));
  }, [project, selectedNode, selectedEdgeIds.join("|"), graph?.version]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!project || !graph) {
    return (
      <>
        <ImportScreen onImport={doImport} onOpen={(p) => loadProject(p, false).catch(fail)} busy={busy} onError={setError} />
        {error && <Toast msg={error} onClose={() => setError(null)} />}
      </>
    );
  }

  const crumbs = breadcrumb(graph, selectedId);
  const importNotes = project.issues.filter((i) => i.level !== "info");
  const labels = new Map(graph.nodes.map((n) => [n.id, n.label]));
  const liveReady = !!devices?.camera.connected && !!devices.camera.calibrated;

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">inteGREAT</span>
        <span className="proj" title={project.repo_root}>
          {project.name} <span className="dim small">v{project.graph_version} · {project.hardware_source}</span>
        </span>
        <span className="device" title="Device status (see Devices tab)">
          Serial: <b className={devices?.serial.connected ? "on" : "off"}>{devices?.serial.connected ? devices.serial.port : "—"}</b>
          {" · "}Camera: <b className={devices?.camera.connected ? "on" : "off"}>
            {devices?.camera.connected ? (devices.camera.calibrated ? "ready" : "uncalibrated") : "—"}</b>
          {" · "}AI: <b className={agentStatus?.available ? "on" : "off"}>{agentStatus?.available ? "on" : "off"}</b>
        </span>
        <select value={focusSub} onChange={(e) => selectSubsystem(e.target.value)} aria-label="Select subsystem">
          <option value="">All subsystems</option>
          {subsystems.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Observation source">
          <optgroup label="Simulated rig (synthetic)">
            {sources.sim.map((r) => <option key={r.id} value={`sim:${r.id}`} title={r.description}>Sim: {r.id}</option>)}
          </optgroup>
          <optgroup label="Replay">
            {sources.replays.map((r) => (
              <option key={r.id} value={`replay:${r.id}`} title={r.description}>
                {r.synthetic ? "Synthetic replay" : "Recorded"}: {r.id}
              </option>
            ))}
          </optgroup>
          <optgroup label="Hardware">
            <option value="live">Live rig{liveReady ? "" : " (connect devices first)"}</option>
          </optgroup>
        </select>
        <button className="action-btn" disabled={!expectation?.confirmed_by_engineer || busy} onClick={runTest}
                title={expectation?.confirmed_by_engineer ? "" : "Confirm a test expectation first"}>
          {busy ? "Running…" : "Run Test"}
        </button>
        <button className="ghost" onClick={rescan} title="Re-read the repository (e.g. after fixing firmware)">Rescan</button>
        <button className="ghost" onClick={() => { store.set(LAST_PROJECT, null); setProject(null); setGraph(null);
                                                   setView(null); setRun(null); setEvents([]); setExpectation(null); }}>
          Projects
        </button>
      </header>

      <main className="main">
        <section className="graph-pane">
          <div className="graph-toolbar">
            <div className="crumbs">
              <span className="crumb" onClick={() => setSelectedId(null)}>System</span>
              {crumbs.map((c) => <span key={c.id} className="crumb" onClick={() => setSelectedId(c.id)}>/ {c.label}</span>)}
            </div>
            <input className="search" placeholder="Search nodes…" value={search} onChange={(e) => setSearch(e.target.value)} />
            {focusIds && <button className="ghost small" onClick={() => { setFocusIds(null); setFocusSub(""); }}>Clear focus</button>}
            <button className="ghost small" onClick={() => setExpanded(new Set(graph.nodes.filter((n) =>
              n.kind === "subsystem" || n.kind === "source_module").map((n) => n.id)))}>Expand all</button>
            <button className="ghost small" onClick={() => setExpanded(new Set())}>Collapse</button>
          </div>
          <GraphView graph={graph} expanded={expanded} highlights={highlights} focusIds={focusIds} search={search}
                     selectedId={selectedId} onToggle={toggle}
                     onSelect={(id) => { setSelectedId(id); setSelectedEdgeIds([]); }}
                     onEdgeSelect={(ids) => { setSelectedEdgeIds(ids); setSelectedId(null); }}
                     fitKey={`${fitKey}-${expanded.size}`} />
          <Legend />
        </section>

        <aside className="side">
          <ExpectationCard projectId={project.id} expectation={expectation} onChange={setExpectation} onError={setError} />
          {selectedEdges.length > 0 && (
            <div className="node-detail">
              <h4>Connection</h4>
              {selectedEdges.map((e) => (
                <div key={e.id} className="edge-detail">
                  <div>
                    {labels.get(e.source_id)} <b>—{e.relation}→</b> {labels.get(e.target_id)}
                    <span className="dim small"> · {e.origin.replace("_", " ")} · {e.verification}</span>
                  </div>
                  {e.origin === "declared_wiring" && (
                    <div className="row">
                      {e.verification !== "verified" ? (
                        <button className="action-btn" onClick={() => api.verifyWiring(project.id, e.id, "verified",
                          "Engineer confirmed physical connection").then(() => reloadGraph(project.id)).catch(fail)}>
                          I checked it: mark verified
                        </button>
                      ) : (
                        <button className="ghost" onClick={() => api.verifyWiring(project.id, e.id, "unverified")
                          .then(() => reloadGraph(project.id)).catch(fail)}>Mark unverified</button>
                      )}
                    </div>
                  )}
                  {e.origin !== "declared_wiring" && (
                    <div className="dim small">From static analysis — not something to physically verify.</div>
                  )}
                </div>
              ))}
              <EvidenceList title="Evidence" ids={selectedEvidence.map((e) => e.id)}
                            evById={new Map(selectedEvidence.map((e) => [e.id, e]))} />
            </div>
          )}
          {selectedNode && !selectedEdges.length && (
            <div className="node-detail">
              <h4>{selectedNode.label} <span className="dim small">{selectedNode.kind} · {selectedNode.verification}</span></h4>
              {Object.keys(selectedNode.attributes ?? {}).length > 0 && (
                <div className="attrs">
                  {Object.entries(selectedNode.attributes ?? {}).map(([k, v]) => <span key={k}>{k}: <b>{String(v)}</b></span>)}
                </div>
              )}
              {selectedEvidence.length > 0 ? (
                <EvidenceList title="Evidence" ids={selectedEvidence.map((e) => e.id)}
                              evById={new Map(selectedEvidence.map((e) => [e.id, e]))} />
              ) : <div className="dim small">No direct evidence attached to this node.</div>}
            </div>
          )}
          {view ? (
            <>
              <InvestigationPanel view={view} busyActionId={busyAction} onAction={(a) => runAction(a)}
                                  onSelectNodes={(ids) => revealNodes(ids)} />
              <AgentsPanel view={view} status={agentStatus} busy={diagnosing} onDiagnose={diagnose}
                           onAction={(id) => { const a = view.actions.find((x) => x.id === id); if (a) runAction(a); }} />
              <PermissionsPanel view={view} onToggle={setPermission} />
              <MessageBox view={view} onSend={async (t) => { setView(await api.message(view.incident.id, t)); }} />
            </>
          ) : run?.result?.outcome === "pass" ? (
            <div className="result result-pass">
              <b>PASS</b> — {run.result.reason}
              {run.synthetic && <div className="replay-note">Synthetic data, not live hardware.</div>}
            </div>
          ) : null}
          {importNotes.length > 0 && (
            <div className="notes">
              <h4>Import notes</h4>
              {importNotes.map((i, k) => (
                <div key={k} className={`note note-${i.level}`} onClick={() => revealNodes(i.related_node_ids)}>
                  <b>{i.code}</b> {i.message}
                  {i.file && <span className="cite"> {i.file}:{i.line}</span>}
                </div>
              ))}
            </div>
          )}
        </aside>
      </main>

      <BottomPanel
        events={events} run={run} observations={observations} serial={serial} expectation={expectation}
        tab={tab} onTab={setTab} onSaveReplay={saveReplay}
        devices={<DevicesPanel status={devices} onStatus={setDevices} onError={setError} />}
        audit={<AuditLog calls={view?.tool_calls ?? []} />}
        onSelectEvent={(e) => { if (e.investigation_id) { setIncidentId(e.investigation_id); refreshView(e.investigation_id); } }}
      />

      {inspectResult && <InspectResultModal result={inspectResult} onClose={() => setInspectResult(null)} />}
      {toolOutput && <ToolOutputModal result={toolOutput} onClose={() => setToolOutput(null)} />}
      {manualAction && <ManualCheckModal action={manualAction} onSubmit={submitManual} onClose={() => setManualAction(null)} />}
      {approval && (
        <ApprovalModal category={approval.category} tool={approval.tool}
          onGrant={async () => { const a = approval.action; setApproval(null);
                                 await setPermission(approval.category as PermissionCategory, true); runAction(a); }}
          onOnce={() => { const a = approval.action; setApproval(null); runAction(a, true); }}
          onCancel={() => setApproval(null)} />
      )}
      {notice && <Toast msg={notice} kind="info" onClose={() => setNotice(null)} />}
      {error && <Toast msg={error} onClose={() => setError(null)} />}
    </div>
  );
}

function Toast({ msg, onClose, kind = "error" }: { msg: string; onClose: () => void; kind?: "error" | "info" }) {
  useEffect(() => {
    if (kind !== "info") return;
    const t = window.setTimeout(onClose, 5000);
    return () => window.clearTimeout(t);
  }, [kind, onClose]);
  return (
    <div className={`toast ${kind}`} role={kind === "error" ? "alert" : "status"}>
      <span>{msg}</span>
      <button className="ghost small" onClick={onClose}>Dismiss</button>
    </div>
  );
}
