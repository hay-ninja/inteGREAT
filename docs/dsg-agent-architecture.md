# DSG agent architecture — implemented (branch `feature/dsg-agent-arch`, 2026-10-18)

**Status: all four stages landed** — D-028 (angle removal + metric-keyed graph write-back),
D-029 (shadow + estimation + deterministic refutation), D-030 (telemetry/vision split +
ambiguity-gated probing), D-031 (causal chain + interventions). 109 pytest + 17 vitest +
`tsc -b` + `vite build` all green. New code: `diagnostics/graph_state.py`, `shadow.py`,
`estimate.py`, `causal.py`; tests in `apps/api/tests/test_shadow.py`.

Restructures diagnosis around **structural grounding + simulation residuals + causal checks**,
per the owner's architecture proposal. Core claim: don't stuff logs/frames/manifests into a
multimodal prompt — ground everything in the graph, compute observed-vs-nominal residuals
with a digital shadow, and let agents reason over *that*.

Also: the product is meant to be **adaptive across rigs**, not servo-shaped. Removing the
hardcoded "Arm angle" drawer plot is the first step; measurement data keeps flowing to
evaluators and agents as generic metric-keyed observations.

## Non-negotiables preserved

- Every finding cites evidence ids that resolve; observed ≠ verified ≠ inferred ≠ unknown.
- Shadow/simulation output is **model-based inference**, labelled as such — never presented
  as a measurement. A shadow "confirmation" is `epistemic=inferred`, full stop.
- Agents never execute tools or arbitrary commands (D-004/D-015). Probes = actions from the
  fixed catalog through the same permission-checked executor.
- Bounded rounds stay bounded (PRD §11.1): the refutation pass runs *inside* the existing
  round; probing recommends actions, never runs them.
- No numeric probabilities anywhere (PRD §12). "Entropy" below means **qualitative
  ambiguity**: count of unresolved top-rank hypotheses + open unknowns.
- Rules keep ranking; everything here *adds evidence* or *adds hypotheses*, never silently
  reorders.

## Target architecture (mapped to existing modules)

```
                ┌────────────────────────────────────────────┐
                │  Orchestrator (StepFun)                    │
                │  triage → refute → synthesize → probe pick │
                └───────┬────────────────────────────────────┘
        ┌───────────────┼───────────────┬────────────┐
        ▼               ▼               ▼            ▼
   code agent    hardware agent   telemetry     vision agent
   (firmware/    (wiring/power/    agent        (CV residuals
    pin logic)    constraints)    (serial/      → node attrs)
                                  events)
        │               │               │            │
        └───────────────┴───┬───────────┴────────────┘
                            ▼
              GROUNDING: canonical graph + dynamic state
              (residuals on nodes, traversal on edges)
                            ▼
              SHADOW: nominal prediction + fault-knob sweep
              → residual evidence → hypothesis support/refute
                            ▼
              CAUSAL: command→ack→signal→motion→observation
              counterfactuals = shadow interventions
```

What already exists and stays: canonical graph (D-023), evidence model, context packets
(already "localized subgraph, not global dump"), scoped validation, deterministic fallback,
flow projection (D-024), the tool registry as the only probe surface.

## Stage A — remove servo-shaped UI + write state back to the graph

1. **Delete the Arm angle tab.** `BottomDrawer.tsx`: drop `"angle"` from `DrawerTab`, the
   `Tab`, and `AnglePlot`. `styles.css`: drop the `.plot` block. `App.tsx`: the four
   `setDrawerTab("angle")` sites → `"serial"` (and default state). Keep the FlowPanel
   verdict line and Event Flow's camera lane — those state the *result*, not a raw feed,
   and read from `result.facts`/`metric` so they're already metric-agnostic.
   *Agents lose nothing*: `read_cv_measurements` and the evidence catalog are unchanged.
2. **Graph state write-back (DSG-lite).** After `expectations.evaluate` produces a result,
   annotate the canonical graph:
   - Component node attributes (flat `AttrValue`, e.g. `obs_<metric>`, `obs_residual`,
     `obs_quality`, `obs_run_id`) — observed value minus nominal expectation = residual,
     evidence-cited.
   - Edge traversal state on `controls`/`configures`/`connected_to` paths: `traversal` ∈
     `observed | interrupted | unobserved` + `traversal_run_id` (missing ACK = interrupted
     `controls` edge; a matched `Serial.print` = observed `calls` edge — extends D-007).
   - Rescan (D-019) rebuilds nodes → re-apply the latest run's state if node ids resolve.
   Metric-keyed attributes, never `angle`-named — this is the adaptivity move.

