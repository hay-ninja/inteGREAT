# inteGREAT — context for another AI

Snapshot: 2026-10-18. This is a portable product/UX brief, not an instruction to rebuild the app. If you have repository access, verify the current code and read AGENTS.md → docs/STATUS.md → docs/decisions.md → PRD.md before making changes. Some older proposal text and STATUS headings lag newer entries; the latest live-provider validation section supersedes earlier “no API keys / unvalidated” statements. This brief summarizes repository evidence; it does not claim its author reran every check.

## Product and current objective

We are building **inteGREAT**, a graph-first debugging workspace for embedded hardware/software projects. Early drafts called it TRACE. Initial scope is existing **ESP32 Arduino C/C++ projects**, demonstrated with a servo, USB serial, and a camera.

The problem: code, wiring diagrams, serial logs, physical behavior, and troubleshooting tools are disconnected. A developer needs to understand which part of the system might be wrong and what to check next.

Core loop: **import project + wiring context → inspect dependency graph → confirm expected behavior → run test → review actual evidence → investigate possible causes → perform a check → repair externally → verify using the same test**.

Primary audience is embedded engineers. Students/hobbyists and first-time viewers should understand component labels and next steps without knowing internal terminology. Technical identity and detailed evidence remain accessible.

This is a 24–36 hour LA Hacks AI Hackathon project, Oct 17–18, 2026, targeting **Beyond the Digital**. Sponsor contributions: Espressif hardware, StepFun orchestration, Gemini specialist analysis, and Devin software repair proposals. Additional company challenges should follow the same useful workflow, not require extra screens. Paper is a design consideration; Sentry is optional and not assumed integrated.

**Current product-design objective:** simplify a feature-heavy interface into a calm, intuitive workflow. Define information hierarchy and feature placement before adding more capabilities or changing visual style.

## Feature inventory

### 1. Project onboarding and wiring

- Import a local existing firmware repository; no inteGREAT instrumentation is required in the firmware.
- Reopen saved projects and explore clearly labeled simulated demo fixtures.
- Parse supported Arduino C/C++ source for modules, functions, calls, pin configuration, and serial log literals.
- Add hardware context with a YAML manifest or supported KiCad XML netlist.
- Preview the netlist and confirm component/pin role mappings. Netlist parsing errors have a manifest fallback.
- Review import warnings and source-versus-wiring discrepancies.
- Distinguish declared wiring from engineer-confirmed physical wiring. A schematic is not proof of the physical connection.
- Rescan after external source changes, retaining project identity, graph versions, and wiring confirmations.

### 2. Dependency graph

- One canonical graph, with stable node/edge IDs, provenance, and evidence references.
- **Combined:** software and hardware regions together, including cross-layer configuration/control links.
- **Hardware:** controller, pins, components, interfaces, power, and wiring.
- **Software:** modules, functions, configuration, calls, and explicit hardware boundary references.
- Subsystem focus, whole-system navigation, search, expand/collapse, zoom/fit, selection, and an explanatory legend.
- Readable component roles and relationship verbs such as calls, configures pin, connected to, powered by, and observed by camera.
- Inspect full names, pin numbers, source file/line, attributes, connection trust, and supporting evidence.
- Highlight conflicts, observations, suspected causes, and related paths. Hidden or collapsed elements must not create fictional direct dependencies or stronger certainty.

### 3. Test configuration and device setup

- Select a component/subsystem and confirm a test expectation before running.
- Define the configured command, measured metric, target, tolerance, and deadline. Example: servo reaches a 90° target within a specified tolerance and time.
- Choose **live**, **simulated**, or **recorded replay** observations. Replays may themselves be synthetic; preserve that distinction.
- Connect/release ESP32 USB serial; choose/connect a camera and calibrate marker tracking.
- Show readiness and recover from missing devices, invalid calibration, or unavailable measurements.
- Camera frame/stream endpoints and OpenCV ArUco tracking exist. Numeric angle comes from deterministic computer vision, not an LLM estimate.
- Release the serial port before external flashing; reconnect deliberately afterward. Opening serial may reset ESP32 boards, so DTR/RTS handling needs real-rig validation.

### 4. Observations and chronological Event Flow

- Capture configured host commands, serial messages, camera observations, and expectation results.
- Keep three facts separate: command sent, firmware response observed, physical movement measured.
- Angle-over-time plot, raw serial records, measurement quality, and clickable evidence.
- **Event Flow** is an alternate main view for a selected run, with lanes for command, software/serial, hardware observations, and result.
- Select initial/repeat/verification runs, step through recorded events, scrub time, and follow event links to graph nodes/evidence.
- Persisted events drive the view. Dense camera samples can be aggregated for display while preserving underlying evidence.
- Timing is **host-clock correlated**, not synchronized. Sequence alone does not prove causation. Log-literal matching associates a message with source; it is not a complete execution trace.
- Playback replays records and does not actuate hardware.

