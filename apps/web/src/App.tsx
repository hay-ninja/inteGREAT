import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  subscribeProject,
  type ActionResult,
  type DiagnosticAction,
  type Evidence,
  type Expectation,
  type GraphSnapshot,
  type Highlight,
  type IntegreatEvent,
  type InvestigationView,
  type Observation,
  type Project,
  type ReplayInfo,
  type SerialEvent,
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
import { BottomPanel } from "./components/observability/BottomPanel";
import { ExpectationCard, ImportScreen } from "./components/onboarding/Onboarding";

export default function App() {
  const [project, setProject] = useState<Project | null>(null);
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [subsystems, setSubsystems] = useState<Subsystem[]>([]);
  const [replays, setReplays] = useState<ReplayInfo[]>([]);
  const [scenario, setScenario] = useState("fault_a_wrong_gpio");
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
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence[]>([]);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [inspectResult, setInspectResult] = useState<ActionResult | null>(null);
  const [manualAction, setManualAction] = useState<DiagnosticAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fitKey, setFitKey] = useState("init");
  const runRef = useRef<string | null>(null);
  const incidentRef = useRef<string | null>(null);
  incidentRef.current = incidentId;

  const fail = useCallback((e: unknown) => setError(e instanceof Error ? e.message : String(e)), []);

  useEffect(() => {
    api.replays().then(setReplays).catch(() => setReplays([]));
  }, []);

  const refreshView = useCallback((iid: string) => {
    api.investigation(iid).then(setView).catch(fail);
  }, [fail]);

  // Live event stream → state
  useEffect(() => {
    if (!project) return;
    return subscribeProject(project.id, (ev) => {
      setEvents((prev) => (prev.some((p) => p.seq === ev.seq) ? prev : [...prev, ev]));
      const p = ev.payload as Record<string, unknown>;
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
        case "incident.resolved":
        case "hypotheses.updated":
        case "action.completed":
          if (ev.investigation_id && ev.investigation_id === incidentRef.current) refreshView(ev.investigation_id);
          break;
        case "error":
          setError(String(p.message));
          setBusy(false);
          break;
      }
    });
  }, [project, refreshView]);

  // On a fresh connection the server replays the whole timeline; reload the latest run's data once.
  useEffect(() => {
    if (run && run.state === "completed") {
      api.test(run.id).then((d) => {
        setObservations(d.observations);
        setSerial(d.serial);
      }).catch(() => undefined);
    }
  }, [run?.id, run?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  const doImport = async (repo: string, manifest: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.importProject(repo, manifest);
      const [g, subs] = await Promise.all([api.graph(p.id), api.subsystems(p.id)]);
      setProject(p);
      setGraph(g);
      setSubsystems(subs);
      setExpanded(new Set());
      setScenario(repo.includes("fault_a") ? "fault_a_wrong_gpio" : "fault_b_disconnected");
      setFitKey(p.id);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
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

  const toggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const revealNodes = (ids: string[]) => {
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
  };

  const runTest = async () => {
    if (!project || !expectation) return;
    setBusy(true);
    setError(null);
    setIncidentId(null);
    setView(null);
    try {
      const r = await api.startTest(project.id, expectation.id, { kind: "replay", scenario });
      runRef.current = r.id;
      setRun(r);
      setObservations([]);
      setSerial([]);
    } catch (e) {
      fail(e);
      setBusy(false);
    }
  };

  const runAction = async (a: DiagnosticAction) => {
    if (!incidentId) return;
    if (a.kind === "request_manual_check") {
      setManualAction(a);
      return;
    }
    setBusyAction(a.id);
    try {
      const needsSource = a.kind === "repeat_test" || a.kind === "verify_fix";
      const { result } = await api.executeAction(incidentId, a.id, needsSource ? { kind: "replay", scenario } : undefined);
      if (result.source_excerpts.length) setInspectResult(result);
      refreshView(incidentId);
    } catch (e) {
      fail(e);
    } finally {
      setBusyAction(null);
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

  // Before any test, still show static conflicts found at import (e.g. GPIO mismatch).
  const highlights: Highlight[] = useMemo(() => {
    if (view) return view.highlights;
    if (!project) return [];
    return project.issues
      .filter((i) => i.code === "GPIO_CONFIG_MISMATCH")
      .flatMap((i) =>
        [...i.related_edge_ids, ...i.related_node_ids].map((id) => ({
          element_id: id,
          style: "conflict" as const,
          reason: i.message,
        })),
      );
  }, [view, project]);

  const selectedNode = graph?.nodes.find((n) => n.id === selectedId) ?? null;
  useEffect(() => {
    if (!project || !selectedNode) return setSelectedEvidence([]);
    api.evidence(project.id, selectedNode.evidence_ids).then(setSelectedEvidence).catch(() => setSelectedEvidence([]));
  }, [project, selectedNode]);

  if (!project || !graph) {
    return (
      <>
        <ImportScreen onImport={doImport} busy={busy} />
        {error && <Toast msg={error} onClose={() => setError(null)} />}
      </>
    );
  }

  const crumbs = breadcrumb(graph, selectedId);
  const selectedReplay = replays.find((r) => r.id === scenario);
  const importNotes = project.issues.filter((i) => i.level !== "info");

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">inteGREAT</span>
        <span className="proj">{project.name}</span>
        <span className="device" title="Live serial/camera adapters arrive in milestone M3">
          Serial: <b className="off">not connected</b> · Camera: <b className="off">not connected</b>
        </span>
        <select value={focusSub} onChange={(e) => selectSubsystem(e.target.value)} aria-label="Select subsystem">
          <option value="">All subsystems</option>
          {subsystems.map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Observation source"
                title={selectedReplay?.description}>
          {replays.map((r) => (
            <option key={r.id} value={r.id}>
              {r.synthetic ? "Synthetic replay" : "Replay"}: {r.id}
            </option>
          ))}
        </select>
        <button className="action-btn" disabled={!expectation?.confirmed_by_engineer || busy} onClick={runTest}
                title={expectation?.confirmed_by_engineer ? "" : "Confirm a test expectation first"}>
          {busy ? "Running…" : "Run Test"}
        </button>
        <button className="ghost" onClick={() => { setProject(null); setGraph(null); setView(null); setRun(null); setEvents([]); setExpectation(null); }}>
          Change project
        </button>
      </header>

      <main className="main">
        <section className="graph-pane">
          <div className="graph-toolbar">
            <div className="crumbs">
              <span className="crumb" onClick={() => setSelectedId(null)}>System</span>
              {crumbs.map((c) => (
                <span key={c.id} className="crumb" onClick={() => setSelectedId(c.id)}>/ {c.label}</span>
              ))}
            </div>
            <input className="search" placeholder="Search nodes…" value={search} onChange={(e) => setSearch(e.target.value)} />
            <button className="ghost small" onClick={() => setExpanded(new Set(graph.nodes.filter((n) => n.kind === "subsystem" || n.kind === "source_module").map((n) => n.id)))}>
              Expand all
            </button>
            <button className="ghost small" onClick={() => setExpanded(new Set())}>Collapse</button>
          </div>
          <GraphView
            graph={graph}
            expanded={expanded}
            highlights={highlights}
            focusIds={focusIds}
            search={search}
            selectedId={selectedId}
            onToggle={toggle}
            onSelect={setSelectedId}
            fitKey={`${fitKey}-${expanded.size}`}
          />
          <Legend />
        </section>

        <aside className="side">
          <ExpectationCard projectId={project.id} expectation={expectation} onChange={setExpectation} onError={setError} />
          {view ? (
            <InvestigationPanel view={view} busyActionId={busyAction} onAction={runAction} onSelectNodes={revealNodes} />
          ) : run?.result?.outcome === "pass" ? (
            <div className="result result-pass">
              <b>PASS</b> — {run.result.reason}
              {run.synthetic && <div className="replay-note">Synthetic replay, not live hardware.</div>}
            </div>
          ) : null}
          {selectedNode && (
            <div className="node-detail">
              <h4>{selectedNode.label} <span className="dim small">{selectedNode.kind} · {selectedNode.verification}</span></h4>
              {Object.keys(selectedNode.attributes ?? {}).length > 0 && (
                <div className="attrs">
                  {Object.entries(selectedNode.attributes ?? {}).map(([k, v]) => (
                    <span key={k}>{k}: <b>{String(v)}</b></span>
                  ))}
                </div>
              )}
              {selectedEvidence.length > 0 ? (
                <EvidenceList title="Evidence" ids={selectedEvidence.map((e) => e.id)} evById={new Map(selectedEvidence.map((e) => [e.id, e]))} />
              ) : (
                <div className="dim small">No direct evidence attached to this node.</div>
              )}
            </div>
          )}
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
        events={events}
        run={run}
        observations={observations}
        serial={serial}
        expectation={expectation}
        onSelectEvent={(e) => {
          if (e.investigation_id) {
            setIncidentId(e.investigation_id);
            refreshView(e.investigation_id);
          }
        }}
      />

      {inspectResult && <InspectResultModal result={inspectResult} onClose={() => setInspectResult(null)} />}
      {manualAction && <ManualCheckModal action={manualAction} onSubmit={submitManual} onClose={() => setManualAction(null)} />}
      {error && <Toast msg={error} onClose={() => setError(null)} />}
    </div>
  );
}

function Toast({ msg, onClose }: { msg: string; onClose: () => void }) {
  return (
    <div className="toast" role="alert">
      <span>{msg}</span>
      <button className="ghost small" onClick={onClose}>Dismiss</button>
    </div>
  );
}
