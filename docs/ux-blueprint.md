# inteGREAT Product & UX Blueprint — unified debugging shell

2026-10-18 · Product-design document. Grounded in `ux-product-outline.md`, `ai-context-brief.md`,
STATUS, and the current React/Astryx implementation. This consolidates information hierarchy;
it does not remove confirmed PRD requirements and does not claim new validation.

Design north star: a 2 AM engineer should be able to answer, in one glance —
**What am I looking at? What do we know? What do I do next?**

---

## Part 1 — Unified layout & viewport shell

### 1.1 The fixed four-region shell

```
┌──────────────────────────────────────────────────────────────────────┐
│ TOP BAR (h=48)   brand · project · focus · source chip · rig state   │
├──────────────────────────────────────────────┬───────────────────────┤
│                                              │  GUIDED INSPECTOR     │
│                                              │  (w=400–420, fixed)   │
│   CANVAS (flexible)                          │  · chapter strip      │
│   Dependencies | Event Flow                  │  · state message      │
│   Combined | Hardware | Software             │  · ONE primary action │
│                                              │  · boxed evidence     │
│                                              │  · collapsed detail   │
├──────────────────────────────────────────────┴───────────────────────┤
│ TELEMETRY DRAWER (collapsed h=36 bar / expanded ≤40% height)         │
│ Angle · Serial · Devices · Activity                                  │
└──────────────────────────────────────────────────────────────────────┘
```

Four regions, four jobs:

- **Top Bar — "where am I."** Brand, project name, subsystem focus selector, a single
  source+readiness chip (`Simulated`, `Live · ESP32 on COM4`, `Recorded replay`), device dots,
  project menu (rescan, rig setup, switch project). No other controls may appear here.
- **Canvas — "what am I looking at."** Exactly one of two views: dependency graph or event flow.
  Canvas-local controls only: view toggle, layer toggle, run selector (event flow), search,
  expand/collapse, zoom, legend. Nothing project-level lives here.
- **Guided Inspector — "what do we know / what do I do next."** The numbered chapter strip
  (01 SETUP · 02 RUN · 03 DEBUG · 04 VERIFY) plus the state-driven content below it.
  This is the only place primary actions live — the canvas never carries a primary action.
- **Telemetry Drawer — "show me the raw records."** Collapsed to a 36px tab bar by default;
  opens on evidence click or explicit tab click. It is supporting evidence, never a destination.
  Angle plot, Serial, Devices status, Activity (renamed generic timeline + tool audit).

### 1.2 Canvas mode behavior

**Dependencies mode (default).** Combined layer focused on the active subsystem.
Selection of a node/edge raises the *contextual inspector card* — a floating card anchored to
the canvas edge (not a third permanent sidebar), with name → role → state → evidence and a
"Show code that touches this" / "Show hardware it drives" reveal. The guided panel's current
step and primary action remain visible while it is open.

**Event Flow mode.** Becomes meaningful only after a run exists. Same shell: the right panel
keeps its state and primary action; the canvas swaps to the four lanes
(Test command / Software·serial / Hardware observations / Test result) with a run selector
(`Initial — fail`, `Verify — pass`) and the step scrubber. Lane labels are dimmed when the
active graph layer hides that evidence class. Selecting an event raises the same contextual
inspector pattern — one selected-thing card everywhere, not per-view inspectors.

**Mode-switch rule.** Switching views never changes investigation state, selection scope, or
the guided step. An event's "In the graph" link jumps back to Dependencies with the node
revealed; a node's "Observed in run" link jumps to Event Flow with the event selected.

### 1.3 Where setup, calibration, and ingestion live

These are **lifecycle-phase features, not runtime debugging features** — they get a home, not
permanent screen real estate:

- **Import / ingestion** lives on the entry screen only (demo → reopen → import).
  Once inside a project, re-import is `Rescan repository` in the project menu.
