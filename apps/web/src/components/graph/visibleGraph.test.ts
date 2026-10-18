import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode, GraphSnapshot } from "../../lib/api";
import { breadcrumb, buildVisibleGraph } from "./visibleGraph";

const node = (id: string, kind: GraphNode["kind"], parent: string | null = null): GraphNode => ({
  id, project_id: "p", kind, label: id, subsystem_id: null, parent_id: parent, attributes: {},
  verification: "verified", evidence_ids: [],
});
const edge = (s: string, t: string, relation: GraphEdge["relation"], verification: GraphEdge["verification"] = "inferred"): GraphEdge => ({
  id: `edge:${relation}:${s}->${t}`, project_id: "p", source_id: s, target_id: t, relation, origin: "source_config",
  verification, label: null, attributes: {}, evidence_ids: [],
});

const g: GraphSnapshot = {
  project_id: "p", version: 1, created_at_utc: "2026-10-17T00:00:00Z",
  nodes: [node("sub", "subsystem"), node("mod", "source_module", "sub"), node("fn", "function", "mod"),
          node("mcu", "mcu"), node("gpio19", "pin", "mcu"), node("servo", "component")],
  edges: [edge("sub", "mod", "contains"), edge("mod", "fn", "contains"), edge("mcu", "gpio19", "contains"),
          edge("fn", "gpio19", "configures", "conflicting"), edge("fn", "servo", "controls")],
};

describe("buildVisibleGraph", () => {
  it("lifts edges from hidden functions to the visible subsystem, keeping the worst verification", () => {
    const vg = buildVisibleGraph(g, new Set(), [], null, "");
    expect(vg.nodes.map((n) => n.id).sort()).toEqual(["gpio19", "mcu", "servo", "sub"]);
    const lifted = vg.edges.find((e) => e.relation === "configures")!;
    expect([lifted.source, lifted.target, lifted.lifted, lifted.verification]).toEqual(["sub", "gpio19", true, "conflicting"]);
    expect(vg.edges.some((e) => e.relation === "contains" && e.source === "sub")).toBe(false);
  });

  it("shows functions when their module and subsystem are expanded", () => {
    const vg = buildVisibleGraph(g, new Set(["sub", "mod"]), [], null, "");
    const cfg = vg.edges.find((e) => e.relation === "configures")!;
    expect([cfg.source, cfg.lifted]).toEqual(["fn", false]);
  });

  it("propagates a hidden node's highlight to its visible ancestor", () => {
    const vg = buildVisibleGraph(g, new Set(), [{ element_id: "fn", style: "observed", reason: "log" }], null, "");
    const sub = vg.nodes.find((n) => n.id === "sub")!;
    expect(sub.highlight).toBeUndefined();
    expect(sub.inheritedHighlight?.style).toBe("observed");
  });

  it("dims nodes outside the focus set and marks search matches", () => {
    const vg = buildVisibleGraph(g, new Set(), [], new Set(["servo"]), "gpio");
    expect(vg.nodes.find((n) => n.id === "servo")!.dimmed).toBe(false);
    expect(vg.nodes.find((n) => n.id === "sub")!.dimmed).toBe(true);
    expect(vg.nodes.find((n) => n.id === "gpio19")!.matched).toBe(true);
  });

  it("builds breadcrumbs from parent links", () => {
    expect(breadcrumb(g, "fn").map((n) => n.id)).toEqual(["sub", "mod", "fn"]);
  });
});
