#include "led_control.h"

void ledSetup() {
  pinMode(LED_PIN, OUTPUT);
  Serial.println("LED ready");
}

void ledOn() {
  digitalWrite(LED_PIN, HIGH);
  Serial.println("ACK LED ON");
}

void ledOff() {
  digitalWrite(LED_PIN, LOW);
  Serial.println("ACK LED OFF");
}
