@echo off
echo Downloading wheels for offline installation...
if not exist "wheels" mkdir wheels
pip download -r requirements.txt -d wheels --python-version 3.9 --platform win_amd64 --only-binary=:all:
echo.
echo Wheels downloaded to wheels/ directory.
echo Copy this entire folder to the target machine.
pause
