import { useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Panel,
  Position,
  PanOnScrollMode,
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
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Layout, LayoutContent, LayoutHeader } from "@astryxdesign/core/Layout";
import type { GraphLayer, GraphSnapshot, Highlight } from "../../lib/api";
import {
  HW_KINDS,
  buildVisibleGraph,
  edgeLabel,
  hiddenByLayer,
  nodeLabel,
  relatedSelection,
  type Region,
  type VEdge,
  type VNode,
} from "./visibleGraph";

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
    v.boundary ? "boundary" : "", v.emphasized ? "emph" : "",
    hl ? `hl-${hl.style}` : "", v.inheritedHighlight && !v.highlight ? "inherited" : "",
    v.dimmed ? "dimmed" : "", v.matched ? "matched" : ""].join(" ");
  const title = [n.label, v.subtitle, n.kind.replace("_", " "), n.verification,
    v.boundary ? "hardware reference — shown because code touches it" : "",
    hl ? `${hl.style.replace("_", " ")}: ${hl.reason}` : ""]
    .filter(Boolean).join(" · ");
  return (
    <span className={cls} title={title}
          onDoubleClick={(e) => { if (v.expandable) { e.stopPropagation(); onToggle(n.id); } }}>
      <Handle type="target" position={Position.Top} />
      {hw ? <span className="gn-kind">{KIND_ICON[n.kind]}</span> : <span className="gn-dot" />}
      <span className="gn-stack">
        <span className="gn-label">{nodeLabel(n)}</span>
        {v.subtitle && hw && <span className="gn-sub">{v.subtitle}{v.boundary ? " · reference" : ""}</span>}
      </span>
      {hw && hl && <span className="gn-mark">{MARK[hl.style]}</span>}
      {hw && !hl && n.verification === "verified" && n.kind !== "mcu" && n.kind !== "pin" && (
        <span className="gn-mark"><CircleCheck size={11} color="var(--color-text-disabled)" /></span>
      )}
      {v.expandable && !v.expanded && <span className="gn-count">+{v.childCount}</span>}
      <Handle type="source" position={Position.Bottom} />
    </span>
  );
}

function RegionView({ data }: NodeProps<Node<{ r: Region }>>) {
  return (
    <span className="graph-region">
      <span className="graph-region-label">{data.r.label}</span>
    </span>
  );
}

const nodeTypes = { trace: GraphNodeView, region: RegionView };

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
  if (e.emphasized) { s.stroke = "var(--color-accent)"; s.strokeWidth = 2; }
  if (e.dimmed) s.opacity = 0.12;
  return s;
}

export type CanvasMode = "deps" | "flow";

interface Props {
  graph: GraphSnapshot;
  expanded: Set<string>;
  highlights: Highlight[];
  focusIds: Set<string> | null;
  selectedId: string | null;
  layer: GraphLayer;
  onLayer: (l: GraphLayer) => void;
  onToggle: (id: string) => void;
  onSelect: (id: string | null) => void;
  onEdgeSelect: (edgeIds: string[], lifted: boolean) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onClearFocus: (() => void) | null;
  fitKey: string;
}

