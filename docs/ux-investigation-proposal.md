# UX journey and company integration proposal

**2026-10-17 · UX portions implemented in D-022; StepFun routing remains a proposal.**

After extended browser verification, the real React app now uses Astryx for import-first onboarding,
manifest recovery, visible rig setup, scoped graph/evidence inspection, explicit manual results, and
source-aware Repeat/Verify. See `STATUS.md` and D-022 for the shipped behavior and validation. The
conversation previews below remain scripted design references; they are not the app implementation.
Owner is focusing on UX and how company challenges, particularly StepFun, fit into the product.
Owner clarified the scope is **all three**: import/hardware setup, graph/evidence navigation, and
investigation/StepFun integration.
See `hackathon-context.md` for the supplied challenge descriptions and `decisions.md` D-021 for the
approved visual direction. Keep Astryx and the Obsidian styling.

## Findings from the running app

- The whole-system fit makes graph labels very small, especially when the long board label participates
  in layout. The useful code-to-pin-to-servo relationship is hard to read at the default zoom.
- The investigation panel repeats the measurement failure in the warning, incident title, and result
  text. On the inspected incident, the main verification action extends below the visible panel.
- AI is behind More tools. Its output appears as a generic summary, making its contribution hard to
  distinguish from deterministic rules and measurements.
- Evidence is available but separated across collapsed hypothesis details, graph selection, and an
  inspection dialog. Keep the relevant source/wiring references close to the recommended check.

## Project import and hardware setup

- Keep importing a repository and supplying electrical context in one place. Offer supported KiCad XML
  with explicit role/pin mapping and a manifest fallback; show source references and import warnings.
- After import, show a concise code-versus-declared-wiring summary and open the graph for review.
  Preserve unverified wiring until the engineer explicitly confirms a physical connection. Allow
  investigations to continue with unknowns instead of requiring invented wiring certainty.
- Give rig readiness a dedicated setup view. Source selection, serial connection, camera connection,
  marker calibration, and expectation confirmation should be visible before the first Run Test.
  Currently device setup is reached through More → Devices in the bottom drawer.
- A simulated source is immediately usable and prominently synthetic. A live source shows the exact
  missing setup step and a corresponding action. Keep live, recorded replay, and synthetic replay
  distinct. Selecting a different source must not make a replay pass look like live repair evidence.
- Confirm the test's command, metric, target, tolerance, and deadline before running. Device connections
  and configured command execution remain deliberate engineer actions under the existing boundaries.

## Graph and evidence navigation

- Default to the active subsystem/incident neighborhood, with an explicit Whole system navigation path.
  Show adjacent power/signal dependencies and retain Expand Scope for relevant external nodes.
- Shorten visible hardware labels (for example, ESP32); put the variant, long names, and assumptions in
  selection details. Preserve readable node labels rather than fitting long labels into a tiny graph.
- Source, wiring, and camera citations should select the corresponding graph elements and open their
  evidence. Display file/line for source, declaration versus engineer confirmation for wiring, and the
  test run/quality/source for measurements.
- Keep selection details from pushing the investigation's next action out of view. Compare an
  on-demand evidence area with a persistent workbench below the graph.

## Investigation flow

1. Focus the graph on the selected subsystem and immediate dependencies. Retain an explicit route back
   to the whole system. Use readable labels and show the source-configured pin beside the wired pin.
2. Show a concise failed expectation and three facts: command sent, firmware ACK, physical motion.
   Preserve distinct live/simulated/replay labeling and unknown measurement states.
3. Present one recommended check, a short reason, its supporting evidence, and what its possible
   outcomes would establish. Keep other hypotheses available without forcing a winner when tied.
4. Clicking a citation or graph element opens the relevant evidence in context. Tool execution still
   uses existing investigation grants; plain conversation never grants tool permissions.
5. After inspection, show the engineer's repair steps. Completing a diagnostic check does not establish
   that a repair happened or a fault was fixed.
