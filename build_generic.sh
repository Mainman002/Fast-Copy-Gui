#!/bin/bash

# ===============================================

# Build FastCopyGUI Executable for macOS/Linux

# ===============================================

set -e

# Detect OS

OS_TYPE="$(uname)"
echo "Detected OS: $OS_TYPE"

# Paths

VENV_PATH="$HOME/python-global"
PYTHON="$VENV_PATH/bin/python"
PYINSTALLER="$VENV_PATH/bin/pyinstaller"

# Check virtual environment

if [ ! -x "$PYTHON" ]; then
    echo "ERROR: Python virtual environment not found at $VENV_PATH"
    echo "Create it first with: python3 -m venv $VENV_PATH"
    exit 1
fi

# Install PyInstaller if missing

if [ ! -x "$PYINSTALLER" ]; then
    echo "Installing PyInstaller in global venv..."
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install pyinstaller
fi

# Assets & PySide6 plugin paths

ASSETS_PATH="assets"
PY_SIDE_PLUGINS="$VENV_PATH/lib/python3.14/site-packages/PySide6/plugins"

# Build command

BUILD_CMD=( "$PYINSTALLER" --paths "$VENV_PATH/lib/python3.14/site-packages" --onefile --windowed )

# Add assets folder

if [ -d "$ASSETS_PATH" ]; then
    BUILD_CMD+=( --add-data "$ASSETS_PATH:$ASSETS_PATH" )
fi

# Add PySide6 plugins

if [ -d "$PY_SIDE_PLUGINS" ]; then
    BUILD_CMD+=( --add-data "$PY_SIDE_PLUGINS:PySide6/plugins" )
fi

# Platform-specific options

if [[ "$OS_TYPE" == "Darwin" ]]; then
    BUILD_CMD+=( --name "FastCopyGUI" main.py )
elif [[ "$OS_TYPE" == "Linux" ]]; then
    BUILD_CMD+=( --name "FastCopyGUI" main.py )
else
    echo "Unsupported OS: $OS_TYPE"
    exit 1
fi

# Execute PyInstaller build

echo "Running PyInstaller..."
"${BUILD_CMD[@]}"

echo "Build complete! Executable is in the 'dist' folder."
