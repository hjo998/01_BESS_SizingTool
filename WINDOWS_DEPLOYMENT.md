# BESS Sizing Tool - Windows Deployment Guide

This guide explains how to deploy and run the BESS Sizing Tool on a Windows machine (including offline/corporate environments).

## Prerequisites

- **Windows 7+** (Windows 10/11 recommended)
- **Python 3.9+** installed and added to PATH
- **Internet connection** (for first-time online installation) OR **pre-downloaded wheels** (for offline installation)

## Quick Start

### Option 1: Online Installation (Requires Internet)

1. Double-click `install.bat`
   - Automatically creates a Python virtual environment
   - Downloads and installs all dependencies from PyPI
   - Displays confirmation when complete

2. Double-click `run.bat`
   - Activates the virtual environment
   - Starts the Flask server on `http://localhost:5000`
   - Press `Ctrl+C` in the terminal to stop

### Option 2: Offline Installation (No Internet Required)

Use this method for corporate/offline environments.

**Step 1: Prepare wheels on an online machine**

On a machine with internet access:

1. Copy the entire project folder to this machine
2. Double-click `download_wheels.bat`
   - Downloads all dependencies as wheel files (.whl)
   - Stores them in the `wheels/` directory
   - Takes 2-5 minutes depending on connection speed

3. Copy the `wheels/` folder to a USB drive or shared location

**Step 2: Deploy to offline machine**

1. Copy the entire project folder (including the `wheels/` subdirectory) to the Windows machine
2. Double-click `install.bat`
   - Detects the `wheels/` folder
   - Installs all dependencies from local wheels (no internet needed)
   - Completes in 1-2 minutes

3. Double-click `run.bat` to start the server

## File Descriptions

| File | Purpose |
|------|---------|
| `install.bat` | Creates virtual environment & installs dependencies |
| `run.bat` | Activates environment & starts Flask server |
| `download_wheels.bat` | Pre-downloads wheels for offline installation |
| `requirements.txt` | List of Python package dependencies |

## Troubleshooting

### "Python not found"
- Install Python 3.9+ from [python.org](https://www.python.org/downloads/)
- During installation, check **"Add Python to PATH"**
- Close and reopen Command Prompt after installation

### "Virtual environment not found"
- Run `install.bat` first before `run.bat`

### Port 5000 already in use
- Edit `run.bat` and change `--port 5000` to another port (e.g., `--port 8000`)

### Installation fails offline
- Ensure the `wheels/` folder exists and contains .whl files
- Verify all files were copied correctly from the source machine

## Advanced Usage

### Custom Port

Edit `run.bat` and change the port number:
```bat
python run.py --host 0.0.0.0 --port 8080
```

### Debug Mode

Edit `run.bat` and add the `--debug` flag:
```bat
python run.py --host 0.0.0.0 --port 5000 --debug
```

### Manual Activation (CMD)

If you prefer to run commands manually:
```bat
venv\Scripts\activate.bat
python run.py
```

## System Requirements

- **Disk space**: ~200MB (including virtual environment and dependencies)
- **RAM**: 512MB minimum recommended
- **Network**: None required after initial setup (if using offline wheels)

## Support

For issues or questions, refer to:
- Main README: `README.md`
- Project documentation: `docs/`
- Handoff notes: `HANDOFF_TO_CLAUDE_CODE.md`
