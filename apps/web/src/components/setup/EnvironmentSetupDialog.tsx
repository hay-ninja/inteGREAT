import { useEffect, useRef, useState,
         type MouseEvent as ReactMouseEvent, type PointerEvent as ReactPointerEvent } from "react";
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
  observationOnly?: boolean;
  open: boolean;
  onClose: () => void;
  devices: DeviceStatus | null;
  onDevices: (s: DeviceStatus) => void;
  onError: (message: string) => void;
  onUseSimulation: () => void;
  expectation: Expectation | null;
  expectations: Expectation[];
  leds: { id: string; label: string }[];
}) {
  const isLed = p.expectation?.metric === "led_state";
  const ledReady = isLed && !!p.devices?.camera.calibrations?.includes(`led_state:${p.expectation?.component_id}`);
  const checks = p.observationOnly ? [{ label: "Camera connected", ready: !!p.devices?.camera.connected }] : [
    { label: "ESP32 connected", ready: !!p.devices?.serial.connected },
    { label: "Camera connected", ready: !!p.devices?.camera.connected },
    isLed
      ? { label: "LED baseline recorded", ready: ledReady }
      : { label: "Camera calibrated", ready: !!p.devices?.camera.connected && !!p.devices?.camera.calibrated },
  ];
  const ready = checks.every((c) => c.ready);
  return (
    <Dialog isOpen={p.open} onOpenChange={(open) => !open && p.onClose()} width={840} maxHeight="90dvh" purpose="form">
      <DialogHeader title="Set up the live environment" subtitle={p.observationOnly ? "Connect a camera, then configure LED regions in the workspace. No serial connection is required." : isLed ? "Connect the board and camera, then select each LED region and record its baseline." : "Connect the board and camera, then calibrate the printed markers at a known angle."} onOpenChange={(open) => !open && p.onClose()} />
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
          <DeviceControls observationOnly={p.observationOnly} ledMode={isLed} status={p.devices} onStatus={p.onDevices} onError={p.onError} />
          {!p.observationOnly && isLed && p.devices?.camera.connected && (
            <LedSetup expectation={p.expectation!} expectations={p.expectations} leds={p.leds}
                      devices={p.devices} onDevices={p.onDevices} onError={p.onError} />
          )}
          <Text type="supporting">{p.observationOnly ? "Configure LED regions and visual expectations in the workspace after connecting the camera." : "Live tests require all three checks. You can explore the complete workflow with a clearly labeled simulated environment."}</Text>
          <HStack gap={2} hAlign="end">
            {!ready && !p.observationOnly && <Button label="Use simulated environment" variant="primary" onClick={p.onUseSimulation} />}
            <Button label={ready ? "Environment ready — continue" : "Close setup"} variant={ready ? "primary" : "ghost"} onClick={p.onClose} />
          </HStack>
        </VStack>
      </div>
    </Dialog>
  );
}

/** LED locator + baseline (D-054). Blink-to-find sends engineer-confirmed fixed serial
 *  commands — never arbitrary writes — and diffs frames; dragging a box on the video
 *  overlay is the manual fallback. */