- **Device setup & calibration** live in one **Setup destination** — the Rig setup dialog
  (serial connect/release, camera select + ArUco calibration, readiness summary). Every
  "not ready" state anywhere in the app links here with the specific missing step named.
- The Top Bar keeps only a *status summary* (device dots + source chip); details and actions
  are always one click into the Setup destination.

This kills the current duplication where "Rig setup" is a top-bar button, a More-menu item, a
drawer tab, and a flow-panel recovery button — four surfaces, one destination. All four keep
working as shortcuts; they all open the same dialog with the right section focused.

### 1.4 Viewport budgets (1280×720 and 1024×768)

| Region | 1280 | 1024 | Rule |
|---|---|---|---|
| Top bar | 48px | 48px | never wraps; device labels collapse to dots+tooltip at ≤1100 |
| Right inspector | 420px | 380px | fixed floor 360px; internal scroll, never page scroll |
| Telemetry drawer open | ≤40% height | ≤40% height | overlays canvas bottom, does not push it |
| Canvas | remainder | remainder | min 560px wide at 1024; canvas-local controls wrap onto a second row |

No horizontal scrollbars at either size. The inspector scrolls internally; the drawer scrolls
internally; the page itself never scrolls inside a project.

---

## Part 2 — State-by-state walkthrough

Conventions: **PRIMARY** = filled button, exactly one per state. *Secondary* = ghost buttons.
`{copy}` = exact UI copy. Eyebrow labels render uppercase mono (`03 · DEBUG — THE INCIDENT`).

### State A — Project onboarded, standby

- **Level 0:** Combined graph focused on `Motor Control`. Nodes show role subtitles
  ("ESP32 controller — runs your program", "Servo motor — moves the arm"). Right panel:
  chapter `01 SETUP` active.
- **Panel copy:**
  - Eyebrow: `01 · SETUP — DEFINE THE TEST`
  - Heading: `What should happen?`
  - Body: `inteGREAT reads the firmware and suggests a test. You confirm it before it decides pass or fail.`
  - If a code/wiring mismatch already exists in the graph: warning notice
    `Already spotted a problem — Source configures GPIO19 for Servo 1 (SG90), but verified wiring connects it to GPIO18`.
  - **PRIMARY:** `Suggest a test from the code`
- After proposal: boxed `TEST PARAMETERS` card (command, target °, ±tolerance, deadline ms),
  collapsed `Why this test?` with evidence citations, **PRIMARY:** `Confirm test`.
- *Secondary:* `Review imported project` (collapsible — file count, declared connections,
  unchecked count). Nothing else.

### State B — Fault A: GPIO mismatch (fail with software evidence)

Run completes → chapter `03 DEBUG` (error bar). Source chip: `Simulated · fault a`.

- **Level 0:**
  - Eyebrow: `03 · DEBUG — THE INCIDENT`
  - Heading: `Servo did not reach 90°`
  - Fact line: `0.0° measured · target 90° ± 8°` + SourceBadge `Simulated · connected`
  - Facts row (StatusDots): `Command sent — yes` · `Firmware ACK (serial) — yes` · `Motion observed (camera) — no`
- **Level 1 (in panel):**
  - Eyebrow `LEADING HYPOTHESIS` + status `plausible`
  - `Incorrect GPIO mapping` — `Source configures GPIO19 but wiring uses GPIO18.`
  - **PRIMARY:** `Inspect GPIO mapping` (tooltip: rationale)
  - *Secondary (row):* `Request a code fix (Devin)` — shown **only** because this incident has
    software-issue evidence; `I made a repair — verify it` stays ghost until a check completes.
  - `Why this check?` (collapsible) → explanation + expected outcomes.
  - `Supporting evidence — select to inspect` → cited rows
    (`armServo.attach(SERVO_PIN, 500, 2400)` · `define SERVO_PIN = 19`).
  - `Evidence and unknowns` / `All hypotheses` / `More tools` collapsed.
  - `AI evidence review` section → *secondary* `Ask AI to review evidence`.
