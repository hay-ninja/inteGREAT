import { List, ListItem } from "@astryxdesign/core/List";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Selector } from "@astryxdesign/core/Selector";
import type { Evidence, ExpectationResult, SourceOptions, TestRun } from "../../lib/api";


const KIND_LABEL: Record<string, string> = {
  source_excerpt: "code", manifest_entry: "manifest", netlist_entry: "netlist", serial_line: "serial",
  host_command: "command", cv_measurement: "camera", tool_output: "tool", engineer_assertion: "you",
  rule_result: "rule",
};

export function cite(e: Evidence): string {
  const f = e.provenance.file;
  return f ? `${f}${e.provenance.line_start ? `:${e.provenance.line_start}` : ""}` : "";
}

/** Compact evidence list: what it says, what kind of fact it is, where it came from. */
export function EvidenceList({ ids, evById, title, onInspect }: { ids: string[]; evById: Map<string, Evidence>; title?: string; onInspect?: (e: Evidence) => void }) {
  const items = ids.map((id) => evById.get(id)).filter(Boolean) as Evidence[];
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

/** The three facts PRD §5.3 says must never be conflated — in words a non-hardware reader can follow. */
export function Facts({ result }: { result: ExpectationResult }) {
  const labels = { command_sent: "The command went out", command_acknowledged: "The board said it got it", physical_motion: "The camera saw the arm move" };
  return (
    <VStack gap={1}>
      {result.facts.map((f) => (
        <HStack key={f.key} gap={1.5} vAlign="center">
          <StatusDot variant={f.value === "yes" ? "success" : f.value === "no" ? "error" : "neutral"}
                     label={`${f.label}: ${f.value}`} tooltip={f.note ?? undefined} />
          <Text type="body" color={f.value === "unknown" ? "secondary" : "primary"}>{labels[f.key]}</Text>
          <Text type="supporting">{f.value === "yes" ? "yes" : f.value === "no" ? "no" : "unknown"}</Text>
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

export function SourceBadge({ run }: { run: TestRun }) {
  const s = run.source;
  const scenario = (s.scenario ?? "").replaceAll("_", " ");
  const label = s.kind === "live" ? "Live hardware" : s.kind === "sim" ? `Simulated · ${scenario}`
    : `${run.synthetic ? "Synthetic replay" : "Recorded replay"} · ${scenario}`;
  return <HStack gap={1} vAlign="center"><StatusDot variant={s.kind === "live" ? "success" : "neutral"} label={label} /><Text type="supporting">{label}</Text></HStack>;
}

/** Where test data comes from: two small choices instead of one long list. */
const SOURCE_PLAIN: Record<string, string> = {
  sim: "Pretend hardware — safe to explore. Nothing physical is connected.",
  replay: "A saved recording of an earlier run. Nothing happens on the device.",
  live: "The real board, servo, and camera on the bench.",
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
