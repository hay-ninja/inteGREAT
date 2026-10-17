# STATUS — handoff file

> Update this at the end of every verifiable slice. Keep it short; history lives in git, intent in `decisions.md`.

**Last updated:** 2026-10-17 · **Current milestone:** M1 done → starting M2 · **Hardware:** not connected yet (D-010)

## Milestone plan (PRD §17 adapted)
| # | Milestone | State |
|---|---|---|
| M0 | Contracts (Pydantic) + fixtures (firmware, manifest, synthetic replay) | **done** |
| H0 | Rig bring-up: board variant, COM port, servo motion, camera+ArUco, real traces | blocked: hardware |
| M1 | Vertical slice: import → graph → replayed test → rules → incident → actions → verify | **done** (replay only) |
| M2 | Permissions + tool registry/audit, `read_serial_buffer`, wiring-verification PATCH, Expand Scope | next |
| M3 | Live serial (D-005) + OpenCV camera + MJPEG preview + device status | todo (needs H0) |
| M4 | Gemini: LLMProvider (+fake), context packets, 3 agents, orchestrator, validation (D-004) | todo |
| M5 | Both faults end-to-end on **hardware** incl. Verify Fix | todo |
| M6 | KiCad XML netlist importer + manifest fallback | todo |
| M7 | Reliability: 3 consecutive live runs, labeled replay fallback, README | todo |

## What works now (verified 2026-10-17)
- **Backend (44 pytest passing):** safe repo scan, tree-sitter Arduino parser, manifest + ESP32 pin
  normalization, graph with provenance + static GPIO-mismatch flag at import, scoped graph query (AC-08),
  SQLite doc store + event timeline, replay source, expectation evaluator (3 separate facts), all 5 P0 rule
  codes, ranked hypotheses + action cards, incident state machine, REST + WebSocket.
- **Frontend (Vite + React + @xyflow/react):** fixture import, expandable graph (subsystem→module→function,
  edges lifted to visible ancestors), legend, subsystem focus, search, breadcrumbs, node evidence panel,
  expectation propose/edit/confirm, Run Test, live CV plot / serial / timeline, investigation panel
  (facts, hypotheses with cited evidence + unknowns, action cards), Inspect GPIO modal, manual-check modal,
  Verify fix, RESOLVED banner with follow-up runs, SYNTHETIC REPLAY badges everywhere.
- **Browser-verified flows** (synthetic replay, NOT hardware):
  - Fault A: import `esp32_servo_demo_fault_a` → run `fault_a_wrong_gpio` → GPIO mismatch #1 → Inspect shows
    `#define SERVO_PIN 19` vs manifest GPIO18 → switch replay to `good` → Verify fix → resolved.
  - Fault B: import `esp32_servo_demo` → run `fault_b_disconnected` → signal/power tied #1 → manual check
    "Disconnected" → signal hypothesis `supported` → Verify fix (`good`) → resolved.

## Next (M2, in order)
1. `tools/registry.py` + `tools/permissions.py` + `tools/executor.py` per PRD §13 and D-004: one execution
   path for every caller, `caller` recorded, per-investigation category grants, audit log of every call/denial.
   Move `inspect_gpio_config` into the registry (currently inline in `service._inspect_gpio`).
2. `read_serial_buffer` + `read_test_events` tools (read stored serial for now; live buffer in M3).
3. Permission grant UI (grant/revoke categories) + approval prompt for ungranted actions (AC-07).
4. `PATCH /projects/{id}/graph/verification` + UI to confirm/correct wiring (PRD §5.1 step 5).
5. `expand_scope` action; text input for clarifications (`/investigations/{id}/messages`) (AC-09).
6. Frontend unit tests for `components/graph/visibleGraph.ts` (pure function, easy to test).

## Known issues / gotchas
- ESP32 resets on serial open (D-005). Windows COM ports are exclusive.
- **React Flow:** nodes are rebuilt on every change; we must pass back each node's `measured` size or React
  Flow drops handle positions and hides nodes/edges. See `GraphView.tsx` (controlled nodes).
- **WebSocket 431:** browsers send every `localhost` cookie (other dev projects); the Vite proxy strips
  cookies (`vite.config.ts`). Vite listens on `localhost` (IPv6), not `127.0.0.1`.
- UI doesn't restore the last project after a page reload (must re-import). Fine for demo; P1.
- Running a replay at real speed takes ~2.6 s; tests use `replay_speed=0`.
- Firmware without a serial command handler gets an `external_sequence` trigger, which can't run yet
  (no live adapter).

## How to run / verify
- Backend setup (once): `cd apps/api && py -3.13 -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"`
- Frontend setup (once): `cd apps/web && npm install`
- Both servers: `apps/api/.venv/Scripts/python scripts/dev.py` → http://localhost:5173
- Backend tests: `cd apps/api && .venv/Scripts/python -m pytest -q`
- Frontend typecheck: `cd apps/web && npx tsc -b`
- After changing backend models: `apps/api/.venv/Scripts/python scripts/gen_api_types.py && (cd apps/web && npm run gen:types)`
- Regenerate synthetic replays: `apps/api/.venv/Scripts/python scripts/gen_synthetic_replays.py`
