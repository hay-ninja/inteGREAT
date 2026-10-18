# inteGREAT — Product Requirements Document

**Version:** 1.0  
**Status:** Approved product direction; implementation assumptions marked  
**Build window:** 24–36 hours  
**Primary target:** Existing ESP32 Arduino (C/C++) projects; laptop-hosted backend  
**AI provider:** Google Gemini API  
**Document purpose:** Hand to Claude as the source of truth for architecture, repository scaffolding, implementation, tests, and iterative development.

## 0. Decision legend

- **[CONFIRMED]** Explicitly selected by product owner in three discovery rounds.
- **[RECOMMENDED]** Concrete implementation decision chosen to make the MVP feasible; may be revised if evidence supports an alternative.
- **[ASSUMPTION]** Depends on hardware, time, access, or unresolved facts; verify early.
- **[STRETCH]** Only implement after all P0 acceptance tests pass.

**Priority:** P0 = must work in the live demo; P1 = high-value if time; P2 = post-hackathon. Do not silently promote P1/P2 to P0.

## 1. Executive summary

inteGREAT is a graph-first, AI-native debugging workspace for embedded systems engineers integrating hardware and software. Engineers import an **existing repository** plus electrical/hardware context, review a proposed dependency graph, select a subsystem, define or confirm expected behavior, and run a test. inteGREAT correlates source code, hardware topology, existing serial/host logs, approved diagnostic CLI results, and optional computer-vision observations. A triage orchestrator delegates bounded evidence-gathering tasks to specialized Gemini agents, ranks evidence-grounded hypotheses, and presents the best next diagnostic actions as **clickable buttons**. The engineer performs any physical repair or approved change, reruns the test, and sees whether the system now behaves as expected.

**Positioning:** An interactive, evidence-driven investigation environment—not a general-purpose autonomous repair bot, a generic chatbot, or a firmware instrumentation SDK.

**Primary promise:** Help engineers locate the next useful test and verify a fix without requiring inteGREAT-specific changes to existing firmware.

**Truth constraint:** No firmware modifications does not imply complete observability. inteGREAT must show what is observed, inferred, unverified, or unknown.

## 2. Problem, users, jobs to be done

### Problem

Hardware/software integration failures cross boundaries: source code configures one pin, a schematic declares another, an actuator physically does not move, and available logs may not reveal which part failed. Engineers manually reconcile code, diagrams, logs, command-line tools, and visual observations. General coding assistants often lack a reliable representation of the actual physical system and cannot validate the real-world result.

### Primary user [CONFIRMED]

Embedded systems engineers working on existing embedded projects. Initial implementation is optimized for ESP32 Arduino C/C++ projects, with Raspberry Pi/Linux devices as optional diagnostic gateways.

### Jobs to be done

1. Understand the subsystem and its software/hardware dependencies quickly.
2. Establish which observed behavior violates an engineer-confirmed expectation.
3. Gather missing evidence with minimal effort and controlled tool permissions.
4. Distinguish plausible root causes and choose a high-information next test.
5. Verify a repair using the same reproducible test and preserve the evidence trail.

## 3. Product principles and hard constraints

1. **Graph first [CONFIRMED].** The graph is the primary workspace; chat and command panels support it.
2. **Existing firmware [CONFIRMED].** inteGREAT never requires adding its own logging SDK or instrumentation. Demo firmware may be written for the rig, but inteGREAT must analyze it as an existing, unmodified project.
3. **Subsystem scope [CONFIRMED].** Investigations start locally; dependencies may cross boundaries when justified.
4. **Evidence provenance.** Every substantive finding references actual source files, netlist items, logs, CLI outputs, CV observations, or engineer assertions.
5. **Trust boundaries.** Imported code, logs, docs, and tool outputs are untrusted data, not instructions to agents.
6. **Human control [CONFIRMED].** Session-scoped approval for diagnostic tool categories; individually approve potentially risky operations. No autonomous physical actuation or code patching in MVP.
7. **Deterministic measurement first.** Use OpenCV for servo angle; Gemini vision only for optional interpretation and not as an unverified numeric sensor.
8. **Bounded multi-agent investigations.** The orchestrator dispatches specialized agents with small scoped contexts and strict budgets; no recursive agent swarm.
9. **Demo reliability over breadth.** One fully working end-to-end loop with two different fault classes is more important than generalized import coverage.

## 4. Confirmed scope versus implementation recommendations

| Topic | Confirmed requirement | Recommended MVP realization |
|---|---|---|
| Audience | Embedded systems engineers | ESP32 Arduino example project |
| Onboarding | Repo import, AI graph, engineer hardware verification | Local repo path or upload; source parser; manifest and narrow KiCad importer |
| Hardware documents | Import KiCad netlist with fallback | KiCad exported XML netlist; explicit mapping to MCU pins; JSON/YAML fallback |
| Graph | Subsystems → modules → functions, expandable | React Flow with semantic node/edge types and scope controls |
| Hardware | ESP32, servo, Raspberry Pi, available camera | ESP32 USB serial to laptop; optional Pi as gateway; fixed camera + marker |
| Runtime | Laptop backend; SSH to Linux gateway where applicable | Local serial adapter first; SSH tool adapter second |
| CV | Camera-agnostic OpenCV angle tracking; Gemini visual interpretation | `cv2.VideoCapture` local index; calibrated marker geometry |
| AI | Gemini API, orchestrator + Code, Hardware, Runtime/Vision agents | Structured-output subagent calls; bounded triage |
| CLI | Session approval of tool categories; risky actions need approval | Tool registry with allowlisted arguments and per-session grants |
| Diagnoses | Ranked evidence-backed hypotheses | Deterministic rules + LLM explanations; no invented percentages |
| Demo | Two distinct root causes and full failure→verification | Wrong GPIO mapping; disconnected servo signal or power |
| Interaction | Graph-first, run test, visualize process/failures, action buttons, optional text | Test timeline, highlighted causal/dependency path, ranked action cards |

## 5. MVP user journey

### 5.1 Project onboarding

