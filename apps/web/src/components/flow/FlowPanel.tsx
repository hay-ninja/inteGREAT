/**
 * Guided debugging flow (D-021): Set up → Run → Investigate → Verify.
 * Rule of thumb: each step shows ONE primary button. Alternatives and advanced tools are collapsed.
 */
import { useEffect, useState, type ReactNode } from "react";
import { Stepper, Step } from "@astryxdesign/core/Stepper";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Heading } from "@astryxdesign/core/Heading";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Badge } from "@astryxdesign/core/Badge";
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
  type Hypothesis,
  type InvestigationView,
  type PermissionCategory,
  type SourceOptions,
  type TestRun,
} from "../../lib/api";
import { EvidenceList, Facts, SourceBadge, SourcePicker } from "./common";

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
      <Stepper activeStep={auto} label="Debugging steps" density="compact"
               horizontalOptions={{ minimumStepWidth: 72, collapsedVariant: "withLabel" }}
               onStepClick={(i) => setViewing(i <= auto ? (i === auto ? null : i) : viewing)}>
        {STEPS.map((s, i) => (
          <Step key={s} step={i} label={s} isDisabled={i > auto}
                status={i === 2 && p.view && p.view.incident.state !== "resolved" ? "error"
                  : i === 3 && p.view?.incident.state === "resolved" ? "success" : undefined} />
        ))}
      </Stepper>
      {step === 0 && <SetupStep {...p} />}
      {step === 1 && <RunStep {...p} />}
      {step === 2 && p.view && <InvestigateStep {...p} view={p.view} />}
      {step === 3 && p.view && <VerifyStep {...p} view={p.view} />}
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
        <HStack gap={1.5} vAlign="center" hAlign="between">
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
        <Heading level={2}>What should happen?</Heading>
        <Text type="body" color="secondary">
          inteGREAT reads the firmware and suggests a test. You confirm it before it decides pass or fail.
        </Text>
        {p.conflictNote && <Notice tone="warning" title="Already spotted a problem" body={p.conflictNote} />}
        <Button label="Suggest a test from the code" variant="primary"
                clickAction={() => api.proposeExpectation(p.projectId).then(p.onExpectation).catch((e) => p.onError(e.message))} />
      </VStack>
    );
  }
  const evById = new Map(cites.map((c) => [c.id, c]));
  return (
    <VStack gap={3}>
      <Heading level={2}>Confirm the test</Heading>
      <Text type="body" color="secondary">Send a command, then the camera checks the servo angle.</Text>
      <TextInput label="Serial command" value={draft.trigger} onChange={(v) => setDraft({ ...draft, trigger: v })} />
      <HStack gap={2}>
        <NumberInput label="Target" units="°" value={draft.target} onChange={(v) => setDraft({ ...draft, target: v })} />
        <NumberInput label="± tolerance" units="°" value={draft.tolerance} min={0} onChange={(v) => setDraft({ ...draft, tolerance: v })} />
        <NumberInput label="Within" units="ms" value={draft.deadline_ms} min={100} step={100}
                     onChange={(v) => setDraft({ ...draft, deadline_ms: v })} />
      </HStack>
      <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Why this test?</Text>}>
        <VStack gap={1}>
          {exp.rationale && <Text type="supporting">{exp.rationale}</Text>}
          <EvidenceList ids={cites.map((c) => c.id)} evById={evById} />
        </VStack>
      </Collapsible>
      <Button label="Confirm test" variant="primary"
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
      <Heading level={2}>Run the test</Heading>
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
      <Button label={p.running ? "Running…" : passed ? "Run again" : "Run test"} variant="primary"
              isLoading={p.running} isDisabled={p.source === "live" && !p.liveReady} onClick={p.onRun} />
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

