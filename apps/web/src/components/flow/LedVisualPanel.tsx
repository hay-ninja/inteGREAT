import { useEffect, useState } from "react";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Button } from "@astryxdesign/core/Button";
import { Text } from "@astryxdesign/core/Text";
import { Heading } from "@astryxdesign/core/Heading";
import { Card } from "@astryxdesign/core/Card";
import { Selector } from "@astryxdesign/core/Selector";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { api, type GraphSnapshot, type Evidence, type VisualRegion, type VisualReference, type VisualConfig, type VisualRun } from "../../lib/api";
import { EvidenceList } from "./common";

export function LedVisualPanel(p: { projectId: string; graph: GraphSnapshot; onSetup: () => void; onError: (m: string) => void; onEvidence: (e: Evidence) => void }) {
  const leds = p.graph.nodes.filter(n => n.attributes.type === "led");
  const [selected, setSelected] = useState(leds[0]?.id ?? "");
  const [regions, setRegions] = useState<Record<string, VisualRegion>>({});
  const [first, setFirst] = useState<{ x: number; y: number } | null>(null);
  const [refs, setRefs] = useState<Record<string, VisualReference>>({});
  const [config, setConfig] = useState<VisualConfig | null>(null);
  const [runs, setRuns] = useState<VisualRun[]>([]);
  const [busy, setBusy] = useState(false);
  const [snapshot, setSnapshot] = useState(0);
  const [imageSize, setImageSize] = useState({ width: 640, height: 480 });
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const latest = runs.at(-1);
  const active = busy || latest?.state === "running";
  const failed = [...runs].reverse().find(r => r.outcome === "fail" && !r.resolved_by_run_id && r.config_id === config?.id);
  const region = regions[selected];
  useEffect(() => {
    let disposed = false;
    api.visualConfigs(p.projectId).then(c => {
      if (disposed) return;
      const saved = c.at(-1) ?? null;
      setConfig(saved);
      if (saved) {
        setRegions(Object.fromEntries(saved.references.map(r => [r.component_id, r.region])));
        setRefs(Object.fromEntries(saved.references.map(r => [`${r.component_id}:${r.state}`, r])));
      }
    }).catch(e => p.onError(e.message));
    const refresh = () => api.visualRuns(p.projectId).then(r => { if (!disposed) setRuns(r); }).catch(e => { if (!disposed) p.onError(e.message); });
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => { disposed = true; window.clearInterval(timer); };
  }, [p.projectId]);
  useEffect(() => {
    const img = new Image();
    img.onload = () => setImageSize({ width: img.naturalWidth, height: img.naturalHeight });
    img.src = `/api/v1/devices/camera/frame.jpg?raw=true&t=${snapshot}`;
  }, [snapshot]);
  useEffect(() => {
    if (!latest) return;
    // Result, confirmed expectation, and calibration; samples remain linked in the result payload.
    const ids = [...latest.evidence_ids.slice(0, 5), ...latest.evidence_ids.slice(-1)];
    api.evidence(p.projectId, ids).then(setEvidence).catch(() => setEvidence([]));
  }, [latest?.id, latest?.state]);
  const action = async (fn: () => Promise<void>) => { setBusy(true); try { await fn(); } catch (e) { p.onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); } };
  const capture = (state: "off" | "on") => action(async () => {
    if (!region) return;
    const ref = await api.visualCapture(p.projectId, selected, region, state);
    setRefs(prev => ({ ...prev, [`${selected}:${state}`]: ref }));
    setConfig(null);
  });
  const clickRegion = (event: React.MouseEvent<SVGSVGElement>) => {
    if (active) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const point = { x: Math.min(0.999, Math.max(0, (event.clientX - rect.left) / rect.width)), y: Math.min(0.999, Math.max(0, (event.clientY - rect.top) / rect.height)) };
    if (!first) { setFirst(point); return; }
    const next = { x: Math.min(first.x, point.x), y: Math.min(first.y, point.y), width: Math.abs(point.x - first.x), height: Math.abs(point.y - first.y) };
    setFirst(null);
    if (next.width < 0.005 || next.height < 0.005) return p.onError("Select opposite corners of a box around the LED.");
    setRegions(prev => ({ ...prev, [selected]: next }));
    setRefs(prev => Object.fromEntries(Object.entries(prev).filter(([key]) => !key.startsWith(`${selected}:`))));
    setConfig(null);
  };
  return <VStack gap={3}>
    <Heading level={2}>LED visual check</Heading>
    <Text type="supporting">Observe two LEDs fading up/down in turns. No commands are sent, and serial is optional. Use the existing fade sketch and a fixed camera.</Text>
    <Button label="Connect or change camera" onClick={p.onSetup} />
    <Collapsible key={config?.id ?? "draft"} defaultIsOpen={!config} trigger={<Text type="label">{config ? "Edit calibrated LED regions" : "Select and calibrate LED regions"}</Text>}>
    <Card padding={3}><VStack gap={2}>
      <Heading level={3}>1. Select and calibrate each LED</Heading>
      <Text type="supporting">Refresh the image, select an LED, then click two opposite corners of a tight box around it. Keep the board/camera fixed and lighting stable. Moving or covering the LED can look like a fault.</Text>
      <Selector label="LED" value={selected} onChange={v => { setSelected(v); setFirst(null); }} options={leds.map(n => ({ value: n.id, label: n.label }))} />
      <Button label="Refresh camera image" isDisabled={active} onClick={() => setSnapshot(Date.now())} />
      <svg className="led-region-picker" role="img" aria-label="Select LED region by clicking two opposite corners" viewBox={`0 0 ${imageSize.width} ${imageSize.height}`} onClick={clickRegion}>
        <image href={`/api/v1/devices/camera/frame.jpg?raw=true&t=${snapshot}`} width={imageSize.width} height={imageSize.height} />
        {Object.entries(regions).map(([id, r]) => <rect key={id} x={r.x * imageSize.width} y={r.y * imageSize.height} width={r.width * imageSize.width} height={r.height * imageSize.height} className={id === selected ? "selected" : ""} />)}
      </svg>
      <Text type="supporting">{first ? "Now click the opposite corner." : region ? "Region selected. References capture the current live frame, not this frozen image." : "Choose the region on the image."}</Text>
      <HStack gap={2} wrap="wrap">
        <Button label={refs[`${selected}:off`] ? "Recapture dim / off" : "Capture dim / off"} isDisabled={!region || active} clickAction={() => capture("off")} />
        <Button label={refs[`${selected}:on`] ? "Recapture bright / on" : "Capture bright / on"} isDisabled={!region || active} clickAction={() => capture("on")} />
      </HStack>
      <Text type="supporting">Wait for the selected LED to be dim, capture off; wait for it to be bright, capture on. Repeat for the other LED. Establish calibration while both are working before seeding faults.</Text>
      {leds.map(n => <Text key={n.id} type="supporting">{n.label}: {refs[`${n.id}:off`] ? "off captured" : "off needed"} · {refs[`${n.id}:on`] ? "on captured" : "on needed"}</Text>)}
    </VStack></Card></Collapsible>
    <Card padding={3}><VStack gap={2}>
      <Heading level={3}>2. Confirm and observe</Heading>
      <Text type="supporting">Expectation: within 8 seconds both regions reach dim (≤25%) and bright (≥75%) states in separate alternating phases, with at least two samples per state. Camera gaps over 750 ms make the result inconclusive.</Text>
      {!config && <Button label="Confirm this visual expectation" variant="primary" isDisabled={Object.keys(refs).length !== 4 || active} clickAction={() => action(async () => setConfig(await api.visualConfigure(p.projectId, Object.values(refs).map(r => r.id))))} />}
      {config && <Button label={active ? "Observing for 8 seconds…" : "Observe LED fades"} variant="primary" isDisabled={active} clickAction={() => action(async () => { const run = await api.visualStart(p.projectId, config.id); setRuns(prev => [...prev, run]); })} />}
      {failed && config && <Button label="I fixed it — verify with the same check" isDisabled={active} clickAction={() => action(async () => { const run = await api.visualStart(p.projectId, config.id, failed.id); setRuns(prev => [...prev, run]); })} />}
    </VStack></Card>
    {latest && <Card padding={3}><VStack gap={2}>
      <Heading level={3}>{latest.state === "running" ? "Observing" : latest.outcome?.toUpperCase()}</Heading>
      <Text>{latest.summary}</Text>
      <Text type="supporting">{latest.synthetic ? "Synthetic source" : "Live camera"} · {latest.source_id}. Brightness is an image measurement, not voltage or PWM.</Text>
      {Object.entries(latest.checks).map(([id, check]) => <Text key={id} type="supporting">{leds.find(n => n.id === id)?.label ?? id}: {check}</Text>)}
      {latest.verifies_run_id && latest.outcome === "pass" && <Text>Visual failure resolved by this passing verification.</Text>}
      <EvidenceList ids={evidence.map(e => e.id)} evById={new Map(evidence.map(e => [e.id, e]))} onInspect={p.onEvidence} />
      <Text type="supporting">For a failed observation, inspect the source GPIO against the wiring graph, then check LED polarity, resistor/jumpers, camera framing and calibration. The camera cannot identify which caused a dark region.</Text>
    </VStack></Card>}
  </VStack>;
}
