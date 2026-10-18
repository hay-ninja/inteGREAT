// Typed API client. Types come from the backend OpenAPI schema (npm run gen:types) — don't hand-edit them.
import type { components } from "../types/api.gen";

type S = components["schemas"];
export type Project = S["Project"];
export type GraphSnapshot = S["GraphSnapshot"];
export type GraphNode = S["GraphNode"];
export type GraphEdge = S["GraphEdge"];
export type Subsystem = S["Subsystem"];
export type Expectation = S["Expectation"];
export type ExpectationResult = S["ExpectationResult"];
export type ExpectationEdit = S["ExpectationEdit"];
export type TestRun = S["TestRun"];
export type Observation = S["Observation"];
export type SerialEvent = S["SerialEvent"];
export type InvestigationView = S["InvestigationView"];
export type Hypothesis = S["Hypothesis"];
export type DiagnosticAction = S["DiagnosticAction"];
export type Evidence = S["Evidence"];
export type Highlight = S["Highlight"];
export type CausalStep = S["CausalStep"];
export type ActionResult = S["ActionResult"];
export type ReplayInfo = S["ReplayInfo"];
export type DemoFixture = S["DemoFixture"];
export type IntegreatEvent = S["IntegreatEvent"];
export type ObservationSourceSpec = S["ObservationSourceSpec-Input"];
export type TestRunDetail = S["TestRunDetail"];
export type AgentRun = S["AgentRun"];
export type AgentStatus = S["AgentStatus"];
export type DeviceStatus = S["DeviceStatus"];
export type PermissionGrant = S["PermissionGrant"];
export type ToolCall = S["ToolCall"];
export type NetlistPreview = S["NetlistPreview"];
export type SourceOptions = S["SourceOptions"];
export type Incident = S["Incident"];
export type PermissionCategory = S["PermissionUpdate"]["category"];
export type EventFlow = S["EventFlow"];
export type FlowEvent = S["FlowEvent"];
export type FlowLane = S["FlowLane"];
export type RepairJob = S["RepairJob"];
export type RepairPreflight = S["RepairPreflight"];
export type ProviderStatus = S["ProviderStatus"];
export type GraphLayer = "combined" | "hardware" | "software";

// Project edits — name/context/subsystem labels are instant; any *_path change rebuilds the graph.
export interface ProjectUpdate {
  name?: string;
  context?: string;
  subsystem_names?: Record<string, string>;
  repo_path?: string | null;
  manifest_path?: string | null;
  netlist_path?: string | null;
  netlist_mapping?: Record<string, unknown> | null;
  rescan?: boolean;
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
  }
}

// ---------------------------------------------------------------- hosted-demo replay (D-034)
// The built static site can run without a backend: a recorded bundle of the demo
// click-path is served from /replay/demo.json. When /api/v1/health is unreachable
// the client switches to replay mode — canned responses for the recorded routes,
// honest errors for anything else. Everything it returns is real recorded data;
// the UI's Simulated/Replay labelling still applies.

type ReplayBundle = {
  routes: Record<string, unknown>;
  evidence: Record<string, unknown>;
  /** iid -> body hashes of verify_fix executes that resolve it (captured). */
  resolves?: Record<string, string[]>;
};
let replay: ReplayBundle | null = null;
let modePromise: Promise<"api" | "replay"> | null = null;
// Incidents flip to their captured resolved view only after the recorded
// passing verify_fix execute — judges see the real open → verify → resolved arc.
const resolvedIncidents = new Set<string>();
const replaySubs = new Set<(e: IntegreatEvent) => void>();
let replaySeq = 0;

export function apiMode(): Promise<"api" | "replay"> {
  modePromise ??= (async () => {
    try {
      const r = await fetch("/api/v1/health", { signal: AbortSignal.timeout(2500) });
      // Static hosts often SPA-rewrite unknown paths to index.html with a 200 — only
      // a parseable health payload counts as a real backend.
      if (r.ok) {
        const j = await r.json().catch(() => null) as { ok?: boolean } | null;
        if (j?.ok === true) return "api";
      }
    } catch { /* unreachable — try the replay bundle */ }
    try {
      replay = await (await fetch("/replay/demo.json")).json() as ReplayBundle;
      return "replay";
    } catch { replay = null; return "api"; }
  })();
  return modePromise;
}

