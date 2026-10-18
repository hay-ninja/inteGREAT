/** Collapsible bottom drawer: measurements and logs live here, out of the way until needed.
 *  Height drags like a VS Code panel (drag the top edge; drag down past the header to close),
 *  and a second pane can be split off beside the first — e.g. camera output next to activity. */
import { useEffect, useState } from "react";
import { HStack } from "@astryxdesign/core/HStack";
import { VStack } from "@astryxdesign/core/VStack";
import { TabList, Tab } from "@astryxdesign/core/TabList";
import { Button } from "@astryxdesign/core/Button";
import { IconButton } from "@astryxdesign/core/IconButton";
import { ChevronDown, ChevronUp, SquareSplitHorizontal, X } from "lucide-react";
import { useResizable, ResizeHandle } from "@astryxdesign/core/Resizable";
import { Text } from "@astryxdesign/core/Text";
import { Table, pixel } from "@astryxdesign/core/Table";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Card } from "@astryxdesign/core/Card";
import {
  api,
  type DeviceStatus,
  type IntegreatEvent,
  type SerialEvent,
  type TestRun,
  type ToolCall,
} from "../../lib/api";
import { Eyebrow, SourceBadge } from "../flow/common";

export type DrawerTab = "serial" | "devices" | "activity" | "camera";

const TAB_LABEL: Record<DrawerTab, string> = {
  serial: "Serial output",
  devices: "Devices",
  activity: "Activity",
  camera: "Camera",
};

interface Props {
  open: boolean;
  onOpen: (o: boolean) => void;
  tab: DrawerTab;
  onTab: (t: DrawerTab) => void;
  run: TestRun | null;
  serial: SerialEvent[];
  events: IntegreatEvent[];
  toolCalls: ToolCall[];
  devices: DeviceStatus | null;
  onEnvSetup: () => void;
  onSaveReplay: (runId: string) => void;
  onError: (m: string) => void;
}

function DrawerTabs({ value, onChange }: { value: DrawerTab; onChange: (t: DrawerTab) => void }) {
  return (
    <TabList value={value} size="sm" onChange={(t) => onChange(t as DrawerTab)}>
      {(Object.keys(TAB_LABEL) as DrawerTab[]).map((t) => <Tab key={t} value={t} label={TAB_LABEL[t]} />)}
    </TabList>
  );
}

/** One tab's content — shared by the single view, the left pane, and the split pane. */
function PaneContent({ tab, p }: { tab: DrawerTab; p: Props }) {
  if (tab === "serial") return <SerialLog serial={p.serial} />;
  if (tab === "devices") return <DeviceSummary status={p.devices} onOpenSetup={p.onEnvSetup} />;
  if (tab === "camera") return <CameraPane devices={p.devices} onOpenSetup={p.onEnvSetup} />;
  return (
    <VStack gap={3}>
      <VStack gap={1}>
        <Eyebrow>Investigation events</Eyebrow>
        <Timeline events={p.events} />
      </VStack>
      <VStack gap={1}>
        <Eyebrow>Tool audit — every run, approval, and denial</Eyebrow>
        <Audit calls={p.toolCalls} />
      </VStack>
    </VStack>
  );
}

