import { useState } from "react";
import type { ActionResult, DiagnosticAction, Evidence, Hypothesis, InvestigationView } from "../../lib/api";

interface Props {
  view: InvestigationView;
  busyActionId: string | null;
  onAction: (a: DiagnosticAction) => void;
  onSelectNodes: (ids: string[]) => void;
}

const STATUS_LABEL: Record<string, string> = {
  supported: "supported",
  plausible: "plausible",
  unverified: "unverified",
  weakened: "weakened",
  ruled_out: "ruled out",
};

export function InvestigationPanel({ view, busyActionId, onAction, onSelectNodes }: Props) {
  const evById = new Map(view.evidence.map((e) => [e.id, e]));
  const actionsById = new Map(view.actions.map((a) => [a.id, a]));
  const inc = view.incident;
  const result = view.test_run.result;
  const closed = inc.state === "resolved" || inc.state === "inconclusive";
  const recommended = view.actions.filter((a) => a.recommended && a.status === "proposed" && !closed);

  return (
    <div className="inv">
      <div className="inv-head">
        <div className="inv-title">{inc.title}</div>
        <span className={`state state-${inc.state}`}>{inc.state.replace("_", " ")}</span>
      </div>
      {inc.state === "resolved" && (() => {
        const v = view.followup_runs.find((r) => r.id === inc.resolved_by_test_run_id);
        return (
          <div className="result result-pass">
            <b>RESOLVED</b> — verified by re-running the same expectation{v?.result ? `: ${v.result.reason}` : "."}
            {v?.synthetic && <div className="replay-note">Verification used a SYNTHETIC replay, not live hardware.</div>}
          </div>
        );
      })()}
      {result && (
        <div className={`result result-${result.outcome}`}>
          <span className="dim small">Original run · </span>
          <b>{result.outcome.toUpperCase()}</b> — {result.reason}
        </div>
      )}
      {view.followup_runs.length > 0 && (
        <section>
          <h4>Follow-up runs</h4>
          <ul className="followups">
            {view.followup_runs.map((r) => (
              <li key={r.id} className={`fact fact-${r.result?.outcome === "pass" ? "yes" : r.result ? "no" : "unknown"}`}>
                <span className="fact-val">{r.result?.outcome ?? r.state}</span>
                <span>
                  {r.attempt_kind} · {r.source.scenario ?? r.source.kind}
                  {r.result && <div className="fact-note">{r.result.reason}</div>}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {view.test_run.synthetic && (
        <div className="replay-note">Based on a SYNTHETIC replay, not live hardware.</div>
      )}

      {result && (
        <section>
          <h4>What was observed</h4>
          <ul className="facts">
            {result.facts.map((f) => (
              <li key={f.key} className={`fact fact-${f.value}`}>
                <span className="fact-val">{f.value}</span>
                <span>{f.label}</span>
                {f.note && <div className="fact-note">{f.note}</div>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {recommended.length > 0 && (
        <section>
          <h4>Recommended next step</h4>
          {recommended.map((a) => (
            <ActionCard key={a.id} a={a} busy={busyActionId === a.id} onRun={onAction} primary />
          ))}
        </section>
      )}

      <section>
        <h4>Hypotheses <span className="dim">(qualitative rank, no probabilities)</span></h4>
        {view.hypotheses.length === 0 && <div className="dim">No rule matched. Evidence is insufficient to rank causes.</div>}
        {view.hypotheses.map((h) => (
          <HypothesisCard
            key={h.id}
            h={h}
            evById={evById}
            actions={h.recommended_action_ids.map((id) => actionsById.get(id)).filter(Boolean) as DiagnosticAction[]}
            busyActionId={busyActionId}
            closed={closed}
            onAction={onAction}
            onSelectNodes={onSelectNodes}
          />
        ))}
      </section>
    </div>
  );
}

function HypothesisCard(props: {
  h: Hypothesis;
  evById: Map<string, Evidence>;
  actions: DiagnosticAction[];
  busyActionId: string | null;
  closed: boolean;
  onAction: (a: DiagnosticAction) => void;
  onSelectNodes: (ids: string[]) => void;
}) {
  const { h, evById } = props;
  const [open, setOpen] = useState(h.rank === 1);
  return (
    <div className={`hyp status-${h.status}`}>
      <div className="hyp-head" onClick={() => setOpen(!open)}>
        <span className="rank">#{h.rank}</span>
        <span className="hyp-title">{h.title}</span>
        <span className={`hstatus hs-${h.status}`}>{STATUS_LABEL[h.status]}</span>
      </div>
      {open && (
        <div className="hyp-body">
          <p>{h.explanation}</p>
          <EvidenceList title="Supporting evidence" ids={h.supporting_evidence_ids} evById={evById} />
          {h.contradicting_evidence_ids.length > 0 && (
            <EvidenceList title="Contradicting evidence" ids={h.contradicting_evidence_ids} evById={evById} />
          )}
          {h.unknowns.length > 0 && (
            <div className="unknowns">
              <div className="sub">Unknowns</div>
              <ul>{h.unknowns.map((u) => <li key={u}>{u}</li>)}</ul>
            </div>
          )}
          <div className="hyp-actions">
            <button className="ghost" onClick={() => props.onSelectNodes([...h.related_node_ids])}>
              Show in graph
            </button>
            {!props.closed &&
              props.actions
                .filter((a) => a.status === "proposed" || a.kind === "repeat_test" || a.kind === "verify_fix")
                .map((a) => (
                  <ActionCard key={a.id} a={a} busy={props.busyActionId === a.id} onRun={props.onAction} compact />
                ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function EvidenceList({ title, ids, evById }: { title: string; ids: string[]; evById: Map<string, Evidence> }) {
  return (
    <div className="evlist">
      <div className="sub">{title}</div>
      <ul>
        {ids.map((id) => {
          const e = evById.get(id);
          return (
            <li key={id} title={id}>
              <span className={`evkind ek-${e?.kind}`}>{e?.kind.replace("_", " ") ?? "missing"}</span>{" "}
              {e ? e.summary : <i>evidence {id} not found</i>}
              {e?.provenance.file && (
                <span className="cite">
                  {" "}
                  {e.provenance.file}:{e.provenance.line_start}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function ActionCard(props: {
  a: DiagnosticAction;
  busy: boolean;
  onRun: (a: DiagnosticAction) => void;
  primary?: boolean;
  compact?: boolean;
}) {
  const { a } = props;
  const done = a.status === "completed" && a.kind !== "repeat_test" && a.kind !== "verify_fix";
  if (props.compact) {
    return (
      <button className={`action-btn ${done ? "done" : ""}`} disabled={props.busy} onClick={() => props.onRun(a)}>
        {props.busy ? "…" : done ? `✓ ${a.label}` : a.label}
      </button>
    );
  }
  return (
    <div className={`action-card ${props.primary ? "primary" : ""}`}>
      <div className="action-top">
        <button className="action-btn big" disabled={props.busy} onClick={() => props.onRun(a)}>
          {props.busy ? "Running…" : a.label}
        </button>
        {a.permission_category && <span className="perm">needs: {a.permission_category}</span>}
      </div>
      <div className="action-why">{a.rationale}</div>
      {a.expected_outcomes.length > 0 && (
        <ul className="outcomes">
          {a.expected_outcomes.map((o) => (
            <li key={o.result}>
              <b>{o.result}</b> → {o.interpretation}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function InspectResultModal({ result, onClose }: { result: ActionResult; onClose: () => void }) {
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>Inspect GPIO mapping</b>
          <button className="ghost" onClick={onClose}>Close</button>
        </div>
        <p className="dim">{result.summary}</p>
        {result.source_excerpts.map((ex) => (
          <div key={ex.evidence_id} className="excerpt">
            <div className="excerpt-file">{ex.file}</div>
            <pre>
              {ex.lines.map((line, i) => {
                const ln = ex.line_start + i;
                return (
                  <div key={ln} className={ex.highlight_lines.includes(ln) ? "hl-line" : ""}>
                    <span className="ln">{ln}</span>
                    {line || " "}
                  </div>
                );
              })}
            </pre>
          </div>
        ))}
        {result.evidence
          .filter((e) => e.kind === "manifest_entry")
          .map((e) => (
            <div key={e.id} className="excerpt">
              <div className="excerpt-file">
                hardware manifest{e.provenance.file ? ` · ${e.provenance.file}:${e.provenance.line_start}` : ""}
              </div>
              <div className="manifest-entry">{e.summary}</div>
            </div>
          ))}
        <p className="dim small">
          inteGREAT does not edit or flash firmware. Fix the pin (or the wiring) yourself, reflash, then click Verify fix.
        </p>
      </div>
    </div>
  );
}

export function ManualCheckModal(props: {
  action: DiagnosticAction;
  onSubmit: (result: string, note: string) => void;
  onClose: () => void;
}) {
  const [note, setNote] = useState("");
  const { action } = props;
  return (
    <div className="modal-bg" onClick={props.onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <b>{action.label}</b>
          <button className="ghost" onClick={props.onClose}>Cancel</button>
        </div>
        <p className="dim">{action.rationale}</p>
        <ol className="instructions">{action.manual_instructions.map((s) => <li key={s}>{s}</li>)}</ol>
        <textarea placeholder="Optional note (what you saw)" value={note} onChange={(e) => setNote(e.target.value)} />
        <div className="choice-row">
          {action.result_choices.map((c) => (
            <button key={c} className="action-btn" onClick={() => props.onSubmit(c, note)}>
              {c}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
