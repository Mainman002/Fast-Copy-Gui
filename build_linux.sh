#!/bin/bash
set -e

# Detect platform
OS=$(uname)

# Determine site-packages for current Python
SITE_PACKAGES=$(python3 -c "import site; print(site.getsitepackages()[0])")

# Common PyInstaller options
NAME="FastCopyGUI"
DATA_ARGS="--add-data fast_copy.sh:. --add-data assets:assets"

if [[ "$OS" == "Darwin" ]]; then
    # macOS: folder-based build is faster and more reliable
    pyinstaller --noconfirm --windowed \
        --name "$NAME" \
        $DATA_ARGS \
        main.py
else
    # Linux: bundle into onefile for portability
    pyinstaller --noconfirm --windowed \
        --name "$NAME" \
        --paths "$SITE_PACKAGES" \
        $DATA_ARGS \
        --onefile \
        main.py
fi
