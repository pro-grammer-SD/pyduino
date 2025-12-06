from typing import Any

HIGH = 1
LOW = 0
INPUT = 0
OUTPUT = 1
INPUT_PULLUP = 2

def pinMode(pin: int, mode: int) -> None: ...
def digitalWrite(pin: int, value: int) -> None: ...
def digitalRead(pin: int) -> int: return LOW
def analogWrite(pin: int, value: int) -> None: ...
def analogRead(pin: int) -> int: return 0
def delay(ms: int) -> None: ...
def delayMicroseconds(us: int) -> None: ...
def millis() -> int: return 0
def map(value: int, a: int, b: int, c: int, d: int) -> int:
    return (value - a) * (d - c) // (b - a) + c
def constrain(value: int, a: int, b: int) -> int:
    return max(a, min(value, b))
