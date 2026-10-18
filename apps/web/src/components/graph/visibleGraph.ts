// Pure graph shaping: layer projections, expand/collapse, edge lifting, highlight propagation,
// dagre layout. Kept framework-free so it can be unit-tested.
//
// Layer views are a projection of ONE canonical graph (D-023): node/edge ids and provenance are
// never rewritten per layer. Software view keeps small explicit "boundary" hardware references
// where code touches the environment; hardware view hides code entirely (the inspector offers the route
// back). Filtering an intermediate node never invents a direct edge: lifted edges keep the real
// edge ids, are marked `lifted`, and take the least-certain provenance.
import dagre from "@dagrejs/dagre";
import type { GraphEdge, GraphLayer, GraphNode, GraphSnapshot, Highlight } from "../../lib/api";

export type Verification = GraphNode["verification"];
export type HighlightStyle = Highlight["style"];

export interface VNode {
  id: string;
  node: GraphNode;
  x: number;
  y: number;
  expandable: boolean;
  expanded: boolean;
  boundary: boolean;      // hardware shown in the Software view only as a reference
  subtitle: string | null; // beginner-readable role, only when imported data supports it
  highlight?: Highlight;
  inheritedHighlight?: Highlight; // from a hidden descendant
  dimmed: boolean;
  matched: boolean;
  emphasized: boolean;    // related to the current selection across layers
  w: number;
  h: number;
  childCount: number;
}

export interface VEdge {
  id: string;
  source: string;
  target: string;
  relation: GraphEdge["relation"];
  origin: GraphEdge["origin"];
  verification: Verification;
  label: string;
  edgeIds: string[]; // original edges merged into this one
  lifted: boolean;
  summary: string | null; // explains a lifted path; original ids are in edgeIds
  highlight?: Highlight;
  dimmed: boolean;
  emphasized: boolean;
}

