from CheapStepper import CheapStepper
from Arduino import *

# Instantiate the stepper with pins 8, 9, 10, 11
motor = CheapStepper(8, 9, 10, 11)

def setup():
    motor.setRpm(15)  # set speed

def loop():
    motor.moveCW(512)   # move clockwise 512 steps
    delay(1000)         # wait 1 second
    motor.moveCCW(512)  # move counter-clockwise 512 steps
    delay(1000)
    