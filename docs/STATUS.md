# STATUS — handoff file

> Update this at the end of every verifiable slice. Keep it short; history lives in git, intent in `decisions.md`.

**Last updated:** 2026-10-17 · **Current milestone:** UI redesign done (D-021); software complete; **blocked on hardware (H0/M5/M7) and a Gemini key**

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

## What works now (verified 2026-10-17)
- **Tests:** 80 backend (pytest) + 5 frontend (vitest) passing; `tsc` clean.
- **Browser-verified** (simulated/synthetic only): import Fault A with KiCad netlist + mapping editor → sim run
  fails with GPIO mismatch #1 → Inspect asks for permission → grant → excerpt + hypothesis `supported` →
  tool audit shows denied then granted → wiring verification (graph v2, solid edge, engineer evidence) →
  Devices tab lists real ports → reload restores project + investigation. M1 flows (Fault A/B on replay)
  were browser-verified earlier.
- **Test-verified only (not clicked through in a browser):** sim Fault A fix → rescan → Verify fix → resolved;
  agents round with validation; agent budget/new-evidence rule; save-as-replay.

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

## Next (in order)
1. **Gemini:** put `GEMINI_API_KEY` + `INTEGREAT_GEMINI_MODEL` in `.env`; run `scripts/gemini_smoke.py`;
   then click *Ask agents* on a Fault A incident. Expect schema friction — fix in `agents/schemas.py` only.
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
- Astryx 0.7.x is pre-1.0 and pinned exactly; `npx astryx doctor` warns about the theme module import (expected, D-021).
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
