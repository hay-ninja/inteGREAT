import { useEffect, useState } from "react";
import { api, type DemoFixture, type Evidence, type Expectation, type NetlistPreview, type Project } from "../../lib/api";

type Mapping = {
  mcu_ref: string;
  board_label: string;
  components: { ref: string; id: string; type: string; label: string; pins: Record<string, string> }[];
  power_sources: { ref: string; id: string; label: string; terminals: Record<string, "pos" | "neg"> }[];
  subsystems: { id: string; label: string; source_globs: string[]; components: string[] }[];
  proposed: boolean;
  notes: string[];
};

export interface ImportArgs {
  repo_path: string;
  manifest_path?: string | null;
  netlist_path?: string | null;
  netlist_mapping?: Record<string, unknown> | null;
}

export function ImportScreen(props: {
  onImport: (a: ImportArgs) => void;
  onOpen: (p: Project) => void;
  busy: boolean;
  onError: (m: string) => void;
}) {
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [demoNetlist, setDemoNetlist] = useState("");
  const [recent, setRecent] = useState<Project[]>([]);
  const [repo, setRepo] = useState("");
  const [manifest, setManifest] = useState("");
  const [netlist, setNetlist] = useState("");
  const [preview, setPreview] = useState<NetlistPreview | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);

  useEffect(() => {
    api.demo().then((d) => { setFixtures(d.fixtures); setDemoNetlist(d.netlist_path); }).catch(() => undefined);
    api.projects().then((ps) => setRecent(ps.slice(-5).reverse())).catch(() => undefined);
  }, []);

  const doPreview = async (nl = netlist, rp = repo) => {
    try {
      const p = await api.netlistPreview(nl, rp || undefined);
      setPreview(p);
      setMapping(p.proposed_mapping as unknown as Mapping);
    } catch (e) {
      props.onError((e as Error).message);
    }
  };

  return (
    <div className="import-screen">
      <h1>inteGREAT</h1>
      <p className="dim">Import an existing ESP32 Arduino project and its hardware context. Nothing is executed or modified.</p>
      {recent.length > 0 && (
        <div className="import-card">
          <h3>Recent projects</h3>
          {recent.map((p) => (
            <button key={p.id} className="fixture" onClick={() => props.onOpen(p)}>
              <b>{p.name}</b>
              <span className="dim small">{p.repo_root} · {p.hardware_source} · graph v{p.graph_version}</span>
            </button>
          ))}
        </div>
      )}
      <div className="import-card">
        <h3>Demo fixtures</h3>
        {fixtures.map((f) => (
          <button key={f.repo_path} className="fixture" disabled={props.busy}
                  onClick={() => props.onImport({ repo_path: f.repo_path, manifest_path: f.manifest_path })}>
            <b>{f.label}</b>
            <span className="dim small">{f.repo_path} + YAML manifest</span>
          </button>
        ))}
        {fixtures[0] && demoNetlist && (
          <button className="fixture" disabled={props.busy}
                  onClick={() => { setRepo(fixtures[0].repo_path); setManifest(fixtures[0].manifest_path);
                                   setNetlist(demoNetlist); doPreview(demoNetlist, fixtures[0].repo_path); }}>
            <b>Fault A firmware + KiCad netlist</b>
            <span className="dim small">Review the proposed netlist mapping before importing</span>
          </button>
        )}
        <h3>Local repository</h3>
        <label>Repository path<input value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="C:\path\to\sketch" /></label>
        <label>
          Hardware manifest (YAML) — used directly, or as fallback for a netlist
          <input value={manifest} onChange={(e) => setManifest(e.target.value)} placeholder="C:\path\to\manifest.yaml" />
        </label>
        <label>
          KiCad XML netlist (optional)
          <div className="row">
            <input value={netlist} onChange={(e) => { setNetlist(e.target.value); setPreview(null); }}
                   placeholder="kicad-cli sch export netlist --format kicadxml" />
            <button className="ghost" disabled={!netlist} onClick={() => doPreview()}>Preview</button>
          </div>
        </label>
        {preview && mapping && <MappingEditor preview={preview} mapping={mapping} onChange={setMapping} />}
        <button className="action-btn big" disabled={props.busy || !repo || (!!netlist && !mapping)}
                onClick={() => props.onImport({
                  repo_path: repo, manifest_path: manifest || null, netlist_path: netlist || null,
                  netlist_mapping: mapping ? { ...mapping, proposed: false } : null })}>
          {props.busy ? "Importing…" : netlist ? "Confirm mapping & import" : "Import"}
        </button>
      </div>
    </div>
  );
}

function MappingEditor({ preview, mapping, onChange }: { preview: NetlistPreview; mapping: Mapping; onChange: (m: Mapping) => void }) {
  const setComp = (i: number, patch: Partial<Mapping["components"][number]>) =>
    onChange({ ...mapping, components: mapping.components.map((c, k) => (k === i ? { ...c, ...patch } : c)) });
  return (
    <div className="mapping">
      <div className="warn small">
        Proposed from net names and component values — confirm or edit. Netlist wiring is the designed schematic and
        will be marked <b>unverified</b> until you confirm the physical connections.
      </div>
      <div className="dim small">
        {preview.file}: {preview.components.length} components, {preview.nets.length} nets · MCU: <b>{mapping.mcu_ref}</b>
      </div>
      <table>
        <thead><tr><th>Ref</th><th>Id</th><th>Type</th><th>Pin → role</th></tr></thead>
        <tbody>
          {mapping.components.map((c, i) => (
            <tr key={c.ref}>
              <td>{c.ref}</td>
              <td><input value={c.id} onChange={(e) => setComp(i, { id: e.target.value })} /></td>
              <td>
                <select value={c.type} onChange={(e) => setComp(i, { type: e.target.value })}>
                  {["servo", "led", "other"].map((t) => <option key={t}>{t}</option>)}
                </select>
              </td>
              <td>
                {Object.entries(c.pins).map(([pin, role]) => (
                  <span key={pin} className="pinrole">
                    {pin}→<input value={role} onChange={(e) => setComp(i, { pins: { ...c.pins, [pin]: e.target.value } })} />
                  </span>
                ))}
              </td>
            </tr>
          ))}
          {mapping.power_sources.map((p) => (
            <tr key={p.ref}><td>{p.ref}</td><td>{p.id}</td><td>power</td>
              <td>{Object.entries(p.terminals).map(([pin, t]) => <span key={pin} className="pinrole">{pin}→{t}</span>)}</td></tr>
          ))}
        </tbody>
      </table>
      {preview.warnings.length > 0 && <ul className="small warn">{preview.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
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
              {c.provenance.file && <span className="cite"> {c.provenance.file}{c.provenance.line_start ? `:${c.provenance.line_start}` : ""}</span>}
            </li>
          ))}
        </ul>
      )}
      <button className="action-btn" onClick={confirm}>Confirm expectation</button>
    </div>
  );
}
