# Architecture

```
Browser (Vite + React + React Flow)
   │  REST /api/v1/*  +  WebSocket /api/v1/ws/projects/{id}   (Vite proxy strips cookies)
FastAPI modular monolith  (apps/api/integreat)
   ├─ ingestion/     repository scan · tree-sitter Arduino parser · YAML manifest · KiCad XML netlist
   ├─ graph/         builder (nodes/edges with provenance) · scoped query · GPIO consistency check
   ├─ observations/  replay · sim rig · live stream · serial adapter · OpenCV camera · ArUco angle
   │                 (the sim rig doubles as the digital shadow — queried, not just replayed)
   ├─ diagnostics/   expectation evaluator · fault rules · hypotheses + action cards · state machines
   │                 graph_state (metric-keyed run-state write-back, D-028) · shadow (nominal
   │                 prediction + residual evidence, D-029) · estimate (fault-knob sweep) ·
   │                 causal (command→ack→signal→motion→feedback chain + interventions, D-031)
   ├─ tools/         registry (fixed read-only functions) → executor (validate · grant · audit)
   ├─ context/       bounded, subsystem-scoped packets for agents (prefetched via the executor)
   ├─ agents/        per-stage providers: StepFun (orchestrator triage/synthesis/refute) · Gemini
   │                 (specialists: code, hardware, telemetry, vision + critic commentary, D-030)
   │                 · fake / unavailable; validation + bounded rounds stay in orchestrator.py (D-025)
   ├─ repair/        Devin v3 client + repair-brief builder + repo snapshot (remote proposals only, D-025)
   ├─ flow.py        persisted event-flow projection per run (lanes, aggregation, gaps — D-024)
   ├─ storage/       SQLite document store + append-only event timeline
   └─ service.py     orchestration; routes in api/ are thin
```

## One test, end to end
1. `POST /projects/{id}/tests` with a source: `replay` (file), `sim` (simulated rig) or `live` (devices).
2. The stream yields events (`host`, `serial`, `cv`) with host-clock times relative to the command (D-006).
   Each becomes Evidence + Observation/SerialEvent and a WebSocket event.
3. `diagnostics/expectations.evaluate` → pass / fail / inconclusive + three separate facts.
   `graph_state.record_run_state` then writes metric-keyed `obs_*` + `traversal` attributes onto
   the graph (D-028); `shadow.py` emits `shadow_residual` evidence vs. the nominal prediction.
4. Not passing → `diagnostics/rules` → `hypotheses.build` → Incident with ranked hypotheses +
   action cards; `estimate.py` tags hypotheses whose shadow-swept fault reproduces the observed
   signature (inferred, never verified); `causal.py` attaches the incident's causal chain.
5. Engineer acts: tool actions go through `tools/executor` (grants, audit); manual checks become
   engineer evidence; Verify fix reruns the same expectation and resolves only on a measured pass.
6. Optional: `POST /investigations/{id}/diagnose` → orchestrator round (max 2 per incident).
   StepFun triage → selected Gemini specialists (code/hardware/telemetry/vision) → deterministic
   shadow refutation of leading hypotheses (+ optional critic report) → StepFun synthesis (D-025,
   D-029/D-030). Tied top hypotheses → the recommendation must be the discriminating action.
7. Optional: `POST /investigations/{id}/repairs` → typed brief + ONE Devin Cloud session on an
   isolated branch; polling only refreshes the persisted `RepairJob` — it never patches locally.

`GET /tests/{id}/flow` projects any persisted run into the chronological Event Flow view
(command / software / hardware / result lanes; host-clock correlated, never causal — D-024).
The three dependency layers are frontend projections of the one canonical graph (D-023).

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
