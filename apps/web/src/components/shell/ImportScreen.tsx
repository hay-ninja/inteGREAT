/** Start screen: reopen a recent project, try a demo, or import your own — in that order. */
import { useEffect, useState } from "react";
import { Layout, LayoutContent } from "@astryxdesign/core/Layout";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { ClickableCard } from "@astryxdesign/core/ClickableCard";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Banner } from "@astryxdesign/core/Banner";
import { Selector } from "@astryxdesign/core/Selector";
import { List, ListItem } from "@astryxdesign/core/List";
import { Badge } from "@astryxdesign/core/Badge";
import { api, type DemoFixture, type NetlistPreview, type Project } from "../../lib/api";

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

export function ImportScreen(p: { onImport: (a: ImportArgs) => void; onOpen: (pr: Project) => void; busy: boolean; onError: (m: string) => void }) {
  const [fixtures, setFixtures] = useState<DemoFixture[]>([]);
  const [demoNetlist, setDemoNetlist] = useState("");
  const [recent, setRecent] = useState<Project[]>([]);
  const [repo, setRepo] = useState("");
  const [manifest, setManifest] = useState("");
  const [netlist, setNetlist] = useState("");
  const [preview, setPreview] = useState<NetlistPreview | null>(null);
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [customOpen, setCustomOpen] = useState(false);

  useEffect(() => {
    api.demo().then((d) => { setFixtures(d.fixtures); setDemoNetlist(d.netlist_path); }).catch(() => undefined);
    api.projects().then((ps) => setRecent(ps.slice(-4).reverse())).catch(() => undefined);
  }, []);

  const doPreview = async (nl: string, rp: string) => {
    try {
      const pr = await api.netlistPreview(nl, rp || undefined);
      setPreview(pr);
      setMapping(pr.proposed_mapping as unknown as Mapping);
    } catch (e) {
      p.onError((e as Error).message);
    }
  };

  return (
    <Layout contentWidth={640} content={
      <LayoutContent>
        <VStack gap={5} paddingBlock={8}>
          <VStack gap={1}>
            <Heading level={1}>inteGREAT</Heading>
            <Text type="body" color="secondary">
              Find why your hardware isn't doing what the code says. Import an ESP32 project — nothing is run or changed.
            </Text>
          </VStack>

          {recent.length > 0 && (
            <List header={<Text type="label" color="secondary">Recent</Text>} hasDividers>
              {recent.map((r) => (
                <ListItem key={r.id} label={r.name} description={r.repo_root} onClick={() => p.onOpen(r)}
                          endContent={<Badge label={`v${r.graph_version}`} />} />
              ))}
            </List>
          )}

          <VStack gap={2}>
            <Text type="label" color="secondary">Try a demo</Text>
            {fixtures.map((f, i) => (
              <ClickableCard key={f.repo_path} label={f.label} padding={3} isDisabled={p.busy}
                             onClick={() => p.onImport({ repo_path: f.repo_path, manifest_path: f.manifest_path })}>
                <VStack gap={0.5}>
                  <Text type="body" weight="semibold">{i === 0 ? "Wrong pin in the code" : "Servo comes unplugged"}</Text>
                  <Text type="supporting">{f.label}</Text>
                </VStack>
              </ClickableCard>
            ))}
          </VStack>

          <Collapsible isOpen={customOpen || !!preview} onOpenChange={setCustomOpen}
                       trigger={<Text type="label">Import your own project</Text>}>
            <VStack gap={3}>
              <TextInput label="Firmware folder" value={repo} onChange={setRepo} placeholder="C:\path\to\sketch" />
              <TextInput label="Hardware manifest (YAML)" isOptional value={manifest} onChange={setManifest}
                         description="Used directly, or as a fallback if the netlist can't be read." />
              <HStack gap={1} vAlign="end">
                <TextInput label="KiCad netlist (XML)" isOptional value={netlist} width="100%"
                           onChange={(v) => { setNetlist(v); setPreview(null); setMapping(null); }} />
                <Button label="Read netlist" isDisabled={!netlist} onClick={() => doPreview(netlist, repo)} />
              </HStack>
              {fixtures[0] && demoNetlist && !netlist && (
                <Button label="Use the demo netlist" variant="ghost" size="sm" onClick={() => {
                  setRepo(fixtures[0].repo_path); setManifest(fixtures[0].manifest_path); setNetlist(demoNetlist);
                  setCustomOpen(true); doPreview(demoNetlist, fixtures[0].repo_path);
                }} />
              )}
              {preview && mapping && <MappingReview preview={preview} mapping={mapping} onChange={setMapping} />}
              <Button label={netlist ? "Confirm and import" : "Import"} variant="primary" isLoading={p.busy}
                      isDisabled={!repo || (!!netlist && !mapping)}
                      onClick={() => p.onImport({ repo_path: repo, manifest_path: manifest || null, netlist_path: netlist || null,
                                                  netlist_mapping: mapping ? { ...mapping, proposed: false } : null })} />
            </VStack>
          </Collapsible>
        </VStack>
      </LayoutContent>
    } />
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
