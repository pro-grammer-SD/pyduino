@echo off
REM Clean old builds
rmdir /s /q dist

REM Install/upgrade hatch
python -m pip install --upgrade hatch

REM Build wheel
python -m hatch build

REM Uninstall old version
python -m pip uninstall -y pyduino

REM Install newly built wheel
for %%f in (dist\*.whl) do python -m pip install "%%f"

REM Run CLI
python -m pyduino %*
