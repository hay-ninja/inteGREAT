import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { GraphSnapshot, Highlight } from "../../lib/api";
import { buildVisibleGraph, type VEdge, type VNode } from "./visibleGraph";

const KIND_LABEL: Record<string, string> = {
  subsystem: "SUBSYSTEM",
  source_module: "MODULE",
  function: "FUNCTION",
  mcu: "MCU",
  pin: "PIN",
  component: "COMPONENT",
  power_source: "POWER",
};

type NodeData = { v: VNode; onToggle: (id: string) => void };

function IntegreatNode({ data }: NodeProps<Node<NodeData>>) {
  const { v, onToggle } = data;
  const n = v.node;
  const hl = v.highlight ?? v.inheritedHighlight;
  const cls = [
    "gnode",
    `kind-${n.kind}`,
    `ver-${n.verification}`,
    hl ? `hl-${hl.style}` : "",
    v.inheritedHighlight && !v.highlight ? "hl-inherited" : "",
    v.dimmed ? "dimmed" : "",
    v.matched ? "matched" : "",
  ].join(" ");
  return (
    <div className={cls} title={hl ? `${hl.style.replace("_", " ")}: ${hl.reason}` : n.id}>
      <Handle type="target" position={Position.Left} />
      <div className="gnode-kind">
        {KIND_LABEL[n.kind] ?? n.kind}
        <span className={`vbadge v-${n.verification}`}>{n.verification}</span>
      </div>
      <div className="gnode-label">
        {v.expandable && (
          <button
            className="caret"
            aria-label={v.expanded ? "Collapse" : "Expand"}
            onClick={(e) => {
              e.stopPropagation();
              onToggle(n.id);
            }}
          >
            {v.expanded ? "▾" : "▸"}
          </button>
        )}
        {n.label}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { integreat: IntegreatNode };

const EDGE_COLOR: Record<string, string> = {
  conflict: "var(--c-conflict)",
  failed_expectation: "var(--c-fail)",
  suspect: "var(--c-suspect)",
  unknown: "var(--c-unknown)",
  observed: "var(--c-observed)",
};

function edgeStyle(e: VEdge): Edge["style"] {
  const base: CSSProperties = { strokeWidth: 1.5, stroke: "var(--c-edge)" };
  if (e.relation === "contains") return { ...base, stroke: "var(--c-edge-faint)", strokeWidth: 1 };
  if (e.verification === "inferred") base.strokeDasharray = "6 4";
  if (e.verification === "unverified") base.strokeDasharray = "2 4";
  if (e.verification === "verified") base.stroke = "var(--c-verified)";
  if (e.verification === "conflicting") {
    base.stroke = "var(--c-conflict)";
    base.strokeWidth = 2.5;
  }
  if (e.highlight) {
    base.stroke = EDGE_COLOR[e.highlight.style];
    base.strokeWidth = 3;
  }
  if (e.dimmed) base.opacity = 0.15;
  return base;
}

interface Props {
  graph: GraphSnapshot;
  expanded: Set<string>;
  highlights: Highlight[];
  focusIds: Set<string> | null;
  search: string;
  selectedId: string | null;
  onToggle: (id: string) => void;
  onSelect: (id: string | null) => void;
  onEdgeSelect: (edgeIds: string[]) => void;
  fitKey: string;
}

function Inner(p: Props) {
  const { fitView } = useReactFlow();
  const vg = useMemo(
    () => buildVisibleGraph(p.graph, p.expanded, p.highlights, p.focusIds, p.search),
    [p.graph, p.expanded, p.highlights, p.focusIds, p.search],
  );
  // Controlled nodes. React Flow only keeps a node's handle positions if the node object we pass back
  // still carries its `measured` size; dropping it hides nodes and edges after every re-layout.
  const [nodes, setNodes] = useState<Node<NodeData>[]>([]);
  const { onToggle } = p;
  useEffect(() => {
    setNodes((prev) => {
      const old = new Map(prev.map((n) => [n.id, n]));
      return vg.nodes.map((v) => ({
        id: v.id,
        type: "integreat",
        position: { x: v.x, y: v.y },
        data: { v, onToggle },
        selected: v.id === p.selectedId,
        measured: old.get(v.id)?.measured,
      }));
    });
  }, [vg, onToggle, p.selectedId]);
  const edges: Edge[] = vg.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.relation === "contains" ? undefined : e.lifted ? `${e.label} ×${e.edgeIds.length}` : e.label,
    animated: e.highlight?.style === "observed",
    style: edgeStyle(e),
    labelStyle: { fill: "var(--c-text-dim)", fontSize: 10, opacity: e.dimmed ? 0.2 : 1 },
    labelBgStyle: { fill: "var(--c-bg)" },
    markerEnd: e.relation === "contains" ? undefined : { type: MarkerType.ArrowClosed, width: 14, height: 14 },
    data: { title: e.highlight?.reason, edgeIds: e.edgeIds },
  }));

  useEffect(() => {
    const t = setTimeout(() => fitView({ padding: 0.15, duration: 300 }), 30);
    return () => clearTimeout(t);
  }, [p.fitKey, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={(changes) => setNodes((ns) => applyNodeChanges(changes, ns) as Node<NodeData>[])}
      onNodeClick={(_, n) => p.onSelect(n.id)}
      onNodeDoubleClick={(_, n) => p.onToggle(n.id)}
      onPaneClick={() => p.onSelect(null)}
      onEdgeClick={(_, e) => p.onEdgeSelect((e.data?.edgeIds as string[]) ?? [e.id])}
      nodesDraggable={false}
      minZoom={0.2}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={24} color="var(--c-grid)" />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={() => "var(--c-minimap)"} maskColor="rgba(0,0,0,0.4)" />
    </ReactFlow>
  );
}

export function GraphView(p: Props) {
  return (
    <ReactFlowProvider>
      <Inner {...p} />
    </ReactFlowProvider>
  );
}

export function Legend() {
  return (
    <div className="legend">
      <div><span className="sw line verified" /> verified wiring</div>
      <div><span className="sw line inferred" /> inferred (static analysis)</div>
      <div><span className="sw line unverified" /> declared, unverified</div>
      <div><span className="sw line conflicting" /> conflicting</div>
      <div><span className="sw box observed" /> observed event</div>
      <div><span className="sw box failed_expectation" /> failed expectation</div>
      <div><span className="sw box suspect" /> suspected (unmeasured)</div>
      <div><span className="sw box unknown" /> unknown / unavailable</div>
    </div>
  );
}
