import { useState } from "react";
import type {
  ActionResult,
  AgentRun,
  AgentStatus,
  Evidence,
  InvestigationView,
  PermissionCategory,
  ToolCall,
} from "../../lib/api";
import { EvidenceList } from "./InvestigationPanel";

export const CATEGORIES: { id: PermissionCategory; label: string; hint: string }[] = [
  { id: "repo_read", label: "Read source", hint: "imported repository files only" },
  { id: "netlist_read", label: "Read wiring", hint: "manifest / netlist connections" },
  { id: "serial_read", label: "Read serial", hint: "device buffer or recorded runs" },
  { id: "camera_observe", label: "Camera data", hint: "angle measurements (no raw video)" },
];

export function PermissionsPanel(props: {
  view: InvestigationView;
  onToggle: (c: PermissionCategory, granted: boolean) => void;
}) {
  const granted = new Set(props.view.permissions.map((p) => p.category));
  const closed = ["resolved", "inconclusive"].includes(props.view.incident.state);
  return (
    <section>
      <h4>Tool permissions <span className="dim">(this investigation only)</span></h4>
      <div className="perms">
        {CATEGORIES.map((c) => (
          <label key={c.id} className={`perm-toggle ${granted.has(c.id) ? "on" : ""}`} title={c.hint}>
            <input type="checkbox" disabled={closed} checked={granted.has(c.id)}
                   onChange={(e) => props.onToggle(c.id, e.target.checked)} />
            {c.label}
          </label>
        ))}
      </div>
      <div className="dim small">
        Read-only tools in granted categories run without asking. Others ask first. Firmware flashing, GPIO or
        serial writes are not available.
      </div>
    </section>
  );
}

