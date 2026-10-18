import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  ReactFlowProvider,
  applyNodeChanges,
  useNodesInitialized,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Cog, Cpu, CircleCheck, CircleDot, CircleHelp, CircleX, Eye, TriangleAlert, Zap } from "lucide-react";
import { Button } from "@astryxdesign/core/Button";
import { IconButton } from "@astryxdesign/core/IconButton";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Card } from "@astryxdesign/core/Card";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import type { GraphSnapshot, Highlight } from "../../lib/api";
import { HW_KINDS, buildVisibleGraph, type VEdge, type VNode } from "./visibleGraph";

const KIND_ICON: Record<string, ReactNode> = {
  mcu: <Cpu size={13} />,
  pin: <CircleDot size={12} />,
  component: <Cog size={13} />,
  power_source: <Zap size={13} />,
};
const MARK: Record<string, ReactNode> = {
  conflict: <TriangleAlert size={12} color="var(--color-error)" />,
  failed_expectation: <CircleX size={12} color="var(--color-error)" />,
  suspect: <CircleHelp size={12} color="var(--color-warning)" />,
  unknown: <CircleHelp size={12} color="var(--color-text-disabled)" />,
  observed: <Eye size={12} color="var(--color-accent)" />,
};

type NodeData = { v: VNode; onToggle: (id: string) => void };

