import type { ReactNode } from "react";
import type { Expectation, IntegreatEvent, Observation, SerialEvent, TestRun } from "../../lib/api";

interface Props {
  events: IntegreatEvent[];
  run: TestRun | null;
  observations: Observation[];
  serial: SerialEvent[];
  expectation: Expectation | null;
  onSelectEvent: (e: IntegreatEvent) => void;
  devices: ReactNode;
  audit: ReactNode;
  onSaveReplay: (runId: string) => void;
  tab: Tab;
  onTab: (t: Tab) => void;
}

export type Tab = "plot" | "serial" | "timeline" | "devices" | "audit";
const TAB_LABEL: Record<Tab, string> = {
  plot: "CV angle", serial: "Serial", timeline: "Timeline", devices: "Devices", audit: "Tool audit",
};

export function BottomPanel(p: Props) {
  const tab = p.tab;
  return (
    <div className="bottom">
      <div className="tabs">
        {(Object.keys(TAB_LABEL) as Tab[]).map((t) => (
          <button key={t} className={tab === t ? "tab active" : "tab"} onClick={() => p.onTab(t)}>
            {TAB_LABEL[t]}
          </button>
        ))}
        {p.run && (
          <span className="run-meta">
            {p.run.id} · {p.run.attempt_kind} · {p.run.state}
            <SourceBadge run={p.run} />
            {p.run.state === "completed" && p.run.source.kind !== "replay" && (
              <button className="ghost small" onClick={() => p.onSaveReplay(p.run!.id)}
                      title="Save this run as a replay fixture for offline demos">Save as replay</button>
            )}
          </span>
        )}
      </div>
      <div className="tab-body">
        {tab === "plot" && <AnglePlot obs={p.observations} exp={p.expectation} />}
        {tab === "serial" && <SerialLog serial={p.serial} />}
        {tab === "timeline" && <Timeline events={p.events} onSelect={p.onSelectEvent} />}
        {tab === "devices" && p.devices}
        {tab === "audit" && p.audit}
      </div>
    </div>
  );
}

export function SourceBadge({ run }: { run: TestRun }) {
  const src = run.source;
  if (src.kind === "live") return <span className="badge live">LIVE HARDWARE</span>;
  if (src.kind === "sim") return <span className="badge replay">SIMULATED RIG: {src.scenario}</span>;
  return <span className="badge replay">{run.synthetic ? "SYNTHETIC REPLAY" : "RECORDED REPLAY"}: {src.scenario}</span>;
}

function AnglePlot({ obs, exp }: { obs: Observation[]; exp: Expectation | null }) {
  if (!obs.length) return <div className="empty">Run a test to see camera angle measurements.</div>;
  const W = 900;
  const H = 150;
  const pad = { l: 40, r: 10, t: 10, b: 22 };
  const maxT = Math.max(exp?.deadline_ms ?? 0, ...obs.map((o) => o.elapsed_ms)) * 1.05;
  const x = (t: number) => pad.l + (t / maxT) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + (1 - v / 180) * (H - pad.t - pad.b);
  const valid = obs.filter((o) => o.measurement_quality === "valid" && o.value != null);
  const invalid = obs.filter((o) => o.measurement_quality !== "valid");
  const path = valid.map((o, i) => `${i ? "L" : "M"}${x(o.elapsed_ms).toFixed(1)},${y(o.value!).toFixed(1)}`).join(" ");
  return (
    <svg className="plot" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
         aria-label="Servo angle over time from camera">
      {exp && (
        <>
          <rect x={pad.l} width={W - pad.l - pad.r} y={y(exp.target + exp.tolerance)}
                height={y(exp.target - exp.tolerance) - y(exp.target + exp.tolerance)} className="band" />
          <line x1={x(exp.deadline_ms)} x2={x(exp.deadline_ms)} y1={pad.t} y2={H - pad.b} className="deadline" />
          <text x={x(exp.deadline_ms) + 4} y={pad.t + 10} className="axis">deadline {exp.deadline_ms} ms</text>
          <text x={pad.l + 4} y={y(exp.target + exp.tolerance) - 3} className="axis">
            target {exp.target}° ± {exp.tolerance}°
          </text>
        </>
      )}
      {[0, 90, 180].map((v) => (
        <text key={v} x={4} y={y(v) + 4} className="axis">{v}°</text>
      ))}
      <path d={path} className="series" />
      {valid.map((o) => <circle key={o.id} cx={x(o.elapsed_ms)} cy={y(o.value!)} r={2} className="pt" />)}
      {invalid.map((o) => (
        <text key={o.id} x={x(o.elapsed_ms) - 3} y={H - pad.b - 2} className="invalid-pt">
          ×
        </text>
      ))}
      <text x={W - 150} y={H - 6} className="axis">
        {valid.length} valid · {invalid.length} invalid frames
      </text>
    </svg>
  );
}

