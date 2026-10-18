/** Edit a project after import: name, engineer context notes (fed to AI review),
    file pointers (changing one rebuilds the graph), subsystem display names,
    and the danger-zone delete. Hosted demo calls this out as local-only. */
import { useState } from "react";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { VStack } from "@astryxdesign/core/VStack";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { Button } from "@astryxdesign/core/Button";
import { TextInput } from "@astryxdesign/core/TextInput";
import { TextArea } from "@astryxdesign/core/TextArea";
import { Banner } from "@astryxdesign/core/Banner";
import { api, isHostedDemo, type Project, type ProjectUpdate, type Subsystem } from "../../lib/api";
import { Eyebrow } from "../flow/common";

export function ProjectSettingsDialog({ project, subsystems, onClose, onSaved, onDeleted }: {
  project: Project;
  subsystems: Subsystem[];
  onClose: () => void;
  onSaved: (p: Project) => void;
  onDeleted: () => void;
}) {
  const [name, setName] = useState(project.name);
  const [context, setContext] = useState(project.context ?? "");
  const [repo, setRepo] = useState(project.repo_root);
  const [manifest, setManifest] = useState(project.manifest_path ?? "");
  const [netlist, setNetlist] = useState(project.netlist_path ?? "");
  const [names, setNames] = useState<Record<string, string>>(() =>
    Object.fromEntries(subsystems.map((s) => [s.id, s.label])));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const hosted = isHostedDemo();

  const filesChanged =
    repo.trim() !== project.repo_root ||
    (manifest.trim() || null) !== (project.manifest_path ?? null) ||
    (netlist.trim() || null) !== (project.netlist_path ?? null);

  // Send only fields that differ from the displayed label; "" asks the backend to restore the original.
  const renamed = Object.fromEntries(
    subsystems.map((s) => [s.id, names[s.id]?.trim() ?? ""]).filter(([id, v]) => v !== sOriginal(id)),
  );
  function sOriginal(id: string) { return subsystems.find((s) => s.id === id)?.label ?? ""; }

  const dirty =
    name.trim() !== project.name ||
    context !== (project.context ?? "") ||
    Object.keys(renamed).length > 0 ||
    filesChanged;

  const save = async () => {
    setBusy(true); setError("");
    try {
      const body: ProjectUpdate = {};
      if (name.trim() !== project.name) body.name = name.trim();
      if (context !== (project.context ?? "")) body.context = context;
      if (Object.keys(renamed).length) body.subsystem_names = renamed;
      if (filesChanged) {
        body.repo_path = repo.trim();
        body.manifest_path = manifest.trim() || "";
        body.netlist_path = netlist.trim() || "";
      }
      const updated = await api.updateProject(project.id, body);
      onSaved(updated);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const del = async () => {
    setBusy(true); setError("");
    try {
      await api.deleteProject(project.id);
      onDeleted();
      onClose();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <Dialog isOpen onOpenChange={(o) => !o && onClose()} width={640} purpose="form">
      <DialogHeader title="Project settings" subtitle={`Graph v${project.graph_version} · ${project.file_count} files`}
                    onOpenChange={(o) => !o && onClose()} />
      <VStack gap={4} padding={4} minHeight={0} isScrollable>
        {hosted && (
          <Banner status="warning" collapsible={false} title="Hosted demo"
                  description="This site replays a recorded session — changes can't be saved. Run inteGREAT locally to edit projects." />
        )}

        <VStack gap={3}>
          <Eyebrow>Project</Eyebrow>
          <TextInput label="Name" value={name} onChange={setName} />
          <TextArea label="Context for debugging" isOptional value={context} onChange={setContext} rows={4}
                    description="Notes about the rig, known quirks, or what you're testing. Shown to AI review and included in repair briefs as engineer notes — never treated as a measurement." />
        </VStack>

        <VStack gap={3}>
          <Eyebrow>Files</Eyebrow>
          <Text type="supporting" color="secondary">
            Changing a path rebuilds the map from the new files — the project, runs, and wiring confirmations stay.
          </Text>
          <TextInput label="Code folder (Software)" value={repo} onChange={setRepo} />
          <TextInput label="Wiring notes file (Component definitions · YAML)" isOptional value={manifest} onChange={setManifest} />
          <TextInput label="KiCad netlist (Hardware CAD · XML)" isOptional value={netlist} onChange={setNetlist} />
          {filesChanged && (
            <Banner status="info" collapsible={false} title="Saving will rebuild the dependency map"
                    description={`The graph goes to v${project.graph_version + 1}. Incidents and run history are kept.`} />
          )}
        </VStack>

        {subsystems.length > 0 && (
          <VStack gap={3}>
            <Eyebrow>Subsystems</Eyebrow>
            <Text type="supporting" color="secondary">Rename how each subsystem shows up in the map and menus.</Text>
            {subsystems.map((s) => (
              <TextInput key={s.id} label={`"${s.label}" shows as`} value={names[s.id] ?? s.label}
                         onChange={(v) => setNames((m) => ({ ...m, [s.id]: v }))}
                         description={project.subsystem_names?.[s.id]
                           ? "Custom name — clear the field to restore the default." : undefined} />
            ))}
          </VStack>
        )}

        {error && <Banner status="error" collapsible={false} title="Couldn't save" description={error} />}

        <HStack gap={2} hAlign="end">
          <Button label="Cancel" variant="ghost" onClick={onClose} />
          <Button label={filesChanged ? "Save & rebuild map" : "Save"} variant="primary"
                  isLoading={busy} isDisabled={!dirty || !name.trim() || hosted} onClick={save} />
        </HStack>

        <VStack gap={2} className="danger-zone">
          <Eyebrow>Danger zone</Eyebrow>
          {confirmDelete ? (
            <Banner status="error" collapsible={false} title={`Delete "${project.name}"?`}
                    description="The project, its map, runs, investigations and event history are removed from this computer. Your code folder is not touched."
                    endContent={<HStack gap={2}>
                      <Button label="Keep it" size="sm" onClick={() => setConfirmDelete(false)} />
                      <Button label="Delete project" variant="primary" size="sm" isLoading={busy} isDisabled={hosted}
                              onClick={del} />
                    </HStack>} />
          ) : (
            <Button label="Delete this project…" variant="ghost" isDisabled={hosted}
                    onClick={() => setConfirmDelete(true)} />
          )}
        </VStack>
      </VStack>
    </Dialog>
  );
}