- **Canvas:** conflict highlight on `GPIO19`+`GPIO18` nodes and the `configures pin` /
  `connected to` edges. Selecting the connection raises the inspector card with
  `connected to · declared wiring — from your schematic; not physically checked yet`.
- **Rescan/verify loop:** after the engineer edits firmware externally → project menu
  `Rescan repository` → panel stays in Debug; **PRIMARY** becomes `I made a repair — verify it`
  → dialog restates command+criteria → `Run verification` → on pass, chapter `04 VERIFY`
  success bar + `Verified on the simulated rig` (source named explicitly — never "fixed" alone).

### State C — Fault B: tied power vs. signal

Same fail surface as B, but the hypothesis box reads:

- Eyebrow `POSSIBLE CAUSES · TIED`, status `plausible`
- Heading: `Signal or power connection`
- Copy: `These causes have equal rank. The next check gathers evidence to distinguish them.`
- **PRIMARY:** `Check the servo signal lead` (a fixed-template manual check)
- The check dialog requires an explicit result: `Connected` / `Disconnected` /
  `Unable to verify` + optional note. "Unable to verify" is a first-class recorded result —
  it must never collapse the tie dishonestly.
- *No* Devin secondary action appears — no software-issue evidence exists. The UI must not
  offer a code fix for an unverified physical problem. `All hypotheses` shows both tied causes
  with identical rank.
- If the user records `Disconnected` on the signal lead → hypothesis updates →
  **PRIMARY** becomes `I made a repair — verify it`.

### State D — Measurement unavailable (marker lost / camera unplugged)

- **Level 0:**
  - Heading: `Measurement unavailable` — **not** "servo failed."
  - Facts: `Command sent — yes` · `Firmware ACK — yes` · `Motion observed (camera) — unavailable`
  - Eyebrow `OBSERVATION ISSUE`, hypothesis heading `Camera could not measure the servo`
- **Copy:** `Check marker visibility and calibration, then repeat with valid measurements.
  Servo behavior is unknown until the camera can measure it.`
- **PRIMARY:** `Repeat the test` (or `Open rig setup` if the camera is disconnected —
  the button targets the actual missing prerequisite).
- **Phantom-certainty rule:** every place a number would appear shows `—` or
  `measurement unavailable`; the angle plot shows the gap region, not a flat 0° trace;
  Event Flow marks the segment `invalid sample — excluded from evaluation`.

### State E — Devin software-repair handoff

- Entry: ghost `Request a code fix (Devin)` under a software-evidence hypothesis only.
- Dialog (`Prepare software fix with Devin`), Level 2 modal:
  - Subtitle: `Devin works on an isolated remote branch and returns a reviewable diff.
    inteGREAT never patches your checkout, flashes firmware, or verifies hardware for you.`
  - Eyebrow card: `READY TO REQUEST A REMOTE FIX PROPOSAL` or `CANNOT START A REPAIR YET`
    with enumerated blockers (`DEVIN_API_KEY not set`, `no accessible git remote`, …).
  - Snapshot facts: base revision, repo ref, `N uncommitted file(s) will NOT be included`
    + acknowledgement checkbox when dirty.
  - **PRIMARY:** `Start repair session` (disabled until preflight passes + ack).
- While working: job card `WORKING` + `Refresh` — job lives in the Debug panel as a boxed
  section so diagnostic context is never lost. Poll/refresh never creates a second session.
- On `READY FOR REVIEW`: job card shows session/PR links — `Open in Devin` (external).
  Copy: `A remote test pass is not hardware verification.`
- After the engineer applies the fix themselves: project menu `Rescan repository` →
  **PRIMARY** `I made a repair — verify it`. The verify dialog warns when the selected
  source changed (`A simulated or replay pass does not verify a live hardware repair`).

---

## Part 3 — Information architecture & consolidation matrix

