# Two-LED camera demo

This is an observation-only LED workflow, separate from the servo/agent investigation
pipeline. It shares the hardware/source graph, camera inputs, evidence store, and
activity events. It does not claim general visual root-cause diagnosis.

## Prepare

- Classic ESP32-WROOM: GPIO18 -> 330-ohm resistor -> LED 1 anode; GPIO19 -> separate
  330-ohm resistor -> LED 2 anode. Both cathodes connect to GND. USB powers the ESP32.
- Open `fixtures/esp32_led_fade/esp32_led_fade.ino` in Arduino IDE and upload manually.
  It fades one LED in/out, then the other, continuously. No serial connection is needed.
- Start inteGREAT normally. In Import your own project, use the absolute path to
  `fixtures/esp32_led_fade` as the code folder and the absolute path to
  `fixtures/manifests/esp32_led_fade.yaml` as the wiring notes file. No KiCad file needed.
- Projects with exactly two LED components and no servo open the LED visual panel.
- Connect a USB/laptop webcam or use the [phone camera guide](phone-camera.md).
  Rig setup for LED projects requires a camera only, not ArUco/servo calibration.

## Calibrate while both LEDs are working

1. Fix the camera position so both LEDs are visible. Keep lighting and exposure stable.
2. Refresh the image; choose LED 1, and click opposite corners of a tight box around it.
   The image used for selecting regions is frozen; references always sample a fresh frame.
3. Wait for LED 1 to be dim, then Capture dim/off. Wait for it to be bright, then Capture
   bright/on. Repeat for LED 2. The references must have clearly different brightness.
4. Confirm the expectation: within eight seconds each LED reaches dim and bright states
   in separate phases. Dim <= 25% and bright >= 75% of its calibrated contrast range;
   at least two frames in each state, with no valid-sample gap over 750 ms.
5. Observe LED fades. A passing result means that pattern was observed visually; it is
   not an electrical measurement or proof of firmware execution.

## Seed a failure and verify

- After establishing working calibration, disconnect one LED jumper. Observe again.
  The selected region should fail to reach the expected bright state; its cause remains
  unverified. Check the source GPIO, wiring graph, polarity, resistor and jumpers.
- Alternatively edit a GPIO in a disposable copy of the sketch and upload externally;
  keep the declared wiring accurate. Inspect source and graph to compare the pins.
- Restore the jumper/firmware and choose **I fixed it — verify with the same check**.
  Only a passing verification linked to the same immutable configuration resolves the
  failed visual run. A passing ordinary repeat does not resolve it.
- A camera gap, stale source, changed resolution or excessive ambient-brightness drift
  yields unavailable data/inconclusive rather than a hardware diagnosis. Reconnecting
  a camera requires new calibration; an old check cannot verify against a new source.

## Limits and reusable CV architecture

The reusable parts are camera transport, frame timestamps, normalized image regions,
calibration, typed measurements, confirmed expectations, stored evidence, and verification.
Detectors and expectations stay specific to what can be observed: LED brightness,
marker orientation, object displacement, switch position, etc. A model can help propose
regions or checks, but a general video description cannot substitute for measured truth.

This LED detector computes a region's 80th-percentile maximum color-channel intensity,
minus median scene intensity, then normalizes against its labeled off/on references.
Ambient drift >25 intensity units invalidates samples; on/off contrast must differ by
at least 15. These are demo heuristics, not calibrated photometry. A covered LED, moved
camera, changing local lighting, or reflection can mimic a dark/bright region. Keep
framing fixed and verify visibility manually. Saturation and exposure changes may
require recalibration. Physical electrical cause, voltage, current, and PWM remain unknown.

Runs retain numeric samples and evidence, not raw images/video. Source/wiring context
IDs are attached to the result; the graph records each LED's latest measured state.
The existing Gemini/StepFun/Devin servo flow is not used by this LED observation path.