## Stage B — digital shadow + residual diagnosis (deterministic core)

`SimRig` is already a reduced-order model with fault knobs (`SimConditions`). Today it's
only a fake observation *source*; this stage makes it a predictive *model*.

3. **`diagnostics/shadow.py`** — derive nominal `SimConditions` from the graph +
   expectation (configured GPIO from `configures` edges, wired GPIO from declared signal
   wiring, leads connected, marker visible, firmware acks). Predict the timeline
   (ACK at ~40 ms, slew-limited motion) and emit a residual record vs. the run's actual
   serial/observation records. Persisted as `Evidence(kind=shadow_residual,
   epistemic=inferred)` — new `EvidenceKind` member.
4. **`diagnostics/estimate.py`** — enumerate θ over the fault-knob space (gpio
   match/mismatch × signal ± × power ± × marker ± × ack ±, pruned by graph-fixed params).
   Each θ predicts a signature `{moves?, acks?, observable?}`; score against the run's
   facts. Consistent θ → supporting evidence on the matching hypothesis; inconsistent θ →
   contradicting evidence. Hypothesis text gains "consistent with simulation; not measured
   on hardware."
5. Wire into the rules path after `run_rules` — evidence only, ranks untouched.
   **Self-verifying test**: `conditions_for(scenario)` → sim run → estimator must recover
   the injected knob. The sim scenarios are ground truth for free.

## Stage C — agent restructure (4 specialists + refutation + gated probing)

6. **Split `runtime_vision` → `telemetry` + `vision`.** `AgentName` gains both (keep
   `runtime_vision` as a legacy enum member so persisted `AgentRun`s still load). Update
   `TriageOut`/`TriageQuestion` literals, `AGENT_ROLES`, `DEFAULT_DISPATCH`,
   `AGENT_TOOLS`, `AGENT_EDGES`: telemetry gets `read_test_events`/`read_serial_buffer`;
   vision gets `read_cv_measurements` + residual evidence. **PRD §11 deviation — flag.**
7. **Refutation pass inside `run_round`** (after specialist merge, before synthesis):
   deterministic first — each leading hypothesis checked against shadow θ consistency —
   then an optional LLM critic (specialist provider, same citation validation) whose job
   is to *invalidate*, output routed to `contradicting_evidence_ids`. The shadow verdict is
   authoritative; the critic only argues.
8. **Ambiguity-gated probing.** Post-synthesis: if ≥2 hypotheses tie at top rank (or open
   unknowns remain), the recommended action must come from those hypotheses'
   `recommended_action_ids` with `expected_outcomes` that discriminate — and the summary
   must say what each result rules out. Recommendation only; execution stays with the
   engineer.

## Stage D — causal layer

9. **`diagnostics/causal.py`** — fixed chain `command_sent → command_acknowledged →
   signal_present → motion → observed`, instantiated per incident with evidence ids.
   Counterfactual queries reuse stage B's machinery: `do(knob=nominal)` = shadow run with
   that parameter forced; "would motion still be absent?" answers land in hypothesis
   explanations ("tested: with signal assumed connected, the model still predicts no
   motion → power fault remains consistent").
10. Keep presentation thin: counterfactual lines on hypotheses + synthesis; no new graph
    view unless it's pulling weight.

## PRD deviations to flag in `decisions.md`

- §11 roster: 3 specialists → 4 (telemetry/vision split).
- §11.1 round contents: refutation pass + critic adds ≤1 specialist call per round —
  still within "maximum calls configured centrally" but worth recording.
- §9 UI: Angle plot removed as a fixed panel; measurements surface via results/flow only.
- §12: shadow-based support is a new deterministic evidence kind — strengthens rules,
  doesn't replace ranking.

## Verification

- `pytest`: shadow prediction vs nominal sim (residual ≈ 0); estimator recovers each
  `SIM_SCENARIOS` knob; refutation drops/shadows a hypothesis correctly; legacy
  `runtime_vision` AgentRun docs still deserialize; packet builder covers new agents.
- `vitest`/`tsc`: drawer tabs, no angle references.
- End-to-end: sim Fault A run → residual evidence → estimator identifies gpio_mismatch →
  hypothesis cites shadow evidence; diagnose round shows 4-agent triage + refutation in
  `AgentRun`s.
- Per-slice `STATUS.md` updates; decision entries D-028+ as each stage lands.
