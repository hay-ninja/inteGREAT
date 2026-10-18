/** What you clicked in the graph: facts about it, and — for declared wiring — a way to confirm it physically. */
import { useEffect, useState } from "react";
import { Card } from "@astryxdesign/core/Card";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Badge } from "@astryxdesign/core/Badge";
import { Button } from "@astryxdesign/core/Button";
import { IconButton } from "@astryxdesign/core/IconButton";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { X } from "lucide-react";
import { api, type Evidence, type GraphEdge, type GraphNode, type GraphSnapshot } from "../../lib/api";
import { EvidenceList } from "./common";

const VER_BADGE: Record<string, "success" | "neutral" | "warning" | "error" | "info"> = {
  verified: "success", observed: "info", inferred: "neutral", unverified: "warning", conflicting: "error",
};

export function SelectionCard(p: {
  projectId: string;
  graph: GraphSnapshot;
  node: GraphNode | null;
  edges: GraphEdge[];
  onClose: () => void;
  onVerify: (edgeId: string, v: "verified" | "unverified") => Promise<void>;
}) {
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const ids = p.edges.length ? p.edges.flatMap((e) => e.evidence_ids) : p.node?.evidence_ids ?? [];
  const key = ids.join("|");
  useEffect(() => {
    api.evidence(p.projectId, ids).then(setEvidence).catch(() => setEvidence([]));
  }, [p.projectId, key]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!p.node && !p.edges.length) return null;
  const labels = new Map(p.graph.nodes.map((n) => [n.id, n.label]));
  const evById = new Map(evidence.map((e) => [e.id, e]));
  const close = <IconButton label="Close" size="sm" variant="ghost" icon={<X size={14} />} onClick={p.onClose} />;

  if (p.edges.length) {
    return (
      <Card padding={3} variant="muted">
        <VStack gap={2}>
          <HStack hAlign="between" vAlign="center"><Text type="label" color="secondary">Connection</Text>{close}</HStack>
          {p.edges.map((e) => (
            <VStack key={e.id} gap={1}>
              <Text type="body">{labels.get(e.source_id)} → {labels.get(e.target_id)}</Text>
              <HStack gap={1}>
                <Badge label={e.relation.replace("_", " ")} />
                <Badge variant={VER_BADGE[e.verification]} label={e.verification} />
                <Badge label={e.origin.replace(/_/g, " ")} />
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
          <EvidenceList title="Evidence" ids={evidence.map((e) => e.id)} evById={evById} />
        </VStack>
      </Card>
    );
  }
  const n = p.node!;
  const attrs = Object.entries(n.attributes ?? {}).filter(([, v]) => v !== null && v !== "");
  return (
    <Card padding={3} variant="muted">
      <VStack gap={2}>
        <HStack hAlign="between" vAlign="center">
          <HStack gap={1} vAlign="center">
            <Text type="body" weight="semibold">{n.label}</Text>
            <Badge label={n.kind.replace("_", " ")} />
            <Badge variant={VER_BADGE[n.verification]} label={n.verification} />
          </HStack>
          {close}
        </HStack>
        {attrs.length > 0 && (
          <MetadataList>
            {attrs.map(([k, v]) => <MetadataListItem key={k} label={k.replace(/_/g, " ")}><Text type="body">{String(v)}</Text></MetadataListItem>)}
          </MetadataList>
        )}
        <EvidenceList ids={evidence.map((e) => e.id)} evById={evById} />
        {!evidence.length && <Text type="supporting">No direct evidence attached.</Text>}
      </VStack>
    </Card>
  );
}