1. User opens inteGREAT and imports a local ESP32 Arduino repository (or a packaged project upload).
2. User optionally imports an exported KiCad netlist; if missing/unsupported, user supplies a hardware manifest.
3. Backend scans supported source/config files, identifies modules, functions, GPIO usage, and relevant call relationships.
4. Gemini proposes subsystem groupings and mappings between software entities and hardware components, each tagged with evidence and verification status.
5. User reviews proposed connections and confirms/corrects hardware topology. Never present inferred wiring as physically verified.
6. inteGREAT displays the expandable graph and stores a project snapshot.

### 5.2 Select subsystem and configure test

1. User selects Motor Control or clicks the servo node.
2. Graph focuses on the relevant local nodes and immediate external dependencies (power, signal, upstream controller).
3. inteGREAT proposes a test expectation from code (e.g., `when test sends 90° target, marker angle should reach 90° ± 8° within 2 s`).
4. User confirms/edits expected behavior, units, tolerances, timing, and available observation source.
5. User clicks **Run Test**. The test runner is an explicitly configured, engineer-approved operation, not a free-form AI-generated shell command.

### 5.3 Observe, investigate, and act

1. inteGREAT creates a `test_run_id` and collects synchronized or timestamp-correlated serial events and CV measurements.
2. Graph highlights confirmed execution/observation events and any failed expectation. Distinguish `command sent`, `command observed in log`, and `physical motion observed` as different facts.
3. If a mismatch exists, orchestrator launches only relevant subagents with subsystem-scoped context.
4. Agents report structured findings with evidence IDs, contradictions, unknowns, and proposed next tests.
5. UI shows ranked hypotheses and **action buttons**, e.g. **Inspect GPIO mapping**, **Read recent serial output**, **Check servo power manually**, **Repeat motion test**, **Expand power dependencies**.
6. Read-only tools within approved categories execute automatically; actions outside grants prompt for consent. Manual tests show clear instructions and allow user to record the result via buttons or text.
7. New results update the investigation; changed hypotheses are explained and linked to evidence.

### 5.4 Verify fix

1. Engineer applies physical or software repair outside inteGREAT (MVP does not auto-patch or flash).
2. User clicks **Verify Fix**, which reruns the same configured test with the same acceptance thresholds.
3. inteGREAT compares before/after observations and marks `resolved` only if verified expectations pass; otherwise remains `open` or `inconclusive`.
4. UI stores the evidence-backed investigation summary and graph highlights the repaired path.

## 6. Primary demo and fault cases

> **Updated by D-036/D-037 (2026-10-18):** the demo is switching from servo motion to LEDs.
> The graph is now content-derived rather than servo-shaped — pin writes actuate whatever
> the declared wiring connects (`digitalWrite` → `controls` through `pin:{board}_*`), and a
> binary `led_state` metric family (ArUco-anchored ROI brightness) sits beside the analog
> `servo_angle_deg` path. The servo fixtures remain as legacy demos. A third fault joins
> the roster: **Fault C — inverted drive logic** (active-low wiring + active-high code),
> discriminable because a lit-at-boot LED visibly turns *off* on an ON command.
> Live-hardware bring-up still follows this section's servo rig guidance until an LED rig
> exists; all LED demo paths are replay/sim-verified only.

### Physical setup [CONFIRMED + ASSUMPTIONS]

- ESP32 development board running an Arduino C/C++ servo example.
- SG90-class servo or equivalent with a visible pointer/marker.
- Stable camera visible to local OpenCV; portable monitor's camera may work **if** recognized by OS as a capture device. If not, use any compatible webcam or Pi Camera Module 3 via Pi.
- Laptop runs FastAPI, agents, graph backend, and CV adapter. ESP32 is connected by USB serial to laptop or to a Pi gateway. SSH is for Linux hosts, **not** the ESP32 itself.
- Servo powered appropriately for its rated voltage/current, with common ground to the ESP32 signal reference. Do **not** power a servo from the ESP32 3.3V pin. Use a suitable external supply if needed.

### Fault A — Software/configuration mismatch [P0]

- Hardware connection is engineer-verified as servo signal on pin X; Arduino source configures pin Y.
- inteGREAT identifies mismatch between verified hardware graph and source/config evidence.
- Expected result: ranked hypothesis `GPIO mismatch`, exact file/line or config reference, netlist/manifest pin reference, and suggested **Inspect mapping** action.
- Engineer corrects the firmware/project configuration and redeploys manually; inteGREAT reruns the test and confirms expected angle.
- **Important:** For ESP32, GPIO naming, physical header labels, and board-specific pin mappings must be normalized; avoid inventing mappings.

### Fault B — Physical connection failure [P0]

- Software/configuration matches verified graph, but servo signal lead or power is intentionally disconnected (choose the safest reproducible fault).
- Test shows a requested motion and observed non-motion; code and configuration alone cannot prove which physical connection failed.
- inteGREAT ranks physical wiring/power as hypotheses, records inability to measure voltage directly, and offers a **Check signal/power connection** manual test with result buttons.
- Engineer reconnects cable; rerun verifies angle reaches target.
- **Important:** Never claim that serial `command issued` proves a PWM waveform reached the servo. Without measurement, power and signal remain hypotheses.

### Test fixture [RECOMMENDED]

A small pre-existing firmware demo should accept a documented host test request (e.g., `MOVE 90` over serial) or run a repeatable built-in motion sequence. This is **not inteGREAT-specific instrumentation**; it is ordinary project functionality. If the firmware does not support host control, run a preconfigured autonomous sequence and align camera measurements to observed start events. Do not claim universal test triggering.

## 7. Functional requirements

### FR-01 Project ingestion [P0]

- Import repository from local filesystem or uploaded archive. Validate path and size, disallow path traversal, ignore `.git`, build artifacts, binaries, secrets, and huge dependency folders.
- Parse `.ino`, `.cpp`, `.h`, relevant build/config files; collect source references with file path and line range.
- Extract declared GPIO pin assignments and servo control calls using conservative parser/rules. If Tree-sitter is available, use it; otherwise implement explicit patterns and label uncertain matches.
- User can edit/correct inferred metadata.
- Never execute imported source code during ingestion.

### FR-02 Electrical context [P0]

