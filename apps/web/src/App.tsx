import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Layout, LayoutContent, LayoutFooter, LayoutHeader, LayoutPanel } from "@astryxdesign/core/Layout";
import { VStack } from "@astryxdesign/core/VStack";
import { useToast } from "@astryxdesign/core/Toast";
import { Button } from "@astryxdesign/core/Button";
import {
  ApiError,
  api,
  subscribeProject,
  type ActionResult,
  type AgentStatus,
  type DeviceStatus,
  type DiagnosticAction,
  type Expectation,
  type Evidence,
  type GraphLayer,
  type GraphSnapshot,
  type Highlight,
  type IntegreatEvent,
  type InvestigationView,
  type Observation,
  type PermissionCategory,
  type Project,
  type SerialEvent,
  type SourceOptions,
  type Subsystem,
  type TestRun,
} from "./lib/api";
import { GraphView, type CanvasMode } from "./components/graph/GraphView";
import { EventFlowView } from "./components/flow/EventFlowView";
import { FlowPanel } from "./components/flow/FlowPanel";
import { SelectionCard } from "./components/flow/SelectionCard";
import { ProjectReview } from "./components/flow/ProjectReview";
import { RigSetupDialog } from "./components/setup/RigSetupDialog";
import { parseSource } from "./components/flow/common";
import { BottomDrawer, type DrawerTab } from "./components/drawer/BottomDrawer";
import { TopBar } from "./components/shell/TopBar";
import { ImportScreen, type ImportArgs } from "./components/shell/ImportScreen";
import { ApprovalDialog, EvidenceDialog, GraphInspector, InspectDialog, ManualCheckDialog, RepeatTestDialog, ToolOutputDialog } from "./components/dialogs/Dialogs";
import { RepairDialog } from "./components/dialogs/RepairDialog";

const LAST_PROJECT = "integreat.lastProject";
const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => {
    try { if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch { /* private mode */ }
  },
};

