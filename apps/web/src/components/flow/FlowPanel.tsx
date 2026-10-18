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
import { TabList, Tab } from "@astryxdesign/core/TabList";
import { Badge } from "@astryxdesign/core/Badge";
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

/**
 * Guided debugging flow (D-021, views per D-041): Test → Debug → Analyze are freely
 * switchable views, not a locked wizard — debugging is a loop, so Test stays reachable.
 * Rule of thumb: each view shows ONE primary button. Alternatives are collapsed.
 */

const VIEWS = ["Test", "Debug", "Analyze", "History"] as const;
type FlowView = "test" | "debug" | "analyze" | "history";

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
  agentProgress: { phase: "triage" | "specialists" | "critique" | "synthesis" | "done"; agents: string[]; reported: string[] } | null;
  onDiagnose: () => void;
  onReveal: (ids: string[]) => void;
  onNewTest: () => void;
  onError: (m: string) => void;
  onOpenDevices: () => void;
  onEvidence: (e: Evidence) => void;
  onSelectRun: (r: TestRun) => void;
  viewRequest: { view: FlowView; seq: number } | null;
  flowSeq: number;
  projectReview: ReactNode;
}

/** Which view to show when the user hasn't picked one: an open/resolved incident → Debug. */
export function autoView(p: Pick<FlowProps, "view">): FlowView {
  return p.view ? "debug" : "test";
}

