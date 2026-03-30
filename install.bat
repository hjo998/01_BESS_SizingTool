@echo off
echo ============================================
echo  BESS Sizing Tool - Installation
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Create virtual environment
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate and install
echo Installing dependencies...
call venv\Scripts\activate.bat

REM Try offline wheels first, then online
if exist "wheels" (
    echo Installing from local wheels...
    pip install --no-index --find-links=wheels -r requirements.txt
) else (
    pip install -r requirements.txt
)

echo.
echo ============================================
echo  Installation complete!
echo  Run 'run.bat' to start the application.
echo ============================================
pause
