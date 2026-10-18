/** What you clicked in the graph: facts about it, and — for declared wiring — a way to confirm it physically. */
import { useEffect, useState } from "react";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { api, type Evidence, type GraphEdge, type GraphLayer, type GraphNode, type GraphSnapshot } from "../../lib/api";
import { HW_KINDS, layerHiddenReason, nodeRole } from "../graph/visibleGraph";
import { EvidenceList } from "./common";
import { InspectorCard } from "./InspectorCard";

const CROSS = new Set(["configures", "controls", "reads_from"]);

const VERB: Record<GraphEdge["relation"], string> = {
  calls: "calls", configures: "configures pin", controls: "controls", connected_to: "connected to",
  powered_by: "powered by", reads_from: "reads from", observed_by: "observed by camera",
  depends_on: "depends on", contains: "contains",
};
const verb = (e: GraphEdge) => VERB[e.relation] ?? e.relation.replace(/_/g, " ");
const originText = (o: GraphEdge["origin"]) =>
  o === "declared_wiring" ? "from your schematic — not physically checked yet" : o.replace(/_/g, " ");

export function SelectionCard(p: {
  projectId: string;
  graph: GraphSnapshot;
  node: GraphNode | null;
  edges: GraphEdge[];
  onClose: () => void;
  onVerify: (edgeId: string, v: "verified" | "unverified") => Promise<void>;
  hideClose?: boolean;
  onEvidence?: (e: Evidence) => void;
  layer?: GraphLayer;
  onLayer?: (l: GraphLayer) => void;
  onReveal?: (ids: string[]) => void;
}) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const ids = p.edges.length ? p.edges.flatMap((e) => e.evidence_ids) : p.node?.evidence_ids ?? [];
  const key = ids.join("|");
  useEffect(() => {
    let current = true;
    setEvidence([]);
    api.evidence(p.projectId, ids).then((es) => { if (current) setEvidence(es); }).catch(() => { if (current) setEvidence([]); });
    return () => { current = false; };
  }, [p.projectId, key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!p.node && !p.edges.length) return null;
  const labels = new Map(p.graph.nodes.map((n) => [n.id, n.label]));
  const evById = new Map(evidence.map((e) => [e.id, e]));
  const close = p.hideClose ? undefined : p.onClose;

  if (p.edges.length) {
    return (
      <InspectorCard eyebrow="Connection" onClose={close}>
        {p.edges.map((e) => (
          <VStack key={e.id} gap={1}>
            <Text type="body">{labels.get(e.source_id)} {verb(e)} {labels.get(e.target_id)}</Text>
            <HStack gap={1}>
              <Text type="supporting">{e.relation.replace(/_/g, " ")} · {e.verification} · {originText(e.origin)}</Text>
            </HStack>
            {e.origin === "declared_wiring" ? (
              e.verification === "verified"
                ? <Button label="Mark as unchecked" size="sm" variant="ghost" clickAction={() => p.onVerify(e.id, "unverified")} />
                : <Button label="I checked this wire — mark verified" size="sm" variant="primary" clickAction={() => p.onVerify(e.id, "verified")} />
            ) : (
              <Text type="supporting">Found by reading the code — not something to check by hand.</Text>
            )}
          </VStack>
        ))}
        <EvidenceList title="Evidence" ids={evidence.map((e) => e.id)} evById={evById} onInspect={p.onEvidence} />
      </InspectorCard>
    );
  }
  const n = p.node!;
  const attrs = Object.entries(n.attributes ?? {}).filter(([, v]) => v !== null && v !== "");
  const role = nodeRole(n, p.graph);
  const hidden = p.layer ? layerHiddenReason(n, p.layer) : null;
  // Cross-layer routes: which code touches this hardware, which hardware this code touches.
  const cross = p.graph.edges.filter((e) => CROSS.has(e.relation) && (e.source_id === n.id || e.target_id === n.id));
  const codeIds = HW_KINDS.has(n.kind) ? cross.map((e) => HW_KINDS.has(p.graph.nodes.find((x) => x.id === e.source_id)?.kind ?? "") ? e.target_id : e.source_id)
    : cross.map((e) => e.source_id);
  const hwIds = !HW_KINDS.has(n.kind) ? cross.map((e) => HW_KINDS.has(p.graph.nodes.find((x) => x.id === e.target_id)?.kind ?? "") ? e.target_id : e.source_id)
    : cross.map((e) => e.target_id);
  return (
    <InspectorCard eyebrow={n.kind.replace(/_/g, " ")} onClose={close}>
      <HStack gap={1} vAlign="center" wrap="wrap">
        <Text type="body" weight="semibold">{n.label}</Text>
        <Text type="supporting">{n.verification}</Text>
      </HStack>
      {role && <Text type="supporting">{role}</Text>}
        {hidden && p.onLayer && (
          <HStack gap={2} vAlign="center" wrap="wrap">
            <Text type="supporting">{hidden}</Text>
            <Button label="Show in Combined view" size="sm" variant="ghost" onClick={() => p.onLayer!("combined")} />
          </HStack>
        )}
        {codeIds.length > 0 && p.onReveal && HW_KINDS.has(n.kind) && (
          <Button label={`Show the code that touches this (${codeIds.length})`} size="sm" variant="ghost"
                  onClick={() => { p.onLayer?.("combined"); p.onReveal!(codeIds); }} />
        )}
        {hwIds.length > 0 && p.onReveal && !HW_KINDS.has(n.kind) && (
          <Button label={`Show the hardware it drives (${hwIds.length})`} size="sm" variant="ghost"
                  onClick={() => { p.onLayer?.("combined"); p.onReveal!(hwIds); }} />
        )}
        {attrs.length > 0 && (
          <MetadataList>
            {attrs.map(([k, v]) => <MetadataListItem key={k} label={k.replace(/_/g, " ")}><Text type="body">{String(v)}</Text></MetadataListItem>)}
          </MetadataList>
        )}
        <EvidenceList ids={evidence.map((e) => e.id)} evById={evById} onInspect={p.onEvidence} />
        {!evidence.length && <Text type="supporting">No direct evidence attached.</Text>}
    </InspectorCard>
  );
}
