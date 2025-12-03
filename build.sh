#!/bin/bash
# SD MetaViewer - Build Script for macOS/Linux

echo "========================================"
echo " SD MetaViewer - Build Script"
echo "========================================"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python is not installed or not in PATH"
    echo "Please install Python 3.8 or later:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip"
    read -p "Press Enter to exit..."
    exit 1
fi

# Install dependencies if needed
echo "Installing/updating dependencies..."
python3 -m pip install --user Pillow pyinstaller --quiet

# Generate icon if it doesn't exist
echo ""
echo "Generating application icon..."
python3 -c "from src.utils import create_app_icon, save_icon_file; icon = create_app_icon(); save_icon_file(icon, 'sd_metaviewer.ico') if icon else None"

# Detect platform for platform-specific options
PLATFORM=$(uname -s)
echo ""
echo "Detected platform: $PLATFORM"

# Create the executable
echo ""
echo "Building executable..."
echo ""

if [ "$PLATFORM" = "Darwin" ]; then
    # macOS build
    pyinstaller --noconfirm --onefile --windowed \
        --name "SD MetaViewer" \
        --add-data "src:src" \
        --optimize 2 \
        --hidden-import PIL \
        --hidden-import PIL.Image \
        --hidden-import PIL.ImageTk \
        --hidden-import PIL.ImageDraw \
        --hidden-import PIL.ImageGrab \
        --osx-bundle-identifier "com.sdmetaviewer.app" \
        --icon "sd_metaviewer.ico" \
        run.py
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "========================================"
        echo " Build Complete!"
        echo "========================================"
        echo ""
        echo "The application is located at:"
        echo "  dist/SD MetaViewer.app"
        echo ""
        echo "You can copy this to your Applications folder."
        echo ""
    else
        echo ""
        echo "ERROR: Build failed!"
        read -p "Press Enter to exit..."
        exit 1
    fi
else
    # Linux build
    pyinstaller --noconfirm --onefile --windowed \
        --name "SD MetaViewer" \
        --add-data "src:src" \
        --optimize 2 \
        --hidden-import PIL \
        --hidden-import PIL.Image \
        --hidden-import PIL.ImageTk \
        --hidden-import PIL.ImageDraw \
        --hidden-import PIL.ImageGrab \
        --icon "sd_metaviewer.ico" \
        run.py
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "========================================"
        echo " Build Complete!"
        echo "========================================"
        echo ""
        echo "The executable is located at:"
        echo "  dist/SD MetaViewer"
        echo ""
        echo "You can copy this file anywhere and run it."
        echo ""
    else
        echo ""
        echo "ERROR: Build failed!"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi
