#include <Arduino.h>
#include "wifi_status.h"

const int STATUS_LED_PIN = 2;
static unsigned long lastBlink = 0;

void wifiStatusSetup() {
  pinMode(STATUS_LED_PIN, OUTPUT);
  Serial.println("WIFI idle");
}

void wifiStatusPoll() {
  if (millis() - lastBlink > 1000) {
    lastBlink = millis();
    digitalWrite(STATUS_LED_PIN, !digitalRead(STATUS_LED_PIN));
  }
}
