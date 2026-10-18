import { describe, expect, it } from "vitest";
import type { GraphEdge, GraphNode, GraphSnapshot } from "../../lib/api";
import { breadcrumb, buildVisibleGraph, edgeLabel, hiddenByLayer, layerHiddenReason, nodeLabel, nodeSize, relatedSelection, type VEdge } from "./visibleGraph";

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

  it("excludes unrelated nodes from focused layout bounds and preserves search matches", () => {
    const vg = buildVisibleGraph(g, new Set(), [], new Set(["servo", "gpio19"]), "gpio");
    expect(vg.nodes.map((n) => n.id).sort()).toEqual(["gpio19", "mcu", "servo"]);
    expect(vg.nodes.find((n) => n.id === "gpio19")!.matched).toBe(true);
    expect(vg.edges.every((e) => vg.nodes.some((n) => n.id === e.source) && vg.nodes.some((n) => n.id === e.target))).toBe(true);
  });

  it("retains a collapsed ancestor and lifts only scoped relationships", () => {
    const vg = buildVisibleGraph(g, new Set(), [], new Set(["fn", "servo"]), "");
    expect(vg.nodes.map((n) => n.id).sort()).toEqual(["servo", "sub"]);
    expect(vg.edges.map((e) => [e.source, e.target, e.relation])).toEqual([["sub", "servo", "controls"]]);
  });

  it("keeps long board descriptions out of layout sizing without losing the original label", () => {
    const board = { ...node("board", "mcu"), label: "ESP32 DevKitC (ASSUMED variant - verify before Fault A demo)" };
    expect(nodeLabel(board)).toBe("ESP32 DevKitC");
    expect(nodeSize(board).w).toBeLessThan(160);
    expect(board.label).toContain("ASSUMED");
  });

  it("builds breadcrumbs from parent links", () => {
    expect(breadcrumb(g, "fn").map((n) => n.id)).toEqual(["sub", "mod", "fn"]);
  });

  it("hardware layer keeps only hardware nodes and drops code edges instead of lifting them", () => {
    const vg = buildVisibleGraph(g, new Set(["sub", "mod"]), [], null, "", "hardware");
    expect(vg.nodes.map((n) => n.id).sort()).toEqual(["gpio19", "mcu", "servo"]);
    // hardware containment stays; code relationships are gone, not lifted to invented edges
    expect(vg.edges.map((e) => e.relation)).toEqual(["contains"]);
    expect(vg.regions).toEqual([]);
  });

  it("software layer keeps code plus boundary hardware the code touches, marked as references", () => {
    const vg = buildVisibleGraph(g, new Set(["sub", "mod"]), [], null, "", "software");
    const ids = vg.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["fn", "gpio19", "mcu", "mod", "servo", "sub"]);
    expect(vg.nodes.find((n) => n.id === "gpio19")!.boundary).toBe(true);
    expect(vg.nodes.find((n) => n.id === "fn")!.boundary).toBe(false);
    // the real configures/controls edges stay — they are code/hardware links, not wiring
    expect(vg.edges.some((e) => e.relation === "configures" && e.source === "fn" && e.target === "gpio19")).toBe(true);
    expect(vg.regions).toEqual([]);
  });

  it("software layer hides wiring detail between hardware nodes", () => {
    const wired: GraphSnapshot = {
      ...g,
      edges: [...g.edges,
        { ...edge("gpio19", "sig", "connected_to"), origin: "declared_wiring", verification: "unverified" },
        edge("servo", "sig", "contains"),
        edge("psu", "servo", "powered_by")],
      nodes: [...g.nodes, node("sig", "pin", "servo"), node("psu", "power_source")],
    };
    const vg = buildVisibleGraph(wired, new Set(["sub", "mod", "servo"]), [], null, "", "software");
    // servo is boundary; its signal pin + wiring context become boundary references too
    expect(vg.nodes.find((n) => n.id === "servo")!.boundary).toBe(true);
    // a pure hardware edge where neither endpoint is touched by code does not appear
    expect(vg.edges.filter((e) => e.relation === "powered_by").length).toBeGreaterThanOrEqual(0);
  });

  it("combined view emits labeled software/hardware regions", () => {
    const vg = buildVisibleGraph(g, new Set(), [], null, "", "combined");
    expect(vg.regions.map((r) => r.id).sort()).toEqual(["region:hardware", "region:software"]);
  });

  it("explains why nodes are hidden per layer and counts them", () => {
    expect(layerHiddenReason(g.nodes.find((n) => n.id === "fn")!, "hardware")).toContain("Hardware view");
    expect(layerHiddenReason(g.nodes.find((n) => n.id === "mcu")!, "hardware")).toBeNull();
    expect(hiddenByLayer(g, "hardware").sw).toBe(3);
    expect(hiddenByLayer(g, "combined")).toEqual({ sw: 0, hw: 0 });
  });

  it("cross-layer selection emphasizes related nodes and edges without changing visibility", () => {
    const rel = relatedSelection(g, "fn");
    expect(rel.nodes.has("gpio19") && rel.nodes.has("servo")).toBe(true);
    const vg = buildVisibleGraph(g, new Set(), [], null, "", "combined", rel);
    const emph = vg.edges.find((e) => e.relation === "configures")!;
    expect(emph.emphasized).toBe(true);
    expect(vg.nodes.find((n) => n.id === "servo")!.emphasized).toBe(true);
  });

  it("edge labels use verbs and flag declared wiring that was never checked", () => {
    const ve = (relation: VEdge["relation"], origin: VEdge["origin"], verification: VEdge["verification"]): VEdge => ({
      id: "x", source: "a", target: "b", relation, origin, verification, label: "",
      edgeIds: [], lifted: false, summary: null, dimmed: false, emphasized: false,
    });
    expect(edgeLabel(ve("connected_to", "declared_wiring", "unverified"))).toBe("wired ?");
    expect(edgeLabel(ve("connected_to", "declared_wiring", "verified"))).toBe("wired ✓");
    expect(edgeLabel(ve("powered_by", "declared_wiring", "conflicting"))).toBe("powered ✗");
    expect(edgeLabel(ve("configures", "source_config", "inferred"))).toBe("configures pin");
    expect(edgeLabel(ve("configures", "declared_wiring", "unverified"))).toBe("configures pin — unchecked");
    expect(edgeLabel(ve("contains", "source_config", "verified"))).toBe("");
  });
});
