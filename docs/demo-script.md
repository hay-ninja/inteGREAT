# Demo script (~5–6 min)

Say the limits out loud: inteGREAT shows what is **observed, verified, inferred or unknown**. It does not
measure voltage or PWM, does not flash firmware, never runs commands an AI wrote, and never auto-applies
a patch. Every run is badged — **Live hardware** / **Simulated environment** / **Synthetic replay** /
**Recorded replay** — and the hosted demo says so in the banner.

## 0. Which demo are we running

- **Hosted replay (zero risk):** static site serving `dist/` — no backend needed. Works offline-of-
  backend by design; the "Hosted demo" banner discloses that everything is a recorded bundle.
  Verify beforehand: `node apps/web/replay_test.mjs` against `http://localhost:8080`.
- **Local sim/replay (recommended on stage):** `apps/api/.venv/Scripts/python scripts/dev.py` →
  http://localhost:5173. Same story, full interactivity (Analyze with real providers, real Devin
  session on the repair step).
- **Live rig (bonus, never the spine):** needs H0 done (`docs/hardware-setup.md`). If it works, the
  iPhone-browser camera path makes a good moment — judge's phone as the CV source.

## 0b. Before the audience arrives

- Hosted: build is current (`npm run build` in `apps/web`), `dist/replay/demo.json` matches
  `apps/web/public/replay/demo.json`, static server on :8080.
- Local: API on :8000, `STEP_API_KEY`/`GEMINI_API_KEY` in `.env` if you want Analyze live (otherwise
  show the honest "provider unavailable" state — deterministic core still works, that IS the message).
- Reset the browser: `localStorage.clear()` + reload (the replay test does this; do it by hand for a
  live demo so the projects hub starts fresh).

## 1. Hook → graph first (60 s)

- Landing → **Open the workspace** → the demo card: **esp32_halloween** ("two LEDs, two faults —
  inverted ghost + dead candle"). **Load demo**.
- The **Combined** graph shows the boundary honestly: dashed "configures pin" edges from
  `esp32_halloween.ino` into GPIO18/GPIO19, both LEDs wired under the Halloween porch lights
  subsystem. **Deliberately no red** — the wiring matches the code; the bug isn't visible
  statically. Say: "the map is consistent — and the system still fails. That gap is the point."
- Flip **Hardware** layer → only the rig (board, pins, both LEDs, GND, 3V3 rail). Flip **Software**
  → code plus dashed boundary refs. Point at `GHOST ON`/`FLICKER` command literals found in source.
- (Contrast for judges who ask: a wrong-pin fault *would* light the code↔wiring edge red
  pre-run — the graph marks conflicts it can prove, not suspicions.)

## 2. Arc A — the ghost LED inverted-logic fault (75 s)

- The ghost expectation is already confirmed (default on open). **Run the test** — pick
  `halloween inverted` if the source picker shows.
- Result card: command sent ✓, firmware ACKed `ACK GHOST ON` ✓ — and the LED *did* change — but ended
  **off**. "This is not 'nothing happened' — the LED responded. It ended wrong."
- **Debug** → **Potential causes** tab → leading hypothesis: **Inverted drive logic (code level vs
  wiring polarity)**. The manifest's `active_low` wiring vs firmware's HIGH-for-on — a diagnosis a
  pin-mismatch rule can't produce.
- **Verify it** → pick `halloween ghost good` replay → **Run verification** → the LED ends on →
  incident **RESOLVED** ("Was: fail → Now: pass"). The fix in the story: firmware drives LOW for on,
  or the LED gets rewired active-high.

## 3. Arc B — the pumpkin candle, dead despite ACK (90 s)

- **History** tab → the `FLICKER` run row (badged *investigation*) → Debug opens on the second
  incident: "Pumpkin candle LED (GPIO18) did not reach expected state 1".
- Serial drawer shows the smoking gun timeline: `FLICKER` → `ACK FLICKER` (39 ms) → `DONE FLICKER`
  (1.1 s) — "the board ran the command to completion; the light never flickered. The bug is between
  'done' and photons."
- **Potential causes**: tied signal/power hypotheses → **Check signal connection** (manual check:
  engineer inspects, records result) — and, once physical checks clear, **Prepare software fix with
  Devin**. Say the honest part: "an *unverified* wiring suspicion can't launch a remote code fix —
  the gate is real. Verified-clean checks shift suspicion to firmware."
- On a live backend this opens ONE Devin session (bounded prompt, repo snapshot, evidence ids). If
  the session reaches `needs_input`, that state is shown as waiting-on-engineer — nobody claims a
  fix that didn't land. The actual bug in the fixture: a `uint8_t` loop counter that wraps at 255 —
  the kind of thing rules flag as 'software-side' and a repair agent can diff in seconds.

## 4. Event flow + honest ambiguity (60 s)

- With the pumpkin run still selected, open the **Timeline** rail → Event Flow: 4 lanes — command →
  serial ACK (`FLICKER` / `ACK FLICKER` / `DONE FLICKER`) → camera samples (a flat row of `0`) →
  verdict — with the step scrubber. Say the correlation caveat: host-clock correlated, ordering ≠
  causation.
- Point at the tied hypotheses again: signal and power stay **tied** until an engineer looks — the
  rules say "we can't tell these apart yet" instead of guessing. Recording *Connected* weakens the
  physical branch (and unlocks the Devin action); recording *Disconnected* makes it **supported** —
  the engineer's observation is first-class evidence, not a note on the side.
- Optional: **Analyze** tab (live backend with keys) — StepFun triage → Gemini specialists → critique
  → synthesis, with per-stage provider attribution and "Evidence cited" chips. Bounded: one fan-out,
  one follow-up; invented evidence ids are rejected.

## If something breaks

- Hosted demo, no test button → click the **Test** chapter (the view remembers the last tab).
- Hosted demo, an action 404s → it wasn't recorded in the bundle; re-run `capture_demo_replay.py`
  and rebuild. The fallback covers source-variant run requests but not arbitrary new flows.
- "Measurement unavailable" / `marker_lost` → that's honest inconclusive, not a fault — say so.
- Providers down → Analyze shows unavailable; rules, graph, hypotheses, event flow all still work.
- Serial gone (live) → Devices → reconnect; Windows COM ports are exclusive (release before flash).
