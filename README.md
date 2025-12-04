# Fast-Copy-GUI

**Fast-Copy-GUI** is a cross-platform desktop application (Windows, MacOS, and Linux) that provides a graphical frontend for fast, robust file synchronization and copying using the native **rsync** or **robocopy** utilities.
It allows users to select source and destination directories, configure move/invert options, monitor progress in real-time, and manage operations efficiently with a simple and responsive interface.

---

## Features

* Select source and destination directories using a folder picker.
* **New:** Uses the robust `rsync` utility for reliable file transfer and integrity checking.
* **New:** Options to perform a move operation (`--remove-source-files`) or invert the source/destination paths.
* Start and cancel copy operations at any time.
* Progress bar and real-time log output for monitoring copy status.
* Dark and light themes.
* Persistent configuration for last used folders, theme, and settings.

<img width="870" height="682" alt="Screenshot 2025-12-04 at 10 49 02 AM" src="https://github.com/user-attachments/assets/971fd74c-bae6-480d-9778-c0e645640921" />

---

## Installation

### Prerequisites

* **Python 3.11 or higher**
* **PySide6** (install via pip)
* **rsync** (must be installed and accessible via system path)

On macOS, the application prefers the Homebrew version if installed at:

* `/opt/homebrew/bin/rsync`
* `/usr/local/bin/rsync`

---

## Linux Dependencies

Depending on distribution, you may need:

* `libgl1-mesa-glx`
* `libxcb1`
* `libx11-6`
* `libxext6`
* `libfreetype6`

---

## macOS Dependencies

* PySide6 installed via pip
* No additional system dependencies typically required

---

## Install Python Dependencies

```bash
pip install PySide6
```

---

## Running from Source

```bash
git clone -b rsync https://github.com/Mainman002/Fast-Copy-Gui.git
cd Fast-Copy-GUI
python main.py
```

---

## Building Standalone Executables

To build a standalone executable for Linux or macOS, use **PyInstaller**. (Note: we no longer bundle `fast_copy.sh.linux`.)

### Linux

```bash
./build_linux.sh
```

### macOS

```bash
./build_macos.sh
```

The resulting executable will be located in the **dist** directory.

---

## Usage

1. Click **"Source"** to select the source directory.
2. Click **"Destination"** to select the destination directory.
3. (Optional) Check **"Move"** to delete files from the source after a successful copy.
4. (Optional) Check **"Invert"** to swap the source and destination directories.
5. Click **"Start Copy"** to begin.
6. Click **"Cancel Copy"** if needed.
7. Monitor progress using the progress bar and log output.

---

## Configuration

Fast-Copy-GUI stores its configuration in:

```
~/.fast_copy_gui_config.json
```

Stored data includes:

* Last used source and destination directories
* Theme (dark or light)
* Last used states of **Move** and **Invert** options

Configuration updates automatically whenever settings change.

---

## License

Licensed under the **MIT License**.
See the `LICENSE` file for details.