export function BottomDrawer(p: Props) {
  // Vertical: the whole drawer height. Collapsible — drag the top edge down past the
  // header threshold to close, and clicking a tab re-opens it (open state stays in App).
  const drawer = useResizable({
    direction: "vertical", defaultSize: 260, minSize: 140, maxSize: "70%",
    collapsible: true, collapsedSize: 44, autoSaveId: "integreat.drawer",
    isCollapsed: !p.open, onCollapseChange: (c) => p.onOpen(!c),
  });
  // Right pane of the split. Collapsible — dragging the divider to the right edge
  // closes the split, like dragging a terminal split back together in VS Code.
  const [split, setSplit] = useState(false);
  const [rightTab, setRightTab] = useState<DrawerTab>("activity");
  const pane = useResizable({
    direction: "horizontal", defaultSize: "45%", minSize: 280, maxSize: "70%",
    collapsible: true, collapsedSize: 100, autoSaveId: "integreat.drawer.split",
    isCollapsed: !split, onCollapseChange: (c) => setSplit(!c),
  });
  const openSplit = () => {
    setRightTab((t) => (t === p.tab ? (p.tab === "camera" ? "activity" : "camera") : t));
    setSplit(true);
    p.onOpen(true);
  };
  return (
    <VStack gap={0} height={p.open ? drawer.size : undefined}>
      <ResizeHandle direction="vertical" isReversed hasDivider resizable={drawer.props} label="Resize logs panel" />
      {/* The handle's invisible hitbox extends ~15px below its 1px line — this grip zone
          absorbs it so tabs and buttons stay fully clickable (VS Code sash behaviour). */}
      <div aria-hidden style={{ height: 16 }} />
      <HStack hAlign="between" vAlign="center" gap={2} paddingInline={2} wrap="wrap">
        <DrawerTabs value={p.tab} onChange={(t) => { p.onTab(t); p.onOpen(true); }} />
        <HStack gap={1} vAlign="center">
          {p.run && <SourceBadge run={p.run} />}
          {p.run?.state === "completed" && p.run.source.kind !== "replay" && (
            <Button label="Save as replay" size="sm" variant="ghost" tooltip="Keep this run for offline demos"
                    onClick={() => p.onSaveReplay(p.run!.id)} />
          )}
          <IconButton label={split ? "Close split view" : "Split into two panes"} size="sm" variant="ghost"
                      tooltip={split ? "Back to one pane" : "Show two panels side by side — e.g. camera next to activity"}
                      icon={<SquareSplitHorizontal size={14} />} onClick={() => (split ? setSplit(false) : openSplit())} />
          <IconButton label={p.open ? "Collapse panel" : "Expand panel"} size="sm" variant="ghost"
                      tooltip={p.open ? "Collapse to the tab row" : "Expand the panel"}
                      icon={p.open ? <ChevronDown size={15} /> : <ChevronUp size={15} />}
                      onClick={() => p.onOpen(!p.open)} />
        </HStack>
      </HStack>
      {p.open && !split && (
        <VStack gap={0} isScrollable height="100%" paddingInline={3} paddingBlock={2}>
          <PaneContent tab={p.tab} p={p} />
        </VStack>
      )}
      {p.open && split && (
        <HStack gap={0} height="100%" vAlign="stretch">
          <VStack gap={0} isScrollable height="100%" paddingInline={3} paddingBlock={2} style={{ flex: 1, minWidth: 0 }}>
            <PaneContent tab={p.tab} p={p} />
          </VStack>
          <ResizeHandle direction="horizontal" isReversed hasDivider resizable={pane.props} label="Resize split pane" />
          <VStack gap={1} height="100%" paddingInline={3} paddingBlock={1} style={{ width: pane.size, minWidth: 0, flexShrink: 0 }}>
            <HStack hAlign="between" vAlign="center">
              <DrawerTabs value={rightTab} onChange={setRightTab} />
              <IconButton label="Close split view" size="sm" variant="ghost" icon={<X size={13} />} onClick={() => setSplit(false)} />
            </HStack>
            <VStack gap={0} isScrollable height="100%" paddingBlock={1}>
              <PaneContent tab={rightTab} p={p} />
            </VStack>
          </VStack>
        </HStack>
      )}
    </VStack>
  );
}

/** Raw camera feed for orientation during a test. Measurements still come from the
    estimator — this picture is never itself evidence. */
