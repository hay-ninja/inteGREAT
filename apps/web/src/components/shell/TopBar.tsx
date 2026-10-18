import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Selector } from "@astryxdesign/core/Selector";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { Button } from "@astryxdesign/core/Button";
import type { AgentStatus, DeviceStatus, Project, Subsystem } from "../../lib/api";

/** Minimal chrome: where you are, what you're focused on, are devices ready. Everything else is in "More". */
export function TopBar(p: {
  project: Project;
  subsystems: Subsystem[];
  focus: string;
  onFocus: (sid: string) => void;
  devices: DeviceStatus | null;
  agents: AgentStatus | null;
  onRescan: () => void;
  onRigSetup: () => void;
  onOpenDrawer: (tab: "activity") => void;
  onProjects: () => void;
}) {
  const serial = p.devices?.serial.connected;
  const cam = p.devices?.camera;
  return (
    <HStack hAlign="between" vAlign="center" gap={3} width="100%">
      <HStack gap={2} vAlign="center">
        <span className="brand">inteGREAT</span>
        <Text type="supporting" maxLines={1}>{p.project.name}</Text>
      </HStack>
      <Selector label="Focus" isLabelHidden variant="ghost" size="sm" width={220} value={p.focus || "all"}
                onChange={(v) => p.onFocus(v === "all" ? "" : v)}
                options={[{ value: "all", label: "Whole system" },
                          ...p.subsystems.map((s) => ({ value: s.id, label: s.label }))]} />
      <HStack gap={3} vAlign="center">
        <Button label="Rig setup" size="sm" onClick={p.onRigSetup} />
        <HStack gap={3} vAlign="center">
          <HStack gap={1} vAlign="center">
            <StatusDot variant={serial ? "success" : "neutral"} label="ESP32 serial"
                       tooltip={serial ? `Controller board connected on ${p.devices?.serial.port}` : "Controller board (ESP32) not connected"} />
            <Text type="supporting">Board</Text>
          </HStack>
          <HStack gap={1} vAlign="center">
            <StatusDot variant={cam?.connected ? (cam.calibrated ? "success" : "warning") : "neutral"} label="Camera"
                       tooltip={cam?.connected ? (cam.calibrated ? "Camera watching the arm — calibrated" : "Camera connected, needs calibration") : "Camera not connected"} />
            <Text type="supporting">Camera</Text>
          </HStack>
          <HStack gap={1} vAlign="center">
            <StatusDot variant={p.agents?.available ? "accent" : "neutral"} label="AI agents"
                       tooltip={p.agents?.available ? `AI review available (${p.agents.model}) — optional; everything works without it` : `AI review off: ${p.agents?.reason ?? ""} — the built-in checks still work`} />
            <Text type="supporting">AI</Text>
          </HStack>
        </HStack>
        <MoreMenu label="More" alignment="end" items={[
          { label: "Rescan repository", description: "After you change the firmware", onClick: p.onRescan },
          { label: "Rig setup", description: "Connect ESP32 and camera", onClick: p.onRigSetup },
          { label: "Activity & tool audit", description: "Every event, tool call and approval", onClick: () => p.onOpenDrawer("activity") },
          { type: "divider" },
          { label: "Switch project", onClick: p.onProjects },
        ]} />
      </HStack>
    </HStack>
  );
}
