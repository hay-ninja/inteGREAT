#pragma once
#include <Arduino.h>

#define SERVO_PIN 19

void servoSetup();
void moveServoTo(int angleDeg);
