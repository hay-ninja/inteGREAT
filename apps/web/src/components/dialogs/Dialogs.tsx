import { useState } from "react";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { CodeBlock } from "@astryxdesign/core/CodeBlock";
import { Card } from "@astryxdesign/core/Card";
import { TextArea } from "@astryxdesign/core/TextArea";
import { List, ListItem } from "@astryxdesign/core/List";
import type { ActionResult, DiagnosticAction } from "../../lib/api";
import { cite } from "../flow/common";

/** Inspect GPIO mapping: the exact source lines next to the declared wiring. */
export function InspectDialog({ result, onClose }: { result: ActionResult | null; onClose: () => void }) {
  if (!result) return null;
  const wiring = result.evidence.filter((e) => e.kind === "manifest_entry" || e.kind === "netlist_entry");
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={720}>
      <DialogHeader title="Pin configuration vs wiring" subtitle={result.summary} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={3} padding={4}>
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
export function ManualCheckDialog({ action, onSubmit, onClose }: {
  action: DiagnosticAction | null;
  onSubmit: (result: string, note: string) => void;
  onClose: () => void;
}) {
  const [note, setNote] = useState("");
  if (!action) return null;
  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={480} purpose="form">
      <DialogHeader title={action.label} subtitle={action.rationale} onOpenChange={(o) => !o && onClose()} />
      <VStack gap={3} padding={4}>
        <List listStyle="decimal" density="compact">
          {action.manual_instructions.map((s) => <ListItem key={s} label={s} />)}
        </List>
        <TextArea label="What did you see?" isOptional value={note} rows={2} onChange={setNote} />
        <Text type="label" color="secondary">Result</Text>
        <HStack gap={1}>
          {action.result_choices.map((c, i) => (
            <Button key={c} label={c} variant={i === 0 ? "secondary" : i === 1 ? "primary" : "ghost"}
                    onClick={() => onSubmit(c, note)} />
          ))}
        </HStack>
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
