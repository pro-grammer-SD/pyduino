#include "CheapStepper.h"

CheapStepper motor(8, 9, 10, 11);
void setup() {
    motor.setRpm(15);
}
void loop() {
    motor.moveCW(512);
    delay(1000);
    motor.moveCCW(512);
    delay(1000);
}