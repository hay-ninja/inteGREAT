# STATUS — handoff file

> Update this at the end of every verifiable slice. Keep it short; history lives in git, intent in `decisions.md`.

**Last updated:** 2026-10-18 · **Current milestone:** DSG/agent architecture implemented on `feature/dsg-agent-arch` (D-028–D-031): angle plot removed, metric-keyed graph write-back, SimRig digital shadow + fault estimation, 4-agent roster + deterministic refutation, causal chain. **Live hardware (H0/M5/M7) still outstanding.**

**Hackathon:** LA Hacks AI Hackathon (Oct 17–18), targeting **Beyond the Digital** and relevant company
challenges. See [hackathon context](hackathon-context.md) for supplied requirements and candidate fit;
this adds context without changing P0 scope.

## Milestone plan (PRD §17 adapted)
| # | Milestone | State |
|---|---|---|
| M0 | Contracts + fixtures | **done** |
| H0 | Rig bring-up (see `docs/hardware-setup.md` checklist) | **blocked: hardware** |
| M1 | Vertical slice import → graph → test → incident → actions → verify | **done** |
| M2 | Tool registry + grants + audit, serial-read tool, wiring verification, Expand Scope, notes | **done** (D-015) |
| M3 | Live serial (D-005), OpenCV camera, ArUco angle, MJPEG preview, devices UI, simulated rig | **done in software** (D-016) — **never run on real hardware** |
| M4 | Gemini agents: provider, context packets, triage → 3 agents → synthesis, validation, 2-round budget | **done, tested with a scripted fake** (D-017) — **never called real Gemini** |
| M5 | Both faults end-to-end on hardware incl. Verify Fix | todo — needs rig |
| M6 | KiCad XML netlist + mapping confirmation + manifest fallback | **done** (D-018) |
| M7 | Reliability | partial: save-as-replay, hardware guide, demo script, markers script done; 3 live runs + real recordings need the rig |
| M8 | Expansion: graph layers (D-023), Event Flow (D-024), StepFun orchestration + Devin repair (D-025) | **done in software** — real adapters + deterministic fallbacks tested; **live StepFun/Gemini/Devin calls blocked: no API keys** |

## What works now (verified 2026-10-18, `feature/dsg-agent-arch`)
- **Tests:** 109 backend (pytest) + 17 frontend (vitest) passing; `tsc -b` clean; production build passing.
- **Browser-verified via headless Chromium walkthrough** (`apps/web/ui_walkthrough.mjs`, simulated data):
  Fault A demo import → combined graph with Software/Hardware regions, verb edge labels
  ("configures pin", "connected to · verified"), conflict highlights → Hardware layer (6 hw nodes,
  0 code, "14 source items hidden" chip) → Software layer (code + dashed boundary refs) → sim run
  fail → **Event flow**: 4 lanes / 5 persisted events, run selector, step scrubber, replay-only note,
  evidence + graph cross-links → Debug panel "Prepare software fix with Devin" → repair dialog with
  honest preflight (missing `DEVIN_API_KEY`, dirty-tree warning, base revision, one-job limit).
  Checked at 1280×720, 1024×768, 800×600 — no console errors, no horizontal overflow.
- **API-verified end-to-end:** import → GPIO mismatch issue → expectation propose/confirm → sim run
  fail → `GET /tests/{id}/flow` (5 events, aggregated CV segment, host-clock-correlated note) →
  incident with ranked hypotheses incl. `prepare_software_fix` → repair preflight (snapshot +
  precise blockers) → `GET /agents/status` per-stage provider attribution (orchestrator:
  STEP_API_KEY not set; specialists: GEMINI_API_KEY not set) → diagnose 503 with honest fallback.
- **Earlier verified (2026-10-17):** 80 backend + 10 frontend tests; full D-022 browser pass below —
  import Fault A with KiCad netlist + mapping editor → sim run fails with GPIO mismatch #1 → Inspect
  asks for permission → grant → excerpt + hypothesis `supported` → tool audit shows denied then
  granted → wiring verification → Devices tab lists real ports → reload restores investigation.

