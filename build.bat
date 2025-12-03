@echo off
echo ========================================
echo  SD MetaViewer - Build Script
echo ========================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8 or later from https://python.org
    pause
    exit /b 1
)

:: Install dependencies if needed
echo Installing/updating dependencies...
pip install Pillow windnd pyinstaller --quiet

:: Generate icon if it doesn't exist
echo.
echo Generating application icon...
python -c "from src.utils import create_app_icon, save_icon_file; icon = create_app_icon(); save_icon_file(icon, 'sd_metaviewer.ico') if icon else None"

:: Create the executable
echo.
echo Building executable...
echo.

pyinstaller --noconfirm --onefile --windowed ^
    --name "SD MetaViewer" ^
    --add-data "src;src" ^
    --optimize 2 ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageTk ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import PIL.ImageGrab ^
    --hidden-import windnd ^
    --icon "sd_metaviewer.ico" ^
    run.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Build Complete!
echo ========================================
echo.
echo The executable is located at:
echo   dist\SD MetaViewer.exe
echo.
echo You can copy this file anywhere and run it.
echo.
pause
