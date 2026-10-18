# Devpost submission — inteGREAT

Copy-paste source for the LA Hacks AI Hackathon submission. Team-only fields (emails,
universities, Gemini project number, ASI:One handles) are marked TODO.

## Project overview

**Project name:** `inteGREAT`

**Elevator pitch:**
```
A graph-first workspace to debug, test, and fix embedded systems — import your ESP32 project, run one real test, and follow the evidence to the fix.
```

## Project details

### About the project (paste into Devpost Markdown editor)

```markdown
## Inspiration

Every embedded engineer knows the moment: the firmware says it moved, the camera says nothing happened, and the bug is somewhere between a `#define`, a jumper wire, and a $3 servo. Coding assistants only see the repo. A multimeter only sees the pin. Neither can tell you which side of the software/hardware boundary is lying to you. We wanted a debugging workspace that holds both halves in one picture — and is honest about what it actually measured versus what it merely inferred.

## What it does

inteGREAT is a graph-first, evidence-driven debugging workspace for **existing** ESP32 Arduino projects — no firmware instrumentation or SDK required.

- **Import** a repo plus a KiCad netlist or a hardware manifest → one dependency graph spanning software and hardware, viewable in three projections (Combined / Hardware / Software).
- **Suggest a test from the code** — inteGREAT proposes a pass/fail expectation with cited source lines; the engineer confirms it before it means anything.
- **Run the test** — serial output and camera observations (ArUco servo-angle markers, drag-to-mark LED regions) are captured on one host-clock-correlated timeline.
- **On failure**, an incident opens with ranked hypotheses where every claim cites evidence, plus the recommended next test as clickable actions: inspect source, read serial buffer, record a manual physical check, repeat the test, verify the fix.
- **Provenance everywhere.** Observed ≠ verified ≠ inferred ≠ unknown. A missing camera frame is "measurement unavailable" — never a hardware fault. Ordering on the timeline is labeled "correlated, not synchronized."
- **Bounded AI, on a leash.** StepFun `step-5-preview` orchestrates triage and synthesis; Gemini specialists analyze scoped evidence packets for code, hardware, telemetry, and vision. Every cited evidence ID is validated against the real catalog — invented citations are dropped and logged. Deterministic rules keep the ranking, so the product works end-to-end even with AI providers down.
- **Accountable autonomy.** A digital-shadow simulation refutes top hypotheses with counterfactuals (`do(signal=connected)`) — diagnosis as parameter estimation, executable and authoritative over prose. An optional engineer-controlled flow hands a typed fix brief to a Devin session on an isolated branch; inteGREAT itself never patches, flashes, or actuates anything without approval.
- **No arbitrary execution.** Diagnostics are fixed templates in a permissioned tool registry — no `shell=True`, no AI-authored commands, individually approved and fully audited.

## How we built it

- **Backend:** FastAPI modular monolith; Pydantic models are the single source of truth; frontend types are generated from the OpenAPI schema.
- **Persistence:** typed JSON document store plus an append-only event log in SQLite — the event table powers both the timeline and WebSocket replay.
- **Graph:** tree-sitter source parsing, a KiCad XML netlist importer (defusedxml), and YAML manifests — every node and edge carries provenance and a verification state.
- **CV:** OpenCV ArUco markers for servo angle; ArUco-anchored or drag-to-mark LED brightness ROIs; a "blink-to-find" locator that toggles the LED over serial and diffs frames. Webcam, MJPEG phone apps, or iPhone Safari via a cert'd LAN capture gateway.
- **Safety:** one tool-execution path — registry → permission check → audit. Session-scoped grants, risky categories refused outright, agents can never self-approve.
- **Frontend:** React 19 + Astryx design system with a custom Obsidian-style theme; React Flow graph with layer projections, an event-flow scrubber, and a guided flow with one primary action per step.
- **Hosted demo:** the deployed build is a self-contained recorded-replay bundle — judges see the real open → verify → resolved arc, honestly badged "Hosted demo — a recorded session."

## Challenges we ran into

- **Honest observability is hard.** Opening a serial port resets most ESP32 boards (DTR/RTS), so a "read-only" open isn't read-only. A serial ACK isn't proof a PWM edge reached the servo. Matching `Serial.print` literals to source is the only execution signal available without touching firmware — we render it as exactly that and no more.
- **Making AI accountable.** LLMs will cite plausible-looking evidence IDs that don't exist. The fix: schema validation plus a citation check against each agent's evidence catalog, dropped-and-logged on miss, deterministic rules owning the ranking, and a hard budget of one fan-out plus one evidence-driven follow-up.
- **Provider quirks, found the hard way.** httpx's hidden 5s default beat our app timeouts; `step-5-preview` spends reasoning tokens inside `max_tokens`, so small budgets return empty content. Both are fixed and covered by tests.
- **Scope discipline.** We cut SSH gateways and Gemini frame interpretation to keep the failure → evidence → repair → measured-verification loop airtight.

## Accomplishments we're proud of

- The full loop verified end-to-end for **three distinct fault classes** — wrong GPIO, disconnected lead, inverted active-low/active-high logic — each diagnosed distinctly, each verified through the same measured test.
- Live-verified the real provider chain on real incident data: StepFun triage → Gemini specialists → StepFun synthesis, plus a real Devin repair session.
- 174 backend + 17 frontend tests, headless-browser walkthroughs at three resolutions, and a hosted demo that works with no backend at all.
- An interface a non-hardware person can follow: "the board received the command and replied OK, but the arm never moved."

## What we learned

Truth-telling scales better than confidence. Once the UI commits to labeling every fact — live hardware, simulated rig, recorded replay, inferred, unmeasured — engineers trust the tool *more*, not less. The epistemology isn't a disclaimer; it's the product.

## What's next

Live validation on the physical rig (the bring-up checklist is written), real captured replays, and letting agents propose registered tool calls through the same permissioned executor — a caller change, not a security redesign.
```

### Built with (tags, max 25 — pick from these)

```
python, fastapi, react, typescript, vite, sqlite, pydantic, opencv, pyserial,
gemini, stepfun, devin, esp32, arduino, embedded-systems, hardware, computer-vision,
websockets, react-flow, kicad, aruco, pytest, tree-sitter, mjpeg
```

### Try it out links

- `https://github.com/hay-ninja/inteGREAT` (verified public)

### Video demo link

TODO — record ~2–3 min following `docs/demo-script.md` (graph → run → incident →
hypothesis → fix → verify). Hosted demo or localhost both work; keep the source
badges visible.

## Additional info

- **Sponsor / Special Prizes to check:** Cognition – Best Use of Devin · Espressif –
  Best Use of Espressif · [MLH] Best Use of Gemini API · Stepfun – Get It Done with
  Step 5 Preview · Paper – Best Designed Hack
- **GitHub Repo:** `https://github.com/hay-ninja/inteGREAT`
- **Track:** **Beyond the Digital**
- **Emails / universities / team names:** TODO (form wants exact LA Hacks login emails;
  names format "First Last, First Last")
- **GoDaddy domains:** none
- **Which AI tools did you use:** Gemini + Other (StepFun step-5-preview, Devin)
- **Did you implement a generative AI model or API?**

```
Yes — two providers with distinct, inspectable roles, plus an optional repair agent. StepFun step-5-preview is the orchestrator: it triages each incident (choosing which specialists to run, and fewer when the fault doesn't need them) and synthesizes findings into a summary with a recommended next test. Google Gemini powers the specialist agents (code, hardware, telemetry, vision), each answering over a scoped evidence packet. All agent output is schema-validated; cited evidence IDs are checked against the real evidence catalog and fabricated citations are dropped and logged. Deterministic rules retain hypothesis ranking and a full fallback runs the product with no AI available. Separately, an engineer-controlled flow can hand a typed fix brief to a Devin session on an isolated remote branch — inteGREAT never patches or flashes itself.
```

- **Gemini Project Number:** TODO (AI Studio → Get API key → project number) — needed
  for the MLH Gemini prize.
- **ASI:One handles:** marked required on the form — register at asi1.ai or leave a
  placeholder and flag it (Fetch.ai prize not otherwise targeted).
