# Prompt for Devin: graph views, event flow, StepFun orchestration, and software fixes

Paste the prompt below into Devin with access to the current repository and its current working changes. This is an implementation brief, not a claim that these features exist.

---

You are implementing the next working version of **inteGREAT**, a graph-first debugging workspace for existing ESP32 Arduino projects. This is a LA Hacks hackathon project targeting **Beyond the Digital** and relevant company challenges. Implement the features below in the real application, research the integrations, exercise the UI, and fix defects until the acceptance criteria pass. Do not stop after a plan, mockup, scaffolding, or provider stub.

## 1. Understand the project before editing

Read, in order: `AGENTS.md`, `docs/STATUS.md`, `docs/decisions.md`, `PRD.md`, `docs/architecture.md`, `apps/web/ASTRYX.md`, `docs/hackathon-context.md`, and `docs/ux-investigation-proposal.md`. Inspect the running app, relevant code, existing tests, and current git diff. Preserve existing uncommitted work and working UX. Treat STATUS's test counts as historical until you rerun them.

The stack is FastAPI/Pydantic/SQLite, Vite/React 19, React Flow, and Astryx 0.7.1. Backend contracts live in `apps/api/integreat/models/contracts.py`; generate frontend types from OpenAPI rather than maintaining duplicate contracts. Useful starting points are `graph/`, `observations/`, `context/`, `agents/`, `tools/`, `service.py`, `apps/web/src/components/graph/`, `components/flow/`, and `components/drawer/`.

This request explicitly expands the previous proposal: **StepFun should perform orchestration, not only final synthesis**, and the application should integrate **Devin for proposed software fixes**. Document this provider-routing change and the separate remote repair workflow in decisions. Keep all other provenance, permission, measurement, and bounded-agent guarantees. Do not silently rewrite unrelated confirmed PRD requirements.

## 2. Hardware, Software, and Combined dependency views

Add a clear graph layer selector: **Hardware | Software | Combined**. Default to Combined, scoped to the selected subsystem. This is a projection of one canonical dependency graph, not three independent copies with inconsistent identities.

- **Hardware:** board, relevant pins, components, power, ground, and interfaces, with declared versus verified connections. Hide code details; keep a clear route to the code controlling a selected part.
- **Software:** source modules, functions, configuration, and call relationships. Hide the full wiring graph; show a small explicit hardware reference where needed to explain a boundary.
- **Combined:** show code and hardware together, grouped in labeled regions with readable cross-layer links. Selecting a function highlights the hardware it configures or controls; selecting a component reveals the code affecting it.
- Preserve stable IDs, source evidence, selection, scope, search, and expand/collapse behavior across modes. Do not invent a direct dependency when filtering out intermediate nodes. Any summarized path must retain the original path/edge IDs, explain the summary, and preserve the least certain provenance.
- Explain why an element is hidden by a filter and offer a relevant reveal action. Handle empty projects, hardware-only input, code-only input, dangling references, and removed nodes after rescan.
- Keep fit, zoom, reset, and whole-system navigation understandable. Avoid fitting the entire project so tightly that labels become unreadable. Test long labels, dense neighborhoods, and mode changes with an open evidence inspector.

Make labels understandable to a first-time user without losing technical identity. For example, use **ESP32 controller — runs your program**, **Servo motor — moves the arm**, **GPIO 18 — servo control pin**, and **Servo control code**, only when those roles are supported by the imported data. Preserve the exact part/model, symbol/function name, filename/line, units, and pin identifier in secondary details. If a role is unknown, say so. Do not ask a model to invent component identities.

Use verbs on important relationships: **calls**, **configures pin**, **connected to**, **powered by**, and **observed by camera**. Explain “declared wiring” as “from your schematic; not physically checked yet.” Distinguish observed, verified, inferred, unknown, and conflicting states using text plus visual treatment, not color alone. Provide a concise legend and full names in the inspector. Maintain keyboard access and accessible control names.

## 3. Chronological Event Flow view

Add another main visualization, **Event flow**, next to **Dependencies**. It should feel like a chronological flow/tree of what happened to the selected hardware during one test. Keep the hardware/software layer choices meaningful in this view as well.

