import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import type { DeviceStatus } from "../../lib/api";
import { DeviceControls } from "../drawer/BottomDrawer";

export function RigSetupDialog(p: {
  open: boolean;
  onClose: () => void;
  devices: DeviceStatus | null;
  onDevices: (s: DeviceStatus) => void;
  onError: (message: string) => void;
  onUseSimulation: () => void;
}) {
  const checks = [
    { label: "ESP32 connected", ready: !!p.devices?.serial.connected },
    { label: "Camera connected", ready: !!p.devices?.camera.connected },
    { label: "Angle calibrated", ready: !!p.devices?.camera.connected && !!p.devices?.camera.calibrated },
  ];
  const ready = checks.every((c) => c.ready);
  return (
    <Dialog isOpen={p.open} onOpenChange={(open) => !open && p.onClose()} width={840} maxHeight="90dvh" purpose="form">
      <DialogHeader title="Set up the live rig" subtitle="Plug in the board and camera, then tell it the arm's current angle so the camera can measure movement." onOpenChange={(open) => !open && p.onClose()} />
      <VStack gap={4} padding={4}>
        <HStack gap={3} wrap="wrap">
          {checks.map((c) => (
            <HStack key={c.label} gap={1} vAlign="center">
              <StatusDot variant={c.ready ? "success" : "neutral"} label={`${c.label}: ${c.ready ? "ready" : "needed"}`} />
              <Text type="supporting">{c.label}</Text>
            </HStack>
          ))}
        </HStack>
        <DeviceControls status={p.devices} onStatus={p.onDevices} onError={p.onError} />
        <Text type="supporting">Live tests require all three checks. You can explore the complete workflow with a clearly labeled simulated rig.</Text>
        <HStack gap={2} hAlign="end">
          {!ready && <Button label="Use simulated rig" variant="primary" onClick={p.onUseSimulation} />}
          <Button label={ready ? "Rig ready — continue" : "Close setup"} variant={ready ? "primary" : "ghost"} onClick={p.onClose} />
        </HStack>
      </VStack>
    </Dialog>
  );
}