function SerialLog({ serial }: { serial: SerialEvent[] }) {
  if (!serial.length) return <div className="empty">No serial traffic for this run.</div>;
  return (
    <div className="serial">
      {serial.map((s) => (
        <div key={s.id} className={`sline ${s.direction}`}>
          <span className="t">{s.elapsed_ms} ms</span>
          <span className="dir">{s.direction === "tx" ? "→ host" : "← esp32"}</span>
          <span className="raw">{s.raw}</span>
          {s.matched_function_ids.length > 0 && (
            <span className="match">matches print in {s.matched_function_ids.map((f) => f.split("::")[1]).join(", ")}()</span>
          )}
        </div>
      ))}
    </div>
  );
}

const IMPORTANT = new Set([
  "project.imported", "graph.updated", "permissions.updated", "tool.called", "action.denied", "agent.started",
  "agent.reported", "message.added", "expectation.confirmed", "test.started", "test.completed", "expectation.failed",
  "incident.created", "hypotheses.updated", "action.started", "action.completed", "test.verification_completed",
  "incident.resolved", "error",
]);

function Timeline({ events, onSelect }: { events: IntegreatEvent[]; onSelect: (e: IntegreatEvent) => void }) {
  const shown = events.filter((e) => IMPORTANT.has(e.type)).slice().reverse();
  if (!shown.length) return <div className="empty">No events yet.</div>;
  return (
    <div className="timeline">
      {shown.map((e) => (
        <div key={e.seq} className={`tl ev-${e.type.replace(".", "-")}`} onClick={() => onSelect(e)}>
          <span className="t">{new Date(e.timestamp_utc).toLocaleTimeString()}</span>
          <span className="type">{e.type}</span>
          <span className="sum">{summarize(e)}</span>
        </div>
      ))}
    </div>
  );
}

function summarize(e: IntegreatEvent): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "expectation.failed":
      return String(p.reason ?? "");
    case "incident.created":
      return `${p.title} [${(p.fault_codes as string[] | undefined)?.join(", ")}]`;
    case "test.completed": {
      const r = p.result as { outcome?: string } | null;
      return `${p.attempt_kind} run → ${r?.outcome ?? p.state}`;
    }
    case "test.verification_completed":
      return `verification ${p.outcome}: ${p.reason}`;
    case "action.completed":
      return String(p.summary ?? p.result ?? p.action_id ?? "");
    case "action.started":
      return String(p.action_id ?? "");
    case "error":
      return String(p.message ?? "");
    case "project.imported":
      return `${p.name} (${p.issues} import notes)`;
    case "graph.updated":
      return `graph v${p.version}${p.reason ? ` (${p.reason})` : ""}${p.verification ? `: wiring ${p.verification}` : ""}`;
    case "permissions.updated":
      return `${p.category} ${p.granted ? "granted" : "revoked"}`;
    case "tool.called":
      return `${p.tool_name} by ${p.caller}: ${p.decision}`;
    case "action.denied":
      return `${p.reason}`;
    case "agent.started":
      return `round ${p.round}: ${(p.agents as string[] | undefined)?.join(", ")}`;
    case "agent.reported":
      return `${p.agent}: ${p.status} (${p.findings} findings)`;
    case "message.added":
      return String(p.text ?? "");
    default:
      return "";
  }
}
