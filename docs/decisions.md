# Decision log

### D-034 Two-LED bench sketch while preparing alternate demo — 2026-10-18
- Owner has two external LEDs on GPIO18/19 and requested alternating fades; added standalone
  Arduino firmware using analogWrite, with no inteGREAT instrumentation or app changes.
- This supports bench bring-up; it does not satisfy or replace the PRD servo-angle acceptance
  criteria. An LED-based app investigation still needs explicitly adapted contracts/observations.
- Each LED requires its own series resistor. Hardware operation is unverified.

Append-only. Each entry: what, why, what it rules out, and when to revisit. Supersede, don't edit:
mark old entries `SUPERSEDED by D-0xx`. The goal is to preserve **intent** — the code shows what, this shows why.

---

### D-001 Frontend: Vite + React instead of Next.js — 2026-10-17 — approved by owner
- **Why:** single-page local tool; no SSR/routing needs. Fewer moving parts, simpler WebSocket + dev proxy.
- **PRD:** §9.1 lists Next.js as [RECOMMENDED], so this is a permitted revision.

### D-002 Repo layout at repo root; backend package `integreat` — 2026-10-17 — approved
- Layout lives at repo root (no nested product folder as PRD §16 originally showed).
- PRD file renamed `TRACE_PRD_v1.md` → `PRD.md`.
- (Package was briefly `trace_api` to avoid the stdlib `trace` clash; moot after D-011.)

### D-003 Add canonical `Evidence` record and `DiagnosticAction.expected_outcomes` — 2026-10-17
- **Why:** PRD §10 references evidence IDs everywhere but never defines Evidence; §12 requires
  expected outcomes per action but §10.7 omits the field. Both are needed for provenance (PRD §3.4).

### D-004 P0 agents do not call tools directly — 2026-10-17 — approved, with future intent
- **P0 behavior:** the context engine runs registry tools deterministically *before* an agent call and puts
  results in the ContextPacket. Agents choose next steps only by referencing action IDs from a fixed catalog.
  Bounded to one initial fan-out + one follow-up (PRD §11.1).
- **Owner intent (important):** owner wants to **later** let agents autonomously invoke CLI diagnostics.
  Design must keep that door open:
  - All tool execution goes through one path: `tools/registry` → `tools/permissions` → `tools/executor`,
    regardless of caller (UI click, context engine, or future agent).
  - Every tool call records `caller` (`engineer` | `context_engine` | `agent:<name>`).
  - A future agent tool call = a `ToolProposal` validated against the same registry + session grants,
    so turning it on is a caller change, not a security redesign.
  - Still never free-form shell: "agent CLI commands" means agents selecting registered command
    templates with schema-validated arguments (PRD §13.3).
- **Revisit:** after the two-fault demo loop passes (PRD §23.9).

### D-005 Serial: one persistent reader, tools read its buffer — 2026-10-17
- **Why:** opening a port on most ESP32 dev boards toggles DTR/RTS and resets the chip, so a "read-only"
  open isn't read-only. Also Windows COM ports are exclusive, so the Arduino IDE can't flash while inteGREAT
  holds the port.
- **Consequence:** open once with DTR/RTS deasserted; `read_serial_buffer` reads in-memory buffer;
  explicit **Release / Reconnect device** control (reconnect is approval-gated).

### D-006 Time correlation is host-clock "correlated", never "synchronized" — 2026-10-17
- Without firmware changes there's no shared clock. Use host monotonic receive time + UTC; record
  estimated latency. UI wording must say "correlated".

### D-007 Execution highlighting via log-literal matching — 2026-10-17
- Function-level execution can't be observed without instrumentation. Match received serial lines to
  `Serial.print*` string literals in source → that function is "observed via log line <evidence>".
  Everything else is rendered as declared/inferred. Honest partial answer to PRD §5.3 / FR-03.

### D-008 CV marker: ArUco on servo horn (+ reference marker) — 2026-10-17 — proposed
- Robust orientation from a single detection; built into `opencv-python` ≥4.7. Undetected → invalid
  measurement (PRD AC-03). Revisit if hardware camera can't resolve markers.

### D-009 Python 3.13 venv — 2026-10-17
- Machine default is 3.14; OpenCV/tree-sitter wheels are safer on 3.13.

### D-010 Hardware not yet available — build on replay fixtures first — 2026-10-17
- Owner: hardware available "in a bit". M1–M2 run on **synthetic** replay JSONL, labeled synthetic.
  Replace with real captures in H0. Never report hardware verification from these.

### D-011 Product renamed TRACE → inteGREAT everywhere — 2026-10-17 — owner request
- Display name `inteGREAT`; Python package `integreat`; manifest schema `integreat-manifest/v1`;
  WS envelope `IntegreatEvent`; env vars will use `INTEGREAT_` prefix. PRD text updated in place.
- Any "TRACE" left in old notes/commits means inteGREAT.

### D-012 Persistence = typed JSON document store + append-only events table — 2026-10-17
- One `docs(kind, id, project_id, parent_id, data)` table instead of a table per entity. Pydantic models
  are the schema; the events table is the timeline and the WebSocket catch-up source.
- **Why:** fastest path that still persists everything PRD FR-09 lists; no ORM. Revisit only if queries get slow.

### D-013 Fault B is split into two tied hypotheses (signal vs power) — 2026-10-17
- `POSSIBLE_POWER_OR_SIGNAL_FAULT` produces "signal lead" and "power/ground" hypotheses at equal rank,
  each with its own manual check. inteGREAT can't measure either, so it must not pick one (PRD §6, FR-07).
- Manual results move a hypothesis to `supported`/`weakened`; ranks are recomputed from status.

### D-014 Repeat/Verify runs attach to the existing incident — 2026-10-17
- Repeat and Verify create new test runs linked by `incident_id` instead of new incidents.
  Verify pass → `resolved`; verify fail/inconclusive → back to `awaiting_engineer` (AC-10).

