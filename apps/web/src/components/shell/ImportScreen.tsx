/** Projects hub: demos on the left, wordmark + your projects in the middle,
    and a "New project" button that opens the import form in a modal. */
import { useEffect, useRef, useState } from "react";
import { Layout, LayoutContent } from "@astryxdesign/core/Layout";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Banner } from "@astryxdesign/core/Banner";
import { Selector } from "@astryxdesign/core/Selector";
import { Grid } from "@astryxdesign/core/Grid";
import { ClickableCard } from "@astryxdesign/core/ClickableCard";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { api, type DemoFixture, type NetlistPreview, type Project } from "../../lib/api";
import { Eyebrow, HostedDemoBanner } from "../flow/common";

type Mapping = {
  mcu_ref: string;
  components: { ref: string; id: string; type: string; label: string; pins: Record<string, string> }[];
  power_sources: { ref: string; id: string; label: string; terminals: Record<string, string> }[];
  proposed: boolean;
  [k: string]: unknown;
};

export interface ImportArgs {
  repo_path: string;
  manifest_path?: string | null;
  netlist_path?: string | null;
  netlist_mapping?: Record<string, unknown> | null;
}

export function ImportScreen(p: { onImport: (a: ImportArgs) => void; onOpen: (pr: Project) => void; onBack?: () => void; busy: boolean; onError: (m: string) => void }) {
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [demoNetlist, setDemoNetlist] = useState("");
  const [recent, setRecent] = useState<Project[]>([]);
  const [repo, setRepo] = useState("");
  const [manifest, setManifest] = useState("");
  const [netlist, setNetlist] = useState("");
  const [preview, setPreview] = useState<NetlistPreview | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewBusy, setPreviewBusy] = useState(false);
  const [pending, setPending] = useState<null | { title: string; lines: string[]; action: string; onConfirm: () => void }>(null);
  const [importOpen, setImportOpen] = useState(false);
  const previewRequest = useRef(0);

  // Card copy from the fixture label — demo fixtures come from the backend; nothing is hardcoded per index.
  const blurbFor = (label: string): string => {
    const l = label.toLowerCase();
    if (l.includes("wrong pin"))
      return "A light project where the code drives one pin but the wiring notes connect a different one — caught before a test even runs.";
    if (l.includes("active-low"))
      return "The same firmware on an LED wired active-low: commanding it on turns it off. The state changes — just backwards.";
    if (l.includes("correct firmware"))
      return "The board acknowledges the command but the light never changes — is it the signal wire, or power?";
    return "A hardware project with a seeded fault and pretend observations — safe to click through.";
  };

  useEffect(() => {
    api.demo().then((d) => { setFixtures(d.fixtures); setDemoNetlist(d.netlist_path); }).catch(() => undefined);
    // One card per folder — re-importing the same repo updates the entry, not duplicates it.
    api.projects().then((ps) => {
      const byRoot = new Map<string, Project>();
      for (const pr of ps) byRoot.set(pr.repo_root, pr);
      setRecent([...byRoot.values()].slice(-8).reverse());
    }).catch(() => undefined);
  }, []);

  const doPreview = async (nl: string, rp: string) => {
    const request = ++previewRequest.current;
    setPreview(null); setMapping(null); setPreviewError(""); setPreviewBusy(true);
    try {
      const pr = await api.netlistPreview(nl, rp || undefined);
      if (request !== previewRequest.current) return;
      setPreview(pr);
      setMapping(pr.proposed_mapping as unknown as Mapping);
    } catch (e) {
      if (request !== previewRequest.current) setPreviewError((e as Error).message);
    } finally {
      if (request !== previewRequest.current) setPreviewBusy(false);
    }
  };

  return (
    <>
    <Layout contentWidth={1200} content={
      <LayoutContent>
        <VStack paddingBlock={6}>
        <HStack gap={6} vAlign="start" wrap="wrap">
          {/* Left rail — demos, like template shortcuts on a projects page */}
          <VStack gap={3} style={{ width: 300, flexShrink: 0 }}>
            <VStack gap={1}>
              <Eyebrow>Demos</Eyebrow>
              <Heading level={2}>Try it on pretend hardware</Heading>
              <Text type="body" color="secondary">Ready-made failure stories with pretend observations — safe to click through.</Text>
            </VStack>
            {fixtures.map((f) => (
              <ClickableCard key={`${f.repo_path}|${f.manifest_path}`} padding={4} isDisabled={p.busy}
                label={f.label}
                onClick={() => setPending({
                  title: `Demo — ${f.label}`,
                  lines: [blurbFor(f.label),
                    "inteGREAT maps code to wiring, runs a simulated test, and walks you through the failure. Nothing runs on real hardware."],
                  action: "Load demo",
                  onConfirm: () => p.onImport({ repo_path: f.repo_path, manifest_path: f.manifest_path }),
                })}>
                <VStack gap={2}>
                  <Text type="body" weight="semibold">{f.label}</Text>
                  <Text type="supporting" color="secondary">{blurbFor(f.label)}</Text>
                  <Text type="supporting" color="secondary">Simulated · ~5 minutes</Text>
                </VStack>
              </ClickableCard>
            ))}
          </VStack>

          {/* Main — wordmark, create button, project grid */}
          <VStack gap={5} style={{ flex: 1, minWidth: 0 }}>
            <HostedDemoBanner />
            <VStack gap={2}>
              <div className="wordmark"><span className="waccent">inte</span>GREAT</div>
              <Text type="large" color="secondary">
                Why isn't your hardware doing what the code says? Import a project — the map, tests, and evidence live here.
              </Text>
            </VStack>
            <HStack gap={2} vAlign="center" wrap="wrap">
              <Button label="+ New project" variant="primary" onClick={() => setImportOpen(true)} />
              {p.onBack && <Button label="What is inteGREAT?" variant="ghost" onClick={p.onBack} />}
            </HStack>
            <VStack gap={3}>
              <Eyebrow>Your projects</Eyebrow>
              {recent.length ? (
                <Grid columns={{ minWidth: 240, repeat: "fill" }} gap={3}>
                  {recent.map((r) => (
                    <ClickableCard key={r.id} padding={4} isDisabled={p.busy} label={r.name}
                      onClick={() => setPending({
                        title: r.name,
                        lines: [r.repo_root,
                          `Graph version ${r.graph_version}. Reopens the workspace where you left it — map, test runs, and investigation state included.`],
                        action: "Open project",
                        onConfirm: () => p.onOpen(r),
                      })}>
                      <VStack gap={2}>
                        <Text type="body" weight="semibold">{r.name}</Text>
                        <Text type="supporting" color="secondary" style={{ wordBreak: "break-all" }}>{r.repo_root}</Text>
                        <Text type="supporting" color="secondary">Graph v{r.graph_version}</Text>
                      </VStack>
                    </ClickableCard>
                  ))}
                </Grid>
              ) : (
                <Card variant="muted" padding={5}>
                  <Text type="body" color="secondary">No projects on this computer yet — import one and it shows up here.</Text>
                </Card>
              )}
            </VStack>
          </VStack>
        </HStack>
        </VStack>
      </LayoutContent>
    } />

    {/* Import modal — the form only lives here, the page stays a projects hub */}
    <Dialog isOpen={importOpen} onOpenChange={setImportOpen} width={640} purpose="form">
      <DialogHeader title="New project" subtitle="Point inteGREAT at your code — nothing is run or changed on import"
                    onOpenChange={setImportOpen} />
      <VStack gap={3} padding={4}>
        <TextInput label="Your code folder (Software)" value={repo} onChange={(v) => {
          setRepo(v); ++previewRequest.current; setPreview(null); setMapping(null); setPreviewError(""); setPreviewBusy(false);
        }} placeholder="C:\path\to\sketch" description="The folder with your Arduino / ESP32 code (.ino, .cpp)." />
        <TextInput label="Wiring notes file (Component definitions · YAML)" isOptional value={manifest} onChange={setManifest}
                   description="A small file describing what is plugged into which pin. Also used as a fallback if the netlist can't be read." />
        <TextInput label="KiCad netlist (Hardware CAD · XML)" isOptional value={netlist} width="100%" description="If you drew the circuit in KiCad, inteGREAT reads the real connections from it."
                   onChange={(v) => { setNetlist(v); ++previewRequest.current; setPreview(null); setMapping(null); setPreviewError(""); setPreviewBusy(false); }} />
        <HStack gap={2} wrap="wrap">
          <Button label="Read netlist" isDisabled={!netlist.trim() || p.busy} isLoading={previewBusy} onClick={() => doPreview(netlist, repo)} />
          {fixtures[0] && demoNetlist && !netlist && (
            <Button label="Use the demo netlist" variant="ghost" size="sm" onClick={() => {
              setRepo(fixtures[0].repo_path); setManifest(fixtures[0].manifest_path); setNetlist(demoNetlist);
              doPreview(demoNetlist, fixtures[0].repo_path);
            }} />
          )}
        </HStack>
        {preview && mapping && <MappingReview preview={preview} mapping={mapping} onChange={setMapping} />}
        {previewError && <Banner status="warning" collapsible={false} title="The netlist could not be read"
                                description={`${previewError}${manifest.trim() ? " Import can continue using the hardware manifest." : " Add a manifest as a fallback, or remove the netlist path."}`} />}
        <Button label={previewError && manifest.trim() ? "Import with manifest fallback" : netlist ? "Confirm mapping and import" : "Import project"} variant="primary" isLoading={p.busy}
                isDisabled={!repo.trim() || previewBusy || (!!netlist.trim() && !mapping && !(previewError && manifest.trim()))}
                onClick={() => { setImportOpen(false); p.onImport({ repo_path: repo, manifest_path: manifest || null, netlist_path: netlist || null,
                                                    netlist_mapping: mapping ? { ...mapping, proposed: false } : null }); }} />
      </VStack>
    </Dialog>

    <Dialog isOpen={!!pending} onOpenChange={(o) => !o && setPending(null)} width={440} purpose="form">
      <DialogHeader title={pending?.title ?? ""} subtitle="What happens when you open it"
                    onOpenChange={(o) => !o && setPending(null)} />
      <VStack gap={3} padding={4}>
        {pending?.lines.map((l) => <Text key={l} type="body" color="secondary">{l}</Text>)}
        <HStack gap={2} hAlign="end">
          <Button label="Back" variant="ghost" onClick={() => setPending(null)} />
          <Button label={pending?.action ?? "Open"} variant="primary"
                  onClick={() => { const go = pending?.onConfirm; setPending(null); go?.(); }} />
        </HStack>
      </VStack>
    </Dialog>
    </>
  );
}