export default function App() {
  const toast = useToast();
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
  const [focusSub, setFocusSub] = useState("");
  const [focusIds, setFocusIds] = useState<Set<string> | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [inspect, setInspect] = useState<ActionResult | null>(null);
  const [toolOutput, setToolOutput] = useState<ActionResult | null>(null);
  const [manual, setManual] = useState<DiagnosticAction | null>(null);
  const [repeat, setRepeat] = useState<DiagnosticAction | null>(null);
  const [approval, setApproval] = useState<{ action: DiagnosticAction; category: string; tool: string } | null>(null);
  const [devices, setDevices] = useState<DeviceStatus | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [diagnosing, setDiagnosing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("angle");
  const [fitKey, setFitKey] = useState("init");
  const [rigSetupOpen, setRigSetupOpen] = useState(false);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [layer, setLayer] = useState<GraphLayer>("combined");
  const [mode, setMode] = useState<CanvasMode>("deps");
  const [flowSeq, setFlowSeq] = useState(0);
  const [repairOpen, setRepairOpen] = useState(false);
  const runRef = useRef<string | null>(null);
  const incidentRef = useRef<string | null>(null);
  const projectRef = useRef<string | null>(null);
  const scopeRef = useRef("");
  const loadVersion = useRef(0);
  incidentRef.current = incidentId;
  scopeRef.current = focusSub;

  const fail = useCallback((e: unknown) => {
    toast({ body: e instanceof Error ? e.message : String(e), type: "error" });
  }, [toast]);
  const notify = useCallback((body: string) => { toast({ body, type: "info" }); }, [toast]);

  useEffect(() => {
    api.sources().then(setSources).catch(() => undefined);
    api.agentStatus().then(setAgentStatus).catch(() => undefined);
    const tick = () => api.devices().then(setDevices).catch(() => undefined);
    tick();
    const t = window.setInterval(tick, 4000);
    return () => window.clearInterval(t);
  }, []);

  const refreshView = useCallback((iid: string) => {
    api.investigation(iid).then((v) => { if (incidentRef.current === iid) setView(v); }).catch((e) => { if (incidentRef.current === iid) fail(e); });
  }, [fail]);

  const loadProject = useCallback(async (p: Project, fresh: boolean) => {
    const version = ++loadVersion.current;
    const [g, subs, exps, incs] = await Promise.all([api.graph(p.id), api.subsystems(p.id), api.expectations(p.id), api.incidents(p.id)]);
    const preferredScope = g.nodes.find((n) => n.kind === "component" && n.subsystem_id)?.subsystem_id ?? subs[0]?.id;
    const scoped = preferredScope ? await api.graph(p.id, preferredScope) : null;
    if (version !== loadVersion.current) return;
    projectRef.current = p.id;
    setProject(p); setGraph(g); setSubsystems(subs); setEvents([]); setRun(null); runRef.current = null; setObservations([]); setSerial([]);
    setDrawerOpen(false); setDrawerTab("angle"); setBusy(false); setBusyAction(null); setDiagnosing(false);
    const lastInc = fresh ? null : incs[incs.length - 1] ?? null;
    const open = lastInc;
    setExpectation(exps.find((e) => e.id === open?.expectation_id)
      ?? [...exps].reverse().find((e) => e.confirmed_by_engineer) ?? exps[exps.length - 1] ?? null);
    incidentRef.current = open?.id ?? null; setIncidentId(open?.id ?? null);
    setView(null);
    if (open) refreshView(open.id);
    // Start one level in: subsystems expanded so modules are visible.
    setExpanded(new Set(subs.map((s) => s.id)));
    setFocusIds(scoped ? new Set(scoped.nodes.map((n) => n.id)) : null);
    setFocusSub(preferredScope ?? ""); setSelectedId(null); setSelectedEdgeIds([]); setEvidence(null);
    setFitKey(`${p.id}-${Date.now()}`);
    store.set(LAST_PROJECT, p.id);
  }, [refreshView]);

  useEffect(() => {
    const pid = store.get(LAST_PROJECT);
    if (pid) api.project(pid).then((p) => loadProject(p, false)).catch(() => store.set(LAST_PROJECT, null));
  }, [loadProject]);

  const reloadGraph = useCallback(async (pid: string) => {
    const [p, g, subs] = await Promise.all([api.project(pid), api.graph(pid), api.subsystems(pid)]);
    const scope = scopeRef.current;
    const scoped = scope && subs.some((s) => s.id === scope) ? await api.graph(pid, scope) : null;
    if (projectRef.current !== pid) return;
    setProject(p); setGraph(g); setSubsystems(subs);
    if (scopeRef.current === scope) {
      setFocusIds(scoped ? new Set(scoped.nodes.map((n) => n.id)) : null);
      if (scope && !scoped) { scopeRef.current = ""; setFocusSub(""); }
    }
  }, []);

  // Live event stream
  useEffect(() => {
    if (!project) return;
    const pid = project.id;
    return subscribeProject(pid, (ev) => {
      setEvents((prev) => (prev.some((x) => x.seq === ev.seq) ? prev : [...prev, ev]));
      const p = ev.payload as Record<string, unknown>;
      const mine = ev.investigation_id && ev.investigation_id === incidentRef.current;
      switch (ev.type) {
        case "test.started":
          runRef.current = ev.test_run_id ?? null;
          setRun(p as unknown as TestRun); setObservations([]); setSerial([]); setFlowSeq((s) => s + 1);
          break;
        case "test.observation":
          if (ev.test_run_id === runRef.current) setObservations((o) => [...o, p as unknown as Observation]);
          setFlowSeq((s) => s + 1);
          break;
        case "test.serial":
          if (ev.test_run_id === runRef.current) setSerial((s) => [...s, p as unknown as SerialEvent]);
          setFlowSeq((s) => s + 1);
          break;
        case "test.completed": {
          const r = p as unknown as TestRun;
          if (r.id === runRef.current) setRun(r);
          if (r.incident_id) { incidentRef.current = r.incident_id; setIncidentId(r.incident_id); refreshView(r.incident_id); }
          setBusy(false); setFlowSeq((s) => s + 1);
          break;
        }
        case "graph.updated": reloadGraph(pid).catch(fail); break;
        case "hypotheses.updated":
          if (mine) { refreshView(ev.investigation_id!); if (p.round !== undefined) setDiagnosing(false); }
          break;
        case "incident.resolved": case "action.completed": case "agent.reported": case "agent.started":
        case "permissions.updated": case "message.added": case "test.verification_completed":
        case "repair.requested": case "repair.updated":
          if (mine) refreshView(ev.investigation_id!);
          break;
        case "error": fail(String(p.message)); setBusy(false); break;
      }
    });
  // Graph rescans replace project metadata. Reconnecting for that would replay graph.updated
  // from seq 0, rescan the metadata again, and create an unbounded reconnect/refetch loop.
  }, [project?.id, refreshView, reloadGraph, fail]);

  useEffect(() => {
    let current = true;
    if (run?.state === "completed") api.test(run.id).then((d) => {
      if (current && runRef.current === run.id) { setObservations(d.observations); setSerial(d.serial); }
    }).catch(() => undefined);
    return () => { current = false; };
  }, [run?.id, run?.state]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!view || runRef.current) return;
    const restored = view.followup_runs[view.followup_runs.length - 1] ?? view.test_run;
    runRef.current = restored.id;
    setRun(restored);
    setSource(restored.source.kind === "live" ? "live" : `${restored.source.kind}:${restored.source.scenario}`);
  }, [view]);

  // Keyboard layer (ux-blueprint Part 4). Space triggers the single primary action,
  // 1–4 jump to chapters, D/E switch canvas modes, H/S/C switch graph layers.
  // ←/→ event scrubbing lives in EventFlowView; Esc is handled by Astryx dialogs.
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (!project || ev.metaKey || ev.ctrlKey || ev.altKey) return;
      const el = ev.target as HTMLElement;
      if (el.closest?.("input, textarea, select, [contenteditable]") || el.closest?.("[role='dialog'], dialog")) return;
      if (ev.key === " ") {
        const btn = document.querySelector<HTMLButtonElement>(".flow-primary:not(:disabled)");
        if (btn) { ev.preventDefault(); btn.click(); }
      } else if (/^[1-4]$/.test(ev.key)) {
        const tabs = document.querySelectorAll<HTMLButtonElement>(".chapter[role='tab']");
        tabs[Number(ev.key) - 1]?.click();
      } else if (ev.key === "d" || ev.key === "D") {
        setMode("deps");
      } else if (ev.key === "e" || ev.key === "E") {
        setMode("flow");
      } else if (ev.key === "h" || ev.key === "H") {
        setLayer("hardware");
      } else if (ev.key === "s" || ev.key === "S") {
        setLayer("software");
      } else if (ev.key === "c" || ev.key === "C") {
        setLayer("combined");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [project]);

  // ------------------------------------------------------------------ actions

  const doImport = async (args: ImportArgs) => {
    setBusy(true);
    try {
      const p = await api.importProject(args);
      await loadProject(p, true);
      setSource(args.repo_path.includes("fault_a") ? "sim:connected" : "sim:signal_disconnected");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const runTest = async () => {
    if (!project || !expectation) return;
    const pid = project.id;
    setBusy(true); incidentRef.current = null; setIncidentId(null); setView(null);
    setDrawerTab("angle"); setDrawerOpen(true);
    try {
      const r = await api.startTest(pid, expectation.id, parseSource(source));
      if (projectRef.current !== pid) return;
      runRef.current = r.id; setRun(r); setObservations([]); setSerial([]);
    } catch (e) { if (projectRef.current === pid) { fail(e); setBusy(false); } }
  };

  const revealNodes = (ids: string[], focus = false) => {
    if (!graph || !ids.length) return;
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    const exp = new Set(expanded);
    for (const id of ids) {
      let cur = byId.get(id);
      while (cur?.parent_id) { exp.add(cur.parent_id); cur = byId.get(cur.parent_id); }
    }
    setExpanded(exp); setSelectedId(ids[0]); setSelectedEdgeIds([]);
    if (focus) { setFocusIds((current) => current ? new Set([...current, ...ids]) : null); setFitKey(`focus-${Date.now()}`); }
  };

  const showEvidence = (e: Evidence) => {
    setEvidence(e); setSelectedId(null); setSelectedEdgeIds([]);
    if (!graph) return;
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    setExpanded((current) => {
      const next = new Set(current);
      for (const n of graph.nodes.filter((n) => n.evidence_ids.includes(e.id))) {
        let parent = n.parent_id;
        while (parent) { next.add(parent); parent = byId.get(parent)?.parent_id ?? null; }
      }
      return next;
    });
  };

  const runAction = async (a: DiagnosticAction, approveOnce = false, confirmedRepeat = false) => {
    if (!incidentId) return;
    const iid = incidentId;
    const needsSource = a.kind === "repeat_test" || a.kind === "verify_fix";
    if (needsSource && busy) { notify("Wait for the current test to finish."); return; }
    if (a.kind === "request_manual_check") { setManual(a); return; }
    if (a.kind === "repeat_test" && !confirmedRepeat) { setRepeat(a); return; }
    // The Devin repair workflow is engineer-controlled and reviewable — it opens its own
    // dialog instead of running through the action executor (D-025).
    if (a.kind === "prepare_software_fix") { setRepairOpen(true); return; }
    setBusyAction(a.id);
    if (needsSource) setBusy(true);
    try {
      const { result } = await api.executeAction(iid, a.id, needsSource ? parseSource(source) : undefined, approveOnce);
      if (incidentRef.current !== iid) return;
      if (needsSource) { setDrawerTab("angle"); setDrawerOpen(true); }
      if (result.source_excerpts.length) setInspect(result);
      else if (result.node_ids.length) { revealNodes(result.node_ids, true); notify(result.summary); }
      else if (a.kind === "run_readonly_tool") setToolOutput(result);
      refreshView(iid);
    } catch (e) {
      if (incidentRef.current !== iid) return;
      if (needsSource) setBusy(false);
      if (e instanceof ApiError && e.code === "permission_required") {
        setApproval({ action: a, category: String(e.details.category), tool: String(e.details.tool) });
      } else fail(e);
    } finally { if (incidentRef.current === iid) setBusyAction(null); }
  };

  const setPermission = async (c: PermissionCategory, granted: boolean) => {
    if (!incidentId) return;
    try { await api.setPermission(incidentId, c, granted); refreshView(incidentId); } catch (e) { fail(e); }
  };

  const diagnose = async () => {
    if (!incidentId) return;
    setDiagnosing(true);
    try { await api.diagnose(incidentId); refreshView(incidentId); } catch (e) { setDiagnosing(false); fail(e); }
  };

  const submitManual = async (result: string, note: string) => {
    if (!incidentId || !manual) return;
    try { setView(await api.manualResult(incidentId, manual.id, result, note || undefined)); setManual(null); } catch (e) { fail(e); }
  };

  const rescan = async () => {
    if (!project) return;
    try { const p = await api.rescan(project.id); await reloadGraph(p.id); notify(`Re-read the firmware — graph v${p.graph_version}`); }
    catch (e) { fail(e); }
  };

  const focusSubsystem = async (sid: string) => {
    scopeRef.current = sid;
    setFocusSub(sid);
    if (!project) return;
    if (!sid) { setFocusIds(null); setFitKey(`all-${Date.now()}`); return; }
    setExpanded((e) => new Set([...e, sid]));
    try {
      const scoped = await api.graph(project.id, sid);
      if (projectRef.current !== project.id || scopeRef.current !== sid) return;
      setFocusIds(new Set(scoped.nodes.map((n) => n.id))); setFitKey(`${sid}-${Date.now()}`);
    } catch (e) { fail(e); }
  };

  const saveReplay = async (runId: string) => {
    const name = `capture_${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
    try { const r = await api.saveReplay(runId, name); notify(`Saved as replay "${r.id}"`); api.sources().then(setSources).catch(() => undefined); }
    catch (e) { fail(e); }
  };

  const highlights: Highlight[] = useMemo(() => {
    if (view) return view.highlights;
    if (!project) return [];
    return project.issues.filter((i) => i.code === "GPIO_CONFIG_MISMATCH")
      .flatMap((i) => [...i.related_edge_ids, ...i.related_node_ids].map((id) => ({ element_id: id, style: "conflict" as const, reason: i.message })));
  }, [view, project]);

  const toggle = useCallback((id: string) => setExpanded((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  }), []);

  // ------------------------------------------------------------------ render

  if (!project || !graph) {
    return <ImportScreen onImport={doImport} onOpen={(p) => loadProject(p, false).catch(fail)} busy={busy} onError={(m) => fail(m)} />;
  }

  const runs: TestRun[] = view ? [view.test_run, ...view.followup_runs] : run ? [run] : [];
  const conflict = project.issues.find((i) => i.code === "GPIO_CONFIG_MISMATCH")?.message ?? null;
  const liveReady = !!devices?.serial.connected && !!devices?.camera.connected && !!devices.camera.calibrated;
  const selectedNode = graph.nodes.find((n) => n.id === selectedId) ?? null;
  const selectedEdges = graph.edges.filter((e) => selectedEdgeIds.includes(e.id));

  return (
    <>
    <Layout
      header={
        <LayoutHeader hasDivider>
          <TopBar project={project} subsystems={subsystems} focus={focusSub} onFocus={focusSubsystem}
                  devices={devices} agents={agentStatus} onRescan={rescan}
                  onRigSetup={() => setRigSetupOpen(true)}
                  onOpenDrawer={(t) => { setDrawerTab(t); setDrawerOpen(true); }}
                  onProjects={() => { store.set(LAST_PROJECT, null); ++loadVersion.current; projectRef.current = null; incidentRef.current = null; runRef.current = null; setIncidentId(null); setProject(null); setGraph(null); setView(null); setRun(null); setExpectation(null); setBusy(false); setBusyAction(null); setDiagnosing(false); }} />
        </LayoutHeader>
      }
      end={
        <LayoutPanel hasDivider width={420} label="Debugging steps" padding={4}>
          <VStack gap={4}>
            <FlowPanel projectId={project.id} conflictNote={conflict} expectation={expectation} onExpectation={setExpectation}
                       run={run} running={busy} view={view} sources={sources} source={source} onSource={setSource}
                       liveReady={liveReady} onRun={runTest} busyActionId={busyAction} onAction={(a) => runAction(a)}
                       onPermission={setPermission}
                       onMessage={async (t) => { if (incidentId) setView(await api.message(incidentId, t)); }}
                       agentStatus={agentStatus} diagnosing={diagnosing} onDiagnose={diagnose}
                       onReveal={(ids) => revealNodes(ids, true)}
                       onEvidence={showEvidence} onOpenDevices={() => setRigSetupOpen(true)}
                       projectReview={<ProjectReview project={project} graph={graph} onConnection={setSelectedEdgeIds} />}
                       onNewTest={() => { incidentRef.current = null; runRef.current = null; setIncidentId(null); setView(null); setRun(null); setObservations([]); setSerial([]); }}
                       onError={(m) => fail(m)} />
          </VStack>
        </LayoutPanel>
      }
      content={
        <LayoutContent padding={0} isScrollable={false}>
          <Layout content={<LayoutContent padding={0} isScrollable={false}>
            {mode === "flow" ? (
              <EventFlowView runs={runs} runId={run?.id ?? runs[runs.length - 1]?.id ?? null}
                             onRunChange={(id) => { const r = runs.find((x) => x.id === id); if (r) { runRef.current = id; setRun(r); } }}
                             layer={layer} mode={mode} onMode={setMode} onLayer={setLayer} refreshSeq={flowSeq}
                             onSelectNode={(id) => { setMode("deps"); revealNodes([id], true); }}
                             onEvidence={showEvidence} />
            ) : (
            <GraphView graph={graph} expanded={expanded} highlights={highlights} focusIds={focusIds}
                       layer={layer} mode={mode} onMode={setMode} onLayer={setLayer}
                       selectedId={selectedId ?? graph.nodes.find((n) => evidence && n.evidence_ids.includes(evidence.id))?.id ?? null} onToggle={toggle}
                       onSelect={(id) => { setSelectedId(id); setSelectedEdgeIds([]); }}
                       onEdgeSelect={(ids) => { setSelectedEdgeIds(ids); setSelectedId(null); }}
                       onExpandAll={() => setExpanded(new Set(graph.nodes.filter((n) => n.kind === "subsystem" || n.kind === "source_module").map((n) => n.id)))}
                       onCollapseAll={() => setExpanded(new Set())}
                       onClearFocus={focusIds ? () => { scopeRef.current = ""; setFocusIds(null); setFocusSub(""); setFitKey(`all-${Date.now()}`); } : null}
                       fitKey={`${fitKey}-${expanded.size}`} />
            )}
          </LayoutContent>} footer={<LayoutFooter hasDivider padding={0}>
            <BottomDrawer open={drawerOpen} onOpen={setDrawerOpen} tab={drawerTab} onTab={setDrawerTab} run={run}
                          observations={observations} serial={serial} expectation={expectation} events={events}
                          toolCalls={view?.tool_calls ?? []} devices={devices}
                          onRigSetup={() => setRigSetupOpen(true)}
                          onSaveReplay={saveReplay} onError={(m) => fail(m)} />
          </LayoutFooter>} />
        </LayoutContent>
      }
    />
      <GraphInspector open={!!selectedNode || !!selectedEdges.length} onClose={() => { setSelectedId(null); setSelectedEdgeIds([]); }}>
        <SelectionCard projectId={project.id} graph={graph} node={selectedNode} edges={selectedEdges}
                       onClose={() => { setSelectedId(null); setSelectedEdgeIds([]); }} hideClose onEvidence={showEvidence}
                       layer={layer} onLayer={setLayer} onReveal={(ids) => { revealNodes(ids, true); setSelectedId(ids[0] ?? null); }}
                       onVerify={async (id, v) => {
                         try { await api.verifyWiring(project.id, id, v, v === "verified" ? "Engineer confirmed on the bench" : undefined); await reloadGraph(project.id); }
                         catch (e) { fail(e); }
                       }} />
        {selectedNode && graph.nodes.some((n) => n.parent_id === selectedNode.id) &&
          <Button label={expanded.has(selectedNode.id) ? "Collapse in graph" : "Expand in graph"} onClick={() => { toggle(selectedNode.id); setSelectedId(null); }} />}
      </GraphInspector>
      <EvidenceDialog evidence={evidence} onClose={() => setEvidence(null)} />
      <RigSetupDialog open={rigSetupOpen} onClose={() => setRigSetupOpen(false)} devices={devices} onDevices={setDevices}
                      onError={(m) => fail(m)} onUseSimulation={() => { setSource(`sim:${sources.sim[0]?.id ?? "connected"}`); setRigSetupOpen(false); }} />
      <InspectDialog result={inspect} onClose={() => setInspect(null)} />
      <ToolOutputDialog result={toolOutput} onClose={() => setToolOutput(null)} />
      <ManualCheckDialog action={manual} run={run ?? view?.test_run} onSubmit={submitManual} onClose={() => setManual(null)} />
      <RepeatTestDialog action={repeat} expectation={expectation} source={source} onSource={setSource} sources={sources} liveReady={liveReady}
                        onClose={() => setRepeat(null)} onOpenDevices={() => { setRepeat(null); setRigSetupOpen(true); }}
                        onRepeat={() => { const action = repeat!; setRepeat(null); runAction(action, false, true); }} />
      {repairOpen && view && (
        <RepairDialog investigation={view} onClose={() => { setRepairOpen(false); if (incidentId) refreshView(incidentId); }} />
      )}
      <ApprovalDialog request={approval}
                      onGrant={async () => { const a = approval!.action; const c = approval!.category; setApproval(null); await setPermission(c as PermissionCategory, true); runAction(a); }}
                      onOnce={() => { const a = approval!.action; setApproval(null); runAction(a, true); }}
                      onCancel={() => setApproval(null)} />
    </>
  );
}