function Inner(p: Props) {
  const { fitView, setCenter, getZoom } = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState("");
  const rel = useMemo(() => relatedSelection(p.graph, p.selectedId), [p.graph, p.selectedId]);
  const vg = useMemo(() => buildVisibleGraph(p.graph, p.expanded, p.highlights, p.focusIds, search, p.layer, rel),
    [p.graph, p.expanded, p.highlights, p.focusIds, search, p.layer, rel]);
  const hidden = hiddenByLayer(p.graph, p.layer);
  const hiddenNote = hidden.sw ? `${hidden.sw} source item${hidden.sw === 1 ? "" : "s"} hidden`
    : hidden.hw ? `${hidden.hw} hardware item${hidden.hw === 1 ? "" : "s"} hidden` : null;

  // Controlled nodes: React Flow keeps handle positions only if we pass back each node's `measured`
  // size; dropping it hides nodes/edges after a re-layout.
  const [nodes, setNodes] = useState<Node[]>([]);
  const { onToggle } = p;
  useEffect(() => {
    setNodes((prev) => {
      const old = new Map(prev.map((n) => [n.id, n]));
      const regionNodes = vg.regions.map((r): Node => ({
        id: r.id, type: "region", position: { x: r.x, y: r.y }, data: { r },
        style: { width: r.w, height: r.h }, selectable: false, draggable: false, focusable: false,
      }));
      return [
        ...regionNodes,
        ...vg.nodes.map((v): Node => ({
          id: v.id, type: "trace", position: { x: v.x, y: v.y }, data: { v, onToggle },
          selected: v.id === p.selectedId, measured: old.get(v.id)?.measured,
        })),
      ];
    });
  }, [vg, onToggle, p.selectedId]);

  const edges: Edge[] = vg.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target,
    label: e.relation === "contains" ? undefined : edgeLabel(e),
    labelStyle: { fontSize: 10 },
    labelShowBg: true,
    labelBgPadding: [4, 2] as [number, number],
    labelBgBorderRadius: 3,
    animated: e.highlight?.style === "observed" || e.highlight?.style === "failed_expectation" || e.emphasized,
    style: edgeStyle(e),
    markerEnd: e.relation === "contains" ? undefined
      : { type: MarkerType.ArrowClosed, width: 10, height: 10, color: (edgeStyle(e).stroke as string) },
    data: { edgeIds: e.edgeIds, lifted: e.lifted },
  }));

  // Fit only once React Flow has measured every node; fitting earlier silently does nothing.
  const initialized = useNodesInitialized();
  // When a node is selected, pan it to the right of the canvas — the inspector docks left.
  const lastPanned = useRef<string | null>(null);
  useEffect(() => {
    const id = p.selectedId;
    if (!id) { lastPanned.current = null; return; }
    if (!initialized || lastPanned.current === id || !canvasRef.current) return;
    const v = vg.nodes.find((n) => n.id === id);
    if (!v) return;
    const n = nodes.find((nd) => nd.id === id);
    const w = n?.measured?.width ?? 0, h = n?.measured?.height ?? 0;
    const zoom = getZoom();
    lastPanned.current = id;
    // Node lands at ~66% of canvas width: viewport center sits left of the node by (fx - 0.5).
    setCenter(v.x + w / 2 - 0.16 * (canvasRef.current.clientWidth / zoom), v.y + h / 2,
      { zoom, duration: 280 });
  }, [p.selectedId, initialized, vg, nodes, setCenter, getZoom]);

  const lastFit = useRef("");
  useEffect(() => {
    const key = `${p.fitKey}|${p.layer}|${vg.nodes.length}`;
    if (!initialized || lastFit.current === key) return;
    lastFit.current = key;
    requestAnimationFrame(() => fitView({ padding: 0.14, maxZoom: 1.25, duration: 250 }));
  }, [initialized, p.fitKey, p.layer, vg.nodes.length, fitView]);
  useEffect(() => {
    if (!initialized || !canvasRef.current) return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => fitView({ padding: 0.14, maxZoom: 1.25, duration: 200 }));
    });
    observer.observe(canvasRef.current);
    return () => { observer.disconnect(); cancelAnimationFrame(frame); };
  }, [initialized, fitView]);

  const layerEmpty = p.layer === "hardware"
    ? { title: "No hardware in this project", body: "Import a hardware manifest or KiCad netlist to see the physical environment." }
    : p.layer === "software"
      ? { title: "No source code in this scope", body: "The current scope has no modules — import a firmware repository." }
      : { title: "Empty project", body: "Nothing has been imported yet." };

  return (
    <Layout header={<LayoutHeader padding={2} hasDivider>
      <HStack gap={2} vAlign="center" wrap="wrap">
        <Text type="label" color="secondary">Dependency map</Text>
        <TextInput label="Search nodes in this view" isLabelHidden size="sm" value={search} onChange={setSearch}
                   placeholder="Search…" startIcon="search" hasClear width={200} />
        <Button label="Expand groups" size="sm" variant="secondary"
                tooltip="Reveal every part hidden inside the grouped boxes" onClick={p.onExpandAll} />
        <Button label="Collapse groups" size="sm" variant="secondary"
                tooltip="Fold the detailed parts back into their groups" onClick={p.onCollapseAll} />
        {p.onClearFocus && <Button label="Show whole system" size="sm" variant="secondary"
                tooltip="Leave the subsystem focus — show the full map again" onClick={p.onClearFocus} />}
        {hiddenNote && <Button label={`${hiddenNote} — show everything`} size="sm" variant="ghost" onClick={() => p.onLayer("combined")} />}
      </HStack>
    </LayoutHeader>} content={<LayoutContent padding={0} isScrollable={false} ref={canvasRef}>
    {vg.nodes.length === 0 ? (
      <EmptyState title={layerEmpty.title} description={layerEmpty.body} />
    ) : (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={(changes) => setNodes((ns) => applyNodeChanges(changes, ns) as Node[])}
      onNodeClick={(_, n) => { if (n.type !== "region") p.onSelect(n.id); }}
      onPaneClick={() => p.onSelect(null)}
      onEdgeClick={(_, e) => p.onEdgeSelect((e.data?.edgeIds as string[]) ?? [e.id], !!e.data?.lifted)}
      nodesDraggable={false}
      className="graph-canvas"
      colorMode="dark"
      minZoom={0.2}
      panOnScroll
      panOnScrollMode={PanOnScrollMode.Free}
      zoomOnScroll={false}
      zoomActivationKeyCode="Control"
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={28} size={1} />
      <Panel position="top-right"><Legend layer={p.layer} /></Panel>
      <Controls showInteractive={false} position="bottom-right" />
    </ReactFlow>
    )}
    </LayoutContent>} />
  );
}