- Accept a **narrow, documented KiCad exported netlist format** (recommended XML). Extract components, reference designators, pins, nets, and net membership.
- Netlist electrical connectivity does not automatically identify application-level device roles; user must confirm mapping from MCU pins/nets to hardware nodes.
- If netlist import fails or lacks relevant pin mappings, offer manifest fallback without blocking onboarding.
- Manifest includes components, pins, connections, power sources, source provenance, and verification status.
- Store unsupported file errors and warnings; do not hallucinate connectivity.

### FR-03 Graph model and visualization [P0]

- Graph node types: `subsystem`, `source_module`, `function`, `mcu`, `pin`, `component`, `power_source`, `interface`, `test`, `observation` (observations may also be overlays instead of graph nodes).
- Edge types: `contains`, `calls`, `configures`, `controls`, `connected_to`, `powered_by`, `reads_from`, `observed_by`, `depends_on`.
- Edge semantics must distinguish source call graph, declared wiring, and inferred dependency. A dependency graph **is not automatically a causal graph**.
- Each node/edge has confidence category (`observed`, `verified`, `inferred`, `unverified`, `conflicting`), source references, and timestamp/version where applicable.
- Default view is subsystem-level; expand module then function on click. Provide focus, breadcrumb, pan/zoom, search, and external-dependency indicators.
- During test, animate/highlight **observed or declared** paths with distinct visual treatment; do not pretend a code path executed unless instrumented/logged evidence supports it.

### FR-04 Subsystem context engine [P0]

- Input: project ID, selected node IDs, incident/test ID, current hypotheses.
- Retrieve relevant graph neighborhood with edge-type weighting; include upstream power dependencies and user-pinned external nodes.
- Retrieve relevant source excerpts, serial/log events, CLI results, expectation, and CV measurements.
- Output a bounded, structured `ContextPacket` with evidence IDs, source citations, uncertainty, and omissions.
- Use deterministic filtering first; optional LLM summarization only for long unstructured documents/logs.
- Expose **Expand Scope** action when evidence suggests a cross-subsystem fault.
- Enforce per-agent token/context budget; never dump entire repository, full video, or unrestricted terminal history.

### FR-05 Tests and expectations [P0]

- AI may propose expectation from code and configuration, but user confirmation is required before using it as pass/fail criterion.
- Expectation fields: trigger/test action, target component, metric, target value, tolerance, observation window, measurement source, provenance, confirmation state.
- Test runner supports a **configured** serial command or engineer-initiated external sequence, not arbitrary generated hardware commands.
- Test states: `configured → running → completed|failed|cancelled`; incident states: `open → investigating → awaiting_engineer → verifying → resolved|inconclusive`.
- Use monotonic timestamps for local timing where available; include UTC wall-clock and source clock metadata. Account for camera/serial latency and dropped frames.

### FR-06 Observability adapters [P0]

- Serial: use `pyserial` to read existing ESP32 output; parse known patterns into structured events; retain raw lines and provenance.
- CLI: capture structured results for approved diagnostic tools, including exit code, stdout/stderr, duration, host, and command ID.
- CV: local OpenCV camera adapter, camera selection, ROI calibration, marker/pointer tracking, angle estimate, measurement confidence, and missing-detection state.
- SSH: optional Pi/Linux gateway adapter. For P0, implement only if the live rig requires it; local USB serial is first-class.
- Camera source adapter interface allows replacement by local webcam or Pi camera bridge without changing the diagnosis engine.
- Gemini vision may inspect **sampled frames** for qualitative description; never replace deterministic angle metrics with unverified LLM measurements.

### FR-07 Agentic diagnosis [P0]

- Gemini-powered **Orchestrator** classifies the incident, chooses relevant agents, maintains investigation state, merges evidence, ranks hypotheses, and proposes tests.
- **Code Agent:** source configuration, pin usage, call relationships, relevant diffs.
- **Hardware Agent:** netlist/manifest, connections, power dependencies, component constraints.
- **Runtime/Vision Agent:** existing logs, approved CLI results, serial timing, CV observations.
- Each agent receives a restricted context packet and permitted tool registry; returns typed JSON matching schema.
- Orchestrator can invoke selected agents concurrently; limit to **one initial fan-out and one evidence-driven follow-up** for MVP. Avoid unbounded loops.
- Findings include supporting and contradicting evidence IDs, unknowns, and proposed tests. LLM outputs are hypotheses, not observations.
- Rank by evidence consistency and diagnostic relevance; do not display unsupported numerical probabilities.
- Suggested next tests should prioritize expected information gain, safety, cost, and ease, but do not claim mathematically optimal selection without a defined model. UI can label **Recommended next step**, not proven globally optimal.

### FR-08 Interactive action buttons [P0]

- Diagnostic action types: `run_readonly_tool`, `request_manual_check`, `repeat_test`, `expand_scope`, `inspect_source`, `inspect_connection`, `verify_fix`, `ask_clarification`.
- Each action card includes label, rationale, expected observation, required permissions, and source/evidence context.
- Clicking an action either executes a permitted tool, opens an approval prompt, shows manual instructions with result choices, or opens a contextual input form.
- Free-text chat can add constraints, describe symptoms, or answer a test question; it must not silently bypass tool permission checks.
- UI updates graph highlighting and hypotheses when results arrive.

### FR-09 Investigation persistence and replay [P0 minimal]

- Persist project, graph snapshot, tests, observations, agent reports, tool calls, decisions, and verification outcomes in SQLite.
- Show a chronological event timeline and current investigation status.
- Full historical playback is P1; a persistent event list with selected graph highlights is sufficient for P0.

## 8. Non-functional requirements

- **Demo responsiveness [RECOMMENDED]:** graph loads within ~3 seconds for the small fixture; CV preview remains usable at ~10–15+ fps on available hardware; initial diagnosis aims for under ~30 seconds excluding external model latency. These are targets, not guaranteed service-level objectives.
- **Reliability:** handle missing camera, disconnected serial, malformed netlist, agent timeout, and Gemini API failure with clear recovery messages. Test and graph remain usable if AI fails.
- **Observability:** structured backend logs with `project_id`, `test_run_id`, `investigation_id`, `agent_run_id`, and `tool_call_id` correlation.
- **Reproducibility:** seed fixtures and recorded observation streams allow offline fallback demonstration.
- **Portability:** run on developer laptop; OS-specific serial/CLI behavior behind adapters.
- **Security:** local-first single-user demo; do not advertise multi-tenant security or remote execution hardening as complete.
- **Cost control:** bounded context packets, max agent calls, timeouts, sampling frames rather than streaming video to Gemini.

