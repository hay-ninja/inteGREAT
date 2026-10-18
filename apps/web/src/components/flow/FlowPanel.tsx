/**
 * Guided debugging flow (D-021): Set up → Run → Investigate → Verify.
 * Rule of thumb: each step shows ONE primary button. Alternatives and advanced tools are collapsed.
 */
import { useEffect, useState, type ReactNode } from "react";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Heading } from "@astryxdesign/core/Heading";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { Divider } from "@astryxdesign/core/Divider";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { TextInput } from "@astryxdesign/core/TextInput";
import { TextArea } from "@astryxdesign/core/TextArea";
import { Switch } from "@astryxdesign/core/Switch";
import { Spinner } from "@astryxdesign/core/Spinner";
import {
  api,
  type AgentStatus,
  type DiagnosticAction,
  type Evidence,
  type Expectation,
  type ExpectationResult,
  type Hypothesis,
  type InvestigationView,
  type PermissionCategory,
  type SourceOptions,
  type TestRun,
} from "../../lib/api";
import { CausalChain, EvidenceList, Eyebrow, Facts, SourceBadge, SourcePicker } from "./common";
import { latestRun, nextCheck } from "./flowState";

const STEPS = ["Setup", "Run", "Debug", "Verify"] as const;

export interface FlowProps {
  projectId: string;
  conflictNote: string | null;
  expectation: Expectation | null;
  onExpectation: (e: Expectation) => void;
  run: TestRun | null;
  running: boolean;
  view: InvestigationView | null;
  sources: SourceOptions;
  source: string;
  onSource: (v: string) => void;
  liveReady: boolean;
  onRun: () => void;
  busyActionId: string | null;
  onAction: (a: DiagnosticAction) => void;
  onPermission: (c: PermissionCategory, granted: boolean) => void;
  onMessage: (text: string) => Promise<void>;
  agentStatus: AgentStatus | null;
  diagnosing: boolean;
  onDiagnose: () => void;
  onReveal: (ids: string[]) => void;
  onNewTest: () => void;
  onError: (m: string) => void;
  onOpenDevices: () => void;
  onEvidence: (e: Evidence) => void;
  projectReview: ReactNode;
}

export function autoStep(p: Pick<FlowProps, "expectation" | "view">): number {
  if (p.view) return ["verifying", "resolved"].includes(p.view.incident.state) ? 3 : 2;
  return p.expectation?.confirmed_by_engineer ? 1 : 0;
}

export function FlowPanel(p: FlowProps) {
  const auto = autoStep(p);
  const [viewing, setViewing] = useState<number | null>(null);
  useEffect(() => setViewing(null), [auto]);
  const step = viewing ?? auto;

  return (
    <VStack gap={4}>
      <div className="chapters" role="tablist" aria-label="Debugging steps">
        {STEPS.map((s, i) => {
          const state =
            i === 2 && p.view && p.view.incident.state !== "resolved" && latestRun(p.view).result?.outcome === "fail" ? "error"
            : i === 3 && p.view?.incident.state === "resolved" ? "done"
            : i < auto ? "done" : i === auto ? "active" : "locked";
          return (
            <button key={s} type="button" role="tab" className="chapter" data-state={state}
                    aria-selected={step === i} disabled={i > auto || (!!p.view && i < auto)}
                    onClick={() => setViewing(i <= auto ? (i === auto ? null : i) : viewing)}>
              <span className="cnum">{String(i + 1).padStart(2, "0")}</span>
              <span className="cname">{s}</span>
              <span className="cbar" />
            </button>
          );
        })}
      </div>
      {step === 0 && <>{p.projectReview}<SetupStep {...p} /></>}
      {step === 1 && <RunStep {...p} />}
      {step === 2 && p.view && <InvestigateStep {...p} view={p.view} />}
      {step === 3 && p.view && <VerifyStep {...p} view={p.view} />}
      <Text type="supporting">Space — next action · 1–4 chapters · D graph · E event flow</Text>
    </VStack>
  );
}

