@echo off
echo ============================================
echo  SI Sizing Tool Ver.2.0 - Starting Server
echo ============================================
echo.

if not exist "venv" (
    echo ERROR: Virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo Starting server at http://localhost:5000
echo Press Ctrl+C to stop.
echo.
python run.py --host 0.0.0.0 --port 5000
pause