function GraphNodeView({ data }: NodeProps<Node<NodeData>>) {
  const { v, onToggle } = data;
  const n = v.node;
  const hl = v.highlight ?? v.inheritedHighlight;
  const hw = HW_KINDS.has(n.kind);
  const cls = ["gn", `k-${n.kind}`, `v-${n.verification}`, hw ? "hw" : "code",
    hl ? `hl-${hl.style}` : "", v.inheritedHighlight && !v.highlight ? "inherited" : "",
    v.dimmed ? "dimmed" : "", v.matched ? "matched" : ""].join(" ");
  const title = [n.label, n.kind.replace("_", " "), n.verification, hl ? `${hl.style.replace("_", " ")}: ${hl.reason}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <span className={cls} title={title}
          onDoubleClick={(e) => { if (v.expandable) { e.stopPropagation(); onToggle(n.id); } }}>
      <Handle type="target" position={Position.Left} />
      {hw ? <span className="gn-kind">{KIND_ICON[n.kind]}</span> : <span className="gn-dot" />}
      <span className="gn-label">{n.label}</span>
      {hw && hl && <span className="gn-mark">{MARK[hl.style]}</span>}
      {hw && !hl && n.verification === "verified" && n.kind !== "mcu" && n.kind !== "pin" && (
        <span className="gn-mark"><CircleCheck size={11} color="var(--color-text-disabled)" /></span>
      )}
      {v.expandable && !v.expanded && <span className="gn-count">+{v.childCount}</span>}
      <Handle type="source" position={Position.Right} />
    </span>
  );
}

const nodeTypes = { trace: GraphNodeView };

const HL_STROKE: Record<string, string> = {
  conflict: "var(--color-error)",
  failed_expectation: "var(--color-error)",
  suspect: "var(--color-warning)",
  unknown: "var(--color-text-disabled)",
  observed: "var(--color-accent)",
};

function edgeStyle(e: VEdge): CSSProperties {
  // Obsidian-quiet by default; colour only for problems or observed activity.
  const s: CSSProperties = { strokeWidth: 1.2, stroke: "var(--color-border-emphasized)" };
  if (e.relation === "contains") return { ...s, stroke: "var(--color-border)", strokeWidth: 1 };
  if (e.verification === "verified") s.stroke = "var(--color-text-disabled)";
  if (e.verification === "inferred") s.strokeDasharray = "5 4";
  if (e.verification === "unverified") s.strokeDasharray = "1.5 4";
  if (e.verification === "conflicting") { s.stroke = "var(--color-error)"; s.strokeWidth = 2; }
  if (e.highlight) { s.stroke = HL_STROKE[e.highlight.style]; s.strokeWidth = 2; }
  if (e.dimmed) s.opacity = 0.12;
  return s;
}

interface Props {
  graph: GraphSnapshot;
  expanded: Set<string>;
  highlights: Highlight[];
  focusIds: Set<string> | null;
  selectedId: string | null;
  onToggle: (id: string) => void;
  onSelect: (id: string | null) => void;
  onEdgeSelect: (edgeIds: string[]) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onClearFocus: (() => void) | null;
  fitKey: string;
}

function Inner(p: Props) {
  const { fitView } = useReactFlow();
  const [search, setSearch] = useState("");
  const vg = useMemo(() => buildVisibleGraph(p.graph, p.expanded, p.highlights, p.focusIds, search),
    [p.graph, p.expanded, p.highlights, p.focusIds, search]);

  // Controlled nodes: React Flow keeps handle positions only if we pass back each node's `measured`
  // size; dropping it hides nodes/edges after a re-layout.
  const [nodes, setNodes] = useState<Node<NodeData>[]>([]);
  const { onToggle } = p;
  useEffect(() => {
    setNodes((prev) => {
      const old = new Map(prev.map((n) => [n.id, n]));
      return vg.nodes.map((v) => ({
        id: v.id, type: "trace", position: { x: v.x, y: v.y }, data: { v, onToggle },
        selected: v.id === p.selectedId, measured: old.get(v.id)?.measured,
      }));
    });
  }, [vg, onToggle, p.selectedId]);

  const edges: Edge[] = vg.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target,
    label: e.relation === "contains" || !e.highlight ? undefined : e.label,
    animated: e.highlight?.style === "observed",
    style: edgeStyle(e),
    markerEnd: e.relation === "contains" ? undefined
      : { type: MarkerType.ArrowClosed, width: 10, height: 10, color: (edgeStyle(e).stroke as string) },
    data: { edgeIds: e.edgeIds },
  }));

  // Fit only once React Flow has measured every node; fitting earlier silently does nothing.
  const initialized = useNodesInitialized();
  const lastFit = useRef("");
  useEffect(() => {
    const key = `${p.fitKey}|${vg.nodes.length}`;
    if (!initialized || lastFit.current === key) return;
    lastFit.current = key;
    requestAnimationFrame(() => fitView({ padding: 0.15, duration: 300 }));
  }, [initialized, p.fitKey, vg.nodes.length, fitView]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={(changes) => setNodes((ns) => applyNodeChanges(changes, ns) as Node<NodeData>[])}
      onNodeClick={(_, n) => p.onSelect(n.id)}
      onPaneClick={() => p.onSelect(null)}
      onEdgeClick={(_, e) => p.onEdgeSelect((e.data?.edgeIds as string[]) ?? [e.id])}
      nodesDraggable={false}
      className="graph-canvas"
      colorMode="dark"
      minZoom={0.2}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={28} size={1} />
      <Panel position="top-right">
        <HStack gap={1} vAlign="center">
          <TextInput label="Search nodes" isLabelHidden size="sm" value={search} onChange={setSearch}
                     placeholder="Search…" startIcon="search" hasClear width={200} />
          <Button label="Expand all" size="sm" variant="ghost" onClick={p.onExpandAll} />
          <Button label="Collapse" size="sm" variant="ghost" onClick={p.onCollapseAll} />
          {p.onClearFocus && <Button label="Show everything" size="sm" variant="ghost" onClick={p.onClearFocus} />}
        </HStack>
      </Panel>
      <Panel position="bottom-left"><Legend /></Panel>
      <Controls showInteractive={false} position="bottom-right" />
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

function Legend() {
  const [open, setOpen] = useState(false);
  if (!open) return <Button label="Legend" size="sm" variant="ghost" onClick={() => setOpen(true)} />;
  return (
    <Card padding={2} elevation="low">
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <Text type="label">Legend</Text>
          <IconButton label="Close legend" size="sm" variant="ghost" icon={<CircleX size={14} />} onClick={() => setOpen(false)} />
        </HStack>
        <Text type="supporting">Solid line: verified · dashed: from code · dotted: declared, unchecked</Text>
        <HStack gap={2} wrap="wrap">
          <HStack gap={1} vAlign="center"><StatusDot variant="error" label="Conflict or failed" /><Text type="supporting">conflict / failed</Text></HStack>
          <HStack gap={1} vAlign="center"><StatusDot variant="warning" label="Suspected" /><Text type="supporting">suspected</Text></HStack>
          <HStack gap={1} vAlign="center"><StatusDot variant="accent" label="Observed" /><Text type="supporting">observed</Text></HStack>
        </HStack>
        <Text type="supporting">Double-click a dot to expand · click a line to verify wiring</Text>
      </VStack>
    </Card>
  );
}
