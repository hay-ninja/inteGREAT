import { describe, expect, it } from "vitest";
import type { DiagnosticAction, InvestigationView, TestRun } from "../../lib/api";
import { latestRun, nextCheck } from "./flowState";

const action = (id: string, kind: DiagnosticAction["kind"] = "inspect_source") => ({ id, kind, status: "proposed" }) as DiagnosticAction;
const investigation = () => ({
  incident: { agent_recommended_action_id: null },
  test_run: { id: "original", result: { outcome: "fail" } },
  followup_runs: [], actions: [action("inspect"), action("verify", "verify_fix")],
  hypotheses: [{ recommended_action_ids: ["inspect", "verify"] }],
}) as unknown as InvestigationView;

describe("investigation presentation", () => {
  it("shows the latest inconclusive verification instead of stale failure measurements", () => {
    const view = investigation();
    const recent = { id: "verification", result: { outcome: "inconclusive" } } as TestRun;
    view.followup_runs = [{ id: "repeat" } as TestRun, recent];
    expect(latestRun(view)).toBe(recent);
    expect(latestRun(investigation()).id).toBe("original");
  });

  it("rejects invented recommendation IDs and keeps verification out of the diagnostic check slot", () => {
    for (const id of ["invented-shell-command", "verify"]) {
      const view = investigation();
      view.incident.agent_recommended_action_id = id;
      expect(nextCheck(view)?.id).toBe("inspect");
    }
  });

  it("uses a validated catalog recommendation without changing hypothesis order", () => {
    const view = investigation();
    view.actions.push(action("connection", "request_manual_check"));
    view.incident.agent_recommended_action_id = "connection";
    const before = JSON.stringify(view.hypotheses);
    expect(nextCheck(view)?.id).toBe("connection");
    expect(JSON.stringify(view.hypotheses)).toBe(before);
  });
});
