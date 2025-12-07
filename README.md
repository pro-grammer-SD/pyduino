# 🌟 PyDuino - Python to Arduino Bridge 🌟

PyDuino is a Python-to-Arduino transpiler and uploader. Write Arduino sketches in Python, automatically convert them to C++ `.ino` files, and upload to your Arduino board.

---

## ⚡ Features

* Convert C++ headers to Python stubs (`.py`) 📝
* Transpile Python scripts to Arduino `.ino` files ⚙️
* Auto-generate `setup()` and `loop()` if missing 🔄
* Upload sketches directly to Arduino from Python 🚀
* Detect Arduino headers in Python files 🔍
* List available COM ports 📡
* Support for multiple function overloads and basic Python-to-C++ expressions ✨
* Your comments are retained! 🗣️

---

## 🛠️ Setup Guide

1. Clone or download the PyDuino repo.
2. Ensure that Python 3.11+ is installed.
3. Run `build.bat`.
4. Enjoy!
5. Examples at: https://github.com/pro-grammer-SD/pyduino_seperate_tests/

---

## 🚀 Commands

### 1️⃣ Create a new project

```bash
python main.py create <project_name>
```

Creates a folder with `main.py` and `lib/` for headers.

### 2️⃣ Convert C++ header to Python stub

```bash
python main.py convert-header <header_file> [--libclang <path_to_libclang>] # or you can skip --libclang by default!
```

Generates Python `.py` stubs in `lib/`.

### 3️⃣ Transpile Python to `.ino`

```bash
python main.py to-ino <python_file> [--auto-loop]
```

Generates `.ino` file. `--auto-loop` will call all functions in `loop()` automatically.

### 4️⃣ Setup Arduino AVR core

```bash
python main.py setupavr
```

Installs the Arduino AVR core using `arduino-cli`.

### 5️⃣ Upload Python script to Arduino

```bash
python main.py upload <python_file> [--auto-loop] [--port <COM>] [--list-ports] [--fqbn <fqbn>]
```

* `--auto-loop`: auto-call functions in `loop()`
* `--port`: specify COM port
* `--list-ports`: show available boards
* `--fqbn`: Fully Qualified Board Name (default: `arduino:avr:uno`)

---

## 📦 Python-to-C++ Conversion

* Converts Python `for`, `while`, `if`, and function definitions to Arduino C++.
* Supports arithmetic, boolean, comparison, and unary operations.
* Detects headers from `from lib.<header> import` lines.

---

## 💡 Logging

* Upload logs are stored in `<sketch_dir>/logs/YYYYMMDD_HHMMSS.log`

---

## ⚙️ Example Workflow

```bash
# Create a project
python main.py create MyProject

# Convert a header
python main.py convert-header lib/CheapStepper.h

# Transpile Python to .ino
python main.py to-ino main.py --auto-loop

# List ports
python main.py upload main.py --list-ports

# Upload to board
python main.py upload main.py --port COM3 --fqbn arduino:avr:uno

#💡 Tip: the port is auto-detected, so generally in normal cases you don't need to specify it. Only use it if you really need to.
```

---

Made with 💜 by @pro-grammer-SD