/** Quiet, Obsidian-style callout (Astryx Banner's solid fills are too loud on charcoal). */
export function Notice({ tone, title, body, end }: {
  tone: "warning" | "error" | "success" | "accent" | "neutral"; title: string; body?: string; end?: ReactNode;
}) {
  return (
    <Card padding={3} variant="muted">
      <VStack gap={1}>
        <HStack gap={1.5} vAlign="center" hAlign="between" wrap="wrap">
          <HStack gap={1.5} vAlign="center">
            <StatusDot variant={tone} label={tone} />
            <Text type="body" weight="semibold">{title}</Text>
          </HStack>
          {end}
        </HStack>
        {body && <Text type="supporting">{body}</Text>}
      </VStack>
    </Card>
  );
}

// ------------------------------------------------------------------ 1. Set up

function SetupStep(p: FlowProps) {
  const exp = p.expectation;
  const [draft, setDraft] = useState({ target: 90, tolerance: 8, deadline_ms: 2000, trigger: "MOVE 90" });
  const [cites, setCites] = useState<Evidence[]>([]);
  useEffect(() => {
    if (!exp) return;
    setDraft({ target: exp.target, tolerance: exp.tolerance, deadline_ms: exp.deadline_ms, trigger: exp.trigger.value });
    api.evidence(p.projectId, exp.proposed_from_evidence_ids).then(setCites).catch(() => setCites([]));
  }, [exp, p.projectId]);

  if (!exp) {
    return (
      <VStack gap={3}>
        <Eyebrow num="01">Setup — define the test</Eyebrow>
        <Heading level={2} type="display-3">What should happen?</Heading>
        <Text type="body" color="secondary">
          inteGREAT reads the firmware and suggests a test. You confirm it before it decides pass or fail.
        </Text>
        {p.conflictNote && <Notice tone="warning" title="Already spotted a problem" body={p.conflictNote} />}
        <Button label="Suggest a test from the code" variant="primary" className="flow-primary"
                clickAction={() => api.proposeExpectation(p.projectId).then(p.onExpectation).catch((e) => p.onError(e.message))} />
      </VStack>
    );
  }
  const evById = new Map(cites.map((c) => [c.id, c]));
  return (
    <VStack gap={3}>
      <Eyebrow num="01">Setup — confirm the test</Eyebrow>
      <Heading level={2} type="display-3">Confirm the test</Heading>
      <Text type="body" color="secondary">Send a command, then the camera checks the servo angle.</Text>
      <Card padding={3} variant="muted">
        <VStack gap={3}>
          <Eyebrow>Test parameters</Eyebrow>
          <Text type="supporting">inteGREAT sends this command to the board, then watches the arm to check it actually moved.</Text>
          <TextInput label="Command to send" value={draft.trigger} onChange={(v) => setDraft({ ...draft, trigger: v })} />
          <HStack gap={2}>
            <NumberInput label="Target" units="°" value={draft.target} onChange={(v) => setDraft({ ...draft, target: v })} />
            <NumberInput label="± tolerance" units="°" value={draft.tolerance} min={0} onChange={(v) => setDraft({ ...draft, tolerance: v })} />
            <NumberInput label="Within" units="ms" value={draft.deadline_ms} min={100} step={100}
                         onChange={(v) => setDraft({ ...draft, deadline_ms: v })} />
          </HStack>
        </VStack>
      </Card>
      <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Why this test?</Text>}>
        <VStack gap={1}>
          {exp.rationale && <Text type="supporting">{exp.rationale}</Text>}
          <EvidenceList ids={cites.map((c) => c.id)} evById={evById} onInspect={p.onEvidence} />
        </VStack>
      </Collapsible>
      <Button label="Confirm test" variant="primary" className="flow-primary"
              clickAction={() => api.confirmExpectation(p.projectId, exp.id, {
                target: draft.target, tolerance: draft.tolerance, deadline_ms: draft.deadline_ms, trigger_value: draft.trigger,
              }).then(p.onExpectation).catch((e) => p.onError(e.message))} />
    </VStack>
  );
}

