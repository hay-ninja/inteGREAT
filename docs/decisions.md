# Decision log

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