const STATUS_BADGE: Record<string, { v: "success" | "info" | "neutral" | "warning"; l: string }> = {
  supported: { v: "success", l: "supported" },
  plausible: { v: "info", l: "plausible" },
  unverified: { v: "neutral", l: "unverified" },
  weakened: { v: "warning", l: "weakened" },
  ruled_out: { v: "neutral", l: "ruled out" },
};

function InvestigateStep(p: FlowProps & { view: InvestigationView }) {
  const { view } = p;
  const evById = new Map(view.evidence.map((e) => [e.id, e]));
  const [top, ...others] = view.hypotheses;
  const primary = recommendedFor(top, view.actions);
  // Once the suggested check is done, the next real step is "fix it, then verify" — promote that instead.
  const checkDone = primary?.status === "completed";
  const failedVerify = [...view.followup_runs].reverse().find((r) => r.attempt_kind === "verify");
  const result = view.test_run.result;
  return (
    <VStack gap={3}>
      {failedVerify?.result && failedVerify.result.outcome !== "pass" && (
        <Notice tone="warning" title="Still failing after your fix" body={failedVerify.result.reason} />
      )}
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <Heading level={2}>{view.incident.title}</Heading>
          <SourceBadge run={view.test_run} />
        </HStack>
        {result && <Text type="supporting">{result.reason}</Text>}
      </VStack>
      {result && <Facts result={result} />}
      <Divider />

      {top ? (
        <Card padding={3}>
          <VStack gap={2}>
            <HStack hAlign="between" vAlign="center">
              <Text type="label" color="secondary">Most likely cause</Text>
              <Badge variant={STATUS_BADGE[top.status].v} label={STATUS_BADGE[top.status].l} />
            </HStack>
            <Heading level={3}>{top.title}</Heading>
            <Text type="body" color="secondary">{top.explanation}</Text>
            {primary && (
              <Button label={checkDone ? `${primary.label} again` : primary.label}
                      variant={checkDone ? "ghost" : "primary"} isLoading={p.busyActionId === primary.id}
                      tooltip={primary.rationale} onClick={() => p.onAction(primary)} />
            )}
            <Collapsible defaultIsOpen={false} trigger={<Text type="supporting">Evidence and unknowns</Text>}>
              <VStack gap={2}>
                <EvidenceList title="Supports it" ids={top.supporting_evidence_ids} evById={evById} />
                <EvidenceList title="Against it" ids={top.contradicting_evidence_ids} evById={evById} />
                {top.unknowns.length > 0 && (
                  <VStack gap={0.5}>
                    <Text type="label" color="secondary">Not measured / unknown</Text>
                    {top.unknowns.map((u) => <Text key={u} type="supporting">• {u}</Text>)}
                  </VStack>
                )}
                {top.related_node_ids.length > 0 && (
                  <Button label="Show in graph" size="sm" variant="ghost" onClick={() => p.onReveal(top.related_node_ids)} />
                )}
              </VStack>
            </Collapsible>
          </VStack>
        </Card>
      ) : (
        <Notice tone="neutral" title="No rule matched" body="Evidence is not enough to rank causes. Try a manual check or ask the agents." />
      )}

      {view.incident.agent_summary && (
        <Card padding={3} variant="muted">
          <VStack gap={1}>
            <Text type="label" color="secondary">AI agents (inference, not measurement)</Text>
            <Text type="body">{view.incident.agent_summary}</Text>
          </VStack>
        </Card>
      )}

      <VerifyLauncher {...p} label="I fixed it — verify" emphasis={checkDone ? "primary" : "secondary"} />

      {others.length > 0 && (
        <Collapsible defaultIsOpen={false} trigger={<Text type="label">Other possibilities ({others.length})</Text>}>
          <VStack gap={2}>
            {others.map((h) => <OtherHypothesis key={h.id} h={h} {...p} />)}
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
    <Card padding={2} variant="muted">
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <Text type="body" weight="medium">{p.h.title}</Text>
          <Badge variant={STATUS_BADGE[p.h.status].v} label={STATUS_BADGE[p.h.status].l} />
        </HStack>
        <Text type="supporting" maxLines={3}>{p.h.explanation}</Text>
        {a && <Button label={a.label} size="sm" isLoading={p.busyActionId === a.id} onClick={() => p.onAction(a)} />}
      </VStack>
    </Card>
  );
}

function VerifyLauncher(p: FlowProps & { view: InvestigationView; label: string; emphasis: "primary" | "secondary" }) {
  const [open, setOpen] = useState(false);
  const verify = p.view.actions.find((a) => a.kind === "verify_fix");
  if (!verify) return null;
  if (!open) return <Button label={p.label} variant={p.emphasis} onClick={() => setOpen(true)} />;
  return (
    <Card padding={3}>
      <VStack gap={2}>
        <Text type="label">Re-run the same test with</Text>
        <SourcePicker value={p.source} onChange={p.onSource} sources={p.sources} liveReady={p.liveReady} />
        <HStack gap={1}>
          <Button label="Run verification" variant="primary" isLoading={p.busyActionId === verify.id}
                  isDisabled={p.source === "live" && !p.liveReady} onClick={() => p.onAction(verify)} />
          <Button label="Cancel" variant="ghost" onClick={() => setOpen(false)} />
        </HStack>
      </VStack>
    </Card>
  );
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
  const rounds = view.incident.agent_rounds_used;
  const aiReason = !p.agentStatus?.available ? `AI unavailable: ${p.agentStatus?.reason ?? "no provider"}`
    : rounds >= 2 ? "Agent budget used (2 rounds)" : "";
  return (
    <Collapsible defaultIsOpen={false} trigger={<Text type="label">More tools</Text>}>
      <VStack gap={3}>
        <VStack gap={1}>
          <Text type="label" color="secondary">Ask the AI agents</Text>
          <HStack gap={1} vAlign="center">
            <Button label={p.diagnosing || view.incident.state === "investigating" ? "Agents investigating…" : rounds ? "Ask again" : "Ask agents"}
                    size="sm" isLoading={p.diagnosing} isDisabled={!!aiReason} tooltip={aiReason || undefined} onClick={p.onDiagnose} />
            <Text type="supporting">round {rounds}/2</Text>
          </HStack>
          {view.agent_runs.filter((r) => r.agent !== "orchestrator").map((r) => (
            <Text key={r.id} type="supporting">
              {r.agent.replace("_", "/")} agent: {r.status}{r.report ? ` · ${r.report.findings.length} finding(s)` : ""}
              {r.validation_errors.length ? ` · ${r.validation_errors.length} rejected` : ""}
            </Text>
          ))}
        </VStack>
        {extra.length > 0 && (
          <VStack gap={1}>
            <Text type="label" color="secondary">Read-only tools</Text>
            <HStack gap={1} wrap="wrap">
              {extra.map((a) => (
                <Button key={a.id} label={a.label} size="sm" tooltip={a.rationale}
                        isLoading={p.busyActionId === a.id} onClick={() => p.onAction(a)} />
              ))}
            </HStack>
          </VStack>
        )}
        <VStack gap={1}>
          <Text type="label" color="secondary">Permissions for this investigation</Text>
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
        <Spinner size="lg" label="Re-running the same test…" />
        <Text type="supporting">Same command, same pass criteria.</Text>
      </VStack>
    );
  }
  const v = view.followup_runs.find((r) => r.id === inc.resolved_by_test_run_id);
  return (
    <VStack gap={3}>
      <Notice tone="success" title="Fixed — verified by measurement"
              body={v?.result?.reason ?? "The same test now passes."} end={v ? <SourceBadge run={v} /> : undefined} />
      {v?.synthetic && <Text type="supporting">Verified on synthetic data, not live hardware.</Text>}
      <Text type="body" color="secondary">Was: {view.hypotheses[0]?.title ?? inc.title}</Text>
      <Button label="Start a new test" variant="primary" onClick={p.onNewTest} />
    </VStack>
  );
}