function CameraPane({ devices, onOpenSetup }: { devices: DeviceStatus | null; onOpenSetup: () => void }) {
  const c = devices?.camera;
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [c?.connected, c?.source_id]);
  if (!c?.connected) {
    return (
      <VStack gap={2}>
        <EmptyState isCompact title="No camera connected"
                    description="Connect a camera in environment setup to watch the live environment during a test." />
        <Button label="Open environment setup" size="sm" onClick={onOpenSetup} />
      </VStack>
    );
  }
  if (failed) {
    return <EmptyState isCompact title="Camera feed unavailable"
                       description="The camera is connected but the stream didn't answer — reconnect it in environment setup." />;
  }
  return (
    <VStack gap={1} height="100%">
      <Text type="supporting">
        {c.source_id}{c.calibrated ? " · calibrated" : " · needs calibration"} — raw view; measurements come from the estimator, not this picture.
      </Text>
      <img className="drawer-camera" src="/api/v1/devices/camera/stream.mjpg"
           alt="Live camera view of the test environment" onError={() => setFailed(true)} />
    </VStack>
  );
}

interface Row extends Record<string, unknown> { id: string; t: string; dir: string; raw: string; note: string }

function SerialLog({ serial }: { serial: SerialEvent[] }) {
  if (!serial.length) return <EmptyState isCompact title="No messages yet" description="Everything sent to and heard back from the board during a test appears here." />;
  const rows: Row[] = serial.map((s) => ({
    id: s.id, t: `${s.elapsed_ms} ms`, dir: s.direction === "tx" ? "→ board" : "← board", raw: s.raw,
    note: s.matched_function_ids.length ? `printed by ${s.matched_function_ids.map((f) => f.split("::")[1]).join(", ")}()` : "",
  }));
  return (
    <Table<Row> data={rows} idKey="id" density="compact" textOverflow="truncate"
               columns={[{ key: "t", header: "Time", width: pixel(80) }, { key: "dir", header: "Direction", width: pixel(80) },
                         { key: "raw", header: "Message" }, { key: "note", header: "From code" }]} />
  );
}

const SHOWN = new Set(["project.imported", "graph.updated", "expectation.confirmed", "test.started", "test.completed",
  "expectation.failed", "incident.created", "action.completed", "action.denied", "permissions.updated",
  "agent.started", "agent.reported", "message.added", "test.verification_completed", "incident.resolved", "error"]);

function Timeline({ events }: { events: IntegreatEvent[] }) {
  const shown = events.filter((e) => SHOWN.has(e.type)).slice().reverse();
  if (!shown.length) return <EmptyState isCompact title="Nothing yet" />;
  interface TRow extends Record<string, unknown> { id: string; t: string; type: string; what: string }
  const rows: TRow[] = shown.map((e) => ({ id: String(e.seq), t: new Date(e.timestamp_utc).toLocaleTimeString(),
                                            type: e.type.replace(".", " "), what: summarize(e) }));
  return (
    <Table<TRow> data={rows} idKey="id" density="compact" textOverflow="truncate"
                 columns={[{ key: "t", header: "Time", width: pixel(90) }, { key: "type", header: "Event", width: pixel(170) },
                           { key: "what", header: "" }]} />
  );
}

function summarize(e: IntegreatEvent): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "expectation.failed": return String(p.reason ?? "");
    case "incident.created": return String(p.title ?? "");
    case "test.completed": { const r = p.result as { outcome?: string } | null; return `${p.attempt_kind} run → ${r?.outcome ?? p.state}`; }
    case "test.verification_completed": return `verification ${p.outcome}`;
    case "action.completed": return String(p.summary ?? p.result ?? "");
    case "action.denied": return String(p.reason ?? "");
    case "permissions.updated": return `${p.category} ${p.granted ? "allowed" : "revoked"}`;
    case "agent.started": return `round ${p.round}: ${(p.agents as string[] | undefined)?.join(", ")}`;
    case "agent.reported": return `${p.agent}: ${p.status}`;
    case "graph.updated": return `graph v${p.version}`;
    case "message.added": return String(p.text ?? "");
    case "error": return String(p.message ?? "");
    default: return "";
  }
}