// ------------------------------------------------------------------ 2. Run

function RunStep(p: FlowProps) {
  const exp = p.expectation!;
  const passed = p.run?.result?.outcome === "pass" && !p.view;
  return (
    <VStack gap={3}>
      <Eyebrow num="02">Run — collect evidence</Eyebrow>
      <Heading level={2} type="display-3">Run the test</Heading>
      <Card padding={3} variant="muted">
        <VStack gap={0.5}>
          <Text type="code">{exp.trigger.value}</Text>
          <Text type="supporting">
            servo should reach {exp.target}° ± {exp.tolerance}° within {exp.deadline_ms} ms
          </Text>
        </VStack>
      </Card>
      {passed && p.run?.result && (
        <Notice tone="success" title="Passed" body={p.run.result.reason} end={<SourceBadge run={p.run} />} />
      )}
      <SourcePicker value={p.source} onChange={p.onSource} sources={p.sources} liveReady={p.liveReady} />
      {p.source === "live" && !p.liveReady ? <Button label="Set up the live rig" variant="primary" className="flow-primary" onClick={p.onOpenDevices} /> :
        <Button label={p.running ? "Running…" : passed ? "Run again" : "Run test"} variant="primary" className="flow-primary"
                isLoading={p.running} onClick={p.onRun} />}
    </VStack>
  );
}

// ------------------------------------------------------------------ 3. Investigate

function recommendedFor(h: Hypothesis | undefined, actions: DiagnosticAction[]): DiagnosticAction | undefined {
  if (!h) return undefined;
  const byId = new Map(actions.map((a) => [a.id, a]));
  const options = h.recommended_action_ids.map((id) => byId.get(id)).filter(Boolean) as DiagnosticAction[];
  return options.find((a) => a.kind !== "verify_fix" && a.status === "proposed") ?? options.find((a) => a.kind !== "verify_fix");
}

/** One-sentence story of the run for readers who don't know hardware: what went out, what came back, what moved. */
function inPlainTerms(result: ExpectationResult): string {
  const f = (k: string) => result.facts.find((x) => x.key === k)?.value;
  if (result.outcome === "inconclusive")
    return "In short: the camera could not measure the arm, so what happened physically is unknown — not proven broken.";
  const ack = f("command_acknowledged"), moved = f("physical_motion");
  if (moved === "no")
    return ack === "yes"
      ? "In short: the board received the command and replied OK, but the arm never moved — something between the code and the motor is wrong."
      : "In short: the command went out, but the board never confirmed it and the arm did not move.";
  if (moved === "unknown")
    return "In short: the command went out, but whether the arm moved is unknown — the camera produced no measurement.";
  return "";
}

const STATUS_LABEL: Record<string, string> = {
  supported: "supported", plausible: "plausible", unverified: "unverified", weakened: "weakened", ruled_out: "ruled out",
};

