# inteGREAT UX outline and feature inventory

2026-10-18 · Working design brief, not an adopted redesign. Grounded in the current STATUS, PRD, decisions, and frontend code. This document proposes organization and visibility; it does not remove confirmed requirements or claim new live validation.

## 1. Product definition

**inteGREAT helps an engineer understand why a physical device is not doing what its code expects, choose the next useful check, and verify a repair.**

Primary user remains an embedded systems engineer (PRD §2). Labels and the first-time experience should also be understandable to a student or hobbyist; deeper source, wiring, timing, and provenance remain available to experienced users.

The first successful experience is: open a project → understand the controller-to-servo relationship → confirm a test → see what happened → perform one useful check → repair → rerun the same test and inspect the result.

Three questions should be answerable throughout: **What am I looking at? What do we know? What should I do next?**

## 2. User journey and primary actions

| Stage | User question | Essential content | Main action | Completion / recovery |
|---|---|---|---|---|
| Open project | What system am I working on? | Own project or clearly simulated demo; recent projects; wiring input | Open project | Show imported graph; explain missing wiring or unsupported input |
| Set up | What am I testing, and can we observe it? | Focused component, wiring status, source choice, device readiness when live, expected behavior | Confirm test | Engineer confirms command, target, tolerance, and deadline; setup problems have a direct recovery action |
| Run | Did the device behave as expected? | Confirmed test, progress, command / response / measured motion, actual evidence source | Run test | Pass, fail, or inconclusive; missing measurement is not a failed motor |
| Investigate | What should I check next, and why? | Result summary, leading hypothesis or tied causes, one recommended check, short reason, citations | Perform recommended check | Tool output or explicitly recorded manual result; denial/failure offers a next step |
| Repair and verify | Did my repair solve the problem? | What changed, current source, same acceptance criteria; optional reviewable code fix | Verify repair | Measured pass resolves; fail/inconclusive keeps investigation open |

These are user tasks, not five new application pages. Keep the existing guided workspace; distinguish its pre-project entry from its Setup / Run / Debug / Verify stages.

## 3. Proposed screen structure

### Project entry

One compact choice between **Open my project** and **Try a simulated demo**, plus recent projects. Keep import help near the field that needs it. Wiring inputs can live under **Add wiring information**; explain manifest/netlist terms in plain language before requesting technical formats. Unsupported KiCad input should have a manifest recovery path, not a dead end.

Choose the starting default deliberately: engineering work favors opening a project; a public demo favors trying a simulation. Preserve the user's last context instead of repeatedly forcing onboarding.

### Investigation workspace

- **Top bar:** project, subsystem focus, and a compact source/readiness summary that opens Setup. Put project switching and maintenance actions in the project menu.
- **Main canvas:** dependency graph, default Combined and focused on the relevant subsystem. Two local controls: **Dependencies / Event Flow** and **Combined / Hardware / Software**. Search, zoom, and a legend are supporting canvas tools.
- **Right panel:** current result and one next action. Short explanation and a few relevant citations. Alternatives, full hypotheses, and detailed AI contributions are expandable.
- **Contextual inspector:** one place for the selected component, connection, source excerpt, or event. Preserve the active test and next action when it opens. Use a small selection summary in the panel and the existing detail dialog; do not add another permanent competing sidebar.
- **Measurements:** a collapsed drawer opened by an evidence click or an explicit Measurements control. Angle and Serial are evidence types, not primary application destinations.
- **Project settings / Activity:** device configuration, AI setup, investigation permissions, audit, notes, and saved runs. Sensitive action approval still appears at the point of use.

Avoid a separate page for each AI provider. Provider contribution belongs in the explanation's details and configuration, while source/uncertainty labels remain visible where they affect interpretation.

## 4. Feature inventory: what exists and where it belongs

“Implemented” below means present in software/current code or reported in STATUS; it does not mean independently revalidated during this outline work. STATUS reports simulated browser checks and 100 backend / 17 frontend tests. Live model/Devin calls and physical hardware validation remain outstanding.