function Audit({ calls }: { calls: ToolCall[] }) {
  if (!calls.length) return <EmptyState isCompact title="No tool calls yet" description="Every tool run, approval and denial is listed here." />;
  interface ARow extends Record<string, unknown> { id: string; t: string; tool: string; who: string; decision: string; what: string }
  const rows: ARow[] = [...calls].reverse().map((c) => ({ id: c.id, t: new Date(c.started_at_utc).toLocaleTimeString(),
    tool: c.tool_name, who: c.caller, decision: c.decision.replace("_", " "), what: c.error ?? c.summary }));
  return (
    <Table<ARow> data={rows} idKey="id" density="compact" textOverflow="truncate"
                 columns={[{ key: "t", header: "Time", width: pixel(90) }, { key: "tool", header: "Tool", width: pixel(170) },
                           { key: "who", header: "By", width: pixel(120) }, { key: "decision", header: "Decision", width: pixel(120) },
                           { key: "what", header: "Result" }]} />
  );
}

/** Status-only view — actual connect/calibrate actions live in the single environment setup dialog. */
function DeviceSummary({ status, onOpenSetup }: { status: DeviceStatus | null; onOpenSetup: () => void }) {
  const s = status?.serial, c = status?.camera;
  return (
    <HStack gap={4} vAlign="center" wrap="wrap">
      <HStack gap={1.5} vAlign="center">
        <StatusDot variant={s?.connected ? "success" : "neutral"} label="ESP32 serial" />
        <Text type="body">Controller board</Text>
        <Text type="supporting">{s?.connected ? `${s.port} · ${s.baud}` : "not connected"}</Text>
      </HStack>
      <HStack gap={1.5} vAlign="center">
        <StatusDot variant={c?.connected ? (c.calibrated ? "success" : "warning") : "neutral"} label="Camera" />
        <Text type="body">Camera</Text>
        <Text type="supporting">
          {c?.connected ? `${c.source_id} · ${c.calibrated ? "calibrated" : "needs calibration"}` : "not connected"}
        </Text>
      </HStack>
      <Button label="Open environment setup" size="sm" onClick={onOpenSetup} />
    </HStack>
  );
}