## 9. Technical architecture

### 9.1 Topology

```
┌───────────────────────────────────────────────────────────────┐
│ Laptop                                                        │
│ Next.js + React Flow (graph, tests, agent actions, chat)       │
│   │ REST + WebSocket                                          │
│ FastAPI modular monolith                                      │
│   ├─ Ingestion: repo + KiCad + manifest                       │
│   ├─ System graph + scoped context builder                    │
│   ├─ Test/expectation + incident state machine                │
│   ├─ Event store + SQLite                                     │
│   ├─ Gemini orchestrator + 3 specialist agents  (D-030: now 4 —│
│   │    code · hardware · telemetry · vision — + critic pass)  │
│   ├─ Tool registry + session permission manager               │
│   ├─ Serial adapter (USB to ESP32)                            │
│   └─ OpenCV adapter (local webcam)                             │
└───────────────┬───────────────────────┬───────────────────────┘
                │ USB serial            │ optional SSH
           ESP32 + servo         Raspberry Pi / Linux gateway
                │                       │
           physical motion       optional camera/serial tools
                └──────── camera observation ──────────────────
```

**[RECOMMENDED] Stack:** Next.js, TypeScript, React Flow (`@xyflow/react`), FastAPI, Python 3.11+, Pydantic v2, SQLite, SQLAlchemy or `sqlite3`, NetworkX, OpenCV, pyserial, Google Gemini SDK, WebSockets, pytest. Use minimal dependencies and a modular monolith. No Neo4j, Kafka, vector DB, or heavy agent framework for P0.

### 9.2 Data flow

1. Ingest repo and netlist/manifest; produce versioned graph with provenance.
2. Engineer confirms wiring and expectations.
3. Test starts with ID; serial/CV adapters emit observations.
4. Expectation evaluator detects mismatch and creates incident.
5. Context engine selects scoped graph/source/events and redacts secrets.
6. Orchestrator triages and invokes relevant agents.
7. Evidence aggregator validates references, deduplicates, and updates hypotheses.
8. UI receives WebSocket updates and renders highlighted graph plus recommended action buttons.
9. Tool executor performs authorized diagnostics; outputs become evidence; agents may run one follow-up round.
10. Engineer fixes problem; verification reruns expectation and closes incident only on measured success.

### 9.3 Distinguish evidence from inference

- **Observed:** Raw log line, measured angle, tool output, user-recorded manual test result.
- **Verified:** Engineer-confirmed wiring or expectation.
- **Inferred:** Static-analysis mapping, LLM-proposed component relationship.
- **Hypothesis:** Candidate explanation with support/contradiction.
- **Unknown:** Required but unavailable measurement or unverified connection.

Graph animations should never assert unobserved runtime execution. Render predicted/dependency paths differently from observed event paths.

## 10. Data contracts (canonical examples)

Use Pydantic models mirroring these contracts. IDs are stable UUIDs or deterministic scoped identifiers; all references must resolve. All events carry `project_id`, `test_run_id` where applicable, source, and timestamp.

### 10.1 GraphNode

```json
{
  "id": "component:servo_1",
  "project_id": "project_demo",
  "kind": "component",
  "label": "Servo 1",
  "subsystem_id": "subsystem:motor_control",
  "attributes": {"type": "servo", "rated_voltage": "per_datasheet"},
  "verification": "verified",
  "evidence_ids": ["evidence:manifest_servo_1"]
}
```

### 10.2 GraphEdge

```json
{
  "id": "edge:gpio18-servo_signal",
  "source_id": "pin:esp32_gpio18",
  "target_id": "pin:servo_signal",
  "relation": "connected_to",
  "verification": "verified",
  "evidence_ids": ["evidence:engineer_confirmation_1"]
}
```

### 10.3 Observation

```json
{
  "id": "obs:301",
  "project_id": "project_demo",
  "test_run_id": "test:42",
  "source_type": "opencv",
  "source_id": "camera:0",
  "component_id": "component:servo_1",
  "timestamp_utc": "2026-10-17T22:00:01.200Z",
  "elapsed_ms": 1200,
  "metric": "servo_angle_deg",
  "value": 12.4,
  "unit": "deg",
  "measurement_quality": "valid",
  "evidence_ref": "frame:42:1200"
}
```

### 10.4 Expectation

```json
{
  "id": "expectation:servo90",
  "test_definition_id": "testdef:servo90",
  "component_id": "component:servo_1",
  "trigger": {"kind": "configured_serial_command", "value": "MOVE 90"},
  "metric": "servo_angle_deg",
  "target": 90,
  "tolerance": 8,
  "deadline_ms": 2000,
  "confirmed_by_engineer": true,
  "proposed_from_evidence_ids": ["evidence:source_servo_write"]
}
```

### 10.5 AgentReport

```json
{
  "agent": "hardware",
  "investigation_id": "investigation:1",
  "scope_node_ids": ["subsystem:motor_control"],
  "findings": [
    {
      "statement": "Verified servo signal wiring differs from configured GPIO",
      "supporting_evidence_ids": ["evidence:manifest_gpio19", "evidence:source_gpio18"],
      "contradicting_evidence_ids": [],
      "epistemic_status": "inferred"
    }
  ],
  "unknowns": ["Electrical PWM waveform not measured"],
  "proposed_action_ids": ["action:inspect_gpio_mapping"]
}
```

### 10.6 Hypothesis

```json
{
  "id": "hypothesis:wrong_gpio",
  "incident_id": "incident:1",
  "title": "Incorrect GPIO mapping",
  "rank": 1,
  "status": "plausible",
  "supporting_evidence_ids": ["evidence:source_gpio18", "evidence:manifest_gpio19"],
  "contradicting_evidence_ids": [],
  "unknowns": ["Whether actual wiring matches the confirmed manifest"],
  "recommended_action_ids": ["action:inspect_gpio_mapping"]
}
```

### 10.7 DiagnosticAction