### D-015 One tool execution path with per-investigation grants and full audit — 2026-10-17
- `tools/registry.py` (fixed functions + typed args) → `tools/executor.py` (validate → risky check → grant
  check → run with timeout/output caps → audit). Callers: `engineer`, `context_engine`, future `agent:<name>`.
- `approve_once` is honoured ONLY for caller `engineer` (individual approval). Agents can never self-approve.
- Risky categories (flash, GPIO write, serial write, file write, reboot) are refused even with approval (P0).
- Grants are per investigation and end when it is resolved/inconclusive (PRD §13.1).
- Implements the "keep door open" half of D-004: enabling agent-initiated tools later = letting the
  orchestrator submit `agent:<name>` calls to this executor. No security redesign needed.

### D-016 Simulated rig as a third observation source (`kind: "sim"`) — 2026-10-17
- Fake firmware on a fake serial port + rendered ArUco frames, run through the REAL live pipeline
  (LiveStream → ArUco estimator → evaluator). Always `synthetic=True` and labelled SIMULATED in the UI.
- Physics follow the fault model: servo moves only if the source-configured GPIO == wired GPIO and the
  sim's signal/power leads are connected — so Fault A in sim comes from the actual code, and a firmware fix
  + rescan really changes the outcome.
- **Why:** lets the whole live code path be tested and demoed before hardware exists. Not evidence of
  hardware behaviour; never presented as such.

### D-017 Agents: deterministic dispatch fallback, validated citations, rules keep the ranking — 2026-10-17
- Triage asks the model to choose among exactly 3 agents; any failure → rule-based plan per fault code.
- Findings citing ids not in the agent's evidence catalog are dropped and logged (`validation_errors`).
- Agent-proposed hypotheses are added `unverified`, origin `agent`, rank after rule hypotheses. The
  synthesis contributes an explanation and a recommended next action only; it never reorders ranks.
- Follow-up round requires new evidence (engineer input, engineer-run tool, or rerun) — agents' own
  context prefetches don't count. Max 2 rounds per incident (PRD §11.1).
- No Gemini model id is hardcoded (PRD §11.4): `INTEGREAT_GEMINI_MODEL` must be set; without it the
  agents report "unavailable" and everything else works. `scripts/gemini_smoke.py` checks access.

### D-018 KiCad: XML netlist only, mapping must be confirmed, all wiring `unverified` — 2026-10-17
- S-expression `.net` is rejected with the `kicad-cli … --format kicadxml` hint. XML parsed with defusedxml.
- MCU GPIOs come from the symbol's *pin function* (IO18), never the module's physical pin number.
- Roles (which ref is the servo, pin roles) are a *proposal* until the engineer confirms; the import
  records `NETLIST_MAPPING_UNCONFIRMED` if not. A netlist is the designed schematic, so every connection
  is `unverified` until confirmed via the wiring-verification endpoint (PRD FR-02, §20).
- Any netlist failure falls back to the manifest without blocking onboarding (AC-01, AC-11).

### D-019 Rescan keeps the project identity — 2026-10-17
- `POST /projects/{id}/rescan` re-reads the repo into the same project (graph version +1), re-applying
  engineer wiring confirmations. Needed for Fault A: engineer fixes firmware → rescan → Verify fix on the
  same incident. Old graph versions are kept as `graph_v<N>` documents.

### D-020 Cut per PRD §17: Gemini frame interpretation and SSH gateway — 2026-10-17
- `LLMProvider.analyze_image_optional` exists (Gemini impl included) but is not wired into tools/UI.
- No SSH/Linux gateway tools. Local USB serial is first-class. Both are P1 if time allows.

### D-021 UI redesign: Obsidian look on Astryx, guided steps, hybrid graph — 2026-10-17 — owner choices
- **Owner intent:** intuitive UI, intentional buttons, *few visible options* (avoid information overload),
  "Obsidian-ish" like the knowledge-mapping app.
- **Chosen:** Obsidian-faithful colours (charcoal `#1e1e1e`, muted text, one purple accent `#8b7cf6`;
  colour only for status) · hybrid graph nodes (dots for code, compact pills for hardware) · **guided
  steps** panel (Set up → Run → Investigate → Verify, ONE primary button per step; advanced tools behind
  "More") · Astryx design system with a theme extending `gothic`.
- **Implementation notes:**
  - React upgraded 18 → 19 (Astryx peer dep). Astryx packages pinned **exactly** at 0.7.1 (pre-1.0,
    releases every few days; canaries daily) — bump deliberately with `astryx upgrade --from 0.7.1`.
  - Theme: `apps/web/src/theme/obsidian/obsidianTheme.ts` → `npx astryx theme build …` → wired in
    `src/theme/index.ts`. The CLI-generated `astryx-themes.ts` was dropped: it pulled gothic's Google Fonts
    (incl. blackletter display faces). Fonts are bundled locally (@fontsource-variable Inter / JetBrains
    Mono) so offline demos look identical. `astryx doctor` will warn "theme-module-import"; expected.
  - Gothic's slow theatrical motion and large type scale are overridden (Obsidian is snappy, 14px base).
  - Astryx rule "no raw div / no hex": followed for app chrome. Exceptions: React Flow node renderers and
    the SVG angle plot (a canvas library and a chart need their own markup); they use theme tokens only.
  - Astryx agent notes live in `apps/web/ASTRYX.md` (written by `astryx init --agent-docs-path`), not in
    our AGENTS.md.

### D-022 Astryx UX refinement and investigation continuity — 2026-10-17 — owner requested UX work and extended verification
- Retain D-021's guided right panel and theme. Implement real React UI with Astryx Layout, Dialog,
  List, Selector, Button, Stepper, and typography components; the conversation mockups remain proposals.
- Put import first, show netlist errors inline, and let a supplied manifest recover a failed netlist
  preview. Preview results are discarded if their inputs change before the request completes.
