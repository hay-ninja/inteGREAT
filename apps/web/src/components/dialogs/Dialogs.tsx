import { useEffect, useState, type ReactNode } from "react";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { CodeBlock } from "@astryxdesign/core/CodeBlock";
import { Card } from "@astryxdesign/core/Card";
import { TextArea } from "@astryxdesign/core/TextArea";
import { List, ListItem } from "@astryxdesign/core/List";
import { SelectableCard } from "@astryxdesign/core/SelectableCard";
import type { ActionResult, DiagnosticAction, Evidence, Expectation, SourceOptions, TestRun } from "../../lib/api";
import { cite, SourceBadge, SourcePicker } from "../flow/common";

export function RepeatTestDialog(p: {
  action: DiagnosticAction | null; expectation: Expectation | null;
  source: string; onSource: (value: string) => void; sources: SourceOptions; liveReady: boolean;
  onRepeat: () => void; onClose: () => void; onOpenDevices: () => void;
}) {
  if (!p.action) return null;
  return <Dialog isOpen onOpenChange={(o) => !o && p.onClose()} width={500} purpose="form">
    <DialogHeader title="Repeat the test" subtitle="Keep the confirmed expectation and choose the observation source." onOpenChange={(o) => !o && p.onClose()} />
    <VStack padding={4} gap={3}>
      {p.expectation && <Text type="supporting">{p.expectation.trigger.value} · {p.expectation.target}° ± {p.expectation.tolerance}° within {p.expectation.deadline_ms} ms</Text>}
      <Text type="supporting">Check marker visibility and calibration if measurements were unavailable. A repeat gathers new evidence; verification closes the incident.</Text>
      <SourcePicker value={p.source} onChange={p.onSource} sources={p.sources} liveReady={p.liveReady} />
      <HStack gap={2}>
        {p.source === "live" && !p.liveReady ? <Button label="Set up environment" variant="primary" onClick={p.onOpenDevices} />
          : <Button label="Repeat test" variant="primary" onClick={p.onRepeat} />}
        <Button label="Cancel" variant="ghost" onClick={p.onClose} />
      </HStack>
    </VStack>
  </Dialog>;
}

export function GraphInspector({ open, onClose, children }: { open: boolean; onClose: () => void; children: ReactNode }) {
  return <Dialog isOpen={open} onOpenChange={(o) => !o && onClose()} width={680}>
    <DialogHeader title="Graph evidence" subtitle="Inspect provenance and confirm physical connections." onOpenChange={(o) => !o && onClose()} />
    <VStack padding={4} gap={2}>{children}</VStack>
  </Dialog>;
}

export function EvidenceDialog({ evidence: e, onClose }: { evidence: Evidence | null; onClose: () => void }) {
  if (!e) return null;
  return <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={720}>
    <DialogHeader title="Evidence record" subtitle={`${e.kind.replaceAll("_", " ")} · ${e.epistemic}`} onOpenChange={(o) => !o && onClose()} />
    <VStack padding={4} gap={3}>
      <Text type="body">{e.summary}</Text>
      <Text type="code">{cite(e) || e.provenance.source_id}</Text>
      <Text type="supporting">Evidence ID: {e.id}{e.test_run_id ? ` · Test run: ${e.test_run_id}` : ""}</Text>
      <CodeBlock code={JSON.stringify(e.payload, null, 2)} language="json" title="Recorded data" width="100%" maxHeight={340} isWrapped />
    </VStack>
  </Dialog>;
}

/** Inspect GPIO mapping: the exact source lines next to the declared wiring. */
export function InspectDialog({ result, onClose }: { result: ActionResult | null; onClose: () => void }) {
  if (!result) return null;
  const wiring = result.evidence.filter((e) => e.kind === "manifest_entry" || e.kind === "netlist_entry");
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={720}>
      <DialogHeader title="Pin configuration vs wiring" subtitle={result.summary} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={3} padding={4}>
        <Text type="supporting" color="secondary">
          Output of a fixed read-only tool — recorded as evidence, not AI-generated.
        </Text>
        {result.source_excerpts.map((ex) => (
          <CodeBlock key={ex.evidence_id} code={ex.lines.join("\n")} language="cpp" width="100%"
                     title={`${ex.file} · lines ${ex.line_start}–${ex.line_start + ex.lines.length - 1}`}
                     highlightLines={ex.highlight_lines.map((ln) => ln - ex.line_start + 1)} />
        ))}
        {wiring.map((e) => (
          <Card key={e.id} padding={3} variant="muted">
            <VStack gap={0.5}>
              <Text type="label" color="secondary">{e.kind === "netlist_entry" ? "KiCad netlist" : "Hardware manifest"} · {cite(e)}</Text>
              <Text type="body">{e.summary}</Text>
            </VStack>
          </Card>
        ))}
        <Text type="supporting">
          inteGREAT never edits or flashes firmware. Fix the pin (or the wiring) yourself, then Rescan and verify.
        </Text>
      </VStack>
    </Dialog>
  );
}

