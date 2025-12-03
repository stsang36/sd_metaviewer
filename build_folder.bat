@echo off
echo ========================================
echo  SD MetaViewer - Quick Build (Folder)
echo ========================================
echo.
echo This creates a folder-based distribution
echo which starts faster than the single-file version.
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

:: Install dependencies
echo Installing dependencies...
pip install Pillow windnd pyinstaller --quiet

:: Generate icon if it doesn't exist
echo.
echo Generating application icon...
python -c "from src.utils import create_app_icon, save_icon_file; icon = create_app_icon(); save_icon_file(icon, 'sd_metaviewer.ico') if icon else None"

:: Create the executable (folder mode - faster startup)
echo.
echo Building...
echo.

pyinstaller --noconfirm --onedir --windowed ^
    --name "SD MetaViewer" ^
    --add-data "src;src" ^
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
echo The application folder is at:
echo   dist\SD MetaViewer\
echo.
echo Run: dist\SD MetaViewer\SD MetaViewer.exe
echo.
pause
