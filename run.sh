#!/bin/bash
# SD MetaViewer - Run Script for macOS/Linux

cd "$(dirname "$0")"

echo "Starting SD MetaViewer..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.8 or later:"
    echo "  macOS: brew install python3"
    echo "  Linux: sudo apt install python3 python3-pip python3-tk"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.8"

if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    echo "ERROR: Python $REQUIRED_VERSION or later is required (found $PYTHON_VERSION)"
    exit 1
fi

# Check if required packages are installed
if ! python3 -c "import PIL" 2>/dev/null; then
    echo "Installing required packages..."
    python3 -m pip install --user Pillow
fi

# Run the application
python3 run.py

# Check exit status
if [ $? -ne 0 ]; then
    echo ""
    echo "Failed to start. Make sure you have:"
    echo "  1. Python 3.8+ installed"
    echo "  2. Required packages: pip3 install Pillow"
    echo "  3. On Linux: tkinter package (python3-tk)"
    read -p "Press Enter to exit..."
fi
