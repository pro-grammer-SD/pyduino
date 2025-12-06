#include "CheapStepper.h"

CheapStepper motor(8, 9, 10, 11);
#define SPEED 15
#define STEPS 512
#define DELAY 1000

void setup() {
    motor.setRpm(SPEED);
}
void loop() {
    motor.moveCW(STEPS);
    delay(DELAY);
    motor.moveCCW(STEPS);
    delay(DELAY);
}