## UI redesign (D-021) — done 2026-10-17
- Obsidian-style dark theme on **Astryx** (React 19, theme extends gothic, Inter/JetBrains Mono bundled).
- Guided right panel: **Setup → Run → Debug → Verify**, one primary button per step; the primary moves to
  "I fixed it — verify" once the suggested check is done. Alternatives + "More tools" (agents, read-only
  tools, permissions, notes) are collapsed by default.
- Hybrid graph: dots for code, pills for hardware; colour only for conflict/failed/suspect/observed.
- Bottom drawer (Angle, Serial, Devices, Activity) collapsed until a test runs.
- Browser-verified: start screen → Fault A demo → suggest/confirm → sim run → Debug (allow dialog, inspect
  dialog, hypothesis supported) → verify with replay `good` → "Fixed — verified" (labelled synthetic).
- Frontend conventions for agents: `apps/web/ASTRYX.md` (Astryx rules) + D-021. Graph CSS only in
  `src/styles.css` (`@layer app`, tokens only). Rebuild theme after editing `src/theme/obsidian/obsidianTheme.ts`:
  `cd apps/web && npx astryx theme build src/theme/obsidian/obsidianTheme.ts`.

## Astryx UX refinement (D-022) — implemented, browser-verified with synthetic data
- Import-first start screen; netlist-preview errors recover through a supplied manifest. Imported
  connections/warnings are reviewable; Rig setup is visible before live Run/Verify.
- Focused top-down graph with readable board labels and full inspector metadata. Evidence rows open
  real records; the inspector offers Expand in graph. Measurement drawers sit under the graph, keeping
  the right-side action visible. Actual app inspected at 1024px and 1280px with Astryx components.
- Tied physical hypotheses stay tied; manual checks require selecting and recording a result.
  AI review is visible with actual provider availability. Repeat offers source selection, shows the
  newest measurements, and keeps a passing repeat open until Verify. Completion names its evidence source.
- Fixed WebSocket reconnect/refetch loop after rescans; reload restores resolved investigations and
  serial/CV data. Stale responses are guarded; running tests hide/block further test actions.
- **Browser checks:** disposable Fault A copy → permission cancel/allow once → failed verification →
  external copy-only pin repair → rescan → simulated pass; Fault B → explicitly synthetic manual result
  → connected simulation → pass; occluded marker → unknown motion → valid repeat → Verify → pass;
  source-change warning, live readiness gating, evidence records, graph expansion, rescans and reload.
- [UX proposal](ux-investigation-proposal.md) retains the design exploration. StepFun orchestration and
  the Devin repair workflow are implemented (D-025) and live-verified — see below.
- Astryx doctor: no failures; it warns that CLI-managed theme wiring is absent. The custom D-021 theme
  is wired through `src/theme/index.ts` and confirmed in the rendered app. Vite's large-chunk advisory remains.

## Chaptered dark redesign (D-026) — done 2026-10-18
- User-approved direction after a reference image: keep the dark theme + canvas/right-panel split,
  adopt the reference's typography and structure. Numbered chapter strip replaces the Stepper
  (`01 SETUP · 02 RUN · 03 DEBUG · 04 VERIFY` with done/active/error state bars); monospace
  uppercase eyebrows label every category (`NN · NAME`); step headings use Astryx `display-*` types;
  content sits in boxed `Card` sections. Same gating, same one-primary-button rule.
- Import screen reordered: demo → reopen → boxed "import your own" form, under a display heading.
- Mixed implementation (user-chosen): Astryx components keep controls/dialogs/cards; token-only
  app CSS adds `.eyebrow` / `.chapters` / `.brand` in `styles.css` (extension of the D-021 exception).
- Re-verified in headless Chromium at 1280×720 / 1024×768 / 800×600 after the restyle: all three
  graph layers, Event Flow (lanes + step scrubber), repair dialog with honest preflight, zero
  console errors, no horizontal overflow. `tsc -b` clean, `vitest` 17/17, `vite build` passes.

## UX consolidation (D-027) — done 2026-10-18
- Implements [ux-blueprint.md](ux-blueprint.md): **one Setup destination** — every device entry point
  (top bar, More menu, drawer Devices tab, flow steps, repeat dialog) opens `RigSetupDialog`, which
  owns connect/calibrate/release. The drawer Devices tab is now a status summary that routes there.