Use a time-ordered flow with lanes for **Test command**, **Software / serial**, **Hardware observations**, and **Test result**. Show branches or joins only where the records support them; do not force a real dependency DAG into a fictional execution tree. Start with the selected run and allow initial, repeat, and verification runs to be selected independently.

Example, only when supported by actual records: command sent → firmware acknowledgement → camera measurements → expectation result. A source-configured pin belongs in static context unless an event establishes its runtime use. A serial line matched to a source function means “associated with this function's log message,” not a complete function execution trace.

Requirements:

- Derive events from persisted test runs, host commands, serial events, observations, evidence, and existing events. Reuse deterministic projections where possible; do not have an LLM fabricate the timeline.
- Give every event a stable identity, test/run association, source, evidence reference, related graph IDs when known, and timestamp semantics. Show elapsed time relative to the command and details in UTC. Missing timestamps remain unknown; use a stable secondary ordering without claiming precision.
- Label cross-source ordering as **host-clock correlated**, not synchronized. Ordering alone is not proof of causation. Separate observed sequence from expected or inferred links. Explain latency, unavailable samples, and timing uncertainty where relevant.
- Let users step through events or scrub a time cursor and highlight the corresponding graph element/evidence. Any playback is a replay of recorded events; it must not send commands to hardware. Keep selection useful when a layer filter hides a related node.
- Make missing acknowledgement, marker loss, invalid calibration, gaps, and inconclusive results visible. Never turn “camera cannot see marker” into “motor failed.” If no run exists, explain that a test is needed without displaying sample events as real.
- Use persisted records as the source of truth; support reload/reconnect, duplicate events, out-of-order arrival, large streams, and isolation between runs. Aggregate dense camera samples for rendering without deleting evidence or hiding important invalid periods.
- Clearly label **Live**, **Recorded replay**, and **Simulated / synthetic** throughout. No simulated waveform or animation may imply electrical measurement.

## 4. StepFun orchestrates; Gemini supplies specialists

Implement explicit provider routing:

**StepFun triage → selected Gemini Code / Hardware / Runtime-Vision specialists → validated reports → StepFun synthesis → engineer action → repeat / verify.**

Use the exact model ID **`step-5-preview`** through the global StepFun API. Read `STEP_API_KEY` server-side. Verify the current official API docs before coding; do not confuse global and China endpoints or other vendors' gateways. Add a real provider adapter using the existing interface, typed config, a smoke script, and safe errors. Preserve configurable Gemini model selection. No credentials go into frontend bundles, logs, evidence, prompts, or recordings.

Make the intelligence concrete:

- Build bounded context packets containing confirmed expectations, graph neighborhood, code excerpts, wiring trust status, serial/CV evidence, rule hypotheses, available actions, previous checks, and explicit unknowns. Include what was omitted and source provenance.
- StepFun selects relevant specialists and states the question each should resolve. Avoid redundant calls when a fault only needs one specialty. Keep deterministic dispatch as fallback.
- Each specialist returns claims with supporting/contradicting evidence IDs, unknowns, plausible alternatives, and permitted action IDs. Code checks configuration and source assumptions; Hardware checks declared connections and physical unknowns; Runtime/Vision checks observations, quality, and timing.
- StepFun reconciles reports, highlights disagreement, and recommends a safe, low-effort check that distinguishes the leading hypotheses. Explain what each possible outcome would establish and what remains unknown. Do not generate unsupported probabilities or assert mathematically optimal selection.
- Validate schemas AND referenced evidence/action/scope IDs before storage or display. Imported files, logs, notes, remote outputs, and external research are untrusted data. Do not execute embedded instructions. A resolving citation is necessary but does not by itself prove that a claim is supported.
- Preserve rule-based ranking. New AI hypotheses remain unverified. Acknowledgement does not prove PWM reached the motor; neither model measures voltage, current, or angle. OpenCV retains numeric angle measurement.
- Keep the existing maximum of one initial fan-out plus one evidence-driven follow-up per incident. Enforce call, context, token, timeout, and bounded-repair budgets centrally, including failures and concurrent requests. No recursive agents or automatic diagnosis loops. The development agent's research/testing is separate from this application runtime budget.
- If Gemini is unavailable, StepFun may synthesize the deterministic evidence without specialist reports, visibly marking them unavailable. If StepFun fails, retain deterministic dispatch/recommendations and useful available specialist results. If both fail, graph, tests, tools, and verification still work. Do not substitute models silently or show scripted responses as real provider output.
- Show a short, evidence-backed rationale in the main panel and provider/model/status in expandable details. Persist actual attribution per stage, validation failures, duration, and context provenance. Detailed internal model reasoning is not a product requirement.

