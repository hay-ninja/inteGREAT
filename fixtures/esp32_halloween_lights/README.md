# Haunted Breadboard

An original Halloween jingle for a **passive piezo transducer**, with two LEDs
alternating at each sounding note. It starts off; press the button to play or stop.
While enabled, it repeats after a silent rest.
The LED outputs are digital on/off, not PWM; tone generation has its own output.

## Wiring (classic ESP32-WROOM)

Unplug USB while wiring. Keep the existing LED connections:

- GPIO18 -> 330-ohm resistor -> LED 1 anode; cathode -> GND.
- GPIO21 -> separate 330-ohm resistor -> LED 2 anode; cathode -> GND.
- **For a confirmed small passive piezo only:** GPIO19 -> 1-kilohm series resistor
  -> piezo positive; piezo negative -> GND. The series resistor limits drive current
  and reduces volume. GPIO19 is not a classic ESP32 boot-strapping/programming pin.
- Power the ESP32 through USB. No external motor supply or HW-627 is involved.
- Connect a **normally open momentary pushbutton between GPIO4 and GND**. No
  external resistor is needed: firmware uses `INPUT_PULLUP` (pressed = LOW).
  With a four-leg tactile switch, each pair of internally connected legs is one
  terminal: use one leg from each separate terminal, not two already connected legs.
  Check continuity or the switch pinout if unsure; straddling the breadboard center
  gap is often convenient. Do not connect the button to 5 V.

One press starts from the beginning; the next press immediately silences the buzzer
and turns both LEDs off after 35 ms debounce. Holding the button does not repeat.
A button held at boot must be released and pressed again to start. This controls
playback; the ESP32 remains powered and able to read the button.

The owner confirmed a passive buzzer is available, but its exact part and whether
it is piezo or magnetic are not identified. Do **not** apply this direct-drive wiring
to an unknown magnetic buzzer, low-impedance speaker, or powered module. A magnetic
sounder may need a transistor/flyback circuit; a three-pin module has different
power/signal wiring. An active buzzer generally plays its own fixed pitch rather
than this melody. Confirm the part's markings/type before connecting it.

The owner's other part, **TMB12A05**, is an active magnetic buzzer; published versions
are rated 5 V and up to 30 mA. Do not use that part on the direct GPIO circuit.
It can provide a fixed-tone rhythm through a suitable driver, not this pitched melody.
[Manufacturer specification hosted by LCSC](https://www.lcsc.com/datasheet/C96093.pdf).

## Run

Open `esp32_halloween_lights.ino` in Arduino IDE, select the ESP32 board/port, and
upload manually. No extra Arduino libraries are needed. Change `BPM` to change tempo.
After uploading, press the button to start. Serial Monitor at 115200 also accepts
`s` to stop and `p` to restart; line-ending bytes
are ignored. Leave the monitor closed if another program needs the serial port.

## inteGREAT demo

Import this folder plus `fixtures/manifests/esp32_halloween_lights.yaml` using
absolute paths. That manifest assumes the passive-piezo circuit above and marks
all wiring unverified. Use the existing two-LED visual check to select/calibrate
each LED while the tune is playing. The eight-second expectation checks alternating
dim/bright phases, not fade smoothness or synchronization with audio. Both LEDs
are off during rests. At the default 120 BPM the sounding phases are long enough
for the camera's normal sampling rate; faster tempos need validation.
Press the button to start playback before running the visual check. An intentionally
stopped system will not satisfy the confirmed alternating-light expectation.

The buzzer appears in the hardware graph, but **sound, pitch and audio/LED beat
synchronization are not measured by inteGREAT**. Camera brightness cannot verify
a song. This firmware and its host tests do not establish hardware operation.

Validation: compiled for `esp32:esp32:esp32` using installed Arduino-ESP32 3.3.2;
host simulation checks alternating LEDs, tone timing, stop/restart and millis wrap.
No hardware was flashed or tested by the coding agent.