| Feature | Job it serves | Existing scope / status | Recommended placement |
|---|---|---|---|
| Repository import and reopening | Load existing firmware without instrumentation | Implemented; ESP32 Arduino scope | Project entry |
| Manifest / KiCad XML and mapping | Provide declared wiring context | Implemented; fallback and confirmation | Import details, then component/connection inspector |
| Wiring verification | Distinguish a schematic from physically checked wiring | Implemented engineer confirmation | Selected connection; show trust status in graph |
| Subsystem selection | Focus the investigation | Implemented | Persistent compact focus control |
| Combined / Hardware / Software | Understand one system through useful layers | Implemented, D-023 | Canvas-local selector |
| Friendly names, relation verbs, legend | Explain components and dependencies | Implemented; clarity still needs user testing | Canvas and inspector |
| Search, expand/collapse, whole system | Navigate detail | Implemented | Secondary canvas controls; avoid presenting every command at equal emphasis |
| Device connection and calibration | Make live observations possible | Implemented in software; real rig outstanding | One Setup destination with contextual readiness links |
| Live / simulation / recorded replay | Choose an observation source honestly | Implemented | Test setup; retain a visible source label beside results |
| Confirmed test expectation | Define success before testing | Implemented | Guided Setup; details expandable after confirmation |
| Run / progress / result facts | Compare expected and observed behavior | Implemented; live rig outstanding | Main guided panel |
| Angle measurements and serial output | Inspect what was recorded | Implemented | Evidence links and Measurements drawer |
| Event Flow and run selection | Understand the recorded sequence | Implemented, D-024 | Alternate canvas view after a run exists |
| Hypotheses, unknowns, and contradictions | Explain plausible causes without overstating certainty | Implemented rules and structured agent paths | One summary in panel, alternatives expandable |
| Recommended checks and outcome meanings | Turn diagnosis into useful work | Implemented fixed catalog | Main contextual action plus Why this check |
| Manual result recording | Capture physical inspection evidence | Implemented explicit choice | Check dialog; include Unable to verify |
| Evidence and source inspection | Make conclusions inspectable | Implemented evidence records | Clickable citations and contextual inspector |
| StepFun orchestration / Gemini specialists | Review scoped evidence and guide investigation | Adapters/routing implemented, D-025; real calls unvalidated | Contextual Review evidence action; provider/run details expandable |
| Devin software fix | Prepare a reviewable change for a software fault | Session workflow implemented, D-025; real calls unvalidated | Conditional repair action after software evidence; separate review dialog |
| Repeat test | Gather new evidence without claiming a repair | Implemented | Secondary contextual action |
| Verify repair | Establish whether the same expectation passes after repair | Implemented, synthetic walkthroughs; live outstanding | Main action once engineer reports a repair |
| Rescan repository | Refresh source context after an external edit | Implemented | In repair-to-verification path and project maintenance menu |
| Persistence, run history, saved replay | Resume and reproduce investigations | Implemented | Automatic persistence; supporting history / save action |
| Notes, permissions, tool audit, activity | Control and explain investigation operations | Implemented | Contextual approval plus advanced Activity/settings access |

## 5. Reduce duplication before removing capabilities

| Current competing concepts | Proposed simplification | Keep accessible |
|---|---|---|
| Rig setup button and Devices tab/menu | One **Setup** destination; all shortcuts open it | Serial connection, release port, camera, calibration |
| Event Flow and generic Timeline | **Event Flow** for the selected test; rename generic timeline **Activity** and move to history | Project events, approvals, errors, audit |
| Angle / Serial / Timeline / Devices / Tool audit tabs always present | One **Measurements** entry; reveal relevant evidence type on demand | Raw records and advanced audit |
| AI review, provider stages, reports, summary, and separate recommendation | One **Review evidence** action and one resulting recommendation area | Actual provider status, specialist findings, rejected claims |
| Inspect / Repeat / Verify / Devin presented together | Show one primary action based on investigation state | Other valid actions as secondary options |
| Failure repeated in notice, title, facts, hypothesis, and summary | One result sentence followed by complementary evidence | Detailed underlying result and unknowns |
| Permanent warnings for unused devices/providers | Show readiness for the active source and contextual availability | Full setup status on demand |

These are navigation proposals. Hiding controls does not remove the underlying capability. Never hide an active simulation label, critical missing-measurement status, permission decision, or the scope of a claimed verification.

## 6. Define the right panel as a state machine

| State | Main message | Primary action |
|---|---|---|
| No confirmed expectation | Define what should happen | Confirm test |
| Live setup incomplete | Name the specific missing setup step | Open relevant setup step |
| Ready | Show test and source | Run test |
| Running | State collection/progress; block overlapping operations | Progress replaces the action |
| Pass without incident | Expected behavior observed on the named source | Start another test or run again, according to context |
| Failed / sufficient evidence | State mismatch and recommended check | Perform check |
| Inconclusive / missing measurement | Explain what could not be observed | Restore observation or rerun |
| Check complete, no repair reported | State what the check established | Next discriminating check when available; offer repair verification only as an explicit engineer choice |
| Software fault with appropriate evidence | Explain why a software fix is relevant | Inspect source or request Devin fix, according to the current recommendation |
| Devin job working | Show real remote status and what the engineer can do meanwhile | View repair progress; never imply local code changed |
| Repair reported / reviewed and applied externally | Confirm source and unchanged acceptance criteria | Verify repair |
| Verification failed / inconclusive | Explain the current result | Continue with a relevant check / restore measurement |
| Verification passed | Name what source verified the repair | Start a new test |

