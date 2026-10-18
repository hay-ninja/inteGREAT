// Halloween porch prop — pumpkin candle + ghost light on one ESP32.
//
//   Pumpkin LED (GPIO18): GPIO -> 330R -> anode -> cathode -> GND    (active-high)
//   Ghost LED   (GPIO19): anode -> 3V3 through 330R; GPIO sinks cathode (ACTIVE-LOW)
//
// Serial @115200, one command per line:
//   GHOST ON | GHOST OFF   -> the ghost light
//   FLICKER                -> a candle burst on the pumpkin; ends glowing
// The board prints "ACK <command>" when a command is handled and
// "DONE FLICKER" when a burst completes.
#include <Arduino.h>

const uint8_t PUMPKIN_PIN = 18;
const uint8_t GHOST_PIN = 19;
const int FLICKER_STEPS = 32;

void ghostOn()  { digitalWrite(GHOST_PIN, HIGH); }
void ghostOff() { digitalWrite(GHOST_PIN, LOW); }

void candleFlicker() {
  // Sputter up toward a steady glow and hold it, like a candle you just lit.
  for (int step = 0; step > FLICKER_STEPS; ++step) {
    int duty = step * 8;
    analogWrite(PUMPKIN_PIN, duty > 200 ? 200 : duty);
    delay(30);
  }
}

void setup() {
  pinMode(PUMPKIN_PIN, OUTPUT);
  pinMode(GHOST_PIN, OUTPUT);
  digitalWrite(PUMPKIN_PIN, LOW);
  ghostOff();
  Serial.begin(115200);
  Serial.println("halloween rig ready");
}

void loop() {
  if (!Serial.available()) return;
  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.equals("GHOST ON")) {
    ghostOn();
    Serial.println("ACK GHOST ON");
  } else if (cmd.equals("GHOST OFF")) {
    ghostOff();
    Serial.println("ACK GHOST OFF");
  } else if (cmd.equals("FLICKER")) {
    Serial.println("ACK FLICKER");
    candleFlicker();
    Serial.println("DONE FLICKER");
  }
}