function MappingReview({ preview, mapping, onChange }: { preview: NetlistPreview; mapping: Mapping; onChange: (m: Mapping) => void }) {
  const setComp = (i: number, patch: Partial<Mapping["components"][number]>) =>
    onChange({ ...mapping, components: mapping.components.map((c, k) => (k === i ? { ...c, ...patch } : c)) });
  return (
    <VStack gap={2}>
      <Banner status="warning" collapsible={false} title="Check what each part is"
              description="Guessed from net names and part values. Schematic wiring stays 'unchecked' until you confirm it on the bench." />
      <Text type="supporting">{preview.file}: {preview.components.length} parts, {preview.nets.length} nets · MCU {mapping.mcu_ref}</Text>
      {mapping.components.map((c, i) => (
        <HStack key={c.ref} gap={2} vAlign="end" wrap="wrap">
          <Text type="code">{c.ref}</Text>
          <Selector label="Type" size="sm" width={120} value={c.type} onChange={(v) => setComp(i, { type: v })}
                    options={["servo", "led", "other"].map((t) => ({ value: t, label: t }))} />
          {Object.entries(c.pins).map(([pin, role]) => (
            <TextInput key={pin} label={`Pin ${pin}`} size="sm" width={110} value={role}
                       onChange={(v) => setComp(i, { pins: { ...c.pins, [pin]: v } })} />
          ))}
        </HStack>
      ))}
      {mapping.power_sources.map((ps) => (
        <Text key={ps.ref} type="supporting">{ps.ref}: power supply ({Object.entries(ps.terminals).map(([k, v]) => `${k}=${v}`).join(", ")})</Text>
      ))}
      {preview.warnings.map((w) => <Text key={w} type="supporting">⚠ {w}</Text>)}
    </VStack>
  );
}