| # | Feature | Lifecycle phase | Visibility tier | Consolidation target |
|---|---|---|---|---|
| 1 | Import / reopen project / demos | Setup (entry) | Entry screen | Entry only; inside project = menu `Rescan`/`Switch project` |
| 2 | Manifest / KiCad netlist + mapping preview | Setup (entry) | Entry screen | Import card; later in connection inspector |
| 3 | Wiring trust (declared vs verified) | Investigate | L1 contextual | Connection inspector card + edge label `· verified`/`· declared` |
| 4 | Subsystem focus | All | **L0** top bar | Single focus Selector |
| 5 | Combined/Hardware/Software layers | Investigate | L0 canvas | Canvas-local segmented control |
| 6 | Friendly names, verbs, legend | All | L0 canvas | Node subtitles, edge labels, Legend overlay |
| 7 | Search / expand / collapse / fit | All | L0 canvas | Canvas toolbar, icon-weight only |
| 8 | Device connect / camera / calibration | Setup | L2 Setup destination | Rig setup dialog; top bar shows dots only |
| 9 | Live / sim / replay source choice | Run | L1 in Run step | SourcePicker in panel; chip in top bar shows result |
| 10 | Confirmed expectation | Setup→Run | L0 | Setup boxed params → Run summary card |
| 11 | Run / progress / result facts | Run→Debug | L0 | Panel state + facts row |
| 12 | Angle plot, serial records | Investigate | L2 drawer | Telemetry drawer (Angle/Serial tabs); open via evidence link |
| 13 | Event Flow + run selection + scrub | Investigate | L1 canvas mode | Canvas view toggle `Dependencies / Event flow` |
| 14 | Hypotheses / unknowns / contradictions | Debug | L1 (lead) + L2 (all) | Panel hypothesis box; `All hypotheses` collapsed |
| 15 | Recommended check + outcome meanings | Debug | **L0** | The ONE primary button + `Why this check?` |
| 16 | Manual result recording | Debug | L2 modal | Check dialog with explicit result radio |
| 17 | Evidence records + citations | Investigate | L1 inline, L2 detail | Inline evidence rows → evidence dialog |
| 18 | StepFun/Gemini review | Debug | L2 | `AI evidence review` section; per-stage providers collapsed |
| 19 | Devin repair handoff | Verify | L2 modal | Conditional secondary action → repair dialog |
| 20 | Repeat test | Debug | L1 secondary | Ghost button when it gathers distinguishing evidence |
| 21 | Verify repair | Verify | **L0** when due | The ONE primary in verify-ready state |
| 22 | Rescan repository | Verify | L2 | Project menu; prompted inside repair flow |
| 23 | Persistence / run history / save replay | All | L2 | Automatic; `Save as replay` in drawer header |
| 24 | Notes / permissions / tool audit / activity | Debug | L2 | `More tools` collapsed + Activity drawer tab |
| 25 | Graph conflict highlights | Investigate | L0 canvas | Node/edge semantic styling |
| 26 | Source/trust labels (sim/replay/live, declared) | All | **L0** | SourceBadge — never hidden, never collapsible |
| 27 | Cross-layer reveal ("show code that touches this") | Investigate | L1 | Inspector card buttons |
| 28 | Provider/model/status details | Debug | L2 | `Provider per stage` collapsible inside AI review |

Rule for the matrix: every feature has exactly one home. Shortcuts may point to that home;
they never duplicate it.

---

## Part 4 — Component architecture & wireframe spec

### 4.1 React 19 structure (maps to existing files, renamed for clarity)

