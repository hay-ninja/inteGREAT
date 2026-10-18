import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";

import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { Selector } from "@astryxdesign/core/Selector";
import { Slider } from "@astryxdesign/core/Slider";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { IconButton } from "@astryxdesign/core/IconButton";
import { Layout, LayoutContent, LayoutHeader } from "@astryxdesign/core/Layout";
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { Evidence, EventFlow, FlowEvent, FlowLane, GraphLayer, TestRun } from "../../lib/api";
import { api } from "../../lib/api";
import { Eyebrow, SourceBadge } from "./common";
import { InspectorCard } from "./InspectorCard";


const LANE_LABEL: Record<FlowLane, string> = {
  command: "What we asked",
  software: "What the board said",
  hardware: "What the camera saw",
  result: "The verdict",
};

const LANE_HINT: Record<FlowLane, string> = {
  command: "The command inteGREAT sent to run the test",
  software: "Messages the board printed back over the serial link",
  hardware: "Measurements the camera took of the component",
  result: "Whether the test passed, and why it didn't",
};

/** Which lanes stay bright under each graph layer — the layer choice stays meaningful here too. */
function laneDimmed(lane: FlowLane, layer: GraphLayer): boolean {
  if (layer === "hardware") return lane === "software";
  if (layer === "software") return lane === "hardware";
  return false;
}

function runLabel(r: TestRun, all: TestRun[]): string {
  const kind = r.attempt_kind === "initial" ? "First run" : r.attempt_kind === "verify" ? "Verify" : "Retry";
  const dup = all.filter((x) => x.attempt_kind === r.attempt_kind);
  const idx = dup.length > 1 ? ` #${dup.indexOf(r) + 1}` : "";
  const res = r.result?.outcome ? ` — ${r.result.outcome.replace(/_/g, " ")}` : ` — ${r.state.replace(/_/g, " ")}`;
  return `${kind}${idx}${res}`;
}

function fmtElapsed(e: FlowEvent): string {
  if (e.elapsed_ms == null) return "time unknown";
  const t = e.elapsed_ms < 1000 ? `${Math.round(e.elapsed_ms)} ms` : `${(e.elapsed_ms / 1000).toFixed(2)} s`;
  if (e.elapsed_end_ms != null && e.elapsed_end_ms > e.elapsed_ms)
    return `${t} – ${(e.elapsed_end_ms / 1000).toFixed(2)} s`;
  return t;
}
function fmtUtc(iso: string | null): string {
  return iso ? new Date(iso).toISOString().slice(11, 23) + " UTC" : "not recorded";
}

const DOT_CLASS: Record<FlowEvent["state"], string> = {
  observed: "fev-observed",
  expected: "fev-expected",
  inferred: "fev-inferred",
};

interface Props {
  runs: TestRun[];
  runId: string | null;
  onRunChange: (id: string) => void;
  layer: GraphLayer;
  refreshSeq: number;
  onSelectNode: (id: string) => void;
  onEvidence: (e: Evidence) => void;
}