### 5. Diagnosis and engineer actions

- Deterministic evaluation yields **pass / fail / inconclusive**, then rules create incidents, qualitative hypothesis ranks, and fixed diagnostic actions.
- Fault categories include GPIO configuration mismatch, missing expected acknowledgement, absent physical motion, possible power/signal issue, and unavailable camera measurement.
- Signal and power hypotheses stay tied when the evidence cannot distinguish them.
- Present a recommended check with a reason, evidence, unknowns, and what different outcomes would mean.
- Inspect source/pin configuration, read wiring/serial/CV records, expand relevant scope, and perform manual checks through defined actions.
- Manual results require an explicit selection such as Connected / Disconnected / Unable to verify and can include notes.
- Evidence citations open real records. Substantive findings must reference resolving evidence IDs; validity of an ID alone does not establish a claim's truth.
- Permissions are scoped to the investigation; fixed registry tools validate args, check grants, and audit execution. Permission denial is recoverable.

### 6. StepFun and Gemini agents

Runtime flow: **StepFun triage → selected Gemini specialists → validate reports → StepFun synthesis → engineer action**.

- StepFun uses exact model `step-5-preview`, global API, and server-side `STEP_API_KEY`.
- It selects relevant specialists and questions, then reconciles findings/contradictions and recommends an existing diagnostic action.
- Gemini specialists are Code, Hardware, and Runtime/Vision. Model selection is configurable; use actual configuration rather than assuming an older model ID still works.
- Agents receive bounded, subsystem-scoped packets with expectations, graph context, source excerpts, evidence, action catalog, previous results, and explicit omissions/unknowns.
- Structured output plus evidence/action/scope validation; unknown IDs are rejected. AI hypotheses remain unverified, and deterministic rules retain ranking.
- Persist stage/provider/model/status, findings, citations, and validation errors. Show honest availability and useful fallbacks.
- Maximum one initial fan-out plus one follow-up after new evidence per incident. No open-ended model loops. Application runtime budgets differ from a coding AI's development/testing work.
- Tools/context fetching remain controlled by the backend/executor, not free-form model commands. Core graph, rules, tests, and tools work without AI.
- Qualitative Gemini camera interpretation is not wired into the main tools/UI; it is not a numeric sensor.

### 7. Devin software repair workflow

- A contextual **Prepare software fix with Devin** action for evidence-supported software issues.
- Engineer explicitly starts a remote repair session; this is separate from diagnosis.
- Preflight checks API/org configuration, accessible repository, exact base revision, dirty working tree, and attempt limits.
- Build a typed brief with evidence, reproduction, expected behavior, relevant source, constraints, and test instructions.
- Devin v3 organization-scoped API creates a session in its own sandbox/branch. Persist session/status, revision, remote artifacts and test results.
- Review session/PR links and distinguish missing results from success. Handle failures, uncertain creation, duplicates, and bounded attempts; status refresh never creates another session.
- Local paths are not automatically accessible to Devin Cloud. Uncommitted source is not silently part of the remote base; exact snapshot alignment matters.
- Engineer reviews/applies any fix externally, rescans, performs any firmware upload externally, and verifies on the relevant observation source.
- Remote software test success is not physical hardware verification. No automatic local patching, merging, deployment, or flashing.

### 8. Verification, persistence, and history

- Repeat gathers more evidence on the same incident; a passing repeat does not itself resolve it.
- Verify reruns the same confirmed command and acceptance criteria. A valid passing verification resolves; fail/inconclusive remains open.
- Completion explicitly names live/simulated/replay evidence. Switching source does not establish a repair on another source.
- SQLite persists projects, graph versions, evidence, runs, incidents, hypotheses, messages, agent runs, repair jobs, permissions/audits, and an append-only event history.
- WebSocket events update the workspace; reload restores context. Runs can be saved as recordings/replays.

## Current UX and desired simplification

Current design: dark Obsidian-inspired theme on **Astryx**, Inter/JetBrains Mono, a central canvas, right-side guided panel, and supporting measurement drawer. Numbered chapters: **01 Setup / 02 Run / 03 Debug / 04 Verify**. Graph nodes distinguish code from hardware; state color is purposeful.

Desired user questions: **What am I looking at? What do we know? What do I do next?** Keep one emphasized action appropriate to the current state, beginner-readable labels with exact identity in details, clear source/trust labels, and accessible evidence without losing context.

Features currently compete for attention. Proposed consolidation, not yet adopted:

- One Setup home for Rig setup and Devices.
- Dependencies/Event Flow as canvas views; Hardware/Software/Combined as layers.
- Event Flow explains a test; generic project Timeline becomes secondary Activity/history.
- One result summary and recommendation; full hypotheses, AI contributors, and raw records are progressive detail.
- Show Devin only for relevant software faults. Provider branding/settings are supporting information, not the user's main workflow.
- Keep Angle/Serial in contextual Measurements; audit/permissions/history remain discoverable supporting tools.
- Do not hide critical simulation, uncertainty, measurement failure, or permission information to reduce visual density.

Prioritize a working desktop flow at 1280×720 and 1024×768. Preserve the established Astryx theme/chapter direction; start by improving organization rather than replacing the visual system. User wants a feature outline and better UX, not more dashboards.

## Demo and validation status

Two principal demo cases:

1. **Fault A:** configured GPIO differs from declared/checked servo wiring. Inspect source and wiring; engineer corrects firmware, rescans, then verifies.
2. **Fault B:** missing movement despite apparently consistent configuration. Signal versus power remains uncertain until an explicit check produces evidence.

The simulator renders fake serial/camera observations through the observation/evaluation pipeline, and its behavior can reflect actual imported source configuration. It is always synthetic, not proof that real hardware works.

Latest STATUS reports 100 backend tests, 17 frontend tests, typecheck/build passing, and simulated browser walkthroughs including graph layers, Event Flow, repair preflight, and multiple desktop sizes. These are reported checks, not newly rerun by this brief.

Later STATUS entries report **real StepFun/Gemini smoke calls and end-to-end diagnosis working**, plus successful Devin authentication and creation of a **real remote repair session**. The returned repair/PR still requires review; this is not evidence of a completed or applied fix. Live testing exposed client-timeout and reasoning-output-budget issues which were fixed. StepFun output budget was raised to 8192 and orchestration timeout made separately configurable.

**Still outstanding:** physical ESP32/camera rig bring-up, both fault classes verified on real hardware, real recordings, and three consecutive successful live demo runs. Do not claim hardware validation from the simulator or model calls.

## Engineering constraints and repository map

- Frontend: Vite, React 19, TypeScript, React Flow (`@xyflow/react`), Dagre layout, Astryx core/theme/CLI pinned 0.7.1, Vitest.
- Backend: FastAPI/Pydantic modular monolith, SQLite typed JSON documents/events, tree-sitter, pyserial, OpenCV/NumPy, google-genai, httpx, pytest. Windows development, Python 3.13 venv; keep scripts cross-platform.
- `apps/api/integreat/models/contracts.py`: canonical contracts; regenerate OpenAPI and TS types after changes.
- `ingestion/`, `graph/`, `observations/`, `diagnostics/`, `tools/`, `context/`, `agents/`, `repair/`, `flow.py`, `storage/`, `service.py`: backend responsibilities.
- `apps/web/src/components/{shell,setup,graph,flow,dialogs,drawer}/`: actual UX. `apps/web/ASTRYX.md` and decisions describe style rules and documented canvas/chapter CSS exceptions.
- Secrets stay server-side. Do not print `.env`, include keys in prompts, or copy credentials into this handoff.
- Existing firmware only; no arbitrary shell execution, LLM-authored commands, automatic physical actions, or automatic local patches/flashes. Fixed test commands execute only through the explicit test workflow.
- Observed, verified, inferred, and unknown are distinct. Never claim PWM/voltage was measured; a missing camera marker means measurement unavailable.
- Preserve uncommitted work. Update STATUS after verified slices and record non-obvious decisions. Tests cover deterministic rules and security boundaries.

Start/verify commands (adapt shell/OS as necessary):

```text
apps/api/.venv/Scripts/python scripts/dev.py
# Web http://localhost:5173; API http://localhost:8000

# From apps/api
.venv/Scripts/python -m pytest -q

# From apps/web
npm test
npm run build

# From repository root after backend contract changes
apps/api/.venv/Scripts/python scripts/gen_api_types.py
# Then from apps/web
npm run gen:types
```

## Suggested task for the receiving AI

Use this context to help simplify and design the UX. First map each feature to **core flow / supporting view / advanced access**. Propose a minimal screen structure and one primary action for each major state. Walk through Fault A, Fault B, missing measurements, and a repair handoff. Explain what to consolidate, what remains visible, and why. Preserve provenance and the graph-first product. Make reasonable assumptions explicit; do not claim unfinished features or unperformed tests are complete.

Repository references: `docs/ux-product-outline.md` for the fuller inventory/state outline; `docs/STATUS.md` for latest validation; `docs/decisions.md` for intent; `PRD.md` for requirements; `docs/demo-script.md` for walkthroughs; `docs/hardware-setup.md` for rig constraints; `docs/integration-research.md` for integration implementation context.