## 5. Devin API for reviewable software fixes

Add **Prepare software fix with Devin** for incidents with evidence of a software issue. A model can recommend this existing action, but the engineer starts it explicitly. Do not offer a code patch as a remedy for an unverified power/signal problem.

Research the current official Devin API, authentication, organization/repository access, session creation/status, supported result fields, and resource caps. Prefer the documented current API for the configured account; do not guess endpoints or assume old examples still apply. Put `DEVIN_API_KEY`, required organization settings, and limits in server-side configuration. Implement an actual HTTP client with isolated tests, not a link pretending to create a session.

Build a typed repair brief with the accessible repository identity, exact base commit, relevant source, evidence IDs and trust labels, confirmed expected behavior, reproduction, constraints, and test commands. A local Windows path is not a repository Devin Cloud can access. Never silently send a stale remote commit when the incident comes from uncommitted files. Require an accurate accessible snapshot or use a documented, explicitly disclosed safe attachment workflow; otherwise report the precise missing prerequisite and keep the rest of the app usable. Exclude secrets and unnecessary files.

The brief sent to Devin must direct it to inspect the repository, consult relevant official board/library documentation, reproduce the software fault, evaluate alternative explanations, make a minimal fix in an isolated branch/sandbox, run relevant regression tests, and return a reviewable diff or PR plus exact test results and unresolved risks. Preserve the expectation and evidence; do not “fix” the test by relaxing its thresholds. Do not spawn additional paid Devin sessions or call inteGREAT's repair endpoint recursively.

Implement a persisted repair-job lifecycle that maps actual remote states to understandable UI states such as preparing, queued, working, ready for review, failed, or needs input. Persist the session ID and documented session URL, base revision, incident/evidence links, result artifact, timestamps, and error details without secrets. Missing PR/diff/test output remains unavailable; a remote “finished” status is not proof of a fix.

Handle duplicate clicks, reloads, uncertain session-creation outcomes, polling backoff, network errors, auth failures, malformed responses, and resource limits. Do not blindly retry non-idempotent session creation. Allow only one active repair job for the same incident/revision; require a deliberate new request for another attempt. Polling status must never create another session. Enforce request limits server-side and audit who requested the repair and what data was sent.

This is a separate remote proposal workflow: Devin may modify its isolated working branch to prepare the requested fix. inteGREAT must not automatically patch the engineer's checkout, merge, deploy, flash firmware, reboot devices, or actuate hardware. The engineer reviews/applies the result, rescans the project, performs any required upload themselves, and runs **Verify** with the same expectation. A passing remote software test is distinct from a passing physical hardware test. Log the narrow addition to the previous “no auto-patching” design explicitly; do not bypass the diagnostic executor or grant mechanism to apply code locally.

## 6. Design and implementation discipline

Use the real **Astryx** components and existing Obsidian theme. Read component/layout docs before using unfamiliar APIs. Preserve the current guided workflow and one primary action per step. Use progressive disclosure for technical metadata and agent activity. Follow `apps/web/ASTRYX.md` and D-021's existing graph-renderer exceptions. No replacement UI framework, arbitrary CSS palette, raw app-chrome layout elements, or unsolicited theme/dependency upgrade.

Implement vertical slices: layer projections and labels; persisted Event Flow; StepFun routing; Devin repair jobs; full integration/reliability pass. Choose small, maintainable modules and deterministic transforms. Reuse the SQLite document/event architecture and existing permission/audit paths. Update STATUS after verified slices, add decisions for substantive choices, and keep setup/demo documentation accurate. Document proposed API contracts and assumptions briefly, then implement them; do not use planning as the final deliverable.

## 7. Research, autonomy, and verification