export function EventFlowView(p: Props) {
  const [flow, setFlow] = useState<EventFlow | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const reqRef = useRef(0);

  useEffect(() => {
    if (!p.runId) { setFlow(null); return; }
    const req = ++reqRef.current;
    api.testFlow(p.runId)
      .then((f) => { if (req === reqRef.current) { setFlow(f); setError(null); setIdx((i) => Math.min(i, Math.max(0, f.events.length - 1))); } })
      .catch((e) => { if (req === reqRef.current) setError(e instanceof Error ? e.message : String(e)); });
    return () => { reqRef.current++; };
  }, [p.runId, p.refreshSeq]);

  const selectedRun = p.runs.find((r) => r.id === p.runId) ?? null;
  const events = useMemo(() => flow?.events ?? [], [flow]);
  const sel = events[idx] ?? null;

  // ←/→ scrubs the event flow while this view is up (blueprint keyboard layer).
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") return;
      const el = ev.target as HTMLElement;
      if (el.closest?.("input, textarea, select, [contenteditable]") || el.closest?.("[role='dialog'], dialog")) return;
      setIdx((i) => Math.max(0, Math.min(events.length - 1, i + (ev.key === "ArrowLeft" ? -1 : 1))));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [events.length]);

  // X scale: elapsed ms → % of lane width. Events with unknown timing stack at the start.
  const maxMs = useMemo(() => {
    const max = events.reduce((m, e) => Math.max(m, e.elapsed_end_ms ?? e.elapsed_ms ?? 0), 0);
    return Math.max(max * 1.06, 40);
  }, [events]);
  const xOf = (e: FlowEvent, orderInLane: number) =>
    e.elapsed_ms == null ? 2 + orderInLane * 12 : 6 + (Math.min(e.elapsed_ms, maxMs) / maxMs) * 88;
  const wOf = (e: FlowEvent) =>
    e.elapsed_ms != null && e.elapsed_end_ms != null && e.elapsed_end_ms > e.elapsed_ms
      ? Math.max(2.5, ((e.elapsed_end_ms - e.elapsed_ms) / maxMs) * 88) : 0;

  const lanes = useMemo(() => {
    const byLane = new Map<FlowLane, FlowEvent[]>();
    for (const e of events) byLane.set(e.lane, [...(byLane.get(e.lane) ?? []), e]);
    const order: FlowLane[] = flow?.lanes ?? ["command", "software", "hardware", "result"];
    return order.map((l) => ({ lane: l, events: byLane.get(l) ?? [] }));
  }, [flow, events]);

  const openEvidence = useCallback((id: string) => {
    if (!flow) return;
    api.evidence(flow.project_id, [id]).then((evs) => { if (evs[0]) p.onEvidence(evs[0]); }).catch(() => undefined);
  }, [flow, p]);

  const isInvalid = (e: FlowEvent) => e.kind === "cv_segment" && e.quality != null && e.quality !== "valid";

  return (
    <Layout header={<LayoutHeader padding={2} hasDivider>
      <HStack gap={2} vAlign="center" wrap="wrap">
        <Text type="label" color="secondary">Event timeline</Text>
        <Selector label="Run" isLabelHidden size="sm" placement="below" value={p.runId ?? ""} onChange={(v) => p.onRunChange(String(v))}
                  options={p.runs.map((r) => ({ value: r.id, label: runLabel(r, p.runs) }))} width={230} />
        {selectedRun && <SourceBadge run={selectedRun} />}
        {selectedRun?.state === "running" && (
          <HStack gap={1} vAlign="center"><StatusDot variant="accent" label="Live" /><Text type="supporting">live — replay of recorded events, nothing is sent to hardware</Text></HStack>
        )}
      </HStack>
    </LayoutHeader>} content={<LayoutContent padding={0} isScrollable={false}>
      {!p.runId ? (
        <EmptyState title="No test run yet" description="Run a test to record the chronological event flow for your hardware." />
      ) : error ? (
        <EmptyState title="Event flow unavailable" description={error} />
      ) : !flow ? (
        <EmptyState title="Loading…" description="Reading the persisted run records." />
      ) : flow.events.length === 0 ? (
        <EmptyState title="No events recorded for this run" description="The run exists but has no persisted commands, serial lines, or observations." />
      ) : (
        <VStack gap={3} padding={3} style={{ height: "100%", overflow: "auto" }}>
          <Text type="supporting">{flow.correlation}</Text>
          {lanes.map(({ lane, events: evs }) => (
            <div key={lane} className={`lane-row ${laneDimmed(lane, p.layer) ? "lane-dimmed" : ""}`}>
              <div className="lane-label">
                <span title={LANE_HINT[lane]}><Eyebrow>{LANE_LABEL[lane]}</Eyebrow></span>
                {laneDimmed(lane, p.layer) && <Text type="supporting">dimmed by the {p.layer} view</Text>}
              </div>
              <div className="lane-track">
                <div className="lane-line" />
                {evs.map((e, oi) => {
                  const isSel = sel?.id === e.id;
                  const span = wOf(e);
                  const cls = ["fev", DOT_CLASS[e.state], oi % 2 ? "fev-alt" : "", isInvalid(e) ? "fev-invalid" : "", isSel ? "fev-sel" : ""].join(" ");
                  return (
                    <button key={e.id} type="button" className={cls} style={{ left: `${xOf(e, oi)}%` }}
                            onClick={() => setIdx(events.indexOf(e))}
                            title={`${e.label} · ${fmtElapsed(e)} · ${e.state}${isInvalid(e) ? " · invalid" : ""}`}
                            aria-label={`${e.label}, ${LANE_LABEL[lane]}, ${fmtElapsed(e)}`}>
                      {span > 0 && <span className="fev-span" style={{ width: `max(18px, ${span}%)` }} />}
                      <span className="fev-dot" />
                      {e.aggregated_ids.length > 1 && <span className="fev-count">{e.aggregated_ids.length}</span>}
                      <span className="fev-label">{e.label}</span>
                    </button>
                  );
                })}
                {sel && sel.lane === lane && sel.elapsed_ms != null && (
                  <div className="lane-cursor" style={{ left: `${xOf(sel, 0)}%` }} />
                )}
              </div>
            </div>
          ))}

          <HStack gap={2} vAlign="center">
            <IconButton label="Previous event" size="sm" variant="ghost" icon={<ChevronLeft size={14} />}
                        isDisabled={idx <= 0} onClick={() => setIdx(idx - 1)} />
            <Slider label="Step through recorded events" isLabelHidden min={0} max={Math.max(0, events.length - 1)}
                    value={idx} onChange={(v: number | number[]) => setIdx(Array.isArray(v) ? v[0] : v)} valueDisplay="none" width={260}
                    formatValue={(v: number) => events[v]?.label ?? ""} />
            <IconButton label="Next event" size="sm" variant="ghost" icon={<ChevronRight size={14} />}
                        isDisabled={idx >= events.length - 1} onClick={() => setIdx(idx + 1)} />
            <Text type="supporting">step {idx + 1} of {events.length} — replay only, nothing is sent to hardware</Text>
          </HStack>

          {sel && (
            <InspectorCard eyebrow={`Event — ${LANE_LABEL[sel.lane]}`}>
              <VStack gap={1}>
                <HStack gap={2} vAlign="center" wrap="wrap">
                  <Text type="body" weight="semibold">{sel.label}</Text>
                  <StatusDot variant={sel.state === "observed" ? "accent" : sel.state === "expected" ? "neutral" : "warning"}
                             label={sel.state} />
                  <Text type="supporting">{sel.state}{isInvalid(sel) ? " · invalid sample — excluded from evaluation" : ""}</Text>
                </HStack>
                {sel.detail && <Text type="supporting">{sel.detail}</Text>}
                <Text type="supporting">
                  +{fmtElapsed(sel)} after the command · {fmtUtc(sel.timestamp_utc)}
                  {sel.aggregated_ids.length > 1 ? ` · aggregates ${sel.aggregated_ids.length} recorded samples — no evidence was deleted` : ""}
                  {sel.quality ? ` · quality: ${sel.quality}` : ""}
                </Text>
                {sel.note && <Text type="supporting">{sel.note}</Text>}
                {sel.evidence_ids.length > 0 && (
                  <HStack gap={1} wrap="wrap" vAlign="center">
                    <Text type="supporting">Evidence:</Text>
                    {sel.evidence_ids.map((id) => (
                      <Button key={id} label={id.slice(0, 8)} size="sm" variant="ghost" onClick={() => openEvidence(id)} />
                    ))}
                  </HStack>
                )}
                {sel.related_node_ids.length > 0 && (
                  <HStack gap={1} wrap="wrap" vAlign="center">
                    <Text type="supporting">In the graph:</Text>
                    {sel.related_node_ids.slice(0, 6).map((id) => (
                      <Button key={id} label={id.split(":").pop() ?? id} size="sm" variant="ghost"
                              onClick={() => p.onSelectNode(id)} />
                    ))}
                  </HStack>
                )}
              </VStack>
            </InspectorCard>
          )}

          {flow.gaps.length > 0 && (
            <VStack gap={0}>
              <Eyebrow>Gaps and uncertainties</Eyebrow>
              {flow.gaps.map((g, i) => <Text key={i} type="supporting">· {g}</Text>)}
            </VStack>
          )}
        </VStack>
      )}
    </LayoutContent>} />
  );
}
