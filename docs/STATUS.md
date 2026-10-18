# STATUS — handoff file

> Update this at the end of every verifiable slice. Keep it short; history lives in git, intent in `decisions.md`.

**Last updated:** 2026-10-18 · **Current milestone:** layer views + Event Flow + StepFun routing + Devin repair implemented (D-023–D-025); **live hardware (H0/M5/M7) and real model/Devin calls remain outstanding (no API keys configured)**

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

## What works now (verified 2026-10-18)
- **Tests:** 100 backend (pytest) + 17 frontend (vitest) passing; `tsc -b` clean; production build passing.
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
- Bottom drawer (Angle, Serial, Timeline, Devices, Tool audit) collapsed until a test runs.
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
  the Devin repair workflow are now implemented (D-025) with per-stage fallbacks; live provider calls
  remain unvalidated (no API keys on this machine).
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

## Next (in order)
The requested expansion is **implemented** (D-023 layers, D-024 Event Flow, D-025 StepFun + Devin).
What remains is live credential/hardware validation — everything else is tested or browser-verified.

1. **Live providers:** put `STEP_API_KEY`, `GEMINI_API_KEY` + `INTEGREAT_GEMINI_MODEL` in `.env`; run
   `scripts/stepfun_smoke.py` then `scripts/gemini_smoke.py`; click *Ask AI to review evidence* on a
   Fault A incident and check per-stage attribution in "Provider per stage".
2. **Devin:** put `DEVIN_API_KEY` + `INTEGREAT_DEVIN_ORG_ID` in `.env`; commit the fixture firmware on a
   disposable branch (uncommitted files are excluded by design); run `scripts/devin_smoke.py`, then
   "Prepare software fix with Devin" on a Fault A incident and review the session/PR it returns.
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