```json
{
  "id": "action:read_serial_logs",
  "kind": "run_readonly_tool",
  "label": "Read recent serial output",
  "rationale": "Check whether the firmware acknowledged the test command",
  "tool_name": "read_serial_buffer",
  "arguments": {"device_id": "device:esp32_usb", "max_lines": 100},
  "permission_category": "serial_read",
  "approval_required": false,
  "status": "proposed"
}
```

### 10.8 ContextPacket

```json
{
  "investigation_id": "investigation:1",
  "focus_node_ids": ["subsystem:motor_control"],
  "included_node_ids": ["component:servo_1", "pin:esp32_gpio18"],
  "source_excerpt_ids": ["evidence:source_gpio18"],
  "observation_ids": ["obs:301"],
  "expectation_ids": ["expectation:servo90"],
  "known_unknowns": ["Actual servo supply voltage"],
  "omitted_context_summary": "Unrelated Wi-Fi module excluded",
  "max_token_budget": 6000
}
```

**Implementation notes:** Define enums for kinds/statuses. Reject hallucinated evidence IDs, invalid graph references, malformed agent output, and tools outside the registry. Preserve immutable raw evidence alongside normalized derivatives. Store only paths/metadata for image/video evidence unless explicitly configured to retain frames.

## 11. Agent orchestration specification

### 11.1 Triage Orchestrator

Inputs: current incident, selected subsystem, verified graph, recent observations, agent budget, available tool grants. Outputs: agent dispatch plan, merged hypotheses, recommended actions, user-facing explanation.

Rules:

- Dispatch Code Agent for configuration/API/path issues.
- Dispatch Hardware Agent for wiring/power/netlist questions.
- Dispatch Runtime/Vision Agent for observed behavior, timing, serial/logs, or CV issues. **Updated by D-030:** this role is split into a Telemetry Agent (serial, timing, event traversal) and a Vision Agent (CV measurements, observation quality) — four specialists total.
- May invoke multiple agents in parallel when independent evidence is needed.
- Every agent receives only its scoped packet and registered tools.
- Limit to one initial dispatch and one follow-up dispatch per incident in P0; maximum tool calls per run and total Gemini calls configured centrally.
- Validate reports against JSON schema and evidence registry; reject or label unsupported claims.
- Preserve conflicting evidence and unknowns; do not force a single root cause.
- Do not allow agent text to grant permissions or modify trust status.

### 11.2 Agent tool boundaries

| Agent | Permitted read tools | Prohibited in MVP |
|---|---|---|
| Code | Search repository, inspect bounded file ranges, read parsed pin references, inspect diff | Edit files, run build scripts, flash firmware |
| Hardware | Read netlist, manifest, verified connections, datasheet snippets | Assume physical wiring from schematic; actuate devices |
| Runtime/Vision | Read serial buffer, inspect events, request camera measurements, approved host diagnostics | Change GPIO states, reset devices, write serial commands outside configured test runner |
| └ split per D-030 → | **Telemetry:** serial buffer, events, timing. **Vision:** camera measurements, observation quality | Same prohibitions, per agent |
| Critic (D-029) | Adversarial commentary on hypotheses only; validated like any report | Cannot override deterministic shadow refutation or tool output |
| Orchestrator | Dispatch agents, rank hypotheses, propose action cards | Execute arbitrary shell, bypass approvals, auto-repair |

### 11.3 Agent failure behavior

- Timeout → show partial findings, preserve raw evidence, offer retry.
- Invalid JSON → one bounded schema repair attempt, then mark agent unavailable.
- Missing evidence reference → omit unsupported claim and log validation error.
- Contradictory agents → show contradiction; recommend discriminating test.
- Gemini outage → deterministic graph, logs, CV, and fault rules still function.

### 11.4 Model adapter

Implement `LLMProvider` interface (`generate_structured`, `analyze_image_optional`) with Gemini as first provider. Keep model identifier, temperature, token budget, retry policy, and API key in configuration. Do not hardcode an unverified model ID or expose credentials to frontend.

## 12. Diagnostic engine and next-best-action selection

### P0 fault library

- `GPIO_CONFIG_MISMATCH`: configured pin differs from engineer-verified signal pin.
- `NO_PHYSICAL_MOTION`: command/test requested motion but CV observed insufficient movement.
- `MISSING_SERIAL_ACK`: expected acknowledgment absent; not proof of firmware failure.
- `CAMERA_MEASUREMENT_UNAVAILABLE`: marker not detected or calibration invalid; do not diagnose servo from missing frames.
- `POSSIBLE_POWER_OR_SIGNAL_FAULT`: no movement despite apparently consistent configuration; requires manual or electrical test.

### Ranking method [RECOMMENDED]

Use deterministic evidence rules for obvious contradictions and an explicit qualitative rank for remaining hypotheses. Agent can propose new hypotheses, but they must be supported by evidence and remain labeled `unverified` until tested. No numeric likelihood percentages for MVP.

### Action selection [RECOMMENDED]

Prioritize actions that are safe, low effort, likely to distinguish current top hypotheses, and supported by available tools. Each action must include `expected_outcomes` and what each result would mean. For manual checks, present result buttons such as **Connected**, **Disconnected**, **Unable to verify**, plus optional text.

**Do not claim optimality:** The UI can say `Recommended next test` or `Highest-priority diagnostic action`; mathematically optimal information gain is P1/P2.

## 13. Tool execution, approval, and security

### 13.1 Permission model [CONFIRMED]

- User grants a **tool category** for a specific investigation and target host/device; grants expire when the investigation ends or are revoked.
- Allowed categories might include `repo_read`, `serial_read`, `host_diagnostics_read`, `camera_observe`, `netlist_read`.
- A tool marked read-only may execute without another prompt **only** if its category is granted and its exact arguments pass validation.
- Risky actions (writing files, firmware flash, process kill, reboot, GPIO state changes, arbitrary serial writes) require explicit individual approval and are **not implemented as autonomous actions in P0**.
- Configured test runner commands are approved as part of test setup and executed only on deliberate **Run Test / Verify Fix** clicks; agents cannot invoke them opportunistically.

### 13.2 Registry design

```python
class DiagnosticTool(Protocol):
    name: str
    permission_category: str
    is_read_only: bool
    async def execute(self, args: dict, context: ToolContext) -> ToolResult: ...
```