export function GraphView(p: Props) {
  return (
    <ReactFlowProvider>
      <Inner {...p} />
    </ReactFlowProvider>
  );
}

function Legend({ layer }: { layer: GraphLayer }) {
  const [open, setOpen] = useState(false);
  if (!open) return <Button label="Legend" size="sm" variant="ghost" onClick={() => setOpen(true)} />;
  return (
    <Card padding={2} elevation="low">
      <VStack gap={1}>
        <HStack hAlign="between" vAlign="center">
          <Text type="label">Legend</Text>
          <IconButton label="Close legend" size="sm" variant="ghost" icon={<CircleX size={14} />} onClick={() => setOpen(false)} />
        </HStack>
        <Text type="supporting">Solid: verified · dashed: from code · dotted: declared, unchecked (from the schematic — not physically checked)</Text>
        <Text type="supporting">Accent outline: related to your selection · dashed border pill: hardware reference</Text>
        <Text type="supporting">Scroll pans · Ctrl+scroll or pinch zooms</Text>
        <HStack gap={2} wrap="wrap">
          <HStack gap={1} vAlign="center"><StatusDot variant="error" label="Conflict or failed" /><Text type="supporting">conflict / failed</Text></HStack>
          <HStack gap={1} vAlign="center"><StatusDot variant="warning" label="Suspected" /><Text type="supporting">suspected</Text></HStack>
          <HStack gap={1} vAlign="center"><StatusDot variant="accent" label="Observed" /><Text type="supporting">observed</Text></HStack>
        </HStack>
        <Text type="supporting">{layer === "combined" ? "Regions group software and hardware — lines crossing the gap are code/hardware links."
          : layer === "hardware" ? "Code is hidden — select a part to see which code controls it."
          : "Only hardware the code touches is shown, as dashed references."} Double-click a node to expand · click a line to inspect.</Text>
      </VStack>
    </Card>
  );
}