export function DeviceControls({ status, onStatus, onError }: { status: DeviceStatus | null; onStatus: (s: DeviceStatus) => void; onError: (m: string) => void }) {
  const [port, setPort] = useState("");
  const [cams, setCams] = useState<number[] | null>(null);
  const [cam, setCam] = useState("0");
  const [cameraKind, setCameraKind] = useState("local");
  const [phoneUrl, setPhoneUrl] = useState("");
  const [pairing, setPairing] = useState<string | null>(null);
  useEffect(() => {
    if (!pairing) return;
    const timer = window.setInterval(() => api.devices().then(onStatus).catch((e) => onError(e.message)), 2000);
    return () => window.clearInterval(timer);
  }, [pairing, onStatus, onError]);
  useEffect(() => { if (!port && status?.serial.ports.length) setPort(status.serial.ports[0].port); }, [status, port]);
  if (!status) return <EmptyState isCompact title="Loading devices…" />;
  const run = (p: Promise<DeviceStatus>) => p.then(onStatus).catch((e) => onError(e.message));
  const s = status.serial, c = status.camera;
  return (
    <HStack gap={4} vAlign="start" wrap="wrap">
      <Card padding={3} width={340}>
        <VStack gap={2}>
          <HStack gap={1} vAlign="center">
            <StatusDot variant={s.connected ? "success" : "neutral"} label={s.connected ? "connected" : "not connected"} />
            <Text type="label">Controller board (ESP32)</Text>
            <Text type="supporting">{s.connected ? `${s.port} · ${s.baud}` : "not connected"}</Text>
          </HStack>
          {s.connected ? (
            <Button label="Release port" tooltip="Free the port so the Arduino IDE can flash" clickAction={() => run(api.serialRelease())} />
          ) : (
            <HStack gap={1} vAlign="end">
              <Selector label="Port" size="sm" value={port} onChange={setPort} width={220} placeholder="No ports found"
                        options={s.ports.map((x) => ({ value: x.port, label: x.port, description: x.description }))} />
              <Button label="Connect ESP32" size="sm" isDisabled={!port} clickAction={() => run(api.serialConnect(port))} />
            </HStack>
          )}
          {s.last_error && <Text type="supporting" color="secondary">{s.last_error}</Text>}
          <Text type="supporting">The board runs your code. Only one program can hold the cable at a time — release the port before flashing new firmware.</Text>
        </VStack>
      </Card>
      <Card padding={3} width={380}>
        <VStack gap={2}>
          <HStack gap={1} vAlign="center">
            <StatusDot variant={c.connected ? (c.calibrated ? "success" : "warning") : "neutral"} label="camera" />
            <Text type="label">Camera</Text>
            <Text type="supporting">
              {c.connected ? `${c.source_id} · ${c.fps} fps · ${c.calibrated ? "calibrated" : "needs calibration"}` : "not connected"}
            </Text>
          </HStack>
          {!c.connected ? (
            <VStack gap={2}>
            <Selector label="Camera source" value={cameraKind} onChange={setCameraKind}
              options={[{ value: "local", label: "USB / laptop webcam" }, { value: "browser", label: "iPhone / Safari (no app)" }, { value: "phone", label: "MJPEG camera app" }]} />
            {cameraKind === "browser" ? (
              <VStack gap={2}>
                <Text type="supporting">Start the local HTTPS phone server first (docs/phone-camera.md). Connect both devices to the same trusted Wi-Fi and trust the demo certificate on your iPhone.</Text>
                <Button label={pairing ? "Create replacement pairing link" : "Pair iPhone camera"} clickAction={() => api.cameraPairBrowser().then((p) => setPairing(p.url)).catch((e) => onError(e.message))} />
                {pairing && <>
                  <TextInput label="Open this link in iPhone Safari" value={pairing} onChange={() => undefined} />
                  <Button label="Copy pairing link" clickAction={() => navigator.clipboard.writeText(pairing).catch(() => onError("Select and copy the pairing link manually."))} />
                  <Text type="supporting">Tap Start camera on your phone. Waiting for frames; this link expires in two hours. Keep it private.</Text>
                  <Button label="Cancel pairing" variant="ghost" clickAction={() => run(api.cameraRelease()).then(() => setPairing(null))} />
                </>}
              </VStack>
            ) : cameraKind === "phone" ? (
              <VStack gap={2}>
                <Text type="supporting">Run an HTTP MJPEG camera app on your phone. Connect both devices to the same trusted Wi-Fi and paste its video stream URL, not its web page. Use 640×480 or 1280×720. Keep the app open.</Text>
                <TextInput label="Phone MJPEG URL" value={phoneUrl} onChange={setPhoneUrl} placeholder="http://192.168.1.42:8080/video" />
                <Button label="Connect phone camera" isDisabled={!phoneUrl.trim()} clickAction={() => run(api.cameraConnectPhone(phoneUrl.trim()))} />
              </VStack>
            ) : cams === null ? (
              <Button label="Find cameras" clickAction={() => api.cameraProbe().then((x) => { setCams(x); if (x.length) setCam(String(x[0])); }).catch((e) => onError(e.message))} />
            ) : (
              <HStack gap={1} vAlign="end">
                <Selector label="Camera" size="sm" value={cam} onChange={setCam} width={160} placeholder="None found"
                          options={cams.map((i) => ({ value: String(i), label: `Camera ${i}` }))} />
                <Button label="Connect camera" size="sm" isDisabled={!cams.length} clickAction={() => run(api.cameraConnect(+cam))} />
              </HStack>
            )}
            </VStack>
          ) : (
            <Button label="Release" size="sm" variant="ghost" clickAction={() => run(api.cameraRelease()).then(() => setPairing(null))} />
          )}
          {c.last_error && <Text type="supporting" color="secondary">{c.last_error}</Text>}
          <Text type="supporting">Keep the printed markers in view — an unseen marker reports "measurement unavailable", never a fault.</Text>
        </VStack>
      </Card>
      {c.connected && <img className="camera-preview" src="/api/v1/devices/camera/stream.mjpg" alt="Live camera preview" />}
    </HStack>
  );
}

