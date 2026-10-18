# Demo script (~5 min)

Say the limits out loud: inteGREAT shows what is **observed, verified, inferred or unknown**. It does not
measure voltage or PWM, does not flash firmware, and never runs commands an AI wrote.

## 0. Before the audience arrives
- `apps/api/.venv/Scripts/python scripts/dev.py`; open http://localhost:5173.
- Live: Devices tab → serial connected, camera connected + calibrated. Run one good test.
- Fallback: pick **Recorded: …** replays (or **Sim** sources). The UI badges every run's source — say so.

## 1. Graph first (60 s)
- Import the project (Fault A firmware). The graph appears; point at the **red conflicting edge**:
  "Before any test, the source configures GPIO19 but the engineer-verified wiring is GPIO18."
- Expand Motor Control → `servo_control.cpp` → functions. Click the GPIO18 wire → evidence shows the manifest line.

## 2. Test → failure (60 s)
- *Propose test from code* → show the cited source lines → **Confirm**.
- **Run Test**. Watch the angle plot stay flat; the three facts: command sent ✓, firmware ACK ✓, motion ✗.
  "The firmware said it moved. The camera says it didn't. Those are different facts."

## 3. Investigate (90 s)
- Ranked hypotheses: #1 Incorrect GPIO mapping (with evidence), #2 signal/power (unmeasured).
- Click **Inspect GPIO mapping** → permission prompt → *Grant for this investigation* → excerpt shows
  `#define SERVO_PIN 19` next to the manifest's GPIO18. Hypothesis becomes **supported**.
- (If Gemini is configured) **Ask agents**: three specialists, each cites evidence; invented ids are rejected
  (expand an agent card → "Rejected by validation"). Show the Tool audit tab.

## 4. Fix → verify (60 s)
- Live: Devices → *Release port*, fix `SERVO_PIN` to 18 in the IDE, reflash, reconnect, **Rescan**.
- **Verify fix** → angle reaches 90° → incident **RESOLVED**, servo turns blue in the graph.

## 5. Fault B (60 s, if time)
- Import correct firmware; unplug the servo signal lead (power down first). Run Test → signal vs power tied.
- **Check signal connection** → *Disconnected* → that hypothesis becomes supported. Reconnect → Verify fix.

## If something breaks
- Serial vanished: Devices → Connect again (board was unplugged or another app grabbed the port).
- Marker lost: result is **inconclusive**, not a servo fault — fix the camera view and Repeat test.
- Gemini down: agents report unavailable; everything else still works. Keep going.
