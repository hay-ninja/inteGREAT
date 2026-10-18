import type { DiagnosticAction, InvestigationView } from "../../lib/api";

export function latestRun(view: InvestigationView) {
  return view.followup_runs[view.followup_runs.length - 1] ?? view.test_run;
}

/** An agent can recommend a catalog action; its text never becomes an executable button. */
export function nextCheck(view: InvestigationView): DiagnosticAction | undefined {
  const recommended = view.actions.find((a) => a.id === view.incident.agent_recommended_action_id && a.kind !== "verify_fix");
  if (recommended) return recommended;
  const ids = view.hypotheses[0]?.recommended_action_ids ?? [];
  const candidates = ids.map((id) => view.actions.find((a) => a.id === id && a.kind !== "verify_fix"))
    .filter((a): a is DiagnosticAction => !!a);
  return candidates.find((a) => a.status === "proposed") ?? candidates[0];
}
