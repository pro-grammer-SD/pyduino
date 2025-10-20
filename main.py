from CheapStepper import CheapStepper
from Arduino import *

# Instantiate the stepper with pins 8, 9, 10, 11
motor = CheapStepper(8, 9, 10, 11)
SPEED=15
STEPS=512
DELAY=1000

def setup():
    motor.setRpm(SPEED)  # set speed

def loop():
    motor.moveCW(STEPS)   # move clockwise 512 steps
    delay(DELAY)         # wait 1 second
    motor.moveCCW(STEPS)  # move counter-clockwise 512 steps
    delay(DELAY)
    