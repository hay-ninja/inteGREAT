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

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public details: Record<string, unknown> = {}) {
    super(message);
  }
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
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
  verifyWiring: (pid: string, edge_id: string, verification: "verified" | "unverified", note?: string) =>
    req<Project>("PATCH", `/projects/${enc(pid)}/graph/verification`, { edge_id, verification, note }),
  expectations: (pid: string) => req<Expectation[]>("GET", `/projects/${enc(pid)}/expectations`),
  incidents: (pid: string) => req<Incident[]>("GET", `/projects/${enc(pid)}/incidents`),
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
  cameraRelease: () => req<DeviceStatus>("POST", "/devices/camera/release"),
  cameraCalibrate: (known_angle_deg: number) => req<DeviceStatus>("POST", "/devices/camera/calibrate", { known_angle_deg }),
  graph: (pid: string, scope?: string) =>
    req<GraphSnapshot>("GET", `/projects/${enc(pid)}/graph${scope ? `?scope_node_id=${enc(scope)}` : ""}`),
  subsystems: (pid: string) => req<Subsystem[]>("GET", `/projects/${enc(pid)}/subsystems`),
  evidence: (pid: string, ids: string[]) =>
    ids.length
      ? req<Evidence[]>("GET", `/projects/${enc(pid)}/evidence?${ids.map((i) => `ids=${enc(i)}`).join("&")}`)
      : Promise.resolve([] as Evidence[]),
  proposeExpectation: (pid: string) => req<Expectation>("POST", `/projects/${enc(pid)}/expectations/propose`),
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

/** Subscribe to the project event stream. Reconnects with catch-up from the last seen seq. */
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
  connect();
  return () => {
    closed = true;
    window.clearTimeout(retry);
    ws?.close();
  };
}
