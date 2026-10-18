import { Collapsible } from "@astryxdesign/core/Collapsible";
import { VStack } from "@astryxdesign/core/VStack";
import { Text } from "@astryxdesign/core/Text";
import { List, ListItem } from "@astryxdesign/core/List";
import type { GraphSnapshot, Project } from "../../lib/api";
import { Eyebrow } from "./common";

export function ProjectReview({ project, graph, onConnection }: {
  project: Project; graph: GraphSnapshot; onConnection: (ids: string[]) => void;
}) {
  const wiring = graph.edges.filter((e) => e.origin === "declared_wiring");
  const labels = new Map(graph.nodes.map((n) => [n.id, n.label]));
  const unchecked = wiring.filter((e) => e.verification !== "verified");
  return (
    <Collapsible defaultIsOpen={false} trigger={<Eyebrow>Review imported project</Eyebrow>}>
      <VStack gap={2}>
        <Text type="supporting">{graph.nodes.filter((n) => n.kind === "source_module").length} source files · {wiring.length} declared connections · {unchecked.length} unchecked</Text>
        <Text type="supporting">A manifest or netlist describes the design. Confirm physical wiring on the bench before treating it as verified.</Text>
        <List density="compact" header={<Eyebrow>Declared wiring</Eyebrow>}>
          {wiring.map((e) => (
            <ListItem key={e.id} label={`${labels.get(e.source_id)} → ${labels.get(e.target_id)}`}
                      description={e.verification === "verified" ? "Marked verified in project context" : "Unchecked — select to review"}
                      onClick={() => onConnection([e.id])} />
          ))}
        </List>
        {project.issues.filter((i) => i.level !== "info").map((issue, i) => <Text key={i} type="supporting">{issue.message}</Text>)}
      </VStack>
    </Collapsible>
  );
}
