# Demo script (~5 min)

Say the limits out loud: inteGREAT shows what is **observed, verified, inferred or unknown**. It does not
measure voltage or PWM, does not flash firmware, and never runs commands an AI wrote.

## 0. Before the audience arrives
- `apps/api/.venv/Scripts/python scripts/dev.py`; open http://localhost:5173.
- Live: **Rig setup** → serial connected, camera connected + calibrated. Run one good test.
- Fallback: pick **Recorded: …** replays (or **Sim** sources). The UI badges every run's source — say so.

## 1. Graph first (60 s)
- Import the project (Fault A firmware). The **Combined** view shows two labelled regions —
  software on the left, the physical rig on the right — with the **red conflicting edge** crossing
  them: "Before any test, the source configures GPIO19 but the engineer-verified wiring is GPIO18."
- Flip the **Hardware** layer: only the rig — "ESP32 DevKitC — controller — runs your program",
  "Servo motor — moves a shaft", "GPIO18 — servo control pin". The header chip says how many source
  items are hidden; one click brings them back.
- Flip the **Software** layer: code plus dashed *reference* hardware the code touches — "this is
  the boundary: configured pin vs wired pin".
- Expand Motor Control → `servo_control.cpp` → functions. Click the GPIO18 wire → evidence shows the manifest line.

## 2. Test → failure (60 s)
- *Suggest a test from the code* → show the cited source lines → **Confirm test**.
- **Run Test**. Watch the angle plot stay flat; the three facts: command sent ✓, firmware ACK ✓, motion ✗.
  "The firmware said it moved. The camera says it didn't. Those are different facts."

## 3. Investigate (90 s)
- Ranked hypotheses: #1 Incorrect GPIO mapping (with evidence), #2 signal/power (unmeasured).
- Click **Inspect GPIO mapping** → permission prompt → *Grant for this investigation* → excerpt shows
  `#define SERVO_PIN 19` next to the manifest's GPIO18. Hypothesis becomes **supported**.
- Switch to **Event flow**: four lanes — command → serial ACK → camera samples → result.
  Step through with the scrubber: "command sent at 0 ms, ACK at 41 ms, the camera saw nothing move,
  verdict at ~2.4 s". Point at the note: *host-clock correlated, not synchronized — ordering is not
  causation*. Click an event's graph link to jump back to the node it concerns.
- (If providers are configured) **Ask AI to review evidence**: StepFun picks which Gemini specialists
  to run — "Provider per stage" shows who did what — each cites evidence; invented ids are rejected
  (expand an agent card → "Rejected by validation"). Show the Tool audit tab.

## 4. Fix → verify (60 s)
- Live: Devices → *Release port*, fix `SERVO_PIN` to 18 in the IDE, reflash, reconnect, **Rescan**.
- **I made a repair — verify it** → review the same command/thresholds → **Run verification** → angle
  reaches 90° → incident **RESOLVED**, graph marks the passing observation. Completion names its source.
- Optional (Devin configured): under the leading hypothesis click **Prepare software fix with
  Devin**. The dialog shows the exact base commit, warns uncommitted files are NOT sent, then opens
  ONE remote session on an isolated branch. "Devin proposes a diff and runs its own tests remotely —
  a remote test is not a hardware verification. The engineer still reviews, applies, re-flashes, and
  verifies here."

## 5. Fault B (60 s, if time)
- Import correct firmware; unplug the servo signal lead (power down first). Run Test → signal vs power tied.
- **Check signal connection** → choose *Disconnected* → **Record check result** → that hypothesis becomes
  supported. Reconnect → **I made a repair — verify it** → **Run verification**.

## If something breaks
- Serial vanished: Devices → Connect again (board was unplugged or another app grabbed the port).
- Marker lost: result is **inconclusive**, not a servo fault — fix the camera view and Repeat test.
- Gemini down: agents report unavailable; everything else still works. Keep going.