Avoid treating AI availability as a required stage or a successful manual check as a repair. Repeat pass and verified repair remain distinct.

## 7. Copy and information hierarchy

Use **name → role → state → evidence** for component details. Example: **Servo motor** / “Moves the arm” / “No movement observed during this test” / “Camera measurement, 2.0 s.” If the camera record is invalid, use “Movement could not be measured” instead.

Suggested plain-language terms, with technical identity retained in details:

| Technical term | First-time wording |
|---|---|
| Subsystem | Part of the system; keep the actual subsystem name |
| GPIO 18 | GPIO 18 — control pin; role only when supported |
| Serial ACK | Board responded; show the actual message in details |
| Hypothesis | Possible cause |
| Declared wiring | From your schematic; not physically checked |
| Epistemic status | Observed / checked / inferred / unknown, each with an explanation |
| Inconclusive | Could not determine the result, followed by why |
| Rescan | Refresh code after your changes |
| Prepare software fix with Devin | Request a code fix; explain remote review workflow before starting |

Default recommendation structure: **Check [specific thing]** → **Why this check** in one sentence → **Evidence** with citations → **What each result means**. Full IDs, schemas, provider names, and audit metadata belong in details. Important source and trust qualifications stay adjacent to the claim.

## 8. Scope for this UX pass

**Essential visible experience:** focused combined graph, understandable labels, source/readiness, confirmed expectation, result, one next check, evidence access, and verification.

**Supporting views retained:** layer switching, Event Flow, source/wiring inspector, measurements, alternative causes, AI review, and conditional Devin repair. They should be discoverable when relevant, not all competing at first load.

**Advanced access retained:** provider setup/stages, permissions management, full audit, raw serial, detailed timestamps, notes, saved runs/replays, and maintenance.

**Avoid adding during this pass:** separate provider dashboards, a required chat conversation to use the graph, autonomous patch/flash controls, generalized hardware support, graph version-history UI, collaborative accounts, or mobile-only features. This is a proposed prioritization, not permission to remove a confirmed requirement. Preserve the existing Astryx theme and chapter direction; solve hierarchy before restyling.

## 9. Concrete design process and review checklist

1. Agree on the first user and one scenario: an engineer/technical student investigating why the demo servo does not move.
2. Use the inventory to assign each feature exactly one main home: core flow, supporting view, or advanced access. Allow contextual shortcuts to that same home.
3. Sketch five states using the same workspace: imported / ready / failed / check complete / verified. Include one missing-measurement recovery and one software-fix handoff.
4. Write real labels and sample evidence before polishing layout. Mark synthetic examples explicitly. Do not let filler copy conceal missing decisions.
5. Identify the intended primary action in every state; remove competing visual emphasis. Check that returning from evidence restores context.
6. Build one end-to-end Astryx slice and inspect it at 1280×720 and 1024×768. Then test keyboard navigation, long labels, loading, errors, and unavailable providers.
7. Ask a new viewer to identify the selected component, source, test expectation, actual result, uncertainty, and next action without coaching. Treat confusion as a layout/copy problem to investigate.

Suggested evaluation targets, not existing measured results:

- Viewer can describe the selected code-to-hardware relationship within 20 seconds.
- Viewer can identify the next action within 5 seconds of seeing a test result.
- Viewer can open the supporting evidence in one interaction.
- No one mistakes a simulation/replay result for live verification, a model inference for measurement, or a completed check for a repaired device.
- Main action stays visible at the supported desktop sizes; no horizontal page overflow or loss of context when opening evidence.

## 10. Source material to use while designing

- [PRD](../PRD.md): §§2–5 for users, principles, and journey; §7 for required features; §14 for UI; §18 for acceptance criteria. These are authoritative requirements, not a mandate to show every feature at once.
- [STATUS](STATUS.md): current implementation and validation limits. Prefer this over older proposal text when determining what is already built.
- [Decisions](decisions.md): D-021/D-022 for guided Astryx UX; D-023 graph layers; D-024 Event Flow semantics; D-025 provider/repair roles; D-026 current visual direction.
- [Architecture](architecture.md): existing backend/frontend responsibilities.
- [Astryx rules](../apps/web/ASTRYX.md): component/layout implementation constraints.
- [Demo script](demo-script.md): concrete paths to turn into storyboards and usability tasks.
- [Hardware setup](hardware-setup.md): real readiness and recovery requirements.
- [Hackathon context](hackathon-context.md): explain sponsor contributions through the actual workflow without turning them into extra required screens.
- [Earlier UX proposal](ux-investigation-proposal.md): design history; its provider implementation status is older than STATUS.

Recommended first deliverable: **one annotated workspace sketch showing a failed servo test**, with the visible result, focused graph, evidence entry, and exactly one emphasized next action. Use it to settle information hierarchy before making more screens.