- Drawer tabs: `Angle · Serial · Devices · Activity`; Timeline + Tool audit merged into Activity.
- New `flow/InspectorCard.tsx` — one inspector chrome shared by graph selections and event details.
- One-primary-action audit: primaries carry `flow-primary`; when a repair returns a PR, "Review the
  pull request" becomes the primary and "Start another attempt" demotes to secondary.
- Keyboard layer: Space = primary action, 1–4 chapters, D/E canvas modes, H/S/C graph layers,
  ←/→ event scrubbing, Esc on dialogs; input/dialog guards. Hint line under the chapter strip.
- Re-verified: `tsc -b` clean, `vitest` 17/17, `pytest` 100/100, `vite build`, headless-Chromium
  walkthrough (now covering Activity tab + Devices→setup routing) at 1280×720 / 1024×768 / 800×600 —
  zero console errors, no horizontal overflow.
- **Plain-language pass** for non-hardware readers: the incident card adds an "In short:" sentence
  derived from the three facts ("the board received the command and replied OK, but the arm never
  moved"); the facts read "The command went out / The board said it got it / The camera saw the arm
  move"; source picker explains Simulated/Replay/Live in one line each; event-flow lanes renamed
  "What we asked · What the board said · What the camera saw · The verdict" (with hover hints);
  drawer tabs read "Arm angle · Board messages · Devices · Activity"; top bar shows "Board" not
  "ESP32"; import fields explain themselves ("Your code folder", "Wiring notes file", KiCad
  description). Provenance wording unchanged — nothing technical was removed, only translated.
- **Legibility pass:** eyebrows/event labels/node subtitles bumped up a type step (were ~7px);
  edge labels shortened to glyphs on the canvas (`wired ✓`, `powered ?`, `configures pin`) with a
  background pill so parallel edges stop colliding — full wording stays in the inspector.
  Top bar re-zoned: `inteGREAT` is now a bold logo button that returns to projects, the focus
  selector is a labeled "Subsystem" dropdown, and a hairline divider separates context
  (project/subsystem) from the live-rig status zone. Canvas header carries a "Graph view" title.
  Home screen: each of the three sections gets a real heading, and clicking a demo or recent
  project opens a context modal ("what happens when you open it") before loading.

## Studio-style view rail + spacious home (D-032) — done 2026-10-18
- Roblox-Studio-inspired navigation: new `shell/ViewRail.tsx` (Astryx `SideNav`) in the Layout
  `start` slot — icon + text label + selected state, grouped `View` (Map / Timeline) and
  `Layer` (All / Hardware / Software). The rail is collapsible to an icon strip
  (`collapsible`, starts collapsed under 1000px viewport).
- The in-canvas `CanvasToggles` segmented controls are removed; canvas headers now only carry
  a view title ("Dependency map" / "Event timeline") and canvas tools (search, expand/collapse,
  whole-system, run selector, hidden-items chip). Keyboard D/E and H/S/C drive the same state.
- Home page de-condensed: `contentWidth` 640→1040, `display-1` hero, demos and recent projects
  as `ClickableCard`s in a responsive `Grid` (`minWidth` auto-fill) with section intros; the
  import form is a full-width card below. Context modal before opening any project unchanged.
- Fixed: duplicate React key when an evidence id is cited twice in one list (dedupe in
  `EvidenceList`).
- Re-verified: `tsc -b` clean, `vitest` 17/17, `vite build` passes, headless-Chromium
  walkthrough (rail labels, layer switching, Timeline mode, Activity, Devices→rig setup,
  repair dialog) at 1280×720 / 1024×768 / 800×600 — zero console errors, no horizontal
  overflow. The run→result wait was raised to 150s because live AI diagnosis (StepFun +
  Gemini) now runs in that window.

## DSG agent architecture (D-028–D-031) — done on `feature/dsg-agent-arch`, 2026-10-18
Plan: [dsg-agent-architecture.md](dsg-agent-architecture.md). The graph is now a state overlay,
not just a structural prior; SimRig doubles as a digital shadow queried diagnostically.
- **Angle demoted (D-028):** the "Arm angle" plot tab is gone from the drawer; default tab is
  Serial. CV evidence/observations unchanged — angle lives in agent/diagnostic logic only.
  After each run, `graph_state.record_run_state` writes metric-keyed `obs_*` attributes +
  `traversal` (`observed`/`unobserved`, evidence-cited) back onto graph nodes/edges; ids are
  deterministic so state re-applies after rescan. `moveServoTo` shows observed (prints ACK),
  `servoSetup` stays unobserved — traversal follows evidence, never assumption.
- **Digital shadow + estimation (D-029):** `shadow.py` predicts the nominal run from graph +
  expectation and emits `shadow_residual` evidence (epistemic=inferred, labelled "model" in UI).
  `estimate.py` sweeps the SimRig fault knobs and reports which θ reproduces the observed
  signature. Diagnosis-as-parameter-estimation with zero API keys.
- **Roster + refutation (D-029/D-030):** `runtime_vision` split into `telemetry` + `vision`
  (4 specialists; `runtime_vision` kept only so old AgentRuns deserialize). New `critic`
  pseudo-agent gives optional adversarial commentary — but `_refute` checks each top hypothesis
  by **shadow consistency first**, executable and authoritative over prose. When ≥2 hypotheses
  tie at top rank, synthesis must recommend the discriminating action (qualitative ambiguity,
  no probabilities per PRD §12).
- **Causal chain (D-031):** `causal.py` builds command→ACK→signal→motion→feedback per incident,
  rendered under the facts in the Debug chapter (deduced links say so; "unmeasured" stays
  honest). Counterfactuals are shadow interventions (`do(signal=connected)`) attached to the
  leading hypothesis as model-level statements.
- Tests added in `tests/test_shadow.py`: graph write-back split, shadow residual for every
  sim fault scenario, θ-estimation recovers injected fault, refute/causal paths, legacy
  `runtime_vision` run deserialization.

## Live provider validation (2026-10-18) — verified
- `stepfun_smoke.py`: step-5-preview triage OK (~8s). `gemini_smoke.py`: OK after model update —
  `gemini-2.5-flash` is retired for new keys; `.env` uses `gemini-3.8-flash`.
- `devin_smoke.py`: org-scoped auth OK (`inteGREAT` service user); smoke is read-only by design.
- Live end-to-end diagnose on real incidents: StepFun triage → Gemini specialists (code/hardware/
  runtime_vision — real findings citing real evidence ids) → StepFun synthesis (~28s) → incident
  summary with a recommended action id that resolves. Triage picks fewer specialists when the
  fault doesn't need them (e.g. hardware+code on a GPIO mismatch, no vision).
- Live Devin session created via the repair flow (`repair:e329572198` on a fault-a incident):
  preflight ready → session working at base `610f259`. Review its PR in Devin Cloud before applying.
- **Bugs found and fixed by live testing:** httpx's hidden 5s default beat the app timeout in the
  StepFun + Devin clients (per-request timeout now passed explicitly); step-5-preview spends
  reasoning tokens inside `max_tokens`, so 2048 returned empty `content` (`finish_reason=length`) —
  output budget raised to 8192 and the orchestrator got `INTEGREAT_ORCHESTRATOR_TIMEOUT_S` (120).

## Next (in order)
LED bench preparation (2026-10-18): added `fixtures/esp32_led_fade/esp32_led_fade.ino`
and `fixtures/manifests/esp32_led_fade.yaml` (two LEDs, two assumed 330-ohm series resistors,
no B10K; all wiring unverified). Manifest reviewed against the schema; runtime validation
unavailable locally because the venv is absent and the Python launcher is inaccessible.
The sketch drives two external LEDs on GPIO18/19, each fading up/down in turn. Source reviewed against
Arduino-ESP32 analogWrite documentation; not compiled (arduino-cli unavailable), flashed,
or hardware-verified. App expectations and adapters still target servo angles; this sketch
alone does not implement an LED investigation flow (D-034).

Portable handoff: [AI context brief](ai-context-brief.md) summarizes features, architecture, UX goals,
and the later live-provider validation status separately from outstanding hardware checks.

The requested expansion is **implemented** (D-023 layers, D-024 Event Flow, D-025 StepFun + Devin),
the UX blueprint is implemented (D-027), and all three providers are live-verified.
What remains is hardware validation.

1. **Review the Devin session** — session a5f20c0b68ec4fa6b59dc062915fed0a on the fault_a incident;
   inspect its branch/PR in Devin Cloud, then decide whether to apply (engineer-controlled).
2. **H0 on the rig:** follow `docs/hardware-setup.md`; record board variant, COM port, camera index;
   confirm opening the port does not reset the board (D-005). Update the manifest's board label.
3. **M5:** both faults live; save real recordings ("Save as replay") for good / Fault A / Fault B.
4. **M7:** three consecutive live demos per `docs/demo-script.md`; fix whatever breaks.
5. Nice-to-have (P1, only after 2–4): SSH gateway tools, Gemini frame description tool (D-020),
   graph version history UI.

## Known issues / gotchas
- ESP32 resets on serial open unless DTR/RTS are low (handled, unverified on hardware). Windows COM ports
  are exclusive → *Release port* before reflashing.
- `probe_cameras` takes ~0.5 s per index on Windows (DirectShow).
- **React Flow:** nodes are rebuilt on every change; GraphView passes back each node's `measured` size or
  React Flow hides nodes/edges. Auto-fit waits for `useNodesInitialized()` — fitting earlier is a no-op. **WebSocket 431:** Vite proxy strips cookies.
- Stopping a background `npx vite` task can leave the Node child holding :5173 — kill it by PID.
- Astryx 0.7.x is pre-1.0 and pinned exactly; `npx astryx doctor` cannot detect our custom theme wiring
  (`src/theme/index.ts`, D-021/D-022); it reports no failures.
- The simulated rig is honest about the fault model but is not hardware evidence; every sim run is
  `synthetic` and badged SIMULATED.
- Agents never run tools themselves (D-004); they only see tool output for categories the engineer granted.

## How to run / verify
- Setup (once): `cd apps/api && py -3.13 -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`;
  `cd apps/web && npm install`; optional `cp .env.example .env` and fill in Gemini.
- Both servers: `apps/api/.venv/Scripts/python scripts/dev.py` → http://localhost:5173
- Backend tests: `cd apps/api && .venv/Scripts/python -m pytest -q` · Frontend: `cd apps/web && npx tsc -b && npm test`
- After changing backend models: `apps/api/.venv/Scripts/python scripts/gen_api_types.py && (cd apps/web && npm run gen:types)`
- Synthetic replays: `scripts/gen_synthetic_replays.py` · Markers: `scripts/make_aruco_markers.py` · Gemini check: `scripts/gemini_smoke.py`

## IDE panels + landing page (D-033) — done 2026-10-18
- Resizable side panels: rail via SideNav `resizable`, guided steps panel via
  `useResizable` + `ResizeHandle` (drag-verified headlessly: 388→509px).
- Dropdowns open downward (`placement="below"`); canvas tools are boxed buttons
  with explanatory tooltips; decorative mono/uppercase eyebrow styling removed.
- `LandingScreen` (story → why → how it works → features → CTA) precedes the
  import screen; home logo returns there.
- Re-verified: `tsc -b` clean; headless walkthrough updated for the landing step —
  rail labels, layers, timeline, Activity, Devices→setup, repair dialog all pass;
  zero console errors; no 800px overflow.

## Phone camera input — 2026-10-18 (D-035)
- Pulled main through `2319948`, preserving the local LED sketch/manifest/notes.
- Rig setup now offers Phone / network camera with an HTTP MJPEG URL. Bounded LAN stream
  adapter feeds existing preview and CV; timeout/errors/release are supported, stale frames
  become unavailable, and invalid/redirect/public/credential URLs are refused.
- Setup guide: `docs/phone-camera.md`. Phone app must serve MJPEG on the same trusted LAN.
- Frontend typecheck, 17 frontend tests, and production build pass. Backend regression:
  126 passed; two subsequently added API connect/preview/release tests also pass
  (19 phone-camera tests total). Only the dependency's Starlette/httpx deprecation warning.
- No real phone camera tested. LED brightness evaluation remains unimplemented; live test
  readiness/calibration still follows the servo-marker contract.
