#pragma once
#include <Arduino.h>

#define SERVO_PIN 18

void servoSetup();
void moveServoTo(int angleDeg);