function InvestigateStep(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const evById = new Map(view.evidence.map((e) => [e.id, e]));
  const [top] = view.hypotheses;
  const primary = nextCheck(view);
  // Once the suggested check is done, the next real step is "fix it, then verify" — promote that instead.
  const currentRun = latestRun(view);
  const result = currentRun.result;
  if (p.running || currentRun.state === "running" || currentRun.state === "configured") return (
    <VStack gap={3}>
      <Eyebrow num="03">Debug — collect evidence</Eyebrow>
      <Heading level={2} type="display-3">Collecting measurements</Heading>
      <SourceBadge run={currentRun} />
      <Spinner label="Collecting new measurements…" />
      <Text type="supporting">The command and pass criteria stay the same. Diagnostic actions resume when this run finishes.</Text>
    </VStack>
  );
  const checkDone = primary?.status === "completed" || result?.outcome === "pass";
  const failedVerify = currentRun.attempt_kind === "verify" ? currentRun : undefined;
  const tied = top ? view.hypotheses.filter((h) => h.rank === top.rank) : [];
  // Secondary recommendations on the leading hypothesis (e.g. "Prepare software fix with Devin")
  // still need an explicit, reachable control — the primary button can't shadow them.
  const byId = new Map(view.actions.map((a) => [a.id, a]));
  const secondary = top
    ? top.recommended_action_ids.map((id) => byId.get(id)).filter((a): a is DiagnosticAction =>
        !!a && a.id !== primary?.id && a.status === "proposed" && a.kind !== "verify_fix")
    : [];
  return (
    <VStack gap={3}>
      {failedVerify?.result && failedVerify.result.outcome !== "pass" && (
        <Notice tone="warning" title={failedVerify.result.outcome === "inconclusive" ? "Fix not yet verified — measurement unavailable" : "The repair did not pass verification"} />
      )}
      <VStack gap={1}>
        <Eyebrow num="03">Debug — the incident</Eyebrow>
        <HStack hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2} type="display-3">{result?.outcome === "pass" ? "Repeat test passed" : result?.outcome === "inconclusive" ? "Measurement unavailable" : view.incident.title}</Heading>
          <SourceBadge run={currentRun} />
        </HStack>
        {result && <Text type="supporting">{result.final_valid_value == null ? "No valid angle measurement is available." : `Expected the arm at ${p.expectation?.target ?? "?"}° ± ${p.expectation?.tolerance ?? "?"}°, camera measured ${result.final_valid_value.toFixed(1)}°`}</Text>}
        {result && inPlainTerms(result) && <Text type="body" color="secondary">{inPlainTerms(result)}</Text>}
      </VStack>
      {result && <Facts result={result} />}
      {view.causal_chain.length > 0 && <CausalChain steps={view.causal_chain} />}
      <Divider />

      {result?.outcome === "pass" ? (
        <VStack gap={2}>
          <Text type="body">The latest repeat meets the expectation. Run verification to close this incident with a passing verification record.</Text>
          <VerifyLauncher {...p} label="Verify this result" emphasis="primary" />
          <EvidenceList title="Latest result" ids={[result.evidence_id]} evById={evById} onInspect={p.onEvidence} />
        </VStack>
      ) : top ? (
          <VStack gap={2}>
            <HStack hAlign="between" vAlign="center">
              <Eyebrow>{top.fault_code === "CAMERA_MEASUREMENT_UNAVAILABLE" ? "Observation issue" : tied.length > 1 ? "Possible causes · tied" : "Leading hypothesis"}</Eyebrow>
              <Text type="supporting">{STATUS_LABEL[top.status]}</Text>
            </HStack>
            <Heading level={3}>{tied.length > 1
              ? tied.every((h) => h.fault_code === "POSSIBLE_POWER_OR_SIGNAL_FAULT") ? "Signal or power connection" : `${tied.length} causes need a distinguishing check`
              : top.title}</Heading>
            {primary && (
              <Button label={checkDone ? `${primary.label} again` : primary.label}
                      variant={checkDone ? "ghost" : "primary"} className={checkDone ? undefined : "flow-primary"}
                      isLoading={p.busyActionId === primary.id}
                      tooltip={primary.rationale} onClick={() => p.onAction(primary)} />
            )}
            {checkDone && <VerifyLauncher {...p} label="I made a repair — verify it" emphasis="primary" />}
            {secondary.length > 0 && (
              <HStack gap={1} wrap="wrap">
                {secondary.map((a) => (
                  <Button key={a.id} label={a.label} size="sm" variant="ghost" tooltip={a.rationale}
                          isLoading={p.busyActionId === a.id} onClick={() => p.onAction(a)} />
                ))}
              </HStack>
            )}
            <Text type="supporting">{top.fault_code === "CAMERA_MEASUREMENT_UNAVAILABLE"
              ? "Check marker visibility and calibration, then repeat with valid measurements. Servo behavior is unknown until the camera can measure it."
              : primary?.rationale ?? top.explanation}</Text>
            {tied.length > 1 && <Text type="supporting">These causes have equal rank. The next check gathers evidence to distinguish them.</Text>}
            <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Why this check?</Text>}>
              <VStack gap={2}>
                <Text type="supporting">{top.explanation}</Text>
                {primary?.expected_outcomes.map((o) => <Text key={o.result} type="supporting">{o.result}: {o.interpretation}</Text>)}
              </VStack>
            </Collapsible>
            <EvidenceList title="Supporting evidence — select to inspect" ids={top.supporting_evidence_ids.slice(0, 2)} evById={evById} onInspect={p.onEvidence} />
            <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Evidence and unknowns</Text>}>
              <VStack gap={2}>
                <EvidenceList title="Supports it" ids={top.supporting_evidence_ids} evById={evById} onInspect={p.onEvidence} />
                <EvidenceList title="Against it" ids={top.contradicting_evidence_ids} evById={evById} onInspect={p.onEvidence} />
                {top.unknowns.length > 0 && (
                  <VStack gap={0.5}>
                    <Eyebrow>Not measured / unknown</Eyebrow>
                    {top.unknowns.map((u) => <Text key={u} type="supporting">• {u}</Text>)}
                  </VStack>
                )}
                {top.related_node_ids.length > 0 && (
                  <Button label="Show in graph" size="sm" variant="ghost" onClick={() => p.onReveal(top.related_node_ids)} />
                )}
              </VStack>
            </Collapsible>
          </VStack>
      ) : (
        <Notice tone="neutral" title="No rule matched" body="Evidence is not enough to rank causes. Try a manual check or ask the agents." />
      )}

      {view.incident.agent_summary && (
        <Card padding={3} variant="muted">
          <VStack gap={1}>
            <Eyebrow>AI agents (inference, not measurement)</Eyebrow>
            <Text type="body">{view.incident.agent_summary}</Text>
          </VStack>
        </Card>
      )}

      {!checkDone && <VerifyLauncher {...p} label="I made a repair — verify it" emphasis="secondary" />}
      <AIReview {...p} />

      {view.hypotheses.length > 1 && (
        <Collapsible defaultIsOpen={false} trigger={<Text type="label">All hypotheses ({view.hypotheses.length})</Text>}>
          <VStack gap={2}>
            {view.hypotheses.map((h) => <OtherHypothesis key={h.id} h={h} {...p} />)}
          </VStack>
        </Collapsible>
      )}
      <MoreTools {...p} />
    </VStack>
  );
}

