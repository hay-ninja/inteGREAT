import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
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
      <div className="setup-dialog-body">
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
      </div>
    </Dialog>
  );
}

/** LED locator + baseline (D-047). Blink-to-find sends engineer-confirmed fixed serial
 *  commands — never arbitrary writes — and diffs frames; dragging a box on the video
 *  overlay is the manual fallback. */
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
  const [roi, setRoi] = useState<number[] | null>(null);
  const [manual, setManual] = useState("");
  useEffect(() => setCandidates(null), [cid]);

  const refresh = () => api.devices().then(onDevices).catch((e) => onError(e.message));
  const locate = () => {
    setBusy(true); setMsg(null); setCandidates(null);
    api.cameraLocateLed(cid, onCmd.trim() || "LED ON", offCmd.trim() || "LED OFF")
      .then((r) => {
        setMsg(r.message);
        if (r.candidates?.length) setCandidates(r.candidates);
        if (r.roi) setRoi(r.roi);
        refresh();
      })
      .catch((e) => onError(e.message))
      .finally(() => setBusy(false));
  };
  const useRoi = (next: number[]) => {
    setBusy(true); setMsg(null);
    api.cameraSetLedRoi(cid, next.map(Math.round))
      .then(onDevices)
      .then(() => { setRoi(next.map(Math.round)); setCandidates(null); setMsg("Region set — LED-off baseline recorded"); })
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
        <RoiView cid={cid} candidates={candidates ?? []} roi={roi} onPick={useRoi} disabled={busy} />
        <Text type="supporting">
          Click once for box 1, then hold and release for box 2 — the region between
          them is the LED. Picking a region also records the LED-off baseline, so make
          sure it is dark right now. Blink-to-find is usually faster: it toggles the
          LED over serial and watches which part of the image changes — no marker
          needed, and it sends exactly the two commands below, nothing else. If the
          board doesn't answer, your firmware may not handle these commands — mark the
          region on the video instead.
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
        {candidates && candidates.length > 1 && (
          <Text type="supporting" color="secondary">
            Several regions changed — click the box on the video that is this LED (outlined above).
          </Text>
        )}
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

/** Live feed with a two-click region marker. Drag doesn't survive the MJPEG stream —
 *  each frame swap can drop pointer capture — so this is click corner 1, click corner 2.
 *  Rects are kept in natural frame pixels and drawn as percentage-positioned divs so
 *  the overlay tracks the scaled <img>. */
function RoiView({ cid, candidates, roi, onPick, disabled }: {
  cid: string;
  candidates: number[][];
  roi: number[] | null;
  onPick: (r: number[]) => void;
  disabled: boolean;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [nat, setNat] = useState<[number, number] | null>(null);
  const [first, setFirst] = useState<[number, number] | null>(null);  // anchored corner 1, frame px
  const [press, setPress] = useState<[number, number] | null>(null);  // gesture origin while held
  const [hover, setHover] = useState<[number, number] | null>(null);  // cursor while held
  const lastCursor = useRef<[number, number] | null>(null);

  // MJPEG frames don't reliably re-fire onLoad — poll natural size until known.
  useEffect(() => {
    const tick = () => {
      const im = imgRef.current;
      if (im?.naturalWidth) setNat((cur) =>
        cur && cur[0] === im.naturalWidth && cur[1] === im.naturalHeight ? cur : [im.naturalWidth, im.naturalHeight]);
    };
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [cid]);
  useEffect(() => { setFirst(null); setPress(null); setHover(null); }, [cid]);

  const toNat = (e: { clientX: number; clientY: number }): [number, number] | null => {
    const im = imgRef.current;
    if (!im?.naturalWidth) return null;
    const b = im.getBoundingClientRect();
    const sx = im.naturalWidth / b.width, sy = im.naturalHeight / b.height;
    return [
      Math.max(0, Math.min(im.naturalWidth, (e.clientX - b.left) * sx)),
      Math.max(0, Math.min(im.naturalHeight, (e.clientY - b.top) * sy)),
    ];
  };

  const finish = (origin: [number, number], end: [number, number] | null) => {
    setPress(null); setHover(null);
    if (!first) { setFirst(origin); return; }        // gesture 1: box 1 stays placed
    const e2 = end ?? origin;                         // gesture 2: commit on release point
    const r = [Math.min(first[0], e2[0]), Math.min(first[1], e2[1]),
               Math.abs(e2[0] - first[0]), Math.abs(e2[1] - first[1])];
    if (r[2] >= 6 && r[3] >= 6) { setFirst(null); onPick(r); }
    // too small a span keeps box 1 so the engineer can just press again
  };

  // Releases off the image still end the gesture — pointer capture over an MJPEG
  // stream is unreliable, so a window listener covers release outside the frame.
  useEffect(() => {
    if (!press) return;
    const done = () => finish(press, lastCursor.current);
    window.addEventListener("pointerup", done);
    return () => window.removeEventListener("pointerup", done);
  }, [!!press]);

  const down = (e: ReactPointerEvent) => {
    if (disabled) return;
    const p = toNat(e);
    if (!p) return;
    lastCursor.current = p;
    setPress(p); setHover(p);
  };
  const move = (e: ReactPointerEvent) => {
    const p = toNat(e);
    if (!p) return;
    lastCursor.current = p;
    if (press) setHover(p);
  };
  const preview = first && press && hover
    ? [Math.min(first[0], hover[0]), Math.min(first[1], hover[1]),
       Math.abs(hover[0] - first[0]), Math.abs(hover[1] - first[1])]
    : null;
  const box = (r: number[]) => nat ? {
    left: `${(r[0] / nat[0]) * 100}%`, top: `${(r[1] / nat[1]) * 100}%`,
    width: `${(r[2] / nat[0]) * 100}%`, height: `${(r[3] / nat[1]) * 100}%`,
  } : undefined;

  return (
    <div className="roi-view">
      <img ref={imgRef} draggable={false}
           src={`/api/v1/devices/camera/stream.mjpg?metric=led_state&component=${encodeURIComponent(cid)}`}
           alt="Live camera — click two corners around the LED" />
      <div className="roi-layer" role="presentation" onPointerDown={down} onPointerMove={move}>
        {nat && roi && <div className="roi-box roi-current" style={box(roi)} />}
        {nat && candidates.map((r, i) => (
          <button key={i} className="roi-box roi-candidate" style={box(r)}
                  aria-label={`Use candidate region ${i + 1}`}
                  onPointerDown={(e) => { e.stopPropagation(); setFirst(null); setPress(null); onPick(r); }} />
        ))}
        {nat && preview && <div className="roi-box roi-drag" style={box(preview)} />}
        {nat && (first ?? press) && <div className="roi-corner" style={box([(first ?? press)![0] - 4, (first ?? press)![1] - 4, 8, 8])} />}
      </div>
      {first && (
        <div className="roi-hint">
          <span>Box 1 placed — hold and release for box 2</span>
          <button className="roi-reset" onPointerDown={(e) => { e.stopPropagation(); setFirst(null); setHover(null); }}>
            Reset
          </button>
        </div>
      )}
    </div>
  );
}