export function ApprovalModal(props: {
  category: string;
  tool: string;
  onGrant: () => void;
  onOnce: () => void;
  onCancel: () => void;
}) {
  const cat = CATEGORIES.find((c) => c.id === props.category);
  return (
    <div className="modal-bg" onClick={props.onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head"><b>Permission needed</b></div>
        <p>
          <code>{props.tool}</code> is a read-only tool in category <b>{cat?.label ?? props.category}</b>
          {cat && <span className="dim"> ({cat.hint})</span>}, which isn't granted for this investigation.
        </p>
        <div className="choice-row">
          <button className="action-btn" onClick={props.onGrant}>Grant for this investigation</button>
          <button className="ghost" onClick={props.onOnce}>Allow once</button>
          <button className="ghost" onClick={props.onCancel}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

export function ToolOutputModal({ result, onClose }: { result: ActionResult; onClose: () => void }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>Tool output</b>
          <button className="ghost" onClick={onClose}>Close</button>
        </div>
        <p>{result.summary}</p>
        {result.lines.length > 0 ? (
          <pre className="tool-lines">{result.lines.join("\n")}</pre>
        ) : (
          <div className="dim">No lines returned.</div>
        )}
        <div className="dim small">Recorded as evidence {result.evidence.map((e) => e.id).join(", ")}</div>
      </div>
    </div>
  );
}

export function AgentsPanel(props: {
  view: InvestigationView;
  status: AgentStatus | null;
  busy: boolean;
  onDiagnose: () => void;
  onAction: (actionId: string) => void;
}) {
  const { view, status } = props;
  const inc = view.incident;
  const rounds = inc.agent_rounds_used;
  const running = inc.state === "investigating";
  const closed = ["resolved", "inconclusive"].includes(inc.state);
  const evById = new Map(view.evidence.map((e) => [e.id, e]));
  const byRound = new Map<number, AgentRun[]>();
  for (const r of view.agent_runs) byRound.set(r.round, [...(byRound.get(r.round) ?? []), r]);
  const rec = view.actions.find((a) => a.id === inc.agent_recommended_action_id);
  const disabledReason = !status?.available
    ? `AI unavailable: ${status?.reason ?? "no provider"}`
    : closed ? "Investigation closed" : rounds >= 2 ? "Agent budget used (2 rounds)" : running ? "Running…" : "";

  return (
    <section className="agents">
      <h4>
        AI agents <span className="dim">round {rounds}/2 · {status?.model ?? "no model"}</span>
      </h4>
      <button className="action-btn" disabled={!!disabledReason || props.busy} onClick={props.onDiagnose}
              title={disabledReason}>
        {running || props.busy ? "Agents investigating…" : rounds === 0 ? "Ask agents" : "Ask agents (follow-up)"}
      </button>
      {disabledReason && !running && <span className="dim small"> {disabledReason}</span>}
      {rounds === 1 && !closed && (
        <div className="dim small">A follow-up needs new evidence: a manual check, tool result, note or rerun.</div>
      )}
      {inc.agent_summary && (
        <div className="agent-summary">
          <div className="sub">Orchestrator summary (inference, not observation)</div>
          <p>{inc.agent_summary}</p>
          {rec && !closed && (
            <button className="action-btn" onClick={() => props.onAction(rec.id)}>Suggested: {rec.label}</button>
          )}
        </div>
      )}
      {[...byRound.entries()].map(([round, runs]) => (
        <div key={round} className="agent-round">
          <div className="sub">Round {round}</div>
          {runs.map((r) => <AgentRunCard key={r.id} run={r} evById={evById} />)}
        </div>
      ))}
    </section>
  );
}

function AgentRunCard({ run, evById }: { run: AgentRun; evById: Map<string, Evidence> }) {
  const [open, setOpen] = useState(false);
  const label = run.agent === "orchestrator" ? (run.dispatched.length ? "Triage" : "Synthesis") : `${run.agent} agent`;
  return (
    <div className={`agent-run st-${run.status}`}>
      <div className="agent-run-head" onClick={() => setOpen(!open)}>
        <b>{label.replace("_", "/")}</b>
        <span className={`hstatus hs-${run.status === "completed" ? "supported" : "weakened"}`}>{run.status}</span>
        <span className="dim small">{run.duration_ms} ms{run.context ? ` · ~${run.context.estimated_tokens} tok` : ""}</span>
      </div>
      {run.dispatched.length > 0 && <div className="small">Dispatched: {run.dispatched.join(", ")} {run.summary && `— ${run.summary}`}</div>}
      {run.error && <div className="small warn">{run.error}</div>}
      {run.report && run.report.findings.map((f, i) => (
        <div key={i} className="finding">
          <span className="evkind">{f.epistemic_status}</span> {f.statement}
          {open && <EvidenceList title="Cites" ids={f.supporting_evidence_ids} evById={evById} />}
        </div>
      ))}
      {open && run.report && run.report.unknowns.length > 0 && (
        <ul className="unknowns small">{run.report.unknowns.map((u) => <li key={u}>{u}</li>)}</ul>
      )}
      {open && run.validation_errors.length > 0 && (
        <div className="small dim">Rejected by validation: {run.validation_errors.join(" · ")}</div>
      )}
      {open && run.context && (
        <div className="small dim">
          Context: {run.context.included_node_ids.length} nodes, {run.context.evidence_ids.length} evidence items.
          {run.context.omitted_context_summary && ` Omitted: ${run.context.omitted_context_summary}`}
        </div>
      )}
    </div>
  );
}

export function MessageBox({ view, onSend }: { view: InvestigationView; onSend: (t: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  return (
    <section>
      <h4>Notes to the investigation</h4>
      {view.messages.map((m) => (
        <div key={m.id} className="msg"><span className="dim small">you:</span> {String(m.payload.text)}</div>
      ))}
      <div className="row">
        <textarea value={text} placeholder="Describe a symptom, a constraint, or what you observed…"
                  onChange={(e) => setText(e.target.value)} />
        <button className="ghost" disabled={!text.trim() || sending}
                onClick={async () => { setSending(true); try { await onSend(text.trim()); setText(""); } finally { setSending(false); } }}>
          Add
        </button>
      </div>
      <div className="dim small">Notes are recorded as evidence and given to agents; they never grant permissions.</div>
    </section>
  );
}

export function AuditLog({ calls }: { calls: ToolCall[] }) {
  if (!calls.length) return <div className="empty">No tool calls yet.</div>;
  return (
    <div className="timeline">
      {[...calls].reverse().map((c) => (
        <div key={c.id} className={`tl dec-${c.decision}`}>
          <span className="t">{new Date(c.started_at_utc).toLocaleTimeString()}</span>
          <span className="type">{c.tool_name}</span>
          <span className="dim" style={{ width: 120 }}>{c.caller}</span>
          <span className={`decision d-${c.decision}`}>{c.decision}</span>
          <span className="sum">{c.error ?? c.summary}</span>
        </div>
      ))}
    </div>
  );
}
