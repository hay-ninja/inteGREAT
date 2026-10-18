import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Selector } from "@astryxdesign/core/Selector";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { Button } from "@astryxdesign/core/Button";
import { Badge } from "@astryxdesign/core/Badge";
import { parseSource } from "../flow/common";
import type { AgentStatus, DeviceStatus, Project, Subsystem } from "../../lib/api";

/** Minimal chrome: where you are, what you're focused on, are devices ready. Everything else is in "More". */
export function TopBar(p: {
  project: Project;
  subsystems: Subsystem[];
  focus: string;
  onFocus: (sid: string) => void;
  devices: DeviceStatus | null;
  agents: AgentStatus | null;
  source: string;
  onRescan: () => void;
  onRigSetup: () => void;
  onSettings: () => void;
  onOpenDrawer: (tab: "activity") => void;
  onProjects: () => void;
}) {
  const serial = p.devices?.serial.connected;
  const cam = p.devices?.camera;
  const kind = parseSource(p.source).kind;
  const mode = kind === "live" ? { variant: "success" as const, label: "Live rig" }
    : kind === "replay" ? { variant: "neutral" as const, label: "Replay" }
    : { variant: "neutral" as const, label: "Simulated" };
  return (
    <HStack hAlign="between" vAlign="center" gap={3} width="100%" wrap="wrap">
      <HStack gap={2} vAlign="center">
        <button type="button" className="brand" onClick={p.onProjects} title="Back to projects"><span className="bmark">inte</span>GREAT</button>
        <Text type="supporting" maxLines={1}>{p.project.name}</Text>
      </HStack>
      <HStack gap={1.5} vAlign="center">
        <Text type="supporting">Subsystem</Text>
        <Selector label="Subsystem" isLabelHidden size="sm" width={200} placement="below" value={p.focus || "all"}
                  onChange={(v) => p.onFocus(v === "all" ? "" : v)}
                  options={[{ value: "all", label: "Whole system" },
                            ...p.subsystems.map((s) => ({ value: s.id, label: s.label }))]} />
      </HStack>
      <div className="topbar-divider" />
      <HStack gap={3} vAlign="center">
        <Badge variant={mode.variant} label={mode.label}
               icon={<StatusDot variant={kind === "live" ? "success" : "neutral"} label={mode.label} />} />
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
          { label: "Project settings…", description: "Name, files, context notes, subsystem names", onClick: p.onSettings },
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