export interface Region {
  id: string;
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export const HW_KINDS = new Set(["mcu", "pin", "component", "power_source", "interface"]);
const SW_KINDS = new Set(["subsystem", "source_module", "function", "test", "observation"]);
const CROSS_RELATIONS = new Set(["configures", "controls", "reads_from"]);

/** Keep long board variants and paths in the inspector, where they can be read at full size. */
export function nodeLabel(n: GraphNode): string {
  const label = n.kind === "mcu" ? n.label.split(" (")[0] : n.label;
  return label.length > 30 ? `${label.slice(0, 27)}…` : label;
}

/** Approximate rendered size, used only for layout spacing (hybrid nodes: dots for code, pills for hardware). */
export function nodeSize(n: GraphNode, subtitle: string | null = null): { w: number; h: number } {
  const chars = Math.max(nodeLabel(n).length, subtitle?.length ?? 0);
  if (HW_KINDS.has(n.kind)) return { w: Math.max(80, 44 + chars * 6.4), h: subtitle ? 42 : 30 };
  const dot = n.kind === "subsystem" ? 14 : n.kind === "source_module" ? 10 : 7;
  return { w: dot + 30 + chars * (n.kind === "subsystem" ? 7.8 : 6.8), h: 22 };
}

/** A short plain-language role, only when the imported data actually supports it (no guessing). */
export function nodeRole(n: GraphNode, g: GraphSnapshot): string | null {
  const byId = new Map(g.nodes.map((x) => [x.id, x]));
  switch (n.kind) {
    case "mcu": return "controller — runs your program";
    case "power_source": return "external power supply";
    case "subsystem": return "subsystem — groups code + hardware";
    case "source_module": {
      const controls = g.edges.some((e) => e.relation === "controls"
        && byId.get(e.source_id)?.parent_id === n.id);
      return controls ? "drives hardware" : "source file";
    }
    case "function": {
      if (g.edges.some((e) => (e.relation === "controls" || e.relation === "configures") && e.source_id === n.id))
        return "drives or configures hardware";
      return "code";
    }
    case "component": {
      const t = String(n.attributes?.type ?? "");
      if (t === "servo") return "servo motor — moves a shaft";
      if (t === "led") return "indicator light";
      return t ? `${t} — role as declared` : "role not declared in the manifest";
    }
    case "pin": {
      const parent = n.parent_id ? byId.get(n.parent_id) : undefined;
      const label = n.label.toUpperCase();
      if (label.includes("GND")) return "ground";
      if (/VIN|VCC|5V|3V3/.test(label)) return "power";
      const link = g.edges.find((e) => e.relation === "connected_to"
        && (e.source_id === n.id || e.target_id === n.id));
      const other = link ? byId.get(link.source_id === n.id ? link.target_id : link.source_id) : undefined;
      const comp = other?.parent_id ? byId.get(other.parent_id) : undefined;
      const pinName = other ? other.label.split(".").pop() : "";
      if (comp && pinName === "signal") return `${comp.label.split(" ")[0].toLowerCase()} signal pin`;
      if (comp && pinName) return `${comp.label.split(" ")[0].toLowerCase()} ${pinName} pin`;
      if (parent?.kind === "mcu") return "controller pin — role not declared";
      if (pinName === "signal") return "signal input";
      if (pinName === "vcc") return "power input";
      if (pinName === "gnd") return "ground return";
      return "pin — role not declared";
    }
    default: return null;
  }
}

const EDGE_VERB: Record<GraphEdge["relation"], string> = {
  calls: "calls",
  configures: "configures pin",
  controls: "controls",
  connected_to: "wired",
  powered_by: "powered",
  reads_from: "reads",
  observed_by: "camera",
  depends_on: "depends on",
  contains: "contains",
};

/** Short canvas label — wiring checks become glyphs so parallel edges don't collide. */
export function edgeLabel(e: VEdge): string {
  if (e.relation === "contains") return "";
  const v = EDGE_VERB[e.relation];
  if (e.origin !== "declared_wiring") return v;
  if (e.relation === "connected_to" || e.relation === "powered_by") {
    return e.verification === "verified" ? `${v} ✓` : e.verification === "conflicting" ? `${v} ✗` : `${v} ?`;
  }
  return e.verification === "verified" ? v : e.verification === "conflicting" ? `${v} — conflicting` : `${v} — unchecked`;
}

const VERIF_SEVERITY: Record<Verification, number> = {
  verified: 0,
  observed: 1,
  inferred: 2,
  unverified: 3,
  conflicting: 4,
};
const HL_PRIORITY: Record<HighlightStyle, number> = {
  conflict: 5,
  failed_expectation: 4,
  suspect: 3,
  unknown: 2,
  observed: 1,
};

const ALWAYS_VISIBLE = new Set(["subsystem", "mcu", "component", "power_source"]);

export function isExpandable(n: GraphNode, all: GraphNode[]): boolean {
  if (n.kind === "subsystem" || n.kind === "source_module") return all.some((c) => c.parent_id === n.id);
  if (n.kind === "component") return all.some((c) => c.parent_id === n.id);
  return false;
}

/** Why this node is hidden by the current layer filter — or null when it isn't hidden. */
export function layerHiddenReason(n: GraphNode, layer: GraphLayer): string | null {
  if (layer === "hardware" && !HW_KINDS.has(n.kind)) return "Source code is hidden in the Hardware view.";
  if (layer === "software" && HW_KINDS.has(n.kind)) return "Hardware detail is hidden in the Software view unless visible code references it.";
  return null;
}

export function hiddenByLayer(g: GraphSnapshot, layer: GraphLayer): { sw: number; hw: number } {
  return {
    sw: layer === "hardware" ? g.nodes.filter((n) => !HW_KINDS.has(n.kind)).length : 0,
    hw: layer === "software" ? g.nodes.filter((n) => HW_KINDS.has(n.kind)).length : 0,
  };
}

/** Nodes/edges related to a selection across layers — cross-highlight without changing the graph. */
export function relatedSelection(g: GraphSnapshot, selectedId: string | null): { nodes: Set<string>; edges: Set<string> } {
  const out = { nodes: new Set<string>(), edges: new Set<string>() };
  if (!selectedId) return out;
  for (const e of g.edges) {
    if (e.relation === "contains") continue;
    if (e.source_id === selectedId) { out.nodes.add(e.target_id); out.edges.add(e.id); }
    if (e.target_id === selectedId) { out.nodes.add(e.source_id); out.edges.add(e.id); }
  }
  return out;
}

interface LayoutResult { pos: Map<string, { x: number; y: number }>; w: number; h: number }

function layoutDagre(nodes: { id: string; w: number; h: number }[],
                     edges: { source: string; target: string; relation: string }[]): LayoutResult {
  const dg = new dagre.graphlib.Graph();
  dg.setGraph({ rankdir: "TB", nodesep: 32, ranksep: 48, marginx: 24, marginy: 24 });
  dg.setDefaultEdgeLabel(() => ({}));
  for (const n of nodes) dg.setNode(n.id, { width: n.w, height: n.h });
  for (const e of edges) dg.setEdge(e.source, e.target, { weight: e.relation === "contains" ? 3 : 1 });
  dagre.layout(dg);
  const pos = new Map<string, { x: number; y: number }>();
  let w = 0, h = 0;
  for (const n of nodes) {
    const p = dg.node(n.id);
    if (!p) continue;
    pos.set(n.id, { x: p.x, y: p.y });
    w = Math.max(w, p.x + n.w / 2);
    h = Math.max(h, p.y + n.h / 2);
  }
  return { pos, w: Math.max(w, 60), h: Math.max(h, 40) };
}

export function buildVisibleGraph(
  g: GraphSnapshot,
  expanded: Set<string>,
  highlights: Highlight[],
  focusIds: Set<string> | null,
  search: string,
  layer: GraphLayer = "combined",
  emphasize: { nodes: Set<string>; edges: Set<string> } | null = null,
): { nodes: VNode[]; edges: VEdge[]; regions: Region[] } {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const hl = new Map(highlights.map((h) => [h.element_id, h]));
  const scopeIds = focusIds ? new Set(focusIds) : null;
  if (scopeIds) for (const id of focusIds!) {
    let cur = byId.get(id);
    while (cur?.parent_id) { scopeIds.add(cur.parent_id); cur = byId.get(cur.parent_id); }
  }

  // Software-layer boundary: hardware the visible code actually touches (configures/controls/
  // reads_from), plus one hop of wiring context so "configured pin vs wired pin" stays visible.
  const boundary = new Set<string>();
  if (layer === "software") {
    for (const e of g.edges) {
      if (!CROSS_RELATIONS.has(e.relation)) continue;
      const s = byId.get(e.source_id), t = byId.get(e.target_id);
      if (s && SW_KINDS.has(s.kind) && t && HW_KINDS.has(t.kind)) boundary.add(e.target_id);
      if (t && SW_KINDS.has(t.kind) && s && HW_KINDS.has(s.kind)) boundary.add(e.source_id);
    }
    const extra = new Set<string>();
    for (const e of g.edges) {
      if (e.relation !== "connected_to" && e.relation !== "powered_by" && e.relation !== "contains") continue;
      const touches = boundary.has(e.source_id) || boundary.has(e.target_id);
      if (!touches) continue;
      const add = (id: string) => { if (HW_KINDS.has(byId.get(id)?.kind ?? "")) extra.add(id); };
      add(e.source_id); add(e.target_id);
    }
    for (const id of [...boundary, ...extra]) {
      const n = byId.get(id);
      if (n?.parent_id && HW_KINDS.has(byId.get(n.parent_id)?.kind ?? "")) extra.add(n.parent_id);
      if (boundary.has(id)) for (const c of g.nodes) if (c.parent_id === id) extra.add(c.id);
    }
    for (const id of extra) boundary.add(id);
  }

  const layerOk = (n: GraphNode): boolean => {
    if (layer === "hardware") return HW_KINDS.has(n.kind);
    if (layer === "software") return SW_KINDS.has(n.kind) || boundary.has(n.id);
    return true;
  };

  const visible = (n: GraphNode): boolean => {
    if (!layerOk(n)) return false;
    if (ALWAYS_VISIBLE.has(n.kind)) return true;
    const parent = n.parent_id ? byId.get(n.parent_id) : undefined;
    if (!parent) return true;
    if (n.kind === "pin" && parent.kind === "mcu") return true;
    return expanded.has(parent.id) && visible(parent);
  };
  const visibleAncestor = (id: string): string | null => {
    let cur = byId.get(id);
    while (cur) {
      if (visible(cur) && (!scopeIds || scopeIds.has(cur.id))) return cur.id;
      cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
    }
    return null;
  };

  const vis = g.nodes.filter((n) => visible(n) && (!scopeIds || scopeIds.has(n.id)));
  const visIds = new Set(vis.map((n) => n.id));

  // Propagate highlights from hidden nodes to their visible ancestor (e.g. an observed function
  // inside a collapsed module), at lower visual weight.
  const inherited = new Map<string, Highlight>();
  for (const h of highlights) {
    if (!byId.has(h.element_id) || visIds.has(h.element_id)) continue;
    const anc = visibleAncestor(h.element_id);
    if (!anc) continue;
    const cur = inherited.get(anc);
    if (!cur || HL_PRIORITY[h.style] > HL_PRIORITY[cur.style]) inherited.set(anc, h);
  }

  const edgeMap = new Map<string, VEdge>();
  for (const e of g.edges) {
    if (scopeIds && (!scopeIds.has(e.source_id) || !scopeIds.has(e.target_id))) continue;
    const direct = visIds.has(e.source_id) && visIds.has(e.target_id);
    if (e.relation === "contains" && !direct) continue;
    const s = visibleAncestor(e.source_id);
    const t = visibleAncestor(e.target_id);
    if (!s || !t || s === t) continue;
    const key = `${e.relation}:${s}->${t}`;
    const ex = edgeMap.get(key);
    const h = hl.get(e.id);
    if (ex) {
      ex.edgeIds.push(e.id);
      if (VERIF_SEVERITY[e.verification] > VERIF_SEVERITY[ex.verification]) ex.verification = e.verification;
      if (h && (!ex.highlight || HL_PRIORITY[h.style] > HL_PRIORITY[ex.highlight.style])) ex.highlight = h;
      ex.lifted = ex.lifted || !direct;
    } else {
      edgeMap.set(key, {
        id: key,
        source: s,
        target: t,
        relation: e.relation,
        origin: e.origin,
        verification: e.verification,
        label: e.label ?? e.relation,
        edgeIds: [e.id],
        lifted: !direct,
        summary: null,
        highlight: h,
        dimmed: false,
        emphasized: false,
      });
    }
  }
  const edges = [...edgeMap.values()];
  for (const e of edges) {
    if (e.lifted) {
      const sName = byId.get(e.source)?.label ?? e.source;
      const tName = byId.get(e.target)?.label ?? e.target;
      e.summary = e.edgeIds.length > 1
        ? `Summarizes ${e.edgeIds.length} real connections — drawn between the nearest visible endpoints (${sName} → ${tName}). Original edges are listed in the inspector; least-certain status is shown.`
        : `Drawn between the nearest visible endpoints (${sName} → ${tName}) — intermediate nodes are hidden. The original edge is listed in the inspector.`;
    }
  }

  const q = search.trim().toLowerCase();
  const inFocus = (id: string) => !focusIds || focusIds.has(id);
  for (const e of edges) e.dimmed = !(inFocus(e.source) && inFocus(e.target));

  // ---- layout: combined view renders two labeled regions (software left, hardware right)
  const subs = new Map(vis.map((n) => [n.id, nodeRole(n, g)]));
  const sizes = new Map(vis.map((n) => [n.id, nodeSize(n, subs.get(n.id) ?? null)]));
  const regions: Region[] = [];
  const positions = new Map<string, { x: number; y: number }>();
  if (layer === "combined") {
    const swN = vis.filter((n) => !HW_KINDS.has(n.kind));
    const hwN = vis.filter((n) => HW_KINDS.has(n.kind));
    const swE = edges.filter((e) => swN.some((n) => n.id === e.source) && swN.some((n) => n.id === e.target));
    const hwE = edges.filter((e) => hwN.some((n) => n.id === e.source) && hwN.some((n) => n.id === e.target));
    const L1 = layoutDagre(swN.map((n) => ({ id: n.id, ...sizes.get(n.id)! })), swE);
    const L2 = layoutDagre(hwN.map((n) => ({ id: n.id, ...sizes.get(n.id)! })), hwE);
    const GAP = 90, PAD = 46;
    const offX = L1.w + GAP;
    for (const n of swN) positions.set(n.id, L1.pos.get(n.id)!);
    for (const n of hwN) {
      const p = L2.pos.get(n.id)!;
      positions.set(n.id, { x: p.x + offX, y: p.y });
    }
    if (swN.length) regions.push({ id: "region:software", label: "Software — your code", x: -PAD, y: -PAD, w: L1.w + PAD * 2, h: L1.h + PAD * 2 });
    if (hwN.length) regions.push({ id: "region:hardware", label: "Hardware — the physical environment", x: offX - PAD, y: -PAD, w: L2.w + PAD * 2, h: L2.h + PAD * 2 });
  } else {
    const L = layoutDagre(vis.map((n) => ({ id: n.id, ...sizes.get(n.id)! })), edges);
    for (const n of vis) positions.set(n.id, L.pos.get(n.id)!);
  }

  const children = new Map<string, number>();
  for (const n of g.nodes) if (n.parent_id) children.set(n.parent_id, (children.get(n.parent_id) ?? 0) + 1);
  const nodes: VNode[] = vis.map((n) => {
    const pos = positions.get(n.id) ?? { x: 0, y: 0 };
    const { w, h } = sizes.get(n.id)!;
    return {
      id: n.id,
      node: n,
      x: pos.x - w / 2,
      y: pos.y - h / 2,
      w,
      h,
      childCount: children.get(n.id) ?? 0,
      expandable: isExpandable(n, g.nodes),
      expanded: expanded.has(n.id),
      boundary: boundary.has(n.id) && HW_KINDS.has(n.kind),
      subtitle: layer === "combined" || HW_KINDS.has(n.kind) || boundary.has(n.id) ? subs.get(n.id) ?? null : null,
      highlight: hl.get(n.id),
      inheritedHighlight: inherited.get(n.id),
      dimmed: !inFocus(n.id),
      matched: q.length > 1 && (n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)),
      emphasized: emphasize?.nodes.has(n.id) ?? false,
    };
  });
  for (const e of edges) e.emphasized = emphasize ? e.edgeIds.some((id) => emphasize.edges.has(id)) : false;
  return { nodes, edges, regions };
}

/** Breadcrumb trail from root to a node, via parent_id. */
export function breadcrumb(g: GraphSnapshot, id: string | null): GraphNode[] {
  if (!id) return [];
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const out: GraphNode[] = [];
  let cur = byId.get(id);
  while (cur) {
    out.unshift(cur);
    cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
  }
  return out;
}