```jsx
<App>
  {project ? <WorkspaceShell/> : <ImportScreen/>}
</App>

<WorkspaceShell>
  <Layout>
    <LayoutHeader>                    {/* TOP BAR — "where am I" */}
      <TopBar>
        <Brand/> <ProjectName/> <FocusSelector/> <SourceChip/>
        <DeviceDots/> <ProjectMenu items=[rescan, rig setup, switch]/>
      </TopBar>
    </LayoutHeader>

    <LayoutPanel side="right" width={420}>   {/* GUIDED INSPECTOR — "what next" */}
      <GuidedInspector>
        <ChapterStrip steps=[Setup,Run,Debug,Verify] state={autoStep}/>
        <StepContent>                  {/* exactly one <PrimaryButton/> per state */}
          <SetupStep|RunStep|DebugStep|VerifyStep/>
          <ContextCard/>               {/* selected node/edge/event summary */}
        </StepContent>
      </GuidedInspector>
    </LayoutPanel>

    <LayoutContent>                   {/* CANVAS — "what am I looking at" */}
      <CanvasHeader>
        <SegmentedControl [Dependencies|Event flow]/>
        <SegmentedControl [Combined|Hardware|Software]/>
        {mode==="flow" && <RunSelector/>}
        <SearchInput/> <ExpandAll/> <Collapse/>
      </CanvasHeader>
      {mode==="deps" ? <GraphCanvas/> : <EventFlowCanvas/>}
      <ContextualInspectorCard/>      {/* floating, one pattern for node/edge/event */}
      <TelemetryDrawer>               {/* collapsed tab bar by default */}
        <Tabs [Angle|Serial|Devices|Activity]/>
        <SaveReplay/> <FocusGraph/>
      </TelemetryDrawer>
    </LayoutContent>
  </Layout>

  {/* Level 2 — modals, unmounted when closed */}
  <RigSetupDialog/> <EvidenceDialog/> <CheckDialog/> <VerifyDialog/>
  <RepairDialog/> <PermissionDialog/> <RepeatDialog/>
</WorkspaceShell>
```

### 4.2 Component contracts

- `ChapterStrip` — derives state per step (`done | active | error | locked`) from
  `autoStep()`; emits `onStepClick(i)` with the existing gating rules. No other component
  may render a primary-styled button while a step is active.
- `StepContent` — pure function of `InvestigationView` state machine (outline §6).
  One `primary` action + optional `secondary[]` ghosts + `details[]` collapsibles.
- `ContextualInspectorCard` — single inspector implementation taking
  `{kind: "node"|"edge"|"event", id}`; replaces per-surface selection cards.
- `TelemetryDrawer` — `open: boolean` persists per session; opens to the tab matching the
  clicked evidence kind (angle evidence → Angle, serial → Serial).
- Every dialog gets `returnFocus` to its invoker; opening one never unmounts the inspector.

### 4.3 Keyboard ergonomics

| Key | Context | Action |
|---|---|---|
| `Space` | workspace, not typing | Run the current primary action (Run test / Perform check / Verify) |
| `1–4` | workspace | Jump to chapter Setup/Run/Debug/Verify (respecting gating) |
| `D` / `E` | canvas | Switch Dependencies ⇄ Event flow |
| `H` / `S` / `C` | canvas, deps mode | Hardware / Software / Combined layer |
| `←` `→` | event flow | Step scrubber prev/next event |
| `↑` `↓` | panel lists | Move through hypotheses/evidence rows |
| `Enter` | focused row | Open evidence record / inspector |
| `Tab` | global | Standard focus order: top bar → inspector → canvas toolbar → drawer |
| `Esc` | modal/drawer | Close topmost Level-2 surface, restore focus to invoker |
| `?` | workspace | Keyboard shortcut overlay (Level 2) |

Focus-visible ring on every interactive element; chapters announce `role="tab"` state;
canvas nodes are reachable via the search → Enter path (React Flow nodes are not
tabbable — keep the search path as the documented keyboard route).

### 4.4 Implementation order (thin slices)

1. Consolidate shortcuts → single Setup destination (rig setup opens focused section).
2. Rename drawer tabs (`Timeline → Activity`), default-collapsed drawer.
3. `ContextualInspectorCard` unification (node/edge/event).
4. Conditional Devin visibility + one-primary-action audit per state.
5. Keyboard layer (`Space`, `1–4`, `D/E`, `Esc` focus-return).
6. Re-verify at 1280×720 + 1024×768 with `apps/web/ui_walkthrough.mjs`.