6. Verify with the same confirmed command and thresholds. Only a valid passing run resolves the
   incident; unavailable measurements remain inconclusive.

## Two layouts to compare

- **Guided investigation:** readable focused graph with a right-side recommendation and evidence opened
  on demand. Closest to the current guided flow; suitable for the first-time experience and demo.
- **Evidence workbench:** graph above, source/wiring evidence and recommendation side by side below.
  Makes comparisons easier for an engineer investigating a specific discrepancy.

An interactive conversation preview explores both layouts, each with Project, Rig setup, and
Investigation screens. It includes import review, wiring confirmation, simulated/live setup states,
readiness-gated test preview, subsystem scope navigation, and evidence inspection.
It uses scripted/simulated examples, makes
no model calls, and changes no project firmware or devices. Preview source references were checked
against the fixture: `servo_control.h:4` and `servo_control.cpp:8`.

## Proposed StepFun responsibility

Give **Step 5 Preview the investigation-guide / next-check synthesis role**. It receives the confirmed
expectation, scoped evidence, validated Gemini specialist reports when available, current hypotheses,
and the fixed action catalog. It returns a concise explanation, citations, an existing next-action ID,
and the discriminating outcomes of that action. Validate every referenced ID before display.

Gemini retains triage and the Code, Hardware, Runtime/Vision specialist roles. Deterministic rules retain
hypothesis ranking; OpenCV retains angle measurement. Replacing the synthesis provider rather than
adding another model round would keep the existing one initial fan-out + one evidence-driven follow-up
budget. Implementation would need an explicit provider-routing decision and tests; it is not adopted
by this proposal.

Expose the recommendation where the engineer chooses the next action. Show provider attribution in
contributor details, actual call status, and stored provenance. A question field can explain the current
evidence; additional model responses must respect the same incident budget. Clearly distinguish a
stored engineer note from an AI response. If the provider is unavailable or validation fails, show the
deterministic recommendation and the real reason AI is unavailable.

This role supports the supplied StepFun criteria: input → useful result, visible model contribution,
reliability, and user control. The running product must actually call `step-5-preview` and preserve a
reviewable call path; the conversation preview does not satisfy that runtime requirement.

StepFun's official documentation confirms JSON Schema output for `step-5-preview` and says business
validation is still necessary: [structured-output documentation](https://platform.stepfun.com/docs/zh/guides/developer/json-mode).
Its [official cookbook](https://platform.stepfun.com/cookbook/step-5-vision-structured) includes the global
`https://api.stepfun.ai/v1` base URL. No live API access was verified during this UX exploration.

## Company contributions to explain through the same workflow

- **Espressif:** the ESP32 is the physical system under investigation, visible in the graph and real demo.
- **Gemini:** specialist analysis of the scoped code, hardware, and runtime evidence.
- **StepFun:** converts that evidence into an understandable, actionable next check.
- **Paper challenge:** intentional layout, legibility, evidence access, and clear interaction states.
- **Sentry, if pursued:** diagnose the application's own failures and latency using the required products;
  show a concrete improvement. This requires additional integration work.

## Review checks before adopting

The scripted preview was browser-checked on 2026-10-17: import starts with unverified wiring; graph review
does not show test measurements before a test; camera calibration and expectation confirmation gate
the live-setup preview; scope/citation controls expose evidence; the sample question response is
explicitly labeled; and the repair/retest example updates the outcome. Both layout variants were
inspected, including 1024px and 360px viewport checks. These checks validate the preview only, not the
running product or hardware. The preview currently illustrates Fault A, not the entire fault library.

Check the two layouts with Fault A, Fault B's tied hypotheses, missing camera measurements, unavailable
AI, denied tool permission, and a failed verification. Ensure the primary action remains visible at the
demo viewport, citations focus the corresponding graph/evidence, and provider attribution reflects
actual calls. Apply implementation changes as a separate verifiable slice with STATUS and decision-log
updates.
