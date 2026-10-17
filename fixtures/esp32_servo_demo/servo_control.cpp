#include <ESP32Servo.h>
#include "servo_control.h"

static Servo armServo;

void servoSetup() {
  armServo.setPeriodHertz(50);
  armServo.attach(SERVO_PIN, 500, 2400);
  Serial.println("SERVO attached");
}

void moveServoTo(int angleDeg) {
  int clamped = constrain(angleDeg, 0, 180);
  armServo.write(clamped);
  Serial.print("ACK MOVE ");
  Serial.println(clamped);
}
