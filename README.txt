========================================

# Arduino Python Transpiler

========================================

This tool converts C++ Arduino headers into Python stubs, and Python sketches into Arduino `.ino` files.
It also auto-detects imported headers, supports `#define` constants from Python variables, and enables direct upload to Arduino boards via `arduino-cli`.

---

## Setup / Requirements

---

1. Python 3.11+ (tested)
2. clang + libclang (Windows: `libclang.dll`)
3. Install Python dependencies:

   ```bash
   pip install clang rich
   ```
4. Arduino CLI installed and configured: [https://arduino.github.io/arduino-cli/installation/](https://arduino.github.io/arduino-cli/installation/)

---

## Usage

---

### 1. Convert Arduino header (.h) to Python stub

```bash
python arduino_transpile.py convert-header path/to/MyLibrary.h
```

* Creates `MyLibrary.py` stub with classes and methods.
* Supports multiple constructors, choosing the one with arguments automatically.

### 2. Convert Python sketch (.py) to Arduino `.ino`

```bash
python arduino_transpile.py to-ino path/to/sketch.py
```

* Auto-detects headers from Python imports (ignores `Arduino.py`).
* Converts Python constants (int/float) to `#define`.
* Converts Python classes/objects to Arduino objects.
* Generates proper `setup()` and `loop()` methods.
* Ignores unsupported Python statements like imports in the `.ino` file.

### 3. Upload Python sketch to Arduino

```bash
python arduino_transpile.py upload path/to/sketch.py --port COM6
```

* Converts `.py` → `.ino`, creates sketch folder if needed.
* Auto-detects Arduino Uno port if `--port` is omitted.
* Optional flags:

  * `--auto-loop`: Auto-generate `loop()` calling all functions.
  * `--fqbn <board>`: Specify Arduino board FQBN.
  * `--list-ports`: List all connected Arduino boards.

---

## Python Sketch Example

---

```python
from CheapStepper import CheapStepper

motor = CheapStepper(8, 9, 10, 11)
RPM = 15  # becomes #define RPM 15

def setup():
    motor.setRpm(RPM)

def loop():
    motor.moveCW(512)
    delay(1000)
    motor.moveCCW(512)
    delay(1000)
```

---

## Generated `.ino` Example

---

```cpp
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
```

---

## Notes

---

* Only Python constants (`int`/`float`) are converted to `#define`.
* Multiple constructors supported; the one with arguments is chosen automatically.
* Other Python statements transpiled into C++-style Arduino syntax.
* Unsupported Python imports/statements are ignored in `.ino`.
* If a header cannot be auto-detected, manually include it:

  ```cpp
  #include "MyLibrary.h"
  ```
* Contributions are welcome! :D

========================================
End of Guide
============
