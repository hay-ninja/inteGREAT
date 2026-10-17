import { useEffect, useState } from "react";
import { api, type DemoFixture, type Evidence, type Expectation } from "../../lib/api";

export function ImportScreen({ onImport, busy }: { onImport: (repo: string, manifest: string | null) => void; busy: boolean }) {
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [repo, setRepo] = useState("");
  const [manifest, setManifest] = useState("");
  useEffect(() => {
    api.demoFixtures().then(setFixtures).catch(() => setFixtures([]));
  }, []);
  return (
    <div className="import-screen">
      <h1>inteGREAT</h1>
      <p className="dim">Import an existing ESP32 Arduino project and its hardware context. Nothing is executed or modified.</p>
      <div className="import-card">
        <h3>Demo fixtures</h3>
        {fixtures.map((f) => (
          <button key={f.repo_path} className="fixture" disabled={busy} onClick={() => onImport(f.repo_path, f.manifest_path)}>
            <b>{f.label}</b>
            <span className="dim small">{f.repo_path}</span>
          </button>
        ))}
        <h3>Local repository</h3>
        <label>Repository path<input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="C:\path\to\sketch" /></label>
        <label>
          Hardware manifest (YAML, optional)
          <input value={manifest} onChange={(e) => setManifest(e.target.value)} placeholder="C:\path\to\manifest.yaml" />
        </label>
        <button className="action-btn big" disabled={busy || !repo} onClick={() => onImport(repo, manifest || null)}>
          {busy ? "Importing…" : "Import"}
        </button>
      </div>
    </div>
  );
}

export function ExpectationCard(props: {
  projectId: string;
  expectation: Expectation | null;
  onChange: (e: Expectation) => void;
  onError: (msg: string) => void;
}) {
  const { expectation: exp } = props;
  const [draft, setDraft] = useState({ target: 90, tolerance: 8, deadline_ms: 2000, trigger: "" });
  const [cites, setCites] = useState<Evidence[]>([]);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!exp) return;
    setDraft({ target: exp.target, tolerance: exp.tolerance, deadline_ms: exp.deadline_ms, trigger: exp.trigger.value });
    api.evidence(props.projectId, exp.proposed_from_evidence_ids).then(setCites).catch(() => setCites([]));
  }, [exp, props.projectId]);

  if (!exp) {
    return (
      <div className="setup">
        <h4>Test expectation</h4>
        <p className="dim small">inteGREAT proposes a test from the source; you confirm it before it's used for pass/fail.</p>
        <button
          className="action-btn"
          onClick={() => api.proposeExpectation(props.projectId).then(props.onChange).catch((e) => props.onError(e.message))}
        >
          Propose test from code
        </button>
      </div>
    );
  }

  const confirmed = exp.confirmed_by_engineer && !editing;
  const confirm = () =>
    api
      .confirmExpectation(props.projectId, exp.id, {
        target: draft.target,
        tolerance: draft.tolerance,
        deadline_ms: draft.deadline_ms,
        trigger_value: draft.trigger,
      })
      .then((e) => {
        setEditing(false);
        props.onChange(e);
      })
      .catch((e) => props.onError(e.message));

  if (confirmed) {
    return (
      <div className="setup confirmed">
        <h4>
          Test expectation <span className="ok">✓ confirmed</span>
          <button className="ghost small" onClick={() => setEditing(true)}>Edit</button>
        </h4>
        <div className="exp-line">
          send <code>{exp.trigger.value}</code> → servo angle {exp.target}° ± {exp.tolerance}° within {exp.deadline_ms} ms
        </div>
        {exp.ack_pattern && <div className="dim small">firmware ACK expected: lines starting “{exp.ack_pattern}”</div>}
      </div>
    );
  }

  return (
    <div className="setup">
      <h4>Proposed test expectation <span className="warn">needs your confirmation</span></h4>
      <div className="exp-form">
        <label>Serial command<input value={draft.trigger} onChange={(e) => setDraft({ ...draft, trigger: e.target.value })} /></label>
        <label>Target °<input type="number" value={draft.target} onChange={(e) => setDraft({ ...draft, target: +e.target.value })} /></label>
        <label>Tolerance °<input type="number" value={draft.tolerance} onChange={(e) => setDraft({ ...draft, tolerance: +e.target.value })} /></label>
        <label>Deadline ms<input type="number" value={draft.deadline_ms} onChange={(e) => setDraft({ ...draft, deadline_ms: +e.target.value })} /></label>
      </div>
      <div className="dim small">Measured by: camera (marker angle). {exp.rationale}</div>
      {cites.length > 0 && (
        <ul className="cites">
          {cites.map((c) => (
            <li key={c.id}>
              {c.summary}
              {c.provenance.file && <span className="cite"> {c.provenance.file}:{c.provenance.line_start}</span>}
            </li>
          ))}
        </ul>
      )}
      <button className="action-btn" onClick={confirm}>Confirm expectation</button>
    </div>
  );
}
