// Pure graph shaping: expand/collapse, edge lifting, highlight propagation, dagre layout.
// Kept framework-free so it can be unit-tested and reused by future context views.
import dagre from "@dagrejs/dagre";
import type { GraphEdge, GraphNode, GraphSnapshot, Highlight } from "../../lib/api";

export type Verification = GraphNode["verification"];
export type HighlightStyle = Highlight["style"];

export interface VNode {
  id: string;
  node: GraphNode;
  x: number;
  y: number;
  expandable: boolean;
  expanded: boolean;
  highlight?: Highlight;
  inheritedHighlight?: Highlight; // from a hidden descendant
  dimmed: boolean;
  matched: boolean;
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
  highlight?: Highlight;
  dimmed: boolean;
}

export const NODE_W = 190;
export const NODE_H = 52;

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

export function buildVisibleGraph(
  g: GraphSnapshot,
  expanded: Set<string>,
  highlights: Highlight[],
  focusIds: Set<string> | null,
  search: string,
): { nodes: VNode[]; edges: VEdge[] } {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const hl = new Map(highlights.map((h) => [h.element_id, h]));

  const visible = (n: GraphNode): boolean => {
    if (ALWAYS_VISIBLE.has(n.kind)) return true;
    const parent = n.parent_id ? byId.get(n.parent_id) : undefined;
    if (!parent) return true;
    if (n.kind === "pin" && parent.kind === "mcu") return true;
    return expanded.has(parent.id) && visible(parent);
  };
  const visibleAncestor = (id: string): string | null => {
    let cur = byId.get(id);
    while (cur) {
      if (visible(cur)) return cur.id;
      cur = cur.parent_id ? byId.get(cur.parent_id) : undefined;
    }
    return null;
  };

  const vis = g.nodes.filter(visible);
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
        highlight: h,
        dimmed: false,
      });
    }
  }
  const edges = [...edgeMap.values()];

  const q = search.trim().toLowerCase();
  const inFocus = (id: string) => !focusIds || focusIds.has(id);
  for (const e of edges) e.dimmed = !(inFocus(e.source) && inFocus(e.target));

  // Layout: left→right flow from software to hardware.
  const dg = new dagre.graphlib.Graph();
  dg.setGraph({ rankdir: "LR", nodesep: 22, ranksep: 70, marginx: 20, marginy: 20 });
  dg.setDefaultEdgeLabel(() => ({}));
  for (const n of vis) dg.setNode(n.id, { width: NODE_W, height: NODE_H });
  // Edge directions already run software → pins → components → power (powered_by points at the supply).
  for (const e of edges) dg.setEdge(e.source, e.target, { weight: e.relation === "contains" ? 3 : 1 });
  dagre.layout(dg);

  const nodes: VNode[] = vis.map((n) => {
    const p = dg.node(n.id);
    return {
      id: n.id,
      node: n,
      x: p.x - NODE_W / 2,
      y: p.y - NODE_H / 2,
      expandable: isExpandable(n, g.nodes),
      expanded: expanded.has(n.id),
      highlight: hl.get(n.id),
      inheritedHighlight: inherited.get(n.id),
      dimmed: !inFocus(n.id),
      matched: q.length > 1 && (n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q)),
    };
  });
  return { nodes, edges };
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