- Expose Rig setup in the header and from unavailable live-run controls. Device connections remain
  deliberate actions; existing camera/serial endpoints and permission boundaries still apply.
- Default to the component subsystem. Filter the focused graph before layout, retain its ancestors,
  and keep Whole system available. Use compact top-down layout and shorten visible board labels while
  preserving full identity/provenance in the inspector. Scope is refreshed after rescans.
- Graph/evidence inspection uses Astryx dialogs, including a discoverable Expand in graph action.
  It no longer pushes the investigation's next action down the panel. Put measurement/log drawers
  under the graph only; keep the investigation panel's height independent of those drawers.
- Keep one primary next step, show tied hypotheses as tied, expose expected outcomes and citations,
  and require an explicit manual-result choice plus Record. AI evidence review is visible and names
  only the configured provider; StepFun synthesis remains a proposal, not a shipped integration.
- Repeat asks for an observation source while retaining the expectation. Show current follow-up
  measurements rather than the original run. A passing repeat remains open until Verify; completion
  explicitly names live/simulated/replay evidence. Active incidents cannot edit criteria through past
  step buttons. Reload restores the incident's expectation, latest run, serial/CV data, and resolved state.
- **Reliability fix found during browser QA:** depend on `project.id`, not the project metadata object,
  for the WebSocket subscription. Rescan metadata replacements otherwise reconnected from seq 0,
  replayed graph.updated, and caused a reconnect/refetch loop. Ignore stale async investigation/data
  responses after changing projects and block overlapping test actions in the UI.
- **Validation:** build/typecheck, 80 backend + 10 frontend tests; actual-browser synthetic Fault A/B,
  permission cancel/allow, failed then passing verification, marker-loss recovery via Repeat + Verify,
  source-change/live-readiness gating, evidence/expansion, reload and repeated rescans, 1024/1280px.
  No real hardware or live model calls were validated. Revisit layout after testing on the physical rig.

### D-023 One canonical graph, three layer projections — 2026-10-18 — Hardware/Software/Combined views
- The three dependency views are a **projection of one graph**, not three copies. Node/edge ids,
  verification state, evidence ids, focus scope, search, and expand/collapse are shared across
  modes; switching layers never rewrites provenance.