function OtherHypothesis(p: FlowProps & { h: Hypothesis; view: InvestigationView }) {
  const a = recommendedFor(p.h, p.view.actions);
  return (
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <Text type="body" weight="medium">{p.h.title}</Text>
          <Text type="supporting">{STATUS_LABEL[p.h.status]}</Text>
        </HStack>
        <Text type="supporting" maxLines={3}>{p.h.explanation}</Text>
        {a && <Button label={a.label} size="sm" isLoading={p.busyActionId === a.id} onClick={() => p.onAction(a)} />}
      </VStack>
  );
}

function VerifyLauncher(p: FlowProps & { view: InvestigationView; label: string; emphasis: "primary" | "secondary" }) {
  const [open, setOpen] = useState(false);
  const verify = p.view.actions.find((a) => a.kind === "verify_fix");
  if (!verify) return null;
  return (
    <>
      <Button label={p.label} variant={p.emphasis} className={p.emphasis === "primary" ? "flow-primary" : undefined}
              onClick={() => setOpen(true)} />
      <Dialog isOpen={open} onOpenChange={setOpen} width={500} purpose="form">
        <DialogHeader title="Verify the repair" subtitle="The same command and acceptance criteria will be used." onOpenChange={setOpen} />
      <VStack gap={3} padding={4}>
        {p.expectation && <VStack gap={0.5}><Text type="code">{p.expectation.trigger.value}</Text><Text type="supporting">{p.expectation.target}° ± {p.expectation.tolerance}° within {p.expectation.deadline_ms} ms</Text></VStack>}
        <Text type="supporting">Apply the repair outside inteGREAT. Release the serial port before flashing, then reconnect and rescan the repository.</Text>
        <Text type="label">Re-run the same test with</Text>
        <SourcePicker value={p.source} onChange={p.onSource} sources={p.sources} liveReady={p.liveReady} />
        {p.source.split(":")[0] !== p.view.test_run.source.kind && <Notice tone="warning" title="Observation source changed" body="Verification applies to the selected source. A simulated or replay pass does not verify a live hardware repair." />}
        <HStack gap={1}>
          <Button label="Run verification" variant="primary" isLoading={p.busyActionId === verify.id}
                  isDisabled={p.source === "live" && !p.liveReady} onClick={() => { setOpen(false); p.onAction(verify); }} />
          {p.source === "live" && !p.liveReady && <Button label="Set up rig" onClick={() => { setOpen(false); p.onOpenDevices(); }} />}
          <Button label="Cancel" variant="ghost" onClick={() => setOpen(false)} />
        </HStack>
      </VStack>
      </Dialog>
    </>
  );
}

