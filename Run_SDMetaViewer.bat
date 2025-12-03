@echo off
cd /d "%~dp0"
echo Starting SD MetaViewer...
python run.py
if errorlevel 1 (
    echo.
    echo Failed to start. Make sure you have:
    echo   1. Python 3.8+ installed
    echo   2. Required packages: pip install Pillow windnd
    pause
)
