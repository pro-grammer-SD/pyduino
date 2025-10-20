========================================
Arduino Python Transpiler
========================================

This tool converts C++ Arduino headers into Python stubs,
and Python sketches into Arduino .ino files.

It also auto-detects imported headers and supports
#define constants from Python variables.

----------------------------------------
Setup / Requirements
----------------------------------------
1. Python 3.11+ (tested)
2. clang + libclang (Windows: libclang.dll)
3. Install Python dependencies:
   pip install clang

----------------------------------------
Usage
----------------------------------------
1. Convert Arduino header (.h) to Python stub:
   python arduino_transpile.py convert-header path/to/MyLibrary.h
   - This creates MyLibrary.py stub with classes and methods.

2. Convert Python sketch (.py) to Arduino .ino:
   python arduino_transpile.py to-ino path/to/sketch.py
   - Automatically detects all headers from Python imports (except Arduino.py)
   - Converts Python constants to #define
   - Converts Python classes/objects to Arduino objects
   - Generates proper setup() and loop() methods

----------------------------------------
Python Sketch Example
----------------------------------------
from CheapStepper import CheapStepper

motor = CheapStepper(8, 9, 10, 11)
RPM = 15  # will become #define RPM 15

def setup():
    motor.setRpm(RPM)

def loop():
    motor.moveCW(512)
    delay(1000)
    motor.moveCCW(512)
    delay(1000)

----------------------------------------
Generated .ino Example
----------------------------------------
#include "CheapStepper.h"

CheapStepper motor(8, 9, 10, 11);
#define RPM 15

void setup() {
    motor.setRpm(RPM);
}

void loop() {
    motor.moveCW(512);
    delay(1000);
    motor.moveCCW(512);
    delay(1000);
}

----------------------------------------
Notes
----------------------------------------
- Only Python constants (int/float) are converted to #define.
- Multiple constructors are supported; the one with arguments is chosen automatically.
- Other Python statements are transpiled into C++-style Arduino syntax.
- If a header cannot be detected, manually add it as:
  #include "MyLibrary.h"
- Contributions are OPENLY supported! :D

========================================
End of Guide
========================================