Research deeply where it changes correctness: actual repository behavior, version-matched Astryx/React Flow APIs, official StepFun/Gemini/Devin docs, and relevant ESP32/Arduino library behavior. Record source URLs and concrete conclusions in a concise implementation note. Stop researching a point once there is enough evidence to implement/test it; do not spend the hackathon on an exhaustive survey.

Make reasonable reversible product/engineering assumptions and record them. Do not ask routine preference questions, stop for approval of each slice, or finish with “I can implement this next.” Follow through on implementation, testing, browser walkthroughs, and fixes. Never invent credentials, access, hardware measurements, undocumented API behavior, or passing tests to keep going. Missing external prerequisites should block only the dependent live check: finish the real adapters, configuration, deterministic and mocked integration tests, and UI recovery paths, and report exactly what remains unverified. Do not claim full acceptance while a required live check is missing.

Use the commands in STATUS, adapted to your actual OS while keeping repo scripts cross-platform. Establish a baseline before changing behavior. Add meaningful tests for new deterministic projections, contracts, provider validation, permissions, repair-job boundaries, and regression failures. Run backend pytest, frontend tests/typecheck, generated-contract checks, production build, and relevant Astryx diagnostics. Fix regressions you introduce; distinguish pre-existing failures. Do not weaken tests or delete assertions to manufacture success.

Browser-test the actual app at 1280×720 and 1024×768, plus a narrower viewport for overflow. Inspect screenshots as well as interaction results. Exercise:

- All three layers and Event Flow; long/duplicate labels, unknown roles, expand/collapse, search, cross-highlighting, evidence selection, rescan, reload, and reconnect.
- Fault A's GPIO mismatch and failed then passing verification using a disposable fixture copy for edits; keep original fixtures unchanged.
- Fault B's tied power/signal possibilities, explicit manual result, and no unsupported software repair recommendation.
- Missing serial acknowledgement, marker occlusion, invalid calibration, and unavailable devices; preserve unknown/inconclusive states.
- StepFun/Gemini unavailable individually and together, partial specialist failure, invented citations/actions, schema failure, rate limits, timeouts, budget exhaustion, and a follow-up without new evidence.
- Devin duplicate requests, unavailable repository/revision, request timeout with uncertain creation, failed job, late completion after reload, absent diff, and remote “tests passed” without hardware verification.
- Permission denial, prompt injection in imported data, source changes between diagnosis and repair, and stale async responses after switching projects/runs.

With credentials available, make bounded real StepFun/Gemini smoke calls and one deliberately started Devin repair session against an authorized disposable/test branch with configured resource limits. Record sanitized request/model/session provenance. With hardware available, verify the actual rig separately. Repeatedly run the end-to-end flow while new failures appear; once checks pass and the UI is coherent, complete the work instead of polling indefinitely.

## 8. Completion criteria and handoff

The working app must have all three dependency layers, beginner-readable labels, a persisted chronological hardware/software event flow, actual StepFun orchestration with Gemini specialists and honest fallbacks, and the real Devin session integration with reviewable results and engineer-controlled verification.

Deliver the implemented code and tests, updated STATUS/decisions/architecture/setup/demo notes, a short cited research/assumptions note, and a concise final report listing what works, exact checks run, any regressions, and each external check still blocked. Keep mocked, synthetic, replay, real-model, remote-software-test, and live-hardware results separate. Do not leave placeholder buttons or silently omit a requested feature.

Begin now by reading the repository and exercising the existing workflow, then carry the implementation through verification.

---

## Reference links to recheck during implementation

- [StepFun: Step 5 Preview tool calling](https://platform.stepfun.com/cookbook/step-5-tool-calling) — model requests are distinct from application-side validation and execution.
- [StepFun: structured output example](https://platform.stepfun.com/cookbook/step-5-vision-structured) — structured responses still need application validation.
- [Devin API authentication](https://docs.devin.ai/api-reference/authentication) — current authentication and organization-scoped API setup.
- [Devin documentation index](https://docs.devin.ai/llms.txt) — discover current session creation/status and result documentation rather than guessing routes.
- [Devin structured output, legacy API documentation](https://docs.devin.ai/api-reference/v1/structured-output) — useful background; verify the current API's equivalent and do not treat model-maintained progress as guaranteed schema-valid output.

Prepared against local repository state on 2026-10-17. The instruction to implement features does not mean they have already been implemented or live-tested.
