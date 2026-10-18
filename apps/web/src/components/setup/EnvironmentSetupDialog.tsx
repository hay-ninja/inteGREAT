import { useEffect, useState } from "react";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Card } from "@astryxdesign/core/Card";
import { TextInput } from "@astryxdesign/core/TextInput";
import { api, type DeviceStatus, type Expectation } from "../../lib/api";
import { DeviceControls } from "../drawer/BottomDrawer";

export function EnvironmentSetupDialog(p: {
  open: boolean;
  onClose: () => void;
  devices: DeviceStatus | null;
  onDevices: (s: DeviceStatus) => void;
  onError: (message: string) => void;
  onUseSimulation: () => void;
  expectation: Expectation | null;
}) {
  const isLed = p.expectation?.metric === "led_state";
  const ledReady = isLed && !!p.devices?.camera.calibrations?.includes(`led_state:${p.expectation?.component_id}`);
  const checks = [
    { label: "ESP32 connected", ready: !!p.devices?.serial.connected },
    { label: "Camera connected", ready: !!p.devices?.camera.connected },
    isLed
      ? { label: "LED baseline recorded", ready: ledReady }
      : { label: "Camera calibrated", ready: !!p.devices?.camera.connected && !!p.devices?.camera.calibrated },
  ];
  const ready = checks.every((c) => c.ready);
  return (
    <Dialog isOpen={p.open} onOpenChange={(open) => !open && p.onClose()} width={840} maxHeight="90dvh" purpose="form">
      <DialogHeader title="Set up the live environment" subtitle="Plug in the board and camera, then keep the printed markers in view so the camera can measure the component." onOpenChange={(open) => !open && p.onClose()} />
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
        {isLed && p.devices?.camera.connected && (
          <LedSetup expectation={p.expectation!} devices={p.devices} onDevices={p.onDevices} onError={p.onError} />
        )}
        <Text type="supporting">Live tests require all three checks. You can explore the complete workflow with a clearly labeled simulated environment.</Text>
        <HStack gap={2} hAlign="end">
          {!ready && <Button label="Use simulated environment" variant="primary" onClick={p.onUseSimulation} />}
          <Button label={ready ? "Environment ready — continue" : "Close setup"} variant={ready ? "primary" : "ghost"} onClick={p.onClose} />
        </HStack>
      </VStack>
    </Dialog>
  );
}

/** LED locator + baseline (D-045). Blink-to-find sends engineer-confirmed fixed serial
 *  commands — never arbitrary writes — and diffs frames; the manual box is the fallback. */
function LedSetup({ expectation, devices, onDevices, onError }: {
  expectation: Expectation;
  devices: DeviceStatus;
  onDevices: (s: DeviceStatus) => void;
  onError: (m: string) => void;
}) {
  const cid = expectation.component_id;
  const calibrated = !!devices.camera.calibrations?.includes(`led_state:${cid}`);
  const serialOk = devices.serial.connected;
  const [busy, setBusy] = useState(false);
  const [onCmd, setOnCmd] = useState(expectation.trigger?.value ?? "LED ON");
  const [offCmd, setOffCmd] = useState(() =>
    (expectation.trigger?.value ?? "LED ON").replace(/on$/i, "OFF"));
  const [msg, setMsg] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<number[][] | null>(null);
  const [manual, setManual] = useState("");
  useEffect(() => setCandidates(null), [cid]);

  const refresh = () => api.devices().then(onDevices).catch((e) => onError(e.message));
  const locate = () => {
    setBusy(true); setMsg(null); setCandidates(null);
    api.cameraLocateLed(cid, onCmd.trim() || "LED ON", offCmd.trim() || "LED OFF")
      .then((r) => {
        setMsg(r.message);
        if (r.candidates?.length) setCandidates(r.candidates);
        refresh();
      })
      .catch((e) => onError(e.message))
      .finally(() => setBusy(false));
  };
  const useRoi = (roi: number[]) => {
    setBusy(true); setMsg(null);
    api.cameraSetLedRoi(cid, roi)
      .then(onDevices)
      .then(() => { setCandidates(null); setMsg("Region set — LED-off baseline recorded"); })
      .catch((e) => onError(e.message))
      .finally(() => setBusy(false));
  };
  const manualRoi = () => {
    const parts = manual.split(",").map((x) => parseInt(x.trim(), 10));
    if (parts.length !== 4 || parts.some((v) => !Number.isFinite(v) || v < 0)) {
      onError("Region must be four numbers: x, y, width, height — in preview pixels");
      return;
    }
    useRoi(parts);
  };
  return (
    <Card padding={3}>
      <VStack gap={2}>
        <HStack gap={1} vAlign="center">
          <StatusDot variant={calibrated ? "success" : "warning"} label={calibrated ? "LED ready" : "LED needs setup"} />
          <Text type="label">LED measurement — {cid}</Text>
          <Text type="supporting">{calibrated ? "region + off-baseline recorded" : "not yet located"}</Text>
        </HStack>
        <Text type="supporting">
          Blink-to-find toggles the LED over serial and watches which part of the image changes —
          no marker needed. It sends exactly the two commands below, nothing else.
        </Text>
        <HStack gap={1} vAlign="end" wrap="wrap">
          <TextInput label="ON command" value={onCmd} onChange={setOnCmd} width={140} />
          <TextInput label="OFF command" value={offCmd} onChange={setOffCmd} width={140} />
          <Button label={busy ? "Blinking…" : "Blink to find the LED"} size="sm"
                  isDisabled={busy || !serialOk}
                  tooltip={serialOk ? "Toggle the LED and diff the frames" : "Connect the ESP32 first — blink needs serial"}
                  clickAction={locate} />
        </HStack>
        {msg && <Text type="supporting" color="secondary">{msg}</Text>}
        {candidates?.map((r, i) => (
          <HStack key={i} gap={1} vAlign="center">
            <Button label={`Use region ${i + 1} — ${r[2]}×${r[3]} at (${r[0]}, ${r[1]})`} size="sm" variant="ghost" clickAction={() => useRoi(r)} />
          </HStack>
        ))}
        <HStack gap={1} vAlign="end">
          <TextInput label="Or type the region: x, y, w, h" value={manual} onChange={setManual} width={240} placeholder="e.g. 188, 68, 24, 24" />
          <Button label="Use region" size="sm" variant="ghost" isDisabled={busy || !manual.trim()} clickAction={manualRoi} />
        </HStack>
        {calibrated && (
          <Button label="Re-record LED-off baseline" size="sm" variant="ghost"
                  tooltip="Assert the LED is currently OFF and save its brightness as the baseline"
                  clickAction={() => api.cameraCalibrateLed(cid).then(onDevices).catch((e) => onError(e.message))} />
        )}
      </VStack>
    </Card>
  );
}
