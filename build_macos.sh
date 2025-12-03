#!/bin/bash

pyinstaller --noconfirm --windowed \
    --name "FastCopyGUI" \
    --add-data "fast_copy.sh:." \
    --add-data "assets:assets" \
    main.py
