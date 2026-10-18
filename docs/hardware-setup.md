# Hardware setup (H0)

Goal: one `MOVE 90` from inteGREAT produces physical motion that the camera measures, and both demo faults
can be reproduced **safely** and undone.

## Parts
- ESP32 dev board (record the exact variant — the manifest says "DevKitC (ASSUMED)"; fix it).
- SG90-class servo + **external 5 V supply** rated ≥1 A. Never power the servo from the ESP32 3.3 V pin.
- Jumper leads; USB cable to the laptop.
- A camera OpenCV can open (built-in webcam, USB webcam; a portable monitor's camera only if Windows lists it).
- Printed ArUco markers: `apps/api/.venv/Scripts/python scripts/make_aruco_markers.py` → print at 100%.

## Wiring (matches `fixtures/manifests/esp32_servo_demo.yaml`)
| From | To | Note |
|---|---|---|
| ESP32 GPIO18 | servo signal (orange/yellow) | the pin the correct firmware uses |
| 5 V supply + | servo V+ (red) | |
| 5 V supply − | servo GND (brown) | |
| 5 V supply − | ESP32 GND | **common ground is required** |

If you change any of this, update the manifest (or the KiCad netlist mapping) and re-confirm wiring in the UI.

## Firmware
Flash `fixtures/esp32_servo_demo/` with the Arduino IDE (board: your ESP32 variant, library: ESP32Servo).
It accepts `MOVE <deg>` at 115200 baud and prints `ACK MOVE <deg>`. This is ordinary project firmware;
inteGREAT adds nothing to it.

## Camera + markers
1. Glue marker **id 1** flat on the servo horn; fix marker **id 0** next to the servo in the same plane.
2. Mount the camera fixed, ~20–40 cm away, facing the markers squarely; even lighting, no glare.
3. In inteGREAT → bottom panel **Devices** → *Find cameras* → *Connect* → check the preview shows both
   markers outlined.
4. Send the servo to a known angle (e.g. connect serial, run a test with `MOVE 0`, or use the Arduino serial
   monitor *before* connecting inteGREAT), then enter that angle and press **Calibrate**.

## Serial
- Devices → pick the COM port → **Connect**. inteGREAT opens it once with DTR/RTS held low so the board
  doesn't reset (D-005).
- To reflash (Fault A repair): **Release port** first — Windows lets only one program hold a COM port.

## Faults
- **Fault A (software):** flash `fixtures/esp32_servo_demo_fault_a/` (servo on GPIO19) while wiring stays on
  GPIO18. Repair: change `SERVO_PIN` to 18, reflash, click **Rescan**, then **Verify fix**.
- **Fault B (physical):** with correct firmware, **power down the 5 V supply**, unplug the servo signal lead,
  power back up. Repair: power down, reconnect, power up, **Verify fix**.
  Prefer unplugging signal over power; never short anything.

## Capture real traces (replaces synthetic fixtures)
After a live run completes, click **Save as replay** in the bottom bar. Files land in
`fixtures/recorded/real/` and appear in the source picker as "Recorded". Capture: good run, Fault A, Fault B.

## Checklist (record results in docs/STATUS.md)
- [ ] Board variant + COM port noted; opening the port does **not** reboot the board
- [ ] Camera index + fps noted; calibration within ±3° at 0° and 90°
- [ ] Good run passes 3× in a row
- [ ] Fault A fails, repair + rescan + verify passes
- [ ] Fault B fails, manual check recorded, repair + verify passes
- [ ] Real traces saved for all three
