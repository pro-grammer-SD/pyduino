#include "CheapStepper.h"

#define SPEED 15
#define STEPS 512
#define DELAY 1000

motor = CheapStepper(8, 9, 10, 11);
void setup() {
    motor.setRpm(SPEED);
}
void loop() {
    motor.moveCW(STEPS);
    delay(DELAY);
    motor.moveCCW(STEPS);
    delay(DELAY);
}