function AIReview(p: FlowProps & { view: InvestigationView }) {
  const rounds = p.view.incident.agent_rounds_used;
  const unavailable = !p.agentStatus?.available;
  const reason = unavailable ? p.agentStatus?.reason ?? "Provider not configured" : rounds >= 2 ? "Two investigation rounds used" : "";
  const evById = new Map(p.view.evidence.map((e) => [e.id, e]));
  return <VStack gap={2}>
    <Divider />
    <Eyebrow>AI evidence review</Eyebrow>
    <Text type="supporting">Code, hardware, telemetry, and vision specialists can review this investigation — a critic pass then tries to invalidate the leading hypotheses before a next check is recommended.</Text>
    {reason && <Text type="supporting">{reason}. Deterministic checks remain available.</Text>}
    <Button label={p.diagnosing ? "Reviewing evidence…" : rounds ? "Review new evidence" : "Ask AI to review evidence"}
            size="sm" isLoading={p.diagnosing} isDisabled={!!reason} onClick={p.onDiagnose} />
    {p.agentStatus?.available && <Text type="supporting">{p.agentStatus.provider} · {p.agentStatus.model} · round {rounds}/2</Text>}
    {p.agentStatus && p.agentStatus.stages.length > 0 && (
      <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Provider per stage</Text>}>
        <VStack gap={0.5}>
          {p.agentStatus.stages.map((s) => (
            <Text key={s.role} type="supporting">
              {s.role}: {s.provider}{s.model ? ` · ${s.model}` : ""} — {s.available ? "available" : `unavailable (${s.reason ?? "not configured"})`}
            </Text>
          ))}
        </VStack>
      </Collapsible>
    )}
    {p.view.agent_runs.filter((r) => r.agent !== "orchestrator").map((r) => (
      <Collapsible key={r.id} defaultIsOpen={false} trigger={<Text type="supporting">{r.agent.replace("_", "/")}: {r.status}{r.validation_errors.length ? ` · ${r.validation_errors.length} rejected` : ""}</Text>}>
        <VStack gap={2}>
          {r.error && <Text type="supporting">{r.error}</Text>}
          {r.report?.findings.map((f, i) => <VStack key={i} gap={1}><Text type="supporting">{f.statement}</Text><EvidenceList ids={f.supporting_evidence_ids} evById={evById} onInspect={p.onEvidence} /></VStack>)}
          {r.validation_errors.map((e, i) => <Text key={i} type="supporting">Rejected: {e}</Text>)}
        </VStack>
      </Collapsible>
    ))}
  </VStack>;
}