P0 tools: `search_source`, `read_source_excerpt`, `inspect_gpio_config`, `read_netlist_connections`, `read_serial_buffer`, `read_cv_measurements`, `read_test_events`, `read_project_metadata`.

Optional Linux gateway tools: `read_kernel_log`, `read_service_status`, `read_device_metadata`, all implemented as predefined command templates with constrained arguments—not raw LLM shell strings.

### 13.3 Execution security

- Never run arbitrary shell commands emitted by LLMs. No `shell=True` with untrusted strings.
- Explicit argument schema, fixed executable, timeouts, output caps, process permissions, and working-directory confinement.
- Avoid arbitrary file reads outside imported repository/approved log paths.
- For SSH, restrict host allowlist, credentials, command templates, and device scope. No credential exposure to model context.
- Redact secrets from source/logs and limit retention of raw camera frames.
- Treat repository files, comments, netlists, and logs as untrusted data; ignore prompt-injection instructions embedded within them.
- Record every tool invocation, grant, denial, exit status, and resulting evidence IDs.
- The term “read-only” refers to intended side effects, not a guarantee; allow only audited templates and warn where a tool may affect device state.

## 14. Frontend specification

### Primary layout [CONFIRMED]

```
┌─────────────────────────────────────────────────────────────────────────┐
│ inteGREAT | Project | Device status | Select subsystem | Run Test | Verify │
├─────────────────────────────────────────────┬───────────────────────────┤
│                                             │ Investigation Panel       │
│ INTERACTIVE SYSTEM GRAPH                    │ - Current test/status     │
│ subsystem → module → function               │ - Ranked hypotheses       │
│ hardware + software dependencies            │ - Evidence/unknowns       │
│ highlighted events and failure paths        │ - Action BUTTONS          │
│                                             │ - Contextual text input   │
├─────────────────────────────────────────────┴───────────────────────────┤
│ Timeline / Serial / CV angle plot / Camera preview / Diagnostic output │
└─────────────────────────────────────────────────────────────────────────┘
```

> **Updated by D-028 (2026-10-18):** the "CV angle plot" bottom-strip output is removed. Angle
> is internal evidence for diagnosis/agents; the strip is Serial · Devices · Activity. CV
> data remains available as evidence per the requirement below.

### UX requirements

- Graph is visible on initial project load and remains central throughout investigation.
- Selected subsystem determines graph focus and context retrieval; breadcrumbs show scope.
- Test execution produces progress events and graph highlights with a legend: verified wiring, inferred dependency, observed event, failed expectation, and unknown.
- Right panel displays ranked hypotheses and action cards; recommended next step appears first, with reason and predicted discriminating outcomes.
- Clicking action performs a real operation or opens an actionable modal; never render inert buttons.
- Contextual free-text input allows symptom specification, expectation edits, and manual observations.
- Camera view can be toggled; CV angle/time data remains available as evidence.
- A timeline links each observation, command, agent report, and engineer response to the graph.
- Clear empty/error states: no camera, no serial device, missing manifest, unsupported netlist, model unavailable, insufficient evidence.
- P0 can be desktop-only; responsive/mobile UI is P2.

## 15. API contracts

All routes are under `/api/v1`. Use typed request/response Pydantic models, structured errors, and consistent IDs. WebSocket events use `{type, project_id, investigation_id?, test_run_id?, timestamp_utc, payload}`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/projects/import` | Import repo path/upload and optional netlist/manifest |
| GET | `/projects/{id}` | Project metadata and import warnings |
| GET | `/projects/{id}/graph?scope_node_id=...&depth=...` | Progressive graph retrieval |
| PATCH | `/projects/{id}/graph/verification` | Confirm/correct wiring and inferred mappings |
| GET | `/projects/{id}/subsystems` | List subsystem scopes |
| GET | `/projects/{id}/devices` | Serial/camera/gateway availability |
| POST | `/projects/{id}/expectations/propose` | Generate candidate test expectations |
| POST | `/projects/{id}/expectations/{id}/confirm` | Engineer confirmation/edits |
| POST | `/projects/{id}/tests` | Start a configured test run |
| GET | `/tests/{id}` | Test state and measurements |
| POST | `/tests/{id}/verify` | Rerun same test after engineer repair |
| GET | `/investigations/{id}` | Current state, hypotheses, evidence, actions |
| POST | `/investigations/{id}/diagnose` | Start bounded agent investigation |
| POST | `/investigations/{id}/actions/{action_id}/execute` | Execute validated approved action |
| POST | `/investigations/{id}/manual-results` | Record engineer physical check |
| POST | `/investigations/{id}/messages` | Contextual text input |
| POST | `/investigations/{id}/permissions` | Grant/revoke tool categories |
| WS | `/ws/projects/{id}` | Graph, test, agent, and action events |

**[RECOMMENDED]** To reduce 36-hour workload, collapse closely related endpoints internally but preserve semantic contracts. All mutating actions should be idempotent where practical and return identifiers for async operations.

### WebSocket event types

`project.imported`, `graph.updated`, `scope.changed`, `test.started`, `test.observation`, `expectation.failed`, `incident.created`, `agent.started`, `agent.reported`, `hypotheses.updated`, `action.proposed`, `action.started`, `action.completed`, `action.denied`, `test.verification_completed`, `incident.resolved`, `error`.

## 16. Recommended repository structure

```text
inteGREAT/
├── README.md
├── PRD.md
├── .env.example
├── docker-compose.yml                # optional; don't block local setup
├── apps/
│   ├── web/                          # Next.js + TypeScript
│   │   ├── app/
│   │   ├── components/
│   │   │   ├── graph/
│   │   │   ├── investigation/
│   │   │   ├── observability/
│   │   │   └── onboarding/
│   │   ├── lib/api.ts
│   │   └── types/
│   └── api/                          # FastAPI modular monolith
│       ├── main.py
│       ├── config.py
│       ├── api/routes/
│       ├── models/                   # Pydantic + persistence
│       ├── ingestion/
│       │   ├── repository.py
│       │   ├── arduino_parser.py
│       │   ├── kicad_netlist.py
│       │   └── manifest.py
│       ├── graph/
│       │   ├── builder.py
│       │   ├── query.py
│       │   └── provenance.py
│       ├── context/
│       │   ├── retriever.py
│       │   └── packet.py
│       ├── observations/
│       │   ├── serial_adapter.py
│       │   ├── camera_adapter.py
│       │   ├── cv_angle.py
│       │   └── events.py
│       ├── diagnostics/
│       │   ├── expectations.py
│       │   ├── rules.py
│       │   ├── hypotheses.py
│       │   ├── actions.py
│       │   └── state_machine.py
│       ├── agents/
│       │   ├── orchestrator.py
│       │   ├── code_agent.py
│       │   ├── hardware_agent.py
│       │   ├── runtime_vision_agent.py
│       │   ├── schemas.py
│       │   └── gemini_provider.py
│       ├── tools/
│       │   ├── registry.py
│       │   ├── permissions.py
│       │   ├── executor.py
│       │   └── ssh_gateway.py
│       ├── storage/
│       └── tests/
├── fixtures/
│   ├── esp32_servo_demo/             # existing-style Arduino firmware
│   ├── manifests/
│   ├── kicad/
│   ├── recorded_serial/
│   ├── recorded_cv/
│   └── expected_reports/
├── scripts/
│   ├── start-dev.sh
│   └── seed-demo.py
└── docs/
    ├── architecture.md
    ├── hardware-setup.md
    ├── tool-security.md
    ├── demo-script.md
    └── decisions.md