export function FlowPanel(p: FlowProps) {
  const auto = autoView(p);
  const [viewing, setViewing] = useState<FlowView | null>(null);
  useEffect(() => setViewing(null), [auto]);
  const requestSeq = p.viewRequest?.seq;
  useEffect(() => { if (p.viewRequest) setViewing(p.viewRequest.view); }, [requestSeq]); // eslint-disable-line react-hooks/exhaustive-deps
  const view = viewing ?? auto;

  return (
    <VStack gap={4}>
      <div className="chapters" role="tablist" aria-label="Workspace views">
        {VIEWS.map((v) => {
          const id = v.toLowerCase() as FlowView;
          const active = view === id;
          const alert = id === "debug" && p.view && p.view.incident.state !== "resolved"
                        && latestRun(p.view).result?.outcome === "fail";
          const resolved = id === "debug" && p.view?.incident.state === "resolved";
          return (
            <button key={v} type="button" role="tab" className="chapter"
                    data-state={alert ? "error" : resolved ? "done" : active ? "active" : "idle"}
                    aria-selected={active} onClick={() => setViewing(active ? null : id)}>
              <span className="cname">{v}{id === "analyze" && p.diagnosing ? " …" : ""}</span>
              <span className="cbar" />
            </button>
          );
        })}
      </div>
      {view === "test" && <>{p.projectReview}<TestView {...p} /></>}
      {view === "debug" && (p.view ? <DebugView {...p} view={p.view} />
        : p.run?.incident_id ? <Spinner label="Loading investigation…" />
        : p.run?.result ? <RunRecord {...p} run={p.run} /> : (
        <VStack gap={3}>
          <Eyebrow>Debug</Eyebrow>
          <Heading level={2} type="display-3">Nothing to debug yet</Heading>
          <Text type="body" color="secondary">
            Run a test in the Test view. If it fails or can't be measured, the investigation opens here —
            causes ranked by evidence, with a suggested next check.
          </Text>
        </VStack>
      ))}
      {view === "analyze" && <AnalyzeView {...p} />}
      {view === "history" && <HistoryView {...p} />}
      <Text type="supporting">Space — next action · 1–4 views · D graph · E event flow</Text>
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

// ------------------------------------------------------------------ Test view (define + run — always reachable)

/** Plain-English name for what the camera measures, derived from the expectation's metric. */
const NOUNS: Record<string, string> = { led_state: "the light", servo_angle_deg: "the arm" };
const noun = (exp?: { metric: string } | null) => NOUNS[exp?.metric ?? ""] ?? "the component";
const goalText = (exp: { metric: string; unit: string; target: number; tolerance: number; deadline_ms: number }) =>
  exp.unit === "state"
    ? `${noun(exp)} should ${exp.target === 1 ? "turn on" : "turn off"} within ${exp.deadline_ms} ms`
    : `${noun(exp)} should reach ${exp.target}° ± ${exp.tolerance}° within ${exp.deadline_ms} ms`;

function TestView(p: FlowProps) {
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
        <Eyebrow>Test — define what should happen</Eyebrow>
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

  if (!exp.confirmed_by_engineer) {
    const evById = new Map(cites.map((c) => [c.id, c]));
    return (
      <VStack gap={3}>
        <Eyebrow>Test — confirm it first</Eyebrow>
        <Heading level={2} type="display-3">Confirm the test</Heading>
        <Text type="body" color="secondary">Send a command, then the camera checks whether {noun(exp)} responded.</Text>
        <Card padding={3} variant="muted">
          <VStack gap={3}>
            <Eyebrow>Test parameters</Eyebrow>
            <Text type="supporting">inteGREAT sends this command to the board, then watches {noun(exp)} to check it actually responded.</Text>
            <TextInput label="Command to send" value={draft.trigger} onChange={(v) => setDraft({ ...draft, trigger: v })} />
            <HStack gap={2}>
              <NumberInput label="Target" units={exp.unit === "state" ? "state" : exp.unit} value={draft.target} onChange={(v) => setDraft({ ...draft, target: v })} />
              <NumberInput label="± tolerance" units={exp.unit === "state" ? "state" : exp.unit} value={draft.tolerance} min={0} onChange={(v) => setDraft({ ...draft, tolerance: v })} />
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

  // Confirmed — the runnable test. Stays reachable from any debugging state.
  const incidentOpen = !!p.view && p.view.incident.state !== "resolved";
  const resolved = p.view?.incident.state === "resolved";
  const repeat = p.view?.actions.find((a) => a.kind === "repeat_test" && a.status === "proposed");
  const last = p.view ? latestRun(p.view) : p.run;
  const passed = last?.result?.outcome === "pass" && !incidentOpen;
  return (
    <VStack gap={3}>
      <Eyebrow>Test</Eyebrow>
      <Heading level={2} type="display-3">{resolved ? "Start fresh, or re-run" : "Run the test"}</Heading>
      <Card padding={3} variant="muted">
        <VStack gap={0.5}>
          <Text type="code">{exp.trigger.value}</Text>
          <Text type="supporting">{goalText(exp)}</Text>
        </VStack>
      </Card>
      {resolved && (
        <Notice tone="success" title="Previous incident verified"
                body="The last verification passed. Running again starts a fresh record."
                end={last ? <SourceBadge run={last} /> : undefined} />
      )}
      {passed && last?.result && (
        <Notice tone="success" title="Passed" body={last.result.reason} end={<SourceBadge run={last} />} />
      )}
      {incidentOpen && last?.result && last.result.outcome !== "pass" && (
        <Notice tone="warning" title={`Latest run: ${last.result.outcome}`}
                body={last.result.reason} end={<SourceBadge run={last} />} />
      )}
      <SourcePicker value={p.source} onChange={p.onSource} sources={p.sources} liveReady={p.liveReady} />
      {p.source === "live" && p.liveReady && (
        <Notice tone="warning" title="Live hardware debugging"
                body="This run sends the command to the real board — the rig may physically move. Measurements come from the serial line and camera, not simulation." />
      )}
      {p.source === "live" && !p.liveReady
        ? <Button label="Set up the live rig" variant="primary" className="flow-primary" onClick={p.onOpenDevices} />
        : resolved
          ? <Button label="Start a new test" variant="primary" className="flow-primary" onClick={p.onNewTest} />
          : incidentOpen && repeat
            ? <Button label="Run the test again" variant="primary" className="flow-primary"
                      isLoading={p.busyActionId === repeat.id} onClick={() => p.onAction(repeat)} />
            : <Button label={p.running ? "Running…" : passed ? "Run again" : "Run test"} variant="primary" className="flow-primary"
                      isLoading={p.running} onClick={p.onRun} />}
      {incidentOpen && (
        <Text type="supporting">
          A failure or missing measurement opens an investigation in Debug — re-running here keeps it in the same incident.
        </Text>
      )}
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

/** One-sentence story of the run for readers who don't know hardware: what went out, what came back, what changed. */
function inPlainTerms(result: ExpectationResult, exp?: { metric: string; unit: string } | null): string {
  const f = (k: string) => result.facts.find((x) => x.key === k)?.value;
  const what = noun(exp);
  const responded = exp?.unit === "state" ? "never changed" : "never moved";
  if (result.outcome === "inconclusive")
    return `In short: the camera could not measure ${what}, so what happened physically is unknown — not proven broken.`;
  const ack = f("command_acknowledged"), moved = f("physical_motion");
  if (moved === "no")
    return ack === "yes"
      ? `In short: the board received the command and replied OK, but ${what} ${responded} — something between the code and the hardware is wrong.`
      : `In short: the command went out, but the board never confirmed it and ${what} did not respond.`;
  if (moved === "unknown")
    return `In short: the command went out, but whether ${what} responded is unknown — the camera produced no measurement.`;
  const st = f("physical_state");
  if (moved === "yes" && st === "no")
    return `In short: ${what} responded to the command — but ended in the wrong state. That's backwards logic, not a dead lead.`;
  return "";
}

const STATUS_LABEL: Record<string, string> = {
  supported: "supported", plausible: "plausible", unverified: "unverified", weakened: "weakened", ruled_out: "ruled out",
};

/** Where a hypothesis came from — the difference between the rules engine and an AI inference (D-041). */
function OriginTag({ origin }: { origin: "rule" | "agent" }) {
  return origin === "agent"
    ? <Badge variant="purple" label="AI" icon={undefined} />
    : <Badge variant="neutral" label="Rules" icon={undefined} />;
}

function DebugView(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const [tab, setTab] = useState<"overview" | "causes">("overview");
  const evById = new Map(view.evidence.map((e) => [e.id, e]));
  const [top] = view.hypotheses;
  const primary = nextCheck(view);
  // Once the suggested check is done, the next real step is "fix it, then verify" — promote that instead.
  const currentRun = latestRun(view);
  const result = currentRun.result;
  if (view.incident.state === "resolved") return <VerifyRecord {...p} view={view} />;
  if (p.running || currentRun.state === "running" || currentRun.state === "configured") return (
    <VStack gap={3}>
      <Eyebrow>Debug — collect evidence</Eyebrow>
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
      <VStack gap={1}>
        <Eyebrow>Debug — the incident</Eyebrow>
        <HStack hAlign="between" vAlign="center" wrap="wrap">
          <Heading level={2} type="display-3">{result?.outcome === "pass" ? "Repeat test passed" : result?.outcome === "inconclusive" ? "Measurement unavailable" : view.incident.title}</Heading>
          <SourceBadge run={currentRun} />
        </HStack>
        {result && <Text type="supporting">{result.final_valid_value == null ? "No valid measurement is available." : p.expectation?.unit === "state" ? `Expected ${noun(p.expectation)} ${p.expectation?.target === 1 ? "on" : "off"}, camera saw ${result.final_valid_value === 1 ? "on" : "off"}` : `Expected ${noun(p.expectation)} at ${p.expectation?.target ?? "?"}° ± ${p.expectation?.tolerance ?? "?"}°, camera measured ${result.final_valid_value.toFixed(1)}°`}</Text>}
        {result && inPlainTerms(result, p.expectation) && <Text type="body" color="secondary">{inPlainTerms(result, p.expectation)}</Text>}
      </VStack>

      <TabList role="tablist" value={tab} onChange={(v) => setTab(v as typeof tab)} size="sm" hasDivider>
        <Tab value="overview" label="Overview" panelId="dbg-overview" />
        <Tab value="causes" label="Potential causes" panelId="dbg-causes"
             endContent={view.hypotheses.length ? <Text type="supporting">{view.hypotheses.length}</Text> : undefined} />
      </TabList>

      {/* Panels stay mounted (hidden, not unmounted) so the primary action keeps
          working from Space and collapsible state survives tab switches. */}
      <div id="dbg-overview" role="tabpanel" hidden={tab !== "overview"}>
        <VStack gap={3}>
          {failedVerify?.result && failedVerify.result.outcome !== "pass" && (
            <Notice tone="warning" title={failedVerify.result.outcome === "inconclusive" ? "Fix not yet verified — measurement unavailable" : "The repair did not pass verification"} />
          )}
          {result && <Facts result={result} />}
          {view.causal_chain.length > 0 && (
            <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">The full evidence chain ({view.causal_chain.length} steps)</Text>}>
              <CausalChain steps={view.causal_chain} />
            </Collapsible>
          )}
          {result?.outcome === "pass" && (
            <VStack gap={2}>
              <Text type="body">The latest repeat meets the expectation. Run verification to close this incident with a passing verification record.</Text>
              <VerifyLauncher {...p} label="Verify this result" emphasis="primary" />
              <EvidenceList title="Latest result" ids={[result.evidence_id]} evById={evById} onInspect={p.onEvidence} />
            </VStack>
          )}
        </VStack>
      </div>

      <div id="dbg-causes" role="tabpanel" hidden={tab !== "causes"}>
        <VStack gap={3}>
          {result?.outcome === "pass" ? (
            <Notice tone="success" title="Latest repeat passed" body="No open causes to rank — verify to close the incident." />
          ) : top ? (
          <VStack gap={2}>
            <HStack hAlign="between" vAlign="center">
              <Eyebrow>{top.fault_code === "CAMERA_MEASUREMENT_UNAVAILABLE" ? "Observation issue" : tied.length > 1 ? "Possible causes · tied" : "Leading hypothesis"}</Eyebrow>
              <Text type="supporting">{STATUS_LABEL[top.status]}</Text>
            </HStack>
            <HStack gap={2} vAlign="center">
              <Heading level={3}>{tied.length > 1
                ? tied.every((h) => h.fault_code === "POSSIBLE_POWER_OR_SIGNAL_FAULT") ? "Signal or power connection" : `${tied.length} causes need a distinguishing check`
                : top.title}</Heading>
              <OriginTag origin={top.origin} />
            </HStack>
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
              ? "Check marker visibility and calibration, then repeat with valid measurements. The component's behavior is unknown until the camera can measure it."
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
          {!checkDone && result?.outcome !== "pass" && <VerifyLauncher {...p} label="I made a repair — verify it" emphasis="secondary" />}
          {view.hypotheses.length > 1 && (
            <Collapsible defaultIsOpen={false} trigger={<Text type="label">All hypotheses ({view.hypotheses.length})</Text>}>
              <VStack gap={2}>
                {view.hypotheses.map((h) => <OtherHypothesis key={h.id} h={h} {...p} />)}
              </VStack>
            </Collapsible>
          )}
        </VStack>
      </div>
    </VStack>
  );
}

function OtherHypothesis(p: FlowProps & { h: Hypothesis; view: InvestigationView }) {
  const a = recommendedFor(p.h, p.view.actions);
  return (
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <HStack gap={2} vAlign="center">
            <Text type="body" weight="medium">{p.h.title}</Text>
            <OriginTag origin={p.h.origin} />
          </HStack>
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
  { id: "camera_observe", label: "Read camera data", hint: "measurement readings, no video" },
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

// ------------------------------------------------------------------ Debug view: resolved state

function VerifyRecord(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const inc = view.incident;
  if (inc.state === "verifying") {
    return (
      <VStack gap={3} hAlign="center">
        <Eyebrow>Debug — verifying</Eyebrow>
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
      <Eyebrow>Debug — resolved</Eyebrow>
      <Notice tone="success" title={title}
              body={v?.result?.reason ?? "The same test now passes."} end={v ? <SourceBadge run={v} /> : undefined} />
      {v?.synthetic && <Text type="supporting">Verified on synthetic data, not live hardware.</Text>}
      {v?.result && <Facts result={v.result} />}
      <Text type="body" color="secondary">Was: {view.hypotheses[0]?.title ?? inc.title}</Text>
      <Button label="Start a new test" variant="primary" className="flow-primary" onClick={p.onNewTest} />
    </VStack>
  );
}

// The stages an agent round moves through (D-041) — a live step list the engineer
// watches while diagnosis runs, fed by agent.stage / agent.reported events.
const AGENT_STAGES = [
  { key: "triage", label: "Triage — choosing which specialists to consult" },
  { key: "specialists", label: "Specialists — reviewing the evidence" },
  { key: "critique", label: "Critic — trying to falsify the leading hypotheses" },
  { key: "synthesis", label: "Synthesis — writing the summary and next check" },
] as const;

function AgentSteps({ progress }: { progress: NonNullable<FlowProps["agentProgress"]> }) {
  const order = AGENT_STAGES.map((s) => s.key) as string[];
  const at = progress.phase === "done" ? order.length : order.indexOf(progress.phase);
  return (
    <Card padding={3} variant="muted">
      <VStack gap={1.5}>
        <Eyebrow>{progress.phase === "done" ? "Agent round finished" : "Agents working…"}</Eyebrow>
        {AGENT_STAGES.map((s, i) => (
          <HStack key={s.key} gap={2} vAlign="center">
            {i < at ? <StatusDot variant="success" label="done" />
              : i === at ? <Spinner size="sm" />
              : <StatusDot variant="neutral" label="pending" />}
            <Text type="supporting" color={i > at ? "secondary" : undefined}>{s.label}</Text>
          </HStack>
        ))}
        {progress.agents.length > 0 && (
          <Text type="supporting" color="secondary" style={{ paddingLeft: 24 }}>
            {progress.agents.map((a) => `${a}${progress.reported.includes(a) ? " ✓" : " …"}`).join("   ")}
          </Text>
        )}
      </VStack>
    </Card>
  );
}

/** Structured agent synthesis (D-041): the summary stays a paragraph, contradictions and
    the outcome explanation render as their own sections, and the recommended check is a
    real button — resolved from the action catalog, never agent-authored text. */
function AgentSummary(p: FlowProps & { view: InvestigationView }) {
  const inc = p.view.incident;
  const evById = new Map(p.view.evidence.map((e) => [e.id, e]));
  const action = nextCheck(p.view);
  // Older stored incidents predate these fields — treat absent as empty, never crash.
  const contradictions = inc.agent_contradictions ?? [];
  const cited = [...new Set(
    [inc.agent_summary ?? "", ...contradictions, inc.agent_check_explanation]
      .join(" ").match(/evidence:[A-Za-z0-9_.:-]+/g) ?? [],
  )].slice(0, 10);
  return (
    <Card padding={3} variant="muted">
      <VStack gap={2}>
        <Eyebrow>AI agents (inference, not measurement)</Eyebrow>
        <Text type="body">{inc.agent_summary}</Text>
        {contradictions.length > 0 && (
          <VStack gap={0.5}>
            <Text type="label">Contradictions</Text>
            {contradictions.map((c, i) => <Text key={i} type="supporting">• {c}</Text>)}
          </VStack>
        )}
        {inc.agent_check_explanation && (
          <VStack gap={0.5}>
            <Text type="label">What the recommended check shows</Text>
            <Text type="supporting">{inc.agent_check_explanation}</Text>
          </VStack>
        )}
        {cited.length > 0 && <EvidenceList title="Evidence cited" ids={cited} evById={evById} onInspect={p.onEvidence} />}
        {action && (
          <Button label={`Run: ${action.label}`} variant="primary" size="sm" tooltip={action.rationale}
                  isLoading={p.busyActionId === action.id} onClick={() => p.onAction(action)} />
        )}
      </VStack>
    </Card>
  );
}

// ------------------------------------------------------------------ Analyze view (AI — clearly fenced)

function AnalyzeView(p: FlowProps) {
  const view = p.view;
  return (
    <VStack gap={3}>
      <Eyebrow>Analyze — where AI helps</Eyebrow>
      <Heading level={2} type="display-3">AI analysis</Heading>
      <Card padding={3} variant="muted">
        <VStack gap={1.5}>
          <Text type="body" weight="semibold">Everything else on this screen is deterministic.</Text>
          <Text type="supporting">
            The map comes from your code and wiring files, checks come from fixed rules, and every claim cites
            evidence you can open. AI only helps reason over that evidence — it never produces a measurement:
          </Text>
          <VStack gap={1}>
            <Text type="supporting">1. <Text type="supporting" weight="semibold">Evidence review</Text> — a StepFun orchestrator dispatches Gemini specialists (code, hardware, telemetry, vision). Findings must cite existing evidence or they're rejected.</Text>
            <Text type="supporting">2. <Text type="supporting" weight="semibold">New hypotheses</Text> — causes an agent proposes appear in Debug → Potential causes tagged "AI". Rule-based causes are tagged "Rules".</Text>
            <Text type="supporting">3. <Text type="supporting" weight="semibold">Repair brief</Text> — a remote Devin session can draft a code fix as a reviewable proposal. Nothing is applied automatically.</Text>
          </VStack>
          {!view && <Text type="supporting">Run a test in the Test view first — AI reviews the evidence a run produces.</Text>}
        </VStack>
      </Card>
      {view && (
        <>
          {p.agentProgress && <AgentSteps progress={p.agentProgress} />}
          {view.incident.agent_summary && <AgentSummary {...p} view={view} />}
          <AIReview {...p} view={view} />
          <MoreTools {...p} view={view} />
        </>
      )}
    </VStack>
  );
}

// ------------------------------------------------------------------ History view (D-044)

function timeAgo(iso: string | null): string {
  if (!iso) return "queued";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

/** The workspace's memory: every run for this project, newest first (D-044).
    Rows with an incident resume it in Debug; passes open a read-only record. */
function HistoryView(p: FlowProps) {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    Promise.all([api.projectTests(p.projectId), api.expectations(p.projectId)])
      .then(([rs, exps]) => {
        if (!live) return;
        setRuns(rs);
        setLabels(Object.fromEntries(exps.map((e) => [e.id, e.trigger.value])));
      })
      .catch((e) => live && setErr((e as Error).message));
    return () => { live = false; };
  }, [p.projectId, p.flowSeq]);
  const selected = p.run?.id;
  return (
    <VStack gap={3}>
      <Eyebrow>History — every run for this project</Eyebrow>
      <Heading level={2} type="display-3">Test history</Heading>
      {err && <Notice tone="warning" title="Couldn't load history" body={err} />}
      {!err && runs.length === 0 && (
        <Text type="body" color="secondary">No test runs yet — run a test in the Test view.</Text>
      )}
      <VStack gap={1}>
        {runs.map((r) => {
          const outcome = r.result?.outcome;
          return (
            <button key={r.id} type="button" className="history-row" aria-selected={r.id === selected}
                    onClick={() => p.onSelectRun(r)}>
              <HStack gap={2} vAlign="center">
                {r.state !== "completed" ? <Spinner size="sm" />
                  : <StatusDot label={outcome ?? "queued"}
                               variant={outcome === "pass" ? "success" : outcome === "fail" ? "error" : "warning"} />}
                <Text type="body">{labels[r.expectation_id] ?? r.expectation_id}</Text>
                {r.attempt_kind !== "initial" && <Badge variant="neutral" label={r.attempt_kind} />}
                {r.incident_id && <Badge variant="neutral" label="investigation" />}
                <span style={{ flex: 1 }} />
                <Text type="supporting" color="secondary"><RunSourceLabel run={r} /></Text>
                <Text type="supporting" color="secondary">{timeAgo(r.started_at_utc)}</Text>
              </HStack>
            </button>
          );
        })}
      </VStack>
      <Text type="supporting">Select a run to load it — failures resume their investigation, passes open a record. Event flow (E) shows its timeline.</Text>
    </VStack>
  );
}

/** One-line provenance for a run row: where its measurements came from. */
function RunSourceLabel({ run }: { run: TestRun }) {
  const k = run.source.kind;
  return <>{k === "live" ? "Live hardware" : k === "sim" ? "Simulated rig" : run.synthetic ? "Synthetic replay" : "Recorded replay"}</>;
}

/** Read-only record for a run that never opened an incident (a pass). Debug = "the
    selected run" — this is the no-incident branch. */
function RunRecord(p: FlowProps & { run: TestRun }) {
  const r = p.run, res = r.result!;
  return (
    <VStack gap={3}>
      <Eyebrow>Debug — run record</Eyebrow>
      <HStack hAlign="between" vAlign="center" wrap="wrap">
        <Heading level={2} type="display-3">
          {res.outcome === "pass" ? "Test passed" : res.outcome === "inconclusive" ? "Measurement unavailable" : "Test failed"}
        </Heading>
        <SourceBadge run={r} />
      </HStack>
      {res.final_valid_value != null && (
        <Text type="supporting">{p.expectation?.unit === "state"
          ? `Camera saw ${res.final_valid_value === 1 ? "on" : "off"} — expected ${p.expectation.target === 1 ? "on" : "off"}`
          : `Camera measured ${res.final_valid_value.toFixed(1)}° — expected ${p.expectation?.target ?? "?"}°`}</Text>
      )}
      <Facts result={res} />
      <Notice tone="neutral" title="No investigation was opened"
              body="This run passed (or produced no fault). Press E for its event timeline; History lists every run." />
      <Button label="Back to current test" variant="ghost" size="sm" onClick={p.onNewTest} />
    </VStack>
  );
}
