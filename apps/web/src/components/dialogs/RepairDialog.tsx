import { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import type { InvestigationView, RepairJob, RepairPreflight } from "../../lib/api";
import { api } from "../../lib/api";
import { Eyebrow } from "../flow/common";

const STATE_LABEL: Record<RepairJob["state"], string> = {
  preparing: "Preparing",
  queued: "Queued",
  working: "Working",
  needs_input: "Needs input",
  ready_for_review: "Ready for review",
  failed: "Failed",
  uncertain: "Status uncertain",
};
const STATE_VARIANT: Record<RepairJob["state"], "neutral" | "accent" | "success" | "warning" | "error"> = {
  preparing: "accent",
  queued: "accent",
  working: "accent",
  needs_input: "warning",
  ready_for_review: "success",
  failed: "error",
  uncertain: "warning",
};
const ACTIVE: RepairJob["state"][] = ["preparing", "queued", "working", "needs_input", "uncertain"];

function JobCard({ job, onRefresh }: { job: RepairJob; onRefresh: () => void }) {
  const r = job.result;
  return (
    <Card padding={3} elevation="low">
      <VStack gap={1}>
        <HStack gap={2} vAlign="center" wrap="wrap">
          <StatusDot variant={STATE_VARIANT[job.state]} label={STATE_LABEL[job.state]} />
          <Eyebrow>Attempt {job.attempt} — {STATE_LABEL[job.state]}</Eyebrow>
          {ACTIVE.includes(job.state) && <Button label="Refresh" size="sm" variant="ghost" onClick={onRefresh} />}
        </HStack>
        <Text type="supporting">
          Requested {new Date(job.created_at_utc).toLocaleString()}
          {job.updated_at_utc !== job.created_at_utc ? ` · updated ${new Date(job.updated_at_utc).toLocaleString()}` : ""}
        </Text>
        {job.session_url && (
          <Button label="Open Devin session" size="sm" variant="ghost" href={job.session_url} target="_blank" rel="noopener noreferrer" />
        )}
        {job.warnings.map((w, i) => <Text key={i} type="supporting">⚠ {w}</Text>)}
        {job.error && <Text type="supporting">Error: {job.error}</Text>}
        {r && (
          <VStack gap={1}>
            {r.pull_requests.length > 0 ? r.pull_requests.map((u) => (
              <Button key={u} label="Review the pull request" size="sm" variant="primary" href={u} target="_blank" rel="noopener noreferrer" />
            )) : (
              <Text type="supporting">No pull request or diff was returned — the proposed change is not available for review.</Text>
            )}
            {r.session_status_detail && <Text type="supporting">Devin reported: {r.session_status_detail}</Text>}
            <Text type="supporting">
              Any tests Devin ran are remote software checks — not verification on your hardware.
              Review the diff, apply it yourself, then re-scan and run Verify.
            </Text>
          </VStack>
        )}
        <details>
          <summary><Text type="supporting">Brief sent to Devin (evidence ids: {job.brief_evidence_ids.length})</Text></summary>
          <pre className="pre-wrap">{job.brief_text}</pre>
        </details>
      </VStack>
    </Card>
  );
}

export function RepairDialog({ investigation, onClose }: {
  investigation: InvestigationView;
  onClose: () => void;
}) {
  const iid = investigation.incident.id;
  const [preflight, setPreflight] = useState<RepairPreflight | null>(null);
  const [jobs, setJobs] = useState<RepairJob[]>([]);
  const [ack, setAck] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reqRef = useRef(0);

  const reload = () => {
    const req = ++reqRef.current;
    Promise.all([api.repairPreflight(iid), api.repairs(iid)])
      .then(([pf, js]) => { if (req === reqRef.current) { setPreflight(pf); setJobs(js); } })
      .catch((e) => { if (req === reqRef.current) setError(e instanceof Error ? e.message : String(e)); });
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(reload, [iid]);

  // Poll while any job is active — polling never creates a new session.
  useEffect(() => {
    const active = jobs.find((j) => ACTIVE.includes(j.state));
    if (!active) return;
    const t = setInterval(() => {
      api.refreshRepair(active.id).then((j) => {
        setJobs((prev) => prev.map((x) => (x.id === j.id ? j : x)));
      }).catch(() => undefined);
    }, 6000);
    return () => clearInterval(t);
  }, [jobs]);

  const needsAck = (preflight?.snapshot?.dirty_files.length ?? 0) > 0;
  const reviewPending = jobs.some((j) => j.state === "ready_for_review" && j.result?.pull_requests.length);
  const start = () => {
    setBusy(true);
    api.requestRepair(iid, ack)
      .then((j) => { setJobs((prev) => [j, ...prev.filter((x) => x.id !== j.id)]); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  };

  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={640}>
      <DialogHeader title="Prepare software fix with Devin"
                    subtitle="Devin works on an isolated remote branch and returns a reviewable diff. inteGREAT never patches your checkout, flashes firmware, or verifies hardware for you."
                    onOpenChange={(o) => !o && onClose()} />
      <VStack gap={3}>
        <Text type="supporting" color="secondary">
          AI-generated proposal by Devin — review the diff before anything is applied.
        </Text>
        {jobs.map((j) => <JobCard key={j.id} job={j} onRefresh={() => api.refreshRepair(j.id).then((x) => setJobs((p) => p.map((y) => y.id === x.id ? x : y))).catch(() => undefined)} />)}

        {preflight && !jobs.some((j) => ACTIVE.includes(j.state)) && (
          <Card padding={3} elevation="low">
            <VStack gap={2}>
              <Eyebrow>{preflight.ready ? "Ready to request a remote fix proposal" : "Cannot start a repair yet"}</Eyebrow>
              {preflight.issues.map((i, k) => <Text key={k} type="supporting">✗ {i}</Text>)}
              {preflight.warnings.map((w, k) => <Text key={k} type="supporting">⚠ {w}</Text>)}
              {preflight.snapshot && (
                <Text type="supporting">
                  Base revision: {preflight.snapshot.base_revision ?? "unknown"}
                  {preflight.snapshot.remote_url ? ` · ${preflight.snapshot.remote_url}` : ""}
                  {needsAck ? ` · ${preflight.snapshot.dirty_files.length} uncommitted file(s) will NOT be included` : ""}
                </Text>
              )}
              {!preflight.devin_configured && preflight.unavailable_reason && (
                <Text type="supporting">Devin is not configured: {preflight.unavailable_reason}</Text>
              )}
              {needsAck && (
                <CheckboxInput label={`I understand the ${preflight!.snapshot!.dirty_files.length} uncommitted change(s) are not part of the remote base revision`}
                               value={ack} onChange={setAck} />
              )}
              <Button label={reviewPending ? "Start another attempt" : "Start repair session"} variant={reviewPending ? "secondary" : "primary"} isLoading={busy}
                      isDisabled={!preflight.ready || (needsAck && !ack)} onClick={start} />
            </VStack>
          </Card>
        )}
        {error && <Text type="supporting">Error: {error}</Text>}
        <Text type="supporting">
          One active job per incident and base revision. After reviewing and applying the fix yourself,
          re-scan the project and run Verify — a remote test is not a hardware verification.
        </Text>
      </VStack>
    </Dialog>
  );
}
