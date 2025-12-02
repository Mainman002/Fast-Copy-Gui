# Fast-Copy-Gui
Linux &amp; MacOS file copy gui.

## Dependancies
* Python 3.11+              # or your target Python version
* PySide6 (via pip)         # GUI framework

## Linux Setup
```bash
sudo apt install python3 python3-pip libgl1-mesa-glx libx11-6 libxext6 libxcb1 libfreetype6
```

## Start App
```bash
python ./main.py
```

## Build App Dependancies
```bash
pip install pyinstaller
```

## Build App
```bash
pyinstaller --noconfirm --windowed --name "FastCopyGUI" python_gui.py
```

## Build App Included Dependancies
```bash
pyinstaller --hidden-import=PySide6.QtGui --hidden-import=PySide6.QtWidgets python_gui.py
```

## Usage
* The Source directory is where the files you want to copy exist
* The Destination directory is where you want to paste the files into
* Threads are how many files will try to copy at the same time
* Start Copy button will begin the process (can be canceled by clicking it again)
* Dark / Light is a theme switcher that kinda works
* If files already exist in a directory they will be skipped