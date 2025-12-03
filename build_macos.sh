#!/bin/bash

pyinstaller --noconfirm --windowed \
    --name "FastCopyGUI" \
    --add-binary "/usr/bin/rsync:binaries/linux/" \
    --add-data "assets:assets" \
    main.py
