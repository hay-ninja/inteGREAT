// Typed API client. Types come from the backend OpenAPI schema (npm run gen:types) — don't hand-edit them.
import type { components } from "../types/api.gen";

type S = components["schemas"];
export type Project = S["Project"];
export type GraphSnapshot = S["GraphSnapshot"];
export type GraphNode = S["GraphNode"];
export type GraphEdge = S["GraphEdge"];
export type Subsystem = S["Subsystem"];
export type Expectation = S["Expectation"];
export type ExpectationEdit = S["ExpectationEdit"];
export type TestRun = S["TestRun"];
export type Observation = S["Observation"];
export type SerialEvent = S["SerialEvent"];
export type InvestigationView = S["InvestigationView"];
export type Hypothesis = S["Hypothesis"];
export type DiagnosticAction = S["DiagnosticAction"];
export type Evidence = S["Evidence"];
export type Highlight = S["Highlight"];
export type ActionResult = S["ActionResult"];
export type ReplayInfo = S["ReplayInfo"];
export type DemoFixture = S["DemoFixture"];
export type IntegreatEvent = S["IntegreatEvent"];
export type ObservationSourceSpec = S["ObservationSourceSpec-Input"];
export type TestRunDetail = S["TestRunDetail"];

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
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
    try {
      const j = await r.json();
      if (j.error) ({ code, message } = j.error);
      else if (j.detail) message = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(r.status, code, message);
  }
  return r.json() as Promise<T>;
}

const enc = encodeURIComponent;

export const api = {
  demoFixtures: () => req<DemoFixture[]>("GET", "/demo-fixtures"),
  replays: () => req<ReplayInfo[]>("GET", "/replays"),
  importProject: (repo_path: string, manifest_path: string | null) =>
    req<Project>("POST", "/projects/import", { repo_path, manifest_path }),
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
  executeAction: (iid: string, aid: string, source?: ObservationSourceSpec) =>
    req<{ result: ActionResult }>("POST", `/investigations/${enc(iid)}/actions/${enc(aid)}/execute`, { source }),
  manualResult: (iid: string, action_id: string, result: string, note?: string) =>
    req<InvestigationView>("POST", `/investigations/${enc(iid)}/manual-results`, { action_id, result, note }),
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
