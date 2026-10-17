// ESP32 servo demo — ordinary project firmware (no inteGREAT instrumentation).
// Accepts "MOVE <deg>" over serial at 115200 baud.
#include "servo_control.h"
#include "wifi_status.h"

void handleCommand(const String& line);

void setup() {
  Serial.begin(115200);
  Serial.println("BOOT esp32_servo_demo v1.2");
  servoSetup();
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
  if (line.startsWith("MOVE ")) {
    int target = line.substring(5).toInt();
    moveServoTo(target);
  } else {
    Serial.print("ERR unknown command: ");
    Serial.println(line);
  }
}