- Filtering is honest: hiding an intermediate node never invents a direct edge. Lifted edges keep
  the original edge ids, carry a `summary` explaining the substitution, and take the least-certain
  verification state of the collapsed path (unchanged from D-022's behaviour, now layer-aware).
- **Hardware view** shows only physical kinds (mcu/pin/component/power/interface); code is hidden
  and the inspector offers the route back ("show the code that touches this"). **Software view**
  shows code plus a small explicit *boundary*: hardware the visible code configures/controls/reads,
  plus one hop of wiring context, rendered dashed as "reference". **Combined view** lays software
  and hardware out in two labelled regions so cross-layer links are visible at a glance.
- Beginner-readable roles (`nodeRole`) are derived only from imported structure — component type,
  pin parentage, wiring neighbours — never guessed by a model. Unknown roles say so ("role not
  declared"). Full identity (part numbers, file:line, pin ids) stays in the inspector.
- Edge verbs (`calls`, `configures pin`, `connected to`, `powered by`, `observed by camera`) carry
  a provenance suffix: declared wiring reads "declared, unchecked" until an engineer verifies it.
- Elements hidden by a layer are counted in the header ("N source items hidden — show everything")
  and explained per-node in the inspector, both with a one-click reveal back to Combined.

### D-024 Event Flow is a persisted projection, not an execution tree — 2026-10-18
- `integreat/flow.py` derives the chronological view from persisted run records only: host commands,
  serial events, CV observations, expectation results, incident/timeline events. No LLM, no
  fabricated ordering, no fictional dependency DAG forced onto records.
- Lanes describe *what kind of record* an event is: command / software-serial / hardware /
  result. Ordering is host-clock correlated and labelled as such in the UI; ordering alone is
  never presented as causation.
- Dense camera samples aggregate into segments for rendering (`cv_segment`, `aggregated_ids`) —
  underlying observation/evidence ids are preserved and linked, nothing is deleted. Missing
  timestamps keep a stable secondary `order` and are labelled "time unknown".
- Stepping/scrubbing is a **replay of recorded events** — the UI states this and issues no
  commands. Each event keeps evidence ids + related graph ids; "In the graph" switches back to
  the Dependencies view with the node revealed.
- The graph layer choice stays meaningful: hardware layer dims the software lane and vice versa.

### D-025 StepFun orchestrates, Gemini supplies specialists, Devin proposes remote fixes — 2026-10-18
- Provider routing per stage, not per app: the orchestrator LLM (StepFun `step-5-preview`,
  `STEP_API_KEY`, global endpoint) performs triage and synthesis; the specialist LLM (configurable
  Gemini model) answers code/hardware/runtime-vision questions. `GET /agents/status` reports
  per-stage provider/model/availability. Deterministic dispatch and rule hypotheses remain the
  fallback whenever a stage is unavailable; nothing is silently substituted.
- **Separate remote repair workflow (narrow addition to the no-auto-patching rule):** the
  `prepare_software_fix` action opens an engineer-controlled dialog, never the action executor.
  `POST /investigations/{id}/repairs` builds a typed brief (repo identity, exact base commit,
  evidence ids, confirmed expectation, repro, constraints, test commands) and creates ONE Devin v3
  org-scoped session. Devin may modify its isolated branch; inteGREAT still never patches the local
  checkout, merges, flashes, or verifies.
- Snapshot honesty: a Windows-local path is not a repo Devin Cloud can reach. Preflight reports the
  exact missing prerequisites (no `DEVIN_API_KEY`, no git remote, uncommitted files are excluded,
  firmware subdirectory is named in the brief). `acknowledge_uncommitted` is required when the
  working tree is dirty — we never silently send a stale base revision.
- Lifecycle is persisted (`RepairJob`: preparing → queued → working → ready_for_review / failed /
  needs_input / uncertain), one active job per incident+revision, polling only refreshes state and
  never re-creates a session. A remote "finished" is not a fix: missing PR/diff/test output stays
  "unavailable", and remote test results are labelled remote software checks, not hardware
  verification. Budget: max attempts per incident enforced server-side.

### D-026 Chaptered dark redesign (user-approved direction) — 2026-10-18
- Visual direction after user review of a reference image: **keep the Obsidian dark theme,
  adopt the reference's typography and structure** — numbered chapter strip
  (`01 SETUP · 02 RUN · 03 DEBUG · 04 VERIFY`), monospace uppercase eyebrows
  (`NN · CATEGORY`), display-scale headings, and boxed sections (Astryx `Card`s + hairline
  borders). Same canvas + right-panel split, balanced density.
- Implementation is intentionally mixed (user-chosen): Astryx components keep owning controls,
  dialogs, lists and cards; app-layer token-based CSS (`styles.css` @layer app, `--color-*`/
  `--font-*`/`--spacing-*` tokens only) provides `.eyebrow`, `.chapters`, `.brand`. This is a
  documented extension of the D-021 custom-CSS exception (graph canvas, event-flow lanes,
  chaptered typography) — no new design system, no palette overrides, no new dependencies.
- The Stepper is replaced by the chapter strip; step gating is unchanged (forward chapters stay
  locked until reached, completed chapters clickable, debug chapter shows error state bar).
- Import screen reordered to match intent: demo → reopen → import your own (boxed form).

### D-027 UX consolidation: single Setup destination, merged inspector, keyboard layer — 2026-10-18
- Implements `docs/ux-blueprint.md` (the principal-designer brief) on top of the D-026 structure.
- **One Setup destination.** All device entry points (`TopBar` "Rig setup", `More` menu, drawer
  Devices tab, FlowPanel "Set up the live rig", RepeatTestDialog) open `RigSetupDialog`, which
  owns `DeviceControls` (connect / calibrate / release). The drawer Devices tab is a read-only
  status summary with an "Open rig setup" route — no duplicated controls.
- **Drawer consolidation.** Tabs are now `Angle · Serial · Devices · Activity`; Timeline and
  Tool audit merged into Activity (eyebrow-separated sections) per the blueprint's
  feature-consolidation matrix.
- **Unified inspector chrome.** New `flow/InspectorCard.tsx` — one card pattern (eyebrow +
  close + content) shared by graph selection (`SelectionCard`) and event-flow detail; the
  selected event card keeps its inline position inside EventFlowView so it stays adjacent to
  the scrubber (a modal would block ←/→ scrubbing).
- **One-primary-action audit.** Primary buttons carry `className="flow-primary"`. Verified each
  state exposes exactly one primary: step steps, preflight "Start repair session", and — when a
  repair returns a PR — "Review the pull request" becomes the primary while "Start another
  attempt" demotes to secondary (retry is not the next action). Devin repair remains a ghost
  secondary and is only reachable via backend-recommended `prepare_software_fix` (software
  evidence only) — unchanged.
- **Keyboard layer.** Window-level handler in `App.tsx`: Space clicks `.flow-primary`, 1–4 click
  `.chapter[role=tab]` buttons, D/E switch canvas modes, H/S/C switch graph layers; EventFlowView
  owns ←/→ event scrubbing. Guards: ignored inside inputs/selects/contenteditable and open
  dialogs; Esc stays with Astryx dialogs. A hint line sits under the chapter strip.
- Verified: `tsc -b` clean, 17 vitest, 100 pytest, `vite build`, headless-Chromium walkthrough
  (extended with Activity + Devices→setup coverage) at 1280×720 / 1024×768 / 800×600 — zero
  console errors, no horizontal overflow.

### D-028 Angle removed as terminal output; run state writes back to the graph, metric-keyed — 2026-10-18 — owner request
- Implements stage A of [dsg-agent-architecture.md](dsg-agent-architecture.md). The bottom drawer
  loses the "Arm angle" plot tab entirely (Serial · Devices · Activity remain); CV observations,
  `cv_measurement` evidence, and `read_cv_measurements` are unchanged — angle is now an input to
  diagnosis, never a universal output surface. Deviates from the PRD §9 wireframe's
  "CV angle plot" row; flagged there.
- `diagnostics/graph_state.py` writes the last run's state back onto the canonical graph:
  metric-keyed node attributes (`obs_metric`, `obs_value`, `obs_residual`, `obs_outcome`,
  `obs_run_id` + evidence ids) and `traversal` on edges (`observed` / `unobserved`, evidence-cited).
  Metric-keying means a different estimator (e.g. an LED brightness observer for a lights demo)
  flows through the same path with no renames; nothing assumes "angle" outside the estimator.
- Traversal is evidence-driven, not ACK-driven: a `controls`/`configured_by` edge is "observed"
  only when the function's own serial literal was received. `moveServoTo` prints `ACK MOVE` and
  is observed; `servoSetup` prints nothing and stays "unobserved" — we never infer execution we
  didn't see. `traversal` = code-path ran, never "the physical thing moved".
- Node/edge ids are deterministic, so `record_run_state` re-applies cleanly after rescan.

### D-029 Digital shadow: SimRig reused predictively; deterministic refutation is authoritative — 2026-10-18
- Implements stage B + the verification half of stage C. `diagnostics/shadow.py` runs `SimRig`
  forward under nominal `SimConditions` derived from the graph + expectation, and emits
  `shadow_residual` evidence comparing predicted vs. observed signatures (ACK, motion,
  valid measurement count). `diagnostics/estimate.py` sweeps the existing fault-knob space
  (GPIO match, signal, power, marker visibility, firmware ACKs) and reports which θ reproduces
  the observed signature — diagnosis as parameter estimation over a 0-d discrete model.
- **Deliberately no MuJoCo/Isaac/FEA/STEP:** the rig has ~6 distinguishable fault states; a
  higher-fidelity sim would answer questions the sensors cannot discriminate. The
  graph-state + shadow interfaces are where a richer model would slot in later.
- All shadow output is `epistemic=inferred`, `synthetic`, labelled "model" in the UI. A θ that
  reproduces the signature is *model-consistent*, never hardware-verified — a fault outside the
  knob space can still be the true cause.
- **Refutation is executable, not argumentative:** `_refute` in the orchestrator checks each top
  hypothesis by shadow consistency — does the implied fault reproduce the observed signature?
  An LLM "critic" run (pseudo-agent `critic`) may add adversarial commentary, but its output
  is validated citations like any other report and can never override a residual record.
  This satisfies the "Prosecutor/Defense" shape without trusting LLM prose as a falsifier, and
  works with zero API keys.

### D-030 Agent roster: runtime_vision splits into telemetry + vision; qualitative ambiguity gates probing — 2026-10-18
- Implements the rest of stage C. `AgentName` gains `telemetry` (serial lines, timing, event
  traversal) and `vision` (CV measurements, observation quality); `runtime_vision` is kept as a
  legacy enum member so persisted `AgentRun`s deserialize but is never dispatched. New roster:
  orchestrator + code + hardware + telemetry + vision + critic. Deviates from PRD §11's "3
  specialist agents" / "Runtime/Vision Agent" wording; flagged there. Packet tools/edges,
  dispatch rules, and triage schema updated; the one-fan-out + one-follow-up bound is unchanged.
- **Ambiguity is qualitative, not numeric:** PRD §12 forbids probabilities and the fault space
  is too small for honest entropy. The synthesizer is told when ≥2 unresolved hypotheses share
  the top rank and must pick the recommended action whose expected_outcomes discriminate them;
  deterministic fallback attaches the same ambiguity note. Probing stays recommendation-only —
  engineer clicks an action card, the executor enforces grants. No agent writes to the device.

### D-031 Causal chain per incident; counterfactuals are shadow interventions — 2026-10-18
- Implements stage D. `diagnostics/causal.py` builds the five-link chain
  (command → ACK → signal → motion → observed feedback) from run facts + declared structure,
  rendered in the debug chapter. Each link is `yes`/`no`/`unknown`/`unmeasured` — e.g. signal
  voltage is honestly "unmeasured" (we never claimed PWM/voltage measurement).
- Counterfactuals (`do(X = nominal)`) are answered by re-running the shadow with that knob
  forced nominal; the result lands on the leading hypothesis as "Counterfactual: had signal
  been connected, prediction would still show motion — consistent" — a model-level statement,
  never a physical claim. No formal do-calculus; the reduced-order model IS the interventional
  semantics at this fidelity.

### D-032 Studio-style left view rail owns view/layer switching — 2026-10-18
- User asked for a Roblox-Studio-like structure: sections with defined purposes, icons with
  clear text labels, visibly separated views. Implemented as `shell/ViewRail.tsx` — an Astryx
  `SideNav` in `Layout`'s `start` slot with grouped `SideNavItem`s: **View** (Map / Timeline)
  and **Layer** (All / Hardware / Software), each with an icon, text label, and selected
  state. Collapsible to an icon strip (`collapsible`, auto-starts collapsed under 1000px).
- This replaces the in-canvas `CanvasToggles` segmented controls — one place owns
  "what am I looking at", the canvas header keeps only tools (search, expand, run selector).
  Deviation from the D-026 segmented-control pattern; the keyboard layer (D/E, H/S/C)
  drives the same state, and the regions are now rail | canvas | guided panel | drawer —
  four separated zones instead of toggles inside the canvas chrome.
- Home page un-condensed (user: "should not be condensed"): wider frame (1040),
  `ClickableCard` grids for demos and recents, full-width import card. Same modal-first
  open behavior. No functionality moved or removed.

### D-033 IDE-style resizable panels + marketing landing page; decorative type removed — 2026-10-18
- User asked for VS Code/Devin-like panels: the view rail uses SideNav's built-in
  `resizable` (drag handle at its edge, width persisted via `autoSaveId`); the guided
  steps panel uses `useResizable` + an adjacent `ResizeHandle` (320–620px). Panel
  *repositioning* (dragging a panel to another side) is not supported — out of
  scope for the Layout slot model.
- `Selector` dropdowns now use `placement="below"` so menus open under the trigger
  instead of centring the selected item over it.
- Decorative typography removed at user request ("easily usable vibe"): eyebrows
  and chapter names are now plain body-font labels (no mono, no uppercase, no
  letter-spacing). The `.eyebrow`/`.chapters` classes remain as layout hooks.
- Canvas tools are explained, not just labelled: "Expand groups" / "Collapse
  groups" / "Show whole system" get descriptive tooltips and `secondary` (boxed)
  styling — plain-text ghost buttons were illegible as controls.
- New `LandingScreen` before the import screen: product story, why, 3-step how-it-
  works, feature grid, and an "Open the workspace" CTA. The logo/home button now
  returns there. Intended to give judges/evaluators context on a live deployment.

### D-034 Hosted site = replay-only demo; full app stays local — 2026-10-18
- Deployment intent (user): the live website only needs a demo; the functional app
  runs on the engineer's computer. So the built static site must be self-contained.
- `scripts/capture_demo_replay.py` drives a running local API through both demo
  stories (fault A: GPIO mismatch → inspect → verify; fault B: tied hypotheses →
  manual check → verify) and records every request/response the frontend can
  send into `apps/web/public/replay/demo.json` — ~90 routes + an id-keyed
  evidence map. POST responses are keyed by a canonical SHA-1 body hash so the
  same route can serve different bodies (sim vs replay source, approve-once).
- `apps/web/src/lib/api.ts` probes `/api/v1/health` on boot and requires a
  parseable `{ok:true}` JSON — static hosts that SPA-rewrite to a 200 index.html
  do not count as a backend. Unreachable → the bundle is fetched and every `req`
  is served from it (`replayReq`). Anything not recorded gets an honest
  `hosted_demo` ApiError ("download inteGREAT locally for this action") instead
  of silently returning wrong data.
- The websocket is replaced by synthesized `IntegreatEvent`s (`replaySubs`):
  `test.started/serial/observation/completed` are emitted from the recorded run
  detail, `action.completed` and `incident.resolved` from execute POSTs, so the
  app's normal event handlers drive busy/serial/incident state unchanged.
- Incident views are state-gated: the plain `GET /investigations/{iid}` route
  returns the *open* view; a `...#resolved` sibling route is served only after a
  verify_fix execute whose body hash is listed in the bundle's `resolves` map —
  the open → verify → resolved arc stays intact for judges.
- Provenance unchanged: run results still carry `SourceBadge` ("Simulated ·
  connected", "Synthetic replay · good") and a "Hosted demo" banner is shown on
  the landing/import screens. Nothing replayed is presented as live hardware.
- Rejected alternatives: hosting the FastAPI backend (works, but adds ops cost
  and turns a judge-clickable URL into a service to babysit); Pyodide/WASM
  backend (slow, fragile); a second fake implementation (duplicate code to keep
  honest).

### D-035 Projects hub instead of stacked import sections — 2026-10-18
- User asked for a Canva-style project page: demos on the left, big wordmark,
  recent projects in the middle, and a "New project" button that opens the
  import form in a modal. The stacked three-section import page became a
  two-column layout: a 300px demo rail (`ClickableCard`s, unchanged context
  modal) beside a main column with a large `inteGREAT` wordmark, the New
  project CTA, a "What is inteGREAT?" back-to-landing link, and a
  `Your projects` grid.
- The import form (repo path / manifest / netlist + preview + mapping review)
  moved into a `Dialog` — the page is a hub, not a form. Field labels now name
  the artifact plainly: "(Software)", "(Component definitions · YAML)",
  "(Hardware CAD · XML)".
- Recents are deduped by `repo_root` (re-imports update the entry instead of
  stacking identical cards) and capped at 8.

### D-036 Dynamic graph: actuation resolves through the pin, not the object type — 2026-10-18
- Problem: importing a folder with no manifest produced a flat "Unassigned" dump of raw
  filenames, and hardware semantics were servo-shaped — `controls` edges only existed for
  `Servo`/`ESP32Servo` objects, and node ids were hardcoded `mcu:esp32`.
- Actuation is now **pin-mediated**: any pin-writing API (`digitalWrite`, `analogWrite`,
  `ledcWrite`) gets a `configures` edge to `pin:{board}_gpioN` and a `controls` edge to
  whatever component is wired to that pin — resolved structurally, not by type registry.
- Component attribution precedence: (1) declared wiring on the pin; (2) sole declared
  component matching a source object's type (`Servo armServo` → servo); (3) sole declared
  component of the source file's subsystem (`led_control.cpp` in `lighting` → status_led);
  (4) inferred wiring. #3 is what exposes a wrong-pin bug: a write to GPIO18 attributes to
  the component its module was declared for, so `configures` turns `conflicting` against
  the GPIO5 wiring. Deduped to one `GPIO_CONFIG_MISMATCH` issue per (pin, component).
- Inferred hardware: object declarations (`Adafruit_NeoPixel strip` → `led_strip`) and
  name-hinted pin symbols (`LED_PIN` → led) create `unverified`/`inferred` component nodes
  only when no declared component already covers the pin or subsystem — a guess never
  outranks a manifest. Files a manifest doesn't claim cluster by filename stem into
  `subsystem:inferred:<stem>` instead of all landing under "Unassigned".
- Board identity is keyed by `manifest.board.id` (`mcu:{board}`, `pin:{board}_*`); esp32
  manifests produce identical ids, so persisted graphs and the pin model are unchanged.
  ESP32 pin validation stays a manifest-time check, not a global assumption.
- LangGraph/Redis explicitly rejected: the hardcoding was a data-model gap, not an
  orchestration or storage gap. The canonical graph + evidence store stay authoritative.

### D-037 Binary metric family + LED demo (led_state) — 2026-10-18
- `Expectation.metric`/`unit` are free-form; `unit == "state"` marks the binary family.
  Analog: displacement ≥ min_motion_deg = "moved", final within tolerance = pass.
  Binary: any state change = "responded" (`physical_motion`), final == target =
  `physical_state` fact — kept separate because the *interesting* failure is "responded
  but ended wrong".
- New `LedStateEstimator` (`cv_led.py`): ArUco anchor marker locates a fixed-offset ROI;
  calibration records the LED-off baseline brightness; state = ROI mean vs baseline+delta.
  Never guesses: missing anchor → `marker_not_found`; an *off* LED is a valid 0.
- Polarity: manifest `attributes.active_low` declares wiring polarity; `Expectation.on_level`
  records the level the code drives for "on", resolved at proposal via source structure
  (command literal → handler function → callee named for the literal's tail → its write
  level). `INVERTED_LOGIC` fires only when state changed + ended wrong + (polarity provably
  mismatched or on-level unresolved); a *consistent* polarity never emits the finding.
- Sim rig models it honestly: `lit()` = leads connected AND level-on-wired-pin == active
  level; GPIOs idle LOW so an active-low LED is lit at boot. Commanding ON writes HIGH →
  the light visibly turns off: `effect=yes, final_ok=no`, which the shadow sweep
  discriminates from a dead lead (`effect=no`). `do(code drives the active level)` is the
  counterfactual. `SimCamera` renders `render_led_scene` when `exp.unit == "state"`.
- Demo fixtures: `esp32_led_demo` (LED_PIN 5, wired GPIO5), `esp32_led_demo_fault_a`
  (LED_PIN 18), `esp32_led_demo_active_low.yaml` manifest (same repo, Fault C wiring).
  Five `led_*.jsonl` synthetic replays; servo fixtures stay importable as legacy demos.

### D-038 Devin org id derived from /v3/self — 2026-10-18
- Root cause of the create-session 404: `INTEGREAT_DEVIN_ORG_ID` in `.env` carried a stray
  character. The key already knows its org, so `INTEGREAT_DEVIN_ORG_ID` is now optional —
  the client derives `org_id` from `GET /v3/self` and validates an explicit override
  against it instead of trusting pasted config.
- 404 semantics split: a 404 on *create* = org/config error (`DevinUnavailable` with the
  response body surfaced, secrets redacted); a 404 on *poll* = `SessionGone` → the job
  fails cleanly so the engineer can retry instead of hanging on a dead session.

### D-039 Debug chapter split into Overview / Potential causes / AI analysis — 2026-10-18
- User asked for clickable tabs because the incident step had become a scroll of facts,
  chain, hypotheses, evidence, AI review, and tools. `InvestigateStep` now renders an
  Astryx `TabList` (`role="tablist"`) under the incident heading: **Overview** (the
  run story — badge, expected-vs-measured, "In short", facts, collapsed evidence chain,
  pass-state verify), **Potential causes** (leading hypothesis card, suggested check,
  alternatives, all-hypotheses list, count badge on the tab), **AI analysis** (agent
  summary, AI evidence review, more tools/permissions).
- Panels stay mounted with `hidden` rather than unmounting: the `.flow-primary` Space
  shortcut still reaches the suggested check from any tab, and Collapsible open state
  survives switching. The causal chain moved behind a collapsible since it largely
  restates the three headline facts.

### D-040 Project management + live/simulated separation — 2026-10-18
- `PATCH /projects/{pid}` (`ProjectUpdate`): name, `context` notes, `subsystem_names`
  (id → display label; "" restores the derived label), and `repo_path`/`manifest_path`/
  `netlist_path` — any path change rebuilds the graph in place (version + 1, wiring
  confirmations and created_at kept), so "editing files" never forks the project.
  `rescan` and `update_project` both carry `context`/`subsystem_names` across `_build`
  (it constructs a fresh Project — without the carry, notes were silently dropped).
- `DELETE /projects/{pid}` removes every doc (`project_id`, `parent_id`, or `id` = pid)
  plus the event timeline rows for that project. The user's code folder is untouched.
- `project.context` is injected into every agent packet as an `ENGINEER NOTES` section
  explicitly framed as engineer assertion — never a measurement (provenance rule).
- Frontend: `ProjectSettingsDialog` shared by the hub card ⋯ menu (MoreMenu icon trigger
  on each project card) and the workspace top bar's More → "Project settings…". Delete
  is a two-step danger zone; hosted-demo mode disables mutations with an honest banner
  instead of pretending persistence.
- Live/simulated separation: the top bar carries a persistent mode `Badge` (Live rig /
  Replay / Simulated) driven by the current source, and `RunStep` shows a warning
  Notice when live is armed and devices are ready. Simulated/replay verification still
  can't be worded as a live-hardware verification (existing `verify_fix` gating).

### D-041 Analyze view + agent progress + structured AI summary — 2026-10-18
- The guided flow became three freely-switchable views — **Test, Debug, Analyze** —
  instead of numbered steps: debugging is a loop, not a wizard. All AI surface lives
  behind Analyze, fenced by an "everything else on this screen is deterministic" card.
- `Incident.agent_summary` used to be one flat string with "Contradictions:" and "What
  the recommended check shows:" appended — a wall of text. `SynthesisOut` already
  returned them as separate fields, so the incident now stores them structured:
  `agent_summary` (paragraph), `agent_contradictions[]`, `agent_check_explanation`,
  `agent_recommended_action_id`. `AgentRun.summary` still keeps the composite text as
  the audit record. Old incidents degrade gracefully (empty lists, text renders as-is).
- Frontend renders the synthesis as sections + an "Evidence cited" chip row extracted
  from the text, and the recommended check as a real button resolved via `nextCheck()`
  — always a catalog action, never agent-authored text (provenance/bounded-agent rules).
- Live progress (the "what is the AI doing" ask): the orchestrator emits `agent.stage`
  websocket events at each phase — triage → specialists (with the dispatched roster) →
  critique → synthesis — and `agent.reported` already marked per-agent completion.
  The Analyze view renders them as a step checklist with per-agent ✓/…, and the
  Analyze chapter tab shows a "…" while a round runs.
- Test view merges the old Setup+Run steps and stays reachable with an open incident:
  it offers "Run the test again" via the `repeat_test` action so repeated runs stay in
  the same investigation rather than forking a new one. The resolved/verified state
  renders inside Debug — there is no separate locked Verify step.
- AI provenance is surfaced, not just stored: hypotheses carry origin badges
  (`AI` for `origin="agent"`, `Rules` otherwise), and dialogs carry captions
  distinguishing rules-engine suggestions and fixed read-only tool output from
  AI-generated content (Devin repair proposal is captioned as AI).
- Manual-check results are full-width `SelectableCard` buttons (one per
  `result_choices` entry, interpretation shown inline) instead of a Selector dropdown —
  the engineer picks an observed outcome, not an option index.
- The right workspace panel resizes to `50vw` (was 620px cap) so Debug/Analyze can act
  as a real workspace beside the map.
### D-042 Phone camera via explicit LAN HTTP MJPEG source — 2026-10-18
- (Renumbered from upstream D-035 on merge — the number collided with the feature
  branch's projects-hub decision; no code references the old number.)
- Owner requested a phone camera while keeping the laptop usable. Rig setup accepts an
  explicit HTTP MJPEG URL from a phone camera app; no phone browser camera permissions,
  HTTPS hosting, public tunnel, or platform-specific virtual webcam driver is required.
- CameraSource receives frames with host receive timestamps; preview and existing ArUco
  estimation reuse that interface. A fresh source ID requires calibration after reconnect.
- Restrict URLs to literal RFC1918 IPv4; refuse credentials/query/fragment, redirects,
  environment proxies, and non-HTTP schemes. Compressed buffers are capped, reads time out,
  stale frames are unavailable after 5 seconds, and reconnection is explicit.
- Camera transport does not implement LED brightness evaluation or change servo acceptance
  criteria. Real phone/app interoperability remains to be verified on the owner's LAN.
- Local LED notes were renumbered D-034 after the pull introduced upstream D-028–D-033.

### D-043 Direct browser camera with isolated local HTTPS gateway — 2026-10-18
- (Renumbered from upstream D-036 on merge — collided with the dynamic-graph decision.)
- Owner requested an iPhone camera without third-party apps. Safari captures rear-camera
  video after explicit permission, samples bounded JPEG frames, and uploads same-origin
  to the laptop. No microphone, cloud service, external JavaScript, or frame persistence.
- A separate restricted FastAPI app exposes only capture assets, token-gated frame upload,
  and token-gated stop on LAN HTTPS :8443. Main project API remains loopback :8000.
  Both listeners share one CameraManager in a single process; no second service/database.
- Pairing is initiated from laptop rig setup; a 256-bit token travels in URL fragment,
  is removed from page history, and authenticates uploads via header. Replacement, Release,
  Stop, and two-hour expiration invalidate access. Hidden-page cleanup is best effort;
  five-second frame freshness prevents stale camera readiness after disconnect.
- Safari secure-context requirements require trusting a locally generated seven-day demo
  CA on iPhone. Scripts generate certs and run the two listeners; trust installation is
  manual, CA signing key is not retained, and secrets stay in ignored .phone-camera/.
  This avoids opening the unrestricted local development API to the LAN.
- Camera transport preserves host receive timestamps and existing ArUco calibration.
  LED metrics remain separate; browser/synthetic tests are not iPhone hardware validation.

### D-044 History view + provenance labels — 2026-10-18
- User asked for test/debugging history on the workspace — a scrollable list of past
  runs to click through ("like Roblox assessment factories"), instead of a workspace
  that only shows the latest failure.
- New fourth view **History** (`.chapters` now 4 columns; keyboard 1–4 already worked).
  `GET /projects/{pid}/tests` returns every `TestRun` newest-first — a separate runs
  list was needed because passing runs never open an incident, so
  `/projects/{pid}/incidents` was not sufficient.
- Selection semantics (chosen with user): a clicked row becomes *the selected run*.
  Runs with `incident_id` resume their investigation in Debug — open ones are fully
  actionable (existing state machine), resolved ones render the existing read-only
  resolved view. Runs without an incident (passes) render a new read-only `RunRecord`
  branch in Debug. The selection also sets `run`/`runRef`, so the Event flow canvas,
  run selector and serial drawer follow it.
- `FlowPanel` gained a `viewRequest` prop so history clicks land the user on Debug.
- Provenance labels renamed across the UI after "Simulated · connected" confused the
  user (it was `sim` + scenario id `connected`, not a device status): badges now say
  `Live hardware` / `Simulated rig — {condition}` / `Recorded|Synthetic replay — {name}`;
  the top-bar mode chip uses the same wording; scenario ids map to plain conditions
  ("wired as declared", "signal lead off", …). The sim SourcePicker copy now says
  plainly it is a software model, no AI involved.

### D-045 Live environment wording + draggable split drawer — 2026-10-18
- User-facing "rig" renamed to "environment" everywhere: "Environment setup"
  (was Rig setup), "Set up the live environment", "Simulated environment — {condition}",
  "Live environment" source segment, graph region "the physical environment", and the
  `sim://environment` port label. `RigSetupDialog` became `EnvironmentSetupDialog`;
  backend internals (`SimRig`, module names) are code identifiers and were left.
- Bottom drawer is now a VS Code-style panel: top-edge `ResizeHandle` (vertical
  `useResizable`, `collapsible`) — drag down past the header to close, click a tab to
  reopen; size persists via `autoSaveId`.
- Drawer gains a fourth tab, **Camera**: the existing `/devices/camera/stream.mjpg`
  feed with honest states (not connected → setup CTA; stream error → unavailable note;
  caption states the raw view is never itself a measurement).
- Split view: an IconButton opens a second pane beside the first — each pane has its own
  tab set (left uses the header TabList, right its own), the divider drags via a
  horizontal `useResizable`, and dragging it to the right edge closes the split
  (`collapsible` → controlled `split` state), matching "drag it back".
- Follow-up polish (same day): "Board messages" renamed "Serial output". The resize
  handle's invisible hitbox extends ~15px below its 1px line and was eating the top
  half of tab/button clicks — a fixed 16px grip spacer now absorbs it (the pill grip
  sits in that zone, like VS Code's panel sash). Text open/close buttons became
  chevron IconButtons (collapse/expand), matching the VS Code panel chrome.

### D-046 Batched event-stream updates for scroll responsiveness — 2026-10-18
- **Problem:** scrolling felt laggy during/after runs. Each `test.observation` and
  `test.serial` websocket event (~15+/sec) caused three React state updates, so the
  entire workspace re-rendered ~15 times a second; `flowSeq`/`refreshSeq` also made
  `HistoryView` and `EventFlowView` fire a fetch per event.
- **Choice:** batch stream events into a 200ms flush window in `App.tsx`
  (`queueStreamEvent`/`flushEvents`): one `setEvents`, one `setSerial`, one
  `flowSeq` bump per window. Lifecycle events (`test.started`, `test.completed`,
  agent/incident/tool events) still apply immediately and `test.completed` forces a
  flush so UI state never lags the run. Refetches in the two views are capped to one
  per 1.5s with a trailing call. Drawer tables are `React.memo`'d so the 4s device
  poll doesn't rebuild them. Serial still feels live (5 updates/sec) but renders and
  fetches dropped ~3-15x. Trade-off accepted: serial lines appear up to 200ms later
  than the wire — imperceptible next to human scroll/reading speed.