/** Physical check the engineer performs; the result becomes evidence. */
export function ManualCheckDialog({ action, onSubmit, onClose, run }: {
  action: DiagnosticAction | null;
  onSubmit: (result: string, note: string) => Promise<void>;
  onClose: () => void;
  run?: TestRun | null;
}) {
  const [note, setNote] = useState("");
  const [result, setResult] = useState("");
  useEffect(() => { setNote(""); setResult(""); }, [action?.id]);
  if (!action) return null;
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={480} purpose="form">
      <DialogHeader title={action.label} subtitle={action.rationale} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={3} padding={4}>
        <Text type="supporting" color="secondary">
          Deterministic check — suggested by the rules engine from your code + wiring files, not AI.
        </Text>
        {run && <SourceBadge run={run} />}
        <List listStyle="decimal" density="compact">
          {action.manual_instructions.map((s) => <ListItem key={s} label={s} />)}
        </List>
        <TextArea label="What did you see?" isOptional value={note} rows={2} onChange={setNote} />
        <VStack gap={1}>
          <Text type="label" color="secondary">What did you find?</Text>
          {action.result_choices.map((c) => {
            const outcome = action.expected_outcomes.find((o) => o.result === c);
            return (
              <SelectableCard key={c} label={c} isSelected={result === c}
                              onChange={(selected) => setResult(selected ? c : "")} padding={3} width="100%">
                <VStack gap={0.5}>
                  <Text type="body">{c}</Text>
                  {outcome && <Text type="supporting" color="secondary">{outcome.interpretation}</Text>}
                </VStack>
              </SelectableCard>
            );
          })}
        </VStack>
        <Button label="Record check result" variant="primary" isDisabled={!result} clickAction={() => onSubmit(result, note)} />
      </VStack>
    </Dialog>
  );
}

const CAT_LABEL: Record<string, string> = {
  repo_read: "read source code", netlist_read: "read wiring", serial_read: "read serial output",
  camera_observe: "read camera data", host_diagnostics_read: "read host diagnostics",
};

/** Asked when a read-only tool's category isn't granted yet. */
export function ApprovalDialog({ request, onGrant, onOnce, onCancel }: {
  request: { tool: string; category: string } | null;
  onGrant: () => void;
  onOnce: () => void;
  onCancel: () => void;
}) {
  if (!request) return null;
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onCancel()} width={480}>
      <DialogHeader title="Allow this?" onOpenChange={(o) => !o && onCancel()} />
      <VStack gap={3} padding={4}>
        <Text type="body">
          This needs permission to <Text type="body" weight="semibold">{CAT_LABEL[request.category] ?? request.category}</Text>.
          It's read-only and recorded in the tool audit.
        </Text>
        <HStack gap={1}>
          <Button label="Allow while debugging this" variant="primary" onClick={onGrant} />
          <Button label="Only once" onClick={onOnce} />
          <Button label="Cancel" variant="ghost" onClick={onCancel} />
        </HStack>
      </VStack>
    </Dialog>
  );
}

export function ToolOutputDialog({ result, onClose }: { result: ActionResult | null; onClose: () => void }) {
  if (!result) return null;
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={720}>
      <DialogHeader title="Tool output" subtitle={result.summary} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={2} padding={4}>
        <Text type="supporting" color="secondary">
          Output of a fixed read-only tool — recorded as evidence, not AI-generated.
        </Text>
        {result.lines.length ? (
          <CodeBlock code={result.lines.join("\n")} width="100%" maxHeight={360} />
        ) : (
          <Text type="supporting">No lines returned.</Text>
        )}
        <Text type="supporting">Recorded as evidence.</Text>
      </VStack>
    </Dialog>
  );
}