function LedSetup({ expectation, expectations, leds, devices, onDevices, onError }: {
  expectation: Expectation;
  expectations: Expectation[];
  leds: { id: string; label: string }[];
  devices: DeviceStatus;
  onDevices: (s: DeviceStatus) => void;
  onError: (m: string) => void;
}) {
  // Each LED keeps its own estimator keyed led_state:{component} — the switcher
  // picks which one the next box/blink applies to.
  const [cid, setCid] = useState(expectation.component_id);
  const calibrated = !!devices.camera.calibrations?.includes(`led_state:${cid}`);
  const serialOk = devices.serial.connected;
  const [busy, setBusy] = useState(false);
  const [onCmd, setOnCmd] = useState(expectation.trigger?.value ?? "LED ON");
  const [offCmd, setOffCmd] = useState(() =>
    (expectation.trigger?.value ?? "LED ON").replace(/on$/i, "OFF"));
  const [msg, setMsg] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<number[][] | null>(null);
  const [rois, setRois] = useState<Record<string, number[]>>({});   // committed regions per component
  const [manual, setManual] = useState("");
  const roi = rois[cid] ?? null;
  useEffect(() => { setCandidates(null); setMsg(null); }, [cid]);
  // Each LED may take a different command (GHOST ON vs FLICKER) — seed the fields
  // from that component's own expectation when it exists; leave edits alone otherwise.
  useEffect(() => {
    const t = expectations.find((e) => e.metric === "led_state" && e.component_id === cid)?.trigger?.value;
    if (t) { setOnCmd(t); setOffCmd(t.replace(/on$/i, "OFF")); }
  }, [cid]);

  const refresh = () => api.devices().then(onDevices).catch((e) => onError(e.message));
  const locate = () => {
    setBusy(true); setMsg(null); setCandidates(null);
    api.cameraLocateLed(cid, onCmd.trim() || "LED ON", offCmd.trim() || "LED OFF")
      .then((r) => {
        setMsg(r.message);
        if (r.candidates?.length) setCandidates(r.candidates);
        if (r.roi) setRois((m) => ({ ...m, [cid]: r.roi! }));
        refresh();
      })
      .catch((e) => onError(e.message))
      .finally(() => setBusy(false));
  };
  const useRoi = (next: number[]) => {
    setBusy(true); setMsg(null);
    api.cameraSetLedRoi(cid, next.map(Math.round))
      .then(onDevices)
      .then(() => { setRois((m) => ({ ...m, [cid]: next.map(Math.round) })); setCandidates(null); setMsg("Region set — LED-off baseline recorded"); })
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
          <Text type="label">LED measurement — {leds.find((l) => l.id === cid)?.label ?? cid}</Text>
          <Text type="supporting">{calibrated ? "region + off-baseline recorded" : "not yet located"}</Text>
        </HStack>
        {leds.length > 1 && (
          <HStack gap={1} wrap="wrap">
            {leds.map((l) => {
              const ready = !!devices.camera.calibrations?.includes(`led_state:${l.id}`);
              return (
                <Button key={l.id} size="sm" variant={l.id === cid ? "primary" : "ghost"}
                        label={`${l.label}${ready ? " ✓" : ""}`}
                        tooltip={ready ? "Region + baseline recorded" : "Not yet located — draw or blink its box"}
                        clickAction={() => setCid(l.id)} />
              );
            })}
          </HStack>
        )}
        <RoiView cid={cid} candidates={candidates ?? []} roi={roi}
                 others={Object.entries(rois).filter(([id]) => id !== cid).map(([, r]) => r)}
                 onPick={useRoi} disabled={busy} />
        <Text type="supporting">
          Click box 1 then box 2, or just press-drag-release a box — the region
          between them is the LED. Picking a region also records the LED-off baseline, so make
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

/** Live feed region marker supporting BOTH gestures: click box 1 + click box 2,
 *  or press-drag-release to draw a box in one motion — the press point is captured
 *  on pointerdown, so a press-release spanning >=6px commits that box outright.
 *  Click (release on the same element) is used instead of raw pointerup so MJPEG
 *  frame swaps can't break the gesture. A minimum gap after corner 1 prevents an
 *  echoed event from closing box 2 prematurely. Rects are natural frame pixels
 *  drawn as percentage-positioned divs so the overlay tracks the scaled <img>. */
const MIN_CLICK_GAP_MS = 350;
const MIN_BOX_PX = 6;

function RoiView({ cid, candidates, roi, others, onPick, disabled }: {
  cid: string;
  candidates: number[][];
  roi: number[] | null;
  others: number[][];
  onPick: (r: number[]) => void;
  disabled: boolean;
}) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [nat, setNat] = useState<[number, number] | null>(null);
  const [first, setFirst] = useState<[number, number] | null>(null);  // anchored corner 1, frame px
  const [hover, setHover] = useState<[number, number] | null>(null);  // preview cursor pos
  const firstAt = useRef(0);
  const pressAt = useRef<[number, number] | null>(null);  // pointerdown of the in-progress gesture

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
  useEffect(() => { setFirst(null); setHover(null); }, [cid]);

  // object-fit: contain letterboxes the frame inside the <img> element — the
  // painted sub-rect is what maps to natural pixels, not the element box.
  const paint = () => {
    const im = imgRef.current;
    if (!im?.naturalWidth) return null;
    const b = im.getBoundingClientRect();
    const s = Math.min(b.width / im.naturalWidth, b.height / im.naturalHeight);
    const w = im.naturalWidth * s, h = im.naturalHeight * s;
    return { l: b.left + (b.width - w) / 2, t: b.top + (b.height - h) / 2, s, el: b };
  };

  const toNat = (e: { clientX: number; clientY: number }): [number, number] | null => {
    const im = imgRef.current;
    const p = paint();
    if (!im || !p) return null;
    const x = (e.clientX - p.l) / p.s, y = (e.clientY - p.t) / p.s;
    if (x < 0 || y < 0 || x >= im.naturalWidth || y >= im.naturalHeight) return null;
    return [x, y];
  };

  const span = (a: [number, number], b: [number, number]): number[] =>
    [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])];

  const down = (e: ReactPointerEvent) => { if (!disabled) pressAt.current = toNat(e); };
  const move = (e: ReactPointerEvent) => { if (first || pressAt.current) setHover(toNat(e)); };

  // click = pointer released on the same element it pressed (MJPEG-safe). The
  // gesture's box spans press point → release point: a span >= MIN_BOX_PX is a
  // drawn box; a smaller span is a plain click (corner placement).
  const click = (e: ReactMouseEvent) => {
    if (disabled) return;
    const end = toNat(e);
    const start = pressAt.current; pressAt.current = null;
    if (!end || !start) return;
    const drawn = span(start, end);
    const dragged = drawn[2] >= MIN_BOX_PX && drawn[3] >= MIN_BOX_PX;
    if (!first) {
      if (dragged) { onPick(drawn); return; }          // drew the whole box in one gesture
      setFirst(start); firstAt.current = performance.now();
      return;
    }
    // A click landing within the gap is the same gesture echoing (double events,
    // stream hiccups) — never let it close box 2 prematurely.
    if (performance.now() - firstAt.current < MIN_CLICK_GAP_MS) return;
    const r = dragged ? drawn : span(first, end);
    if (r[2] < MIN_BOX_PX || r[3] < MIN_BOX_PX) return;  // degenerate — keep box 1, click again
    setFirst(null); setHover(null);
    onPick(r);
  };
  const leave = () => { pressAt.current = null; if (!first) setHover(null); };

  // Preview follows the cursor from whichever anchor is active — an anchored
  // corner 1, or the press point mid-drag. Below MIN_BOX_PX it stays hidden so
  // a tiny preview never reads as a committed box.
  const anchor = first ?? pressAt.current;
  const pv = anchor && hover ? span(anchor, hover) : null;
  const preview = pv && pv[2] >= MIN_BOX_PX && pv[3] >= MIN_BOX_PX ? pv : null;
  const box = (r: number[]) => {
    const p = paint();
    if (!p || !p.el.width || !p.el.height) return undefined;
    return {
      left: `${((p.l - p.el.left + r[0] * p.s) / p.el.width) * 100}%`,
      top: `${((p.t - p.el.top + r[1] * p.s) / p.el.height) * 100}%`,
      width: `${(r[2] * p.s / p.el.width) * 100}%`,
      height: `${(r[3] * p.s / p.el.height) * 100}%`,
    };
  };

  return (
    <div className="roi-view">
      <img ref={imgRef} draggable={false}
           src={`/api/v1/devices/camera/stream.mjpg?metric=led_state&component=${encodeURIComponent(cid)}`}
           alt="Live camera — click two corners around the LED" />
      <div className="roi-layer" role="presentation"
           onPointerDown={down} onPointerMove={move} onPointerLeave={leave} onClick={click}>
        {nat && roi && <div className="roi-box roi-current" style={box(roi)} />}
        {nat && others.map((r, i) => <div key={`o${i}`} className="roi-box roi-other" style={box(r)} />)}
        {nat && candidates.map((r, i) => (
          <button key={i} className="roi-box roi-candidate" style={box(r)}
                  aria-label={`Use candidate region ${i + 1}`}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => { e.stopPropagation(); pressAt.current = null; setFirst(null); onPick(r); }} />
        ))}
        {nat && preview && <div className="roi-box roi-drag" style={box(preview)} />}
        {nat && first && <div className="roi-corner" style={box([first[0] - 4, first[1] - 4, 8, 8])} />}
      </div>
      {first && (
        <div className="roi-hint">
          <span>Box 1 placed — click or drag box 2</span>
          <button className="roi-reset" onClick={(e) => { e.stopPropagation(); setFirst(null); setHover(null); }}>
            Reset
          </button>
        </div>
      )}
    </div>
  );
}