const PERMS: { id: PermissionCategory; label: string; hint: string }[] = [
  { id: "repo_read", label: "Read source code", hint: "imported repository only" },
  { id: "netlist_read", label: "Read wiring", hint: "manifest / netlist" },
  { id: "serial_read", label: "Read serial output", hint: "device buffer or recordings" },
  { id: "camera_observe", label: "Read camera data", hint: "angle measurements, no video" },
];

function MoreTools(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const granted = new Set(view.permissions.map((g) => g.category));
  const extra = view.actions.filter((a) => a.tool_name && a.kind !== "inspect_source");
  const [note, setNote] = useState("");
  return (
    <Collapsible defaultIsOpen={false} trigger={<Eyebrow>More tools</Eyebrow>}>
      <VStack gap={3}>
        {extra.length > 0 && (
          <VStack gap={1}>
            <Eyebrow>Read-only tools</Eyebrow>
            <HStack gap={1} wrap="wrap">
              {extra.map((a) => (
                <Button key={a.id} label={a.label} size="sm" tooltip={a.rationale}
                        isLoading={p.busyActionId === a.id} onClick={() => p.onAction(a)} />
              ))}
            </HStack>
          </VStack>
        )}
        <VStack gap={1}>
          <Eyebrow>Permissions for this investigation</Eyebrow>
          {PERMS.map((c) => (
            <Switch key={c.id} size="sm" label={c.label} description={c.hint} value={granted.has(c.id)}
                    labelSpacing="spread" width="100%" onChange={(v) => p.onPermission(c.id, v)} />
          ))}
          <Text type="supporting">Flashing firmware and writing to the device are never available.</Text>
        </VStack>
        <VStack gap={1}>
          <TextArea label="Add a note" description="Symptoms or observations. Stored as evidence; never grants permissions."
                    value={note} rows={2} onChange={setNote} />
          <Button label="Add note" size="sm" isDisabled={!note.trim()}
                  clickAction={async () => { await p.onMessage(note.trim()); setNote(""); }} />
          {view.messages.map((m) => <Text key={m.id} type="supporting">• {String(m.payload.text)}</Text>)}
        </VStack>
      </VStack>
    </Collapsible>
  );
}

// ------------------------------------------------------------------ 4. Verify

function VerifyStep(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const inc = view.incident;
  if (inc.state === "verifying") {
    return (
      <VStack gap={3} hAlign="center">
        <Eyebrow num="04">Verify — same test again</Eyebrow>
        <Spinner size="lg" label="Re-running the same test…" />
        <Text type="supporting">Same command, same pass criteria.</Text>
      </VStack>
    );
  }
  const v = view.followup_runs.find((r) => r.id === inc.resolved_by_test_run_id);
  const title = v?.source.kind === "sim" ? "Verified on the simulated rig"
    : v?.source.kind === "replay" ? `Verified on ${v.synthetic ? "synthetic" : "recorded"} replay`
    : v?.source.kind === "live" ? "Fixed — verified on live hardware" : "Verification record unavailable";
  return (
    <VStack gap={3}>
      <Eyebrow num="04">Verify — closed loop</Eyebrow>
      <Notice tone="success" title={title}
              body={v?.result?.reason ?? "The same test now passes."} end={v ? <SourceBadge run={v} /> : undefined} />
      {v?.synthetic && <Text type="supporting">Verified on synthetic data, not live hardware.</Text>}
      {v?.result && <Facts result={v.result} />}
      <Text type="body" color="secondary">Was: {view.hypotheses[0]?.title ?? inc.title}</Text>
      <Button label="Start a new test" variant="primary" className="flow-primary" onClick={p.onNewTest} />
    </VStack>
  );
}
