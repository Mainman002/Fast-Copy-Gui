# Fast-Copy-GUI

Fast-Copy-GUI is a cross-platform desktop application (macOS and Linux) that provides a graphical frontend for parallel file copying. It allows users to select source and destination directories, configure the number of copy threads, monitor progress in real-time, and manage operations efficiently with a simple and responsive interface.

## Features

* Select source and destination directories using a folder picker.
* Configure the number of parallel copy threads.
* Start and cancel copy operations at any time.
* Progress bar and real-time log output for monitoring copy status.
* Dark and light themes.
* Persistent configuration for last used folders, theme, and thread count.

<img width="812" height="640" alt="Screenshot 2025-12-02 at 10 55 53 AM" src="https://github.com/user-attachments/assets/79531fd6-017e-4469-a472-9da96f5e10c8" />

## Installation

### Prerequisites

* Python 3.11 or higher.
* PySide6 for GUI: install via pip.

#### Linux Dependencies

Depending on the distribution, you may need to install additional system libraries:

* `libgl1-mesa-glx`
* `libxcb1`
* `libx11-6`
* `libxext6`
* `libfreetype6`

#### macOS Dependencies

* PySide6 installed via pip.
* No additional system dependencies are typically required for macOS.

### Install Python Dependencies

```bash
pip install PySide6
```

## Running from Source

Clone the repository and run the main application:

```bash
git clone https://github.com/Mainman002/Fast-Copy-GUI.git
cd Fast-Copy-GUI
python main.py
```

## Building Standalone Executables

To build a standalone executable for Linux or macOS, PyInstaller can be used:

# linux
```bash
pyinstaller --noconfirm --windowed --name "FastCopyGUI" \
    --add-data "fast_copy.sh:." main.py
```

# macOS
```bash
pyinstaller --noconfirm --windowed --name "FastCopyGUI" \
    --add-data "fast_copy.sh:." main.py
```

The resulting executable will be located in the `dist` directory.

## Usage

1. Click the "Source" button to select the source directory.
2. Click the "Destination" button to select the destination directory.
3. Adjust the "Threads" spin box to set the number of parallel copy threads.
4. Click "Start Copy" to begin the operation. Click again to cancel if needed.
5. Monitor progress using the progress bar and log output.

## Configuration

Fast-Copy-GUI stores configuration in the file:

```
~/.fast_copy_gui_config.json
```

The configuration includes:

* Last used source and destination directories.
* Theme (dark or light).
* Number of copy threads.

The configuration is automatically updated whenever settings are changed.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
