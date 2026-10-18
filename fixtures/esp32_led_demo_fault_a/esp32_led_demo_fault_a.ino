// ESP32 status-LED demo — ordinary project firmware (no inteGREAT instrumentation).
// Accepts "LED ON" / "LED OFF" over serial at 115200 baud.
#include "led_control.h"
#include "wifi_status.h"

void handleCommand(const String& line);

void setup() {
  Serial.begin(115200);
  Serial.println("BOOT esp32_led_demo v1.1");
  ledSetup();
  wifiStatusSetup();
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    handleCommand(line);
  }
  wifiStatusPoll();
}

void handleCommand(const String& line) {
  if (line.startsWith("LED ON")) {
    ledOn();
  } else if (line.startsWith("LED OFF")) {
    ledOff();
  } else {
    Serial.print("ERR unknown command: ");
    Serial.println(line);
  }
}
