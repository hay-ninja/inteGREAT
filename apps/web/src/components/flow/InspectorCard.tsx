/** One inspector pattern for every selected thing — node, connection, or event (D-027).
 * Shared chrome: muted card, eyebrow category label, optional close. Content varies per kind. */
import type { ReactNode } from "react";
import { Card } from "@astryxdesign/core/Card";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { IconButton } from "@astryxdesign/core/IconButton";
import { X } from "lucide-react";
import { Eyebrow } from "./common";

export function InspectorCard({ eyebrow, onClose, children }: {
  eyebrow: string;
  onClose?: () => void;
  children: ReactNode;
}) {
  return (
    <Card padding={3} variant="muted">
      <VStack gap={2}>
        <HStack hAlign="between" vAlign="center">
          <Eyebrow>{eyebrow}</Eyebrow>
          {onClose && <IconButton label="Close" size="sm" variant="ghost" icon={<X size={14} />} onClick={onClose} />}
        </HStack>
        {children}
      </VStack>
    </Card>
  );
}
