import { List, ListItem } from "@astryxdesign/core/List";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Selector } from "@astryxdesign/core/Selector";
import { useEffect, useState } from "react";
import { Banner } from "@astryxdesign/core/Banner";
import { apiMode, type CausalStep, type Evidence, type ExpectationResult, type SourceOptions, type TestRun } from "../../lib/api";


const KIND_LABEL: Record<string, string> = {
  source_excerpt: "code", manifest_entry: "manifest", netlist_entry: "netlist", serial_line: "serial",
  host_command: "command", cv_measurement: "camera", tool_output: "tool", engineer_assertion: "you",
  rule_result: "rule", shadow_residual: "model",
};

export function cite(e: Evidence): string {
  const f = e.provenance.file;
  return f ? `${f}${e.provenance.line_start ? `:${e.provenance.line_start}` : ""}` : "";
}

/** Compact evidence list: what it says, what kind of fact it is, where it came from. */
export function EvidenceList({ ids, evById, title, onInspect }: { ids: string[]; evById: Map<string, Evidence>; title?: string; onInspect?: (e: Evidence) => void }) {
  const items = [...new Map(ids.map((id) => [id, evById.get(id)])).values()].filter(Boolean) as Evidence[];
  if (!items.length) return null;
  return (
    <List density="compact" header={<Text type="label" color="secondary">{title ?? "Evidence"}</Text>}>
      {items.map((e) => (
        <ListItem key={e.id} label={e.summary}
                  onClick={onInspect ? () => onInspect(e) : undefined}
                  description={[KIND_LABEL[e.kind] ?? e.kind, cite(e)].filter(Boolean).join(" · ")} />
      ))}
    </List>
  );
}

/** The facts PRD §5.3 says must never be conflated — in words a non-hardware reader can follow. */
export function Facts({ result }: { result: ExpectationResult }) {
  const labels: Record<string, string> = {
    command_sent: "The command went out",
    command_acknowledged: "The board said it got it",
    physical_motion: "The camera saw the component respond",
    physical_state: "It ended in the expected state",
  };
  return (
    <VStack gap={1}>
      {result.facts.map((f) => (
        <HStack key={f.key} gap={1.5} vAlign="center">
          <StatusDot variant={f.value === "yes" ? "success" : f.value === "no" ? "error" : "neutral"}
                     label={`${f.label}: ${f.value}`} tooltip={f.note ?? undefined} />
          <Text type="body" color={f.value === "unknown" ? "secondary" : "primary"}>{labels[f.key] ?? f.label}</Text>
          <Text type="supporting">{f.value === "yes" ? "yes" : f.value === "no" ? "no" : "unknown"}</Text>
        </HStack>
      ))}
    </VStack>
  );
}

/** The causal chain from command to observation. Deduced links say "deduced"; links we cannot
    measure say "not measurable" — nothing is smoothed over. */
export function CausalChain({ steps }: { steps: CausalStep[] }) {
  if (!steps.length) return null;
  const variant = (s: CausalStep) => s.value === "yes" ? "success" : s.value === "no" ? "error" : "neutral";
  const text = (s: CausalStep) =>
    s.value === "unmeasured" ? "not measurable" : s.value === "unknown" ? "unknown"
    : s.inferred ? `${s.value} — deduced` : s.value;
  return (
    <VStack gap={1}>
      {steps.map((s) => (
        <HStack key={s.key} gap={1.5} vAlign="center">
          <StatusDot variant={variant(s)} label={`${s.label}: ${text(s)}`}
                     tooltip={s.breaks_if ? `Breaks if: ${s.breaks_if}` : undefined} />
          <Text type="body" color={s.value === "yes" || s.value === "no" ? "primary" : "secondary"}>{s.label}</Text>
          <Text type="supporting">{text(s)}</Text>
        </HStack>
      ))}
    </VStack>
  );
}

/** Numbered category label — the reference's "01 · SENSING" eyebrows, on the dark theme. */
export function Eyebrow({ num, children }: { num?: string; children: React.ReactNode }) {
  return (
    <span className="eyebrow">{num && <span className="num">{num}</span>}{children}</span>
  );
}

/** Shown when the static hosted build is serving the recorded demo bundle (D-034)
    instead of a live backend — the honest "this is a replay" disclosure. */
export function HostedDemoBanner() {
  const [hosted, setHosted] = useState(false);
  useEffect(() => { apiMode().then((m) => setHosted(m === "replay")); }, []);
  if (!hosted) return null;
  return (
    <Banner status="info" collapsible={false} title="Hosted demo — a recorded session"
            description="Everything here replays real captured data from a live session. Run inteGREAT locally for your own imports, live hardware, and AI review." />
  );
}

/** Sim scenario ids read like device status ("connected") — show them as conditions (D-044). */
const SCENARIO_LABEL: Record<string, string> = {
  connected: "wired as declared",
  signal_disconnected: "signal lead off",
  power_disconnected: "power lead off",
  marker_occluded: "camera marker hidden",
};

export function SourceBadge({ run }: { run: TestRun }) {
  const s = run.source;
  const scenario = SCENARIO_LABEL[s.scenario ?? ""] ?? (s.scenario ?? "").replaceAll("_", " ");
  const label = s.kind === "live" ? "Live hardware" : s.kind === "sim" ? `Simulated rig — ${scenario}`
    : `${run.synthetic ? "Synthetic replay" : "Recorded replay"} — ${scenario}`;
  return <HStack gap={1} vAlign="center"><StatusDot variant={s.kind === "live" ? "success" : "neutral"} label={label} /><Text type="supporting">{label}</Text></HStack>;
}

/** Where test data comes from: two small choices instead of one long list. */
const SOURCE_PLAIN: Record<string, string> = {
  sim: "A software model of the rig — no AI involved. Nothing physical is connected.",
  replay: "A saved recording of an earlier run. Nothing happens on the device.",
  live: "The real board, component, and camera on the bench.",
};

export function SourcePicker({ value, onChange, sources, liveReady }: {
  value: string;
  onChange: (v: string) => void;
  sources: SourceOptions;
  liveReady: boolean;
}) {
  const [kind, scenario] = value.split(":");
  const list = kind === "sim" ? sources.sim : kind === "replay" ? sources.replays : [];
  const pick = (k: string) => {
    if (k === "live") return onChange("live");
    const first = (k === "sim" ? sources.sim : sources.replays)[0]?.id ?? "";
    onChange(`${k}:${first}`);
  };
  return (
    <VStack gap={1.5}>
      <SegmentedControl label="Where the test runs" value={kind} onChange={pick} layout="fill" size="sm">
        <SegmentedControlItem value="sim" label="Simulated" />
        <SegmentedControlItem value="replay" label="Replay" />
        <SegmentedControlItem value="live" label="Live rig" />
      </SegmentedControl>
      <Text type="supporting">
        {SOURCE_PLAIN[kind] ?? ""}
        {kind === "live" && !liveReady ? " Open Rig setup to connect the board and calibrate the camera." : ""}
      </Text>
      {kind !== "live" && (
        <Selector label={kind === "sim" ? "Simulated condition" : "Recording"} isLabelHidden size="sm"
                  value={scenario} onChange={(v) => onChange(`${kind}:${v}`)} width="100%"
                  options={list.map((r) => ({ value: r.id, label: r.id.replace(/_/g, " "),
                                              description: r.description }))} />
      )}
    </VStack>
  );
}

export function parseSource(v: string): { kind: "live" | "sim" | "replay"; scenario?: string } {
  const [kind, scenario] = v.split(":");
  return kind === "live" ? { kind: "live" } : { kind: kind as "sim" | "replay", scenario };
}
