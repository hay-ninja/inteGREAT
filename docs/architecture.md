# Architecture

```
Browser (Vite + React + React Flow)
   │  REST /api/v1/*  +  WebSocket /api/v1/ws/projects/{id}   (Vite proxy strips cookies)
FastAPI modular monolith  (apps/api/integreat)
   ├─ ingestion/     repository scan · tree-sitter Arduino parser · YAML manifest · KiCad XML netlist
   ├─ graph/         builder (nodes/edges with provenance) · scoped query · GPIO consistency check
   ├─ observations/  replay · sim rig · live stream · serial adapter · OpenCV camera · ArUco angle
   ├─ diagnostics/   expectation evaluator · fault rules · hypotheses + action cards · state machines
   ├─ tools/         registry (fixed read-only functions) → executor (validate · grant · audit)
   ├─ context/       bounded, subsystem-scoped packets for agents (prefetched via the executor)
   ├─ agents/        LLM provider (Gemini / fake / unavailable) · orchestrator (triage → agents → synthesis)
   ├─ storage/       SQLite document store + append-only event timeline
   └─ service.py     orchestration; routes in api/ are thin
```

## One test, end to end
1. `POST /projects/{id}/tests` with a source: `replay` (file), `sim` (simulated rig) or `live` (devices).
2. The stream yields events (`host`, `serial`, `cv`) with host-clock times relative to the command (D-006).
   Each becomes Evidence + Observation/SerialEvent and a WebSocket event.
3. `diagnostics/expectations.evaluate` → pass / fail / inconclusive + three separate facts.
4. Not passing → `diagnostics/rules` → `hypotheses.build` → Incident with ranked hypotheses + action cards.
5. Engineer acts: tool actions go through `tools/executor` (grants, audit); manual checks become
   engineer evidence; Verify fix reruns the same expectation and resolves only on a measured pass.
6. Optional: `POST /investigations/{id}/diagnose` → orchestrator round (max 2 per incident).

## Trust boundaries
- Imported code, logs, netlists, notes: untrusted data. Agents see them only inside `<data>` with rules.
- Every tool call — engineer, context engine, or (future) agent — goes through one executor (D-015).
- Agent output is validated against the evidence and action catalogs before storage (D-017).
- No shell execution, no device writes except the configured test command on Run/Verify.

## Where to change things
| Want to… | Edit |
|---|---|
| add a fault rule | `diagnostics/rules.py` + card in `diagnostics/hypotheses.py` + test |
| add a read-only tool | `tools/registry.py` (`@tool(...)`) + test in `tests/test_tools.py` |
| support another pin API | `ingestion/arduino_parser.py` (`PIN_FUNCS` / `SERVO_*`) |
| change contracts | `models/contracts.py` → `scripts/gen_api_types.py` → `npm run gen:types` |