```

Do not generate empty files for every proposed module unless implementation needs them. Prefer cohesive, tested slices to scaffolding theater.

## 17. Implementation milestones and dependency order

### Phase 0 — Hardware and demo contract (hours 0–3)

- Verify ESP32 USB serial and Arduino example can produce repeatable servo movement.
- Verify usable camera with OpenCV and establish fixed viewpoint/marker calibration.
- Define the two faults and a repeatable manual repair for each.
- Capture a known-good serial/CV trace for fallback.
- Define manifest, graph, observation, expectation, agent report, and action schemas.

**Exit:** one command/test produces physical motion and a measurable angle; both faults can be reproduced safely.

### Phase 1 — Vertical skeleton (hours 3–9)

- FastAPI + Next.js skeleton with graph rendering.
- Import fixture repo and manifest; show verified/inferred edges.
- Add one configured test, serial reader, camera adapter, and event store.
- Build graph overlay for test events.

**Exit:** user can select servo subsystem, run test, see graph and measured outcome.

### Phase 2 — Detection and action loop (hours 9–17)

- Implement deterministic expectation evaluation and fault library.
- Add investigation state and evidence registry.
- Build clickable actions and manual-result input.
- Add permission grants and two or three safe tool implementations.

**Exit:** each demo fault creates an incident with evidence and at least one actionable next test.

### Phase 3 — Gemini agents and context filtering (hours 17–25)

- Implement scoped context packets and three specialist agent schemas. *(D-030: four — runtime/vision split into telemetry + vision.)*
- Add triage orchestrator, selective dispatch, evidence validation, and bounded follow-up.
- Rank hypotheses and render explanation/evidence links.
- Add engineer fix verification.

**Exit:** one full fault→diagnose→action→fix→verify loop works, with traceable evidence.

### Phase 4 — KiCad and polish (hours 25–31)

- Implement narrow exported KiCad XML netlist importer with manifest fallback.
- Polish graph highlights, timelines, loading/error states, camera panel, and demo script.
- Ensure second fault works end to end.

**Exit:** both distinct fault cases pass repeatedly; unsupported netlist gracefully falls back.

### Phase 5 — Reliability and presentation (hours 31–36)

- Run three consecutive full demos; fix failures.
- Record backup evidence/video and seedable offline fixtures.
- Write setup README, permission explanation, and concise architecture diagram.
- Rehearse pitch and explain limits of observability.

**Exit:** stable live demo and recorded fallback. Stop adding features.

### Cut order if behind schedule

1. Cut Gemini frame interpretation (retain deterministic CV).
2. Cut SSH gateway (retain local USB serial).
3. Cut advanced source call graph; retain module/GPIO mapping.
4. Cut KiCad importer from live demo, retain manifest fallback and documented parser stub/fixture only if not misleading.
5. Reduce agent fan-out to two specialist calls while retaining agent contracts.
6. Never cut graph-first test loop, provenance, safety approvals, or fix verification.

## 18. Acceptance criteria

### AC-01 Onboarding

Given a supported ESP32 Arduino repository and manifest, inteGREAT imports source and hardware context, creates an expandable graph, shows source references, and allows engineer verification. Missing/unsupported KiCad input does not block the manifest path.

### AC-02 Graph semantics

User can navigate subsystem→module→function and inspect hardware nodes. Edges show verified/inferred status. During tests, observed events and inferred paths are visually distinct.

### AC-03 Physical measurement

With a calibrated fixed camera, inteGREAT reports servo angle with valid/invalid measurement state. It flags a failure only when the confirmed expectation is violated by a valid measurement. Missing marker does not become a false servo diagnosis.

### AC-04 Fault A

A deliberately mismatched source GPIO and verified hardware pin yields a cited configuration mismatch hypothesis and a working **Inspect GPIO mapping** action. Engineer correction plus retest passes.

### AC-05 Fault B

With consistent configuration but disconnected servo signal/power, inteGREAT detects non-motion, does **not** claim to have measured electrical voltage or PWM, offers a manual connection check, records its result, and verifies reconnection by retest.

### AC-06 Agents

At least two specialized Gemini agents return schema-valid reports for a live incident. Orchestrator references existing evidence IDs and does not invent new observations. Missing agent response fails gracefully.

### AC-07 Tool permissions

Granted read-only category can execute a validated tool without repeated approval. Ungranted category is blocked. Risky tool is individually gated or unavailable. All executions are auditable.

### AC-08 Context scope

Selected subsystem controls graph focus and agent context. Unrelated modules are excluded unless a relevant dependency or engineer expansion justifies inclusion.

### AC-09 Action UX

At least three distinct action buttons perform actual operations: inspect source/graph, run read-only diagnostic, and record manual check or rerun test. Text input accepts a contextual clarification.

### AC-10 Fix verification

A repaired system reruns the same confirmed expectation and marks incident resolved only after valid passing evidence. Failed retest keeps incident open.

### AC-11 Robustness

Camera unavailable, serial disconnected, unsupported KiCad netlist, and Gemini timeout each show recoverable errors. App never fabricates successful measurements or diagnosis.

### AC-12 Demo reliability

Both faults work live in separate runs, and the primary failure→verification flow succeeds three times consecutively before presentation. Recorded fixtures support an honest fallback demo clearly labeled as replay.

## 19. Test plan

- **Unit:** graph edge provenance; pin normalization; manifest parsing; netlist pin/net extraction; scoped retrieval; expectation tolerance/deadline; hypothesis ranking; action permission checks; agent schema validation.
- **Integration:** import→graph; serial/CV→observations; observations→incident; incident→agent context; tool result→hypothesis update; repair→verification.
- **Fault injection:** wrong GPIO, disconnected signal/power, serial unavailable, marker occluded, camera unavailable, invalid netlist, LLM returns invalid evidence IDs, tool denied.
- **Manual hardware tests:** fixed camera angle calibration, repeated servo commands, timing correlation, stable power, safe reconnection procedure.
- **Recorded fixtures:** deterministic serial/CV JSONL streams for local development and CI without physical hardware.

## 20. Risks, unknowns, and explicit assumptions

| Item | Status | Mitigation / decision |
|---|---|---|
| Portable monitor camera enumerates as webcam | **[ASSUMPTION]** | Verify with OS/OpenCV; fallback webcam or Pi camera |
| ESP32 board pin labels and firmware pin semantics | **[ASSUMPTION]** | Verify board variant and pin mapping before fault A |
| Servo, stable power supply, and jumper leads available | **[ASSUMPTION]** | Inventory immediately; use safe rated power/common ground |
| Existing firmware exposes serial logs or controllable behavior | **[ASSUMPTION]** | Select a known example; never require inteGREAT SDK |
| KiCad file maps cleanly to real breadboard wiring | **[ASSUMPTION]** | Treat schematic as declared design; engineer verifies physical wiring |
| Gemini API access, quotas, latency | **[ASSUMPTION]** | Test structured output immediately; fixture fallback |
| Multi-agent calls fit 36-hour budget | **[RISK]** | Bounded agents, typed reports, limited fan-out |
| OpenCV angle robust under lighting/occlusion | **[RISK]** | Fixed viewpoint, high-contrast marker, calibration and invalid-state handling |
| Live fault can be safely reproduced | **[RISK]** | Prefer unplugged signal over risky shorts; power down before rewiring |
| Graph inference may overstate causality | **[RISK]** | Source citations and verified/inferred/observed status everywhere |
| SSH applicability to ESP32 | **[RESOLVED]** | SSH targets Linux gateway only; ESP32 uses USB serial |

## 21. Non-goals and post-MVP roadmap

### Explicitly out of scope for hackathon

- General automatic physical wiring discovery.
- Arbitrary embedded architectures/firmware and complete static analysis.
- Unrestricted LLM shell execution.
- Autonomous firmware flashing, code editing, hardware actuation, or repair.
- Oscilloscope-level electrical assertions without corresponding measurements.
- Arbitrary mechanical CAD (STEP/STL) interpretation.
- Generalized video anomaly detection across unknown hardware.
- Guaranteed causal inference or statistically calibrated root-cause probabilities.
- Production-grade multi-user tenancy, RBAC, cloud agents, or hardened remote SSH service.

### P1 extensions

- Better KiCad project/schematic import, source-to-netlist mapping, and richer pin normalization.
- Optional Pi gateway/companion and more host diagnostic tools.
- Full replay of investigations, screenshot/frame attachments, and CV overlays.
- More source frameworks and richer AST/call graph.
- Data-driven test recommendation scoring and reproducible diagnosis evaluation.

### P2 extensions

- ESP-IDF, Zephyr, ROS, Linux device-tree, and additional MCU families.
- JTAG, SWD, logic analyzer, multimeter, and oscilloscope adapters.
- Schematic/CAD document understanding with human confirmation.
- Multi-device time synchronization, hardware fleet debugging, and team collaboration.
- Calibrated probabilistic fault models with real evaluation data.

## 22. Definition of done

inteGREAT MVP is done when an engineer can **import an existing ESP32 Arduino project, verify a graph of hardware/software dependencies, select the motor subsystem, run a test, see physical evidence and failures reflected in the graph, invoke recommended diagnostic actions as buttons, use approved read-only tools or manual checks, and verify the repair**—for **two distinct fault causes**—without installing inteGREAT-specific firmware instrumentation.

The app must transparently report missing evidence, preserve citations/provenance, and fail safely when a device, camera, tool, or LLM is unavailable.

## 23. Instructions for Claude implementing this PRD

Treat this document as the product contract. Before coding, inspect the repository and identify what exists. Then:

1. Summarize the architecture and distinguish **CONFIRMED**, **RECOMMENDED**, and **ASSUMPTION** decisions.
2. Identify blockers that genuinely prevent Phase 0 (hardware/model access), and use recorded fixtures to proceed on independent software work.
3. Propose a dependency-ordered implementation plan with small verifiable slices and explicit P0 acceptance criteria.
4. Build **vertical slices**, not a large scaffold of placeholders. Prefer working imports→graph→test→evidence→actions→verification before polish.
5. Define Pydantic/TypeScript contracts early and keep the frontend/backend aligned.
6. Implement strict agent tool registries and permission checks. Never let model text become shell commands or hardware actions without validation.
7. Write tests for every deterministic diagnostic rule and critical security boundary.
8. At each milestone, report implemented features, test evidence, known limitations, and next tasks. Never claim hardware verification from simulated data.
9. Do not add features outside P0 until the two-fault demo loop passes. If the time budget becomes tight, follow the documented cut order.
10. Record changes to assumptions and architectural decisions in `docs/decisions.md`; do not silently change confirmed product requirements.

**Suggested first Claude task:** “Read `PRD.md`. Inspect this repository. Produce a Phase 0/1 plan and implement the smallest runnable vertical slice: import a fixture Arduino project plus manifest, render an expandable graph, run a simulated servo test, and highlight an evidence-backed expectation failure. Include backend/frontend contracts and tests. Do not implement unbounded agents or arbitrary shell execution.”