export const isHostedDemo = () => replay != null;

const canonical = (v: unknown): string => JSON.stringify(v, (_k, x) =>
  x && typeof x === "object" && !Array.isArray(x)
    ? Object.keys(x).sort().reduce((o: Record<string, unknown>, k) => (o[k] = x[k], o), {})
    : x);

async function bodyKey(method: string, path: string, body: unknown): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-1", new TextEncoder().encode(canonical(body)));
  const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${method} ${path}::${hex.slice(0, 12)}`;
}

const emitReplay = (ev: Record<string, unknown>) =>
  queueMicrotask(() => replaySubs.forEach((cb) => cb({ seq: ++replaySeq, ...ev } as IntegreatEvent)));

/** Re-create the websocket lifecycle for a recorded run so busy/spinner state resolves. */
function emitRunLifecycle(detail: { run?: TestRun; serial?: SerialEvent[]; observations?: unknown[] } | undefined, fallback?: TestRun) {
  const run = detail?.run ?? fallback;
  if (!run?.id) return;
  emitReplay({ type: "test.started", test_run_id: run.id, payload: { ...run, state: "running" } });
  for (const s of detail?.serial ?? []) emitReplay({ type: "test.serial", test_run_id: run.id, payload: s });
  for (const o of detail?.observations ?? []) emitReplay({ type: "test.observation", test_run_id: run.id, payload: o });
  emitReplay({ type: "test.completed", test_run_id: run.id, payload: run });
}

async function replayReq<T>(method: string, path: string, body?: unknown): Promise<T> {
  const bundle = replay!;
  // /evidence?ids=… is resolved dynamically — judges can inspect any cited record.
  const ev = method === "GET" ? path.match(/^\/projects\/[^/]+\/evidence\?(.*)$/) : null;
  if (ev) {
    const ids = new URLSearchParams(ev[1]).getAll("ids");
    return ids.map((id) => bundle.evidence[id]).filter(Boolean) as T;
  }
  const key = body === undefined ? `${method} ${path}` : await bodyKey(method, path, body);
  // Investigation GETs serve the open-state view until a resolving verify run.
  const invGet = method === "GET" ? path.match(/^\/investigations\/([^/]+)$/) : null;
  const rkey = `${key}#resolved`;
  if (invGet && resolvedIncidents.has(decodeURIComponent(invGet[1])) && rkey in bundle.routes) {
    return bundle.routes[rkey] as T;
  }
  let hit = bundle.routes[key];
  if (hit === undefined && method === "POST" && /^\/projects\/[^/]+\/tests$/.test(path)) {
    // Each demo project recorded exactly one run — serve it whatever scenario the
    // judge picked; the result's SourceBadge still labels the recording honestly.
    const prefix = `${method} ${path}::`;
    const alts = Object.keys(bundle.routes).filter((k) => k.startsWith(prefix));
    if (alts.length === 1) hit = bundle.routes[alts[0]];
  }
  if (hit === undefined) {
    throw new ApiError(503, "hosted_demo",
      "The hosted site replays a recorded session — download inteGREAT locally for this action.");
  }
  // Synthesize the events the app normally gets over the websocket.
  const runMatch = method === "POST" && path.match(/^\/projects\/[^/]+\/tests$/);
  const actionMatch = method === "POST" && path.match(/^\/investigations\/([^/]+)\/actions\/([^/]+)\/execute$/);
  if (runMatch) {
    emitRunLifecycle(bundle.routes[`GET /tests/${encodeURIComponent((hit as TestRun).id)}`] as never, hit as TestRun);
  } else if (actionMatch) {
    const iid = decodeURIComponent(actionMatch[1]);
    const tid = ((hit as { result?: { test_run_id?: string } }).result)?.test_run_id;
    if (tid) emitRunLifecycle(bundle.routes[`GET /tests/${encodeURIComponent(tid)}`] as never);
    emitReplay({ type: "action.completed", investigation_id: iid,
                 payload: { investigation_id: iid, action_id: decodeURIComponent(actionMatch[2]) } });
    const hash = key.split("::")[1] ?? "";
    if (bundle.resolves?.[iid]?.includes(hash)) {
      resolvedIncidents.add(iid);
      emitReplay({ type: "incident.resolved", investigation_id: iid, payload: { investigation_id: iid } });
    }
  }
  return hit as T;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  if ((await apiMode()) === "replay") return replayReq<T>(method, path, body);
  const r = await fetch(`/api/v1${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    let code = "http_error";
    let message = `${r.status} ${r.statusText}`;
    let details: Record<string, unknown> = {};
    try {
      const j = await r.json();
      if (j.error) ({ code, message, details = {} } = j.error);
      else if (j.detail) message = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, code, message, details);
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  demo: () => req<{ fixtures: DemoFixture[]; netlist_path: string }>("GET", "/demo"),
  replays: () => req<ReplayInfo[]>("GET", "/replays"),
  sources: () => req<SourceOptions>("GET", "/sources"),
  projects: () => req<Project[]>("GET", "/projects"),
  project: (pid: string) => req<Project>("GET", `/projects/${enc(pid)}`),
  importProject: (body: {
    repo_path: string;
    manifest_path?: string | null;
    netlist_path?: string | null;
    netlist_mapping?: Record<string, unknown> | null;
  }) => req<Project>("POST", "/projects/import", body),
  netlistPreview: (netlist_path: string, repo_path?: string) =>
    req<NetlistPreview>("POST", "/netlist/preview", { netlist_path, repo_path }),
  rescan: (pid: string) => req<Project>("POST", `/projects/${enc(pid)}/rescan`),
  updateProject: (pid: string, body: ProjectUpdate) => req<Project>("PATCH", `/projects/${enc(pid)}`, body),
  deleteProject: (pid: string) => req<void>("DELETE", `/projects/${enc(pid)}`),
  verifyWiring: (pid: string, edge_id: string, verification: "verified" | "unverified", note?: string) =>
    req<Project>("PATCH", `/projects/${enc(pid)}/graph/verification`, { edge_id, verification, note }),
  expectations: (pid: string) => req<Expectation[]>("GET", `/projects/${enc(pid)}/expectations`),
  incidents: (pid: string) => req<Incident[]>("GET", `/projects/${enc(pid)}/incidents`),
  projectTests: (pid: string) => req<TestRun[]>("GET", `/projects/${enc(pid)}/tests`),
  saveReplay: (runId: string, name: string) => req<ReplayInfo>("POST", `/tests/${enc(runId)}/save-replay`, { name }),
  setPermission: (iid: string, category: PermissionCategory, granted: boolean) =>
    req<PermissionGrant[]>("POST", `/investigations/${enc(iid)}/permissions`, { category, granted }),
  message: (iid: string, text: string) => req<InvestigationView>("POST", `/investigations/${enc(iid)}/messages`, { text }),
  diagnose: (iid: string) => req<Incident>("POST", `/investigations/${enc(iid)}/diagnose`),
  agentStatus: () => req<AgentStatus>("GET", "/agents/status"),
  devices: () => req<DeviceStatus>("GET", "/devices"),
  serialConnect: (port: string, baud = 115200) => req<DeviceStatus>("POST", "/devices/serial/connect", { port, baud }),
  serialRelease: () => req<DeviceStatus>("POST", "/devices/serial/release"),
  cameraProbe: () => req<number[]>("GET", "/devices/camera/probe"),
  cameraConnect: (index: number) => req<DeviceStatus>("POST", "/devices/camera/connect", { index }),
  cameraConnectPhone: (stream_url: string) => req<DeviceStatus>("POST", "/devices/camera/connect", { stream_url }),
  cameraPairBrowser: () => req<S["BrowserCameraPairing"]>("POST", "/devices/camera/browser/pair"),
  cameraRelease: () => req<DeviceStatus>("POST", "/devices/camera/release"),
  cameraCalibrate: (known_angle_deg: number) => req<DeviceStatus>("POST", "/devices/camera/calibrate", { known_angle_deg }),
  cameraCalibrateLed: (component_id: string) =>
    req<DeviceStatus>("POST", "/devices/camera/calibrate", { mode: "led_baseline", component_id }),
  cameraLocateLed: (component_id: string, on_command: string, off_command: string, cycles = 2) =>
    req<S["LedLocateResult"]>("POST", "/devices/camera/locate-led", { component_id, on_command, off_command, cycles }),
  cameraSetLedRoi: (component_id: string, roi: number[], calibrate_baseline = true) =>
    req<DeviceStatus>("POST", "/devices/camera/led-roi", { component_id, roi, calibrate_baseline }),
  graph: (pid: string, scope?: string) =>
    req<GraphSnapshot>("GET", `/projects/${enc(pid)}/graph${scope ? `?scope_node_id=${enc(scope)}` : ""}`),
  subsystems: (pid: string) => req<Subsystem[]>("GET", `/projects/${enc(pid)}/subsystems`),
  evidence: (pid: string, ids: string[]) =>
    ids.length
      ? req<Evidence[]>("GET", `/projects/${enc(pid)}/evidence?${ids.map((i) => `ids=${enc(i)}`).join("&")}`)
      : Promise.resolve([] as Evidence[]),
  proposeExpectation: (pid: string, componentId?: string) =>
    req<Expectation>("POST", `/projects/${enc(pid)}/expectations/propose`,
                   componentId ? { component_id: componentId } : undefined),
  confirmExpectation: (pid: string, eid: string, edit: ExpectationEdit) =>
    req<Expectation>("POST", `/projects/${enc(pid)}/expectations/${enc(eid)}/confirm`, edit),
  startTest: (pid: string, expectation_id: string, source: ObservationSourceSpec) =>
    req<TestRun>("POST", `/projects/${enc(pid)}/tests`, { expectation_id, source }),
  test: (runId: string) => req<TestRunDetail>("GET", `/tests/${enc(runId)}`),
  investigation: (iid: string) => req<InvestigationView>("GET", `/investigations/${enc(iid)}`),
  executeAction: (iid: string, aid: string, source?: ObservationSourceSpec, approve_once = false) =>
    req<{ result: ActionResult }>("POST", `/investigations/${enc(iid)}/actions/${enc(aid)}/execute`, {
      source,
      approve_once,
    }),
  manualResult: (iid: string, action_id: string, result: string, note?: string) =>
    req<InvestigationView>("POST", `/investigations/${enc(iid)}/manual-results`, { action_id, result, note }),
  testFlow: (runId: string) => req<EventFlow>("GET", `/tests/${enc(runId)}/flow`),
  repairPreflight: (iid: string) => req<RepairPreflight>("GET", `/investigations/${enc(iid)}/repairs/preflight`),
  repairs: (iid: string) => req<RepairJob[]>("GET", `/investigations/${enc(iid)}/repairs`),
  requestRepair: (iid: string, acknowledge_uncommitted = false) =>
    req<RepairJob>("POST", `/investigations/${enc(iid)}/repairs`, { acknowledge_uncommitted }),
  refreshRepair: (jobId: string) => req<RepairJob>("POST", `/repairs/${enc(jobId)}/refresh`),
};

/** Subscribe to the project event stream. Reconnects with catch-up from the last seen seq.
    In hosted-demo mode there is no socket — the callback registers for synthesized
    replay events (run lifecycle) instead. */
export function subscribeProject(pid: string, onEvent: (e: IntegreatEvent) => void): () => void {
  let lastSeq = 0;
  let ws: WebSocket | null = null;
  let closed = false;
  let retry: number | undefined;
  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/api/v1/ws/projects/${enc(pid)}?after_seq=${lastSeq}`);
    ws.onmessage = (m) => {
      const ev = JSON.parse(m.data) as IntegreatEvent;
      lastSeq = Math.max(lastSeq, ev.seq ?? 0);
      onEvent(ev);
    };
    ws.onclose = () => {
      if (!closed) retry = window.setTimeout(connect, 1000);
    };
  };
  apiMode().then((m) => {
    if (closed) return;
    if (m === "replay") replaySubs.add(onEvent);
    else connect();
  });
  return () => {
    closed = true;
    replaySubs.delete(onEvent);
    window.clearTimeout(retry);
    ws?.close();
  };
}
