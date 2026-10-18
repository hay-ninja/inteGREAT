// Two external LEDs: GPIO -> 330 ohm resistor -> LED anode; cathode -> GND.
// LED 1 fades up and down, then LED 2 takes its turn. Repeats automatically.
#include <Arduino.h>

const uint8_t LED_1_PIN = 18;
const uint8_t LED_2_PIN = 19;
const unsigned long FADE_STEP_MS = 5;  // About 1.3 seconds per fade.
const unsigned long BETWEEN_LEDS_MS = 150;

void fadeInAndOut(uint8_t pin) {
  for (int brightness = 0; brightness <= 255; ++brightness) {
    analogWrite(pin, brightness);
    delay(FADE_STEP_MS);
  }
  for (int brightness = 254; brightness >= 0; --brightness) {
    analogWrite(pin, brightness);
    delay(FADE_STEP_MS);
  }
}

void setup() {
  pinMode(LED_1_PIN, OUTPUT);
  pinMode(LED_2_PIN, OUTPUT);
  analogWrite(LED_1_PIN, 0);
  analogWrite(LED_2_PIN, 0);
}

void loop() {
  fadeInAndOut(LED_1_PIN);
  delay(BETWEEN_LEDS_MS);
  fadeInAndOut(LED_2_PIN);
  delay(BETWEEN_LEDS_MS);
}
