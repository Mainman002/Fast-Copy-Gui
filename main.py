import sys
import os
import signal
import subprocess
import json
import multiprocessing
import re # Added for rsync progress parsing
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QProgressBar, QTextEdit,
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QSpinBox, QSpacerItem, QSizePolicy,
    QScrollArea, QCheckBox
)

from PySide6.QtGui import (
    QPalette, QColor, QIcon, QFont # Added QFont for global font manipulation
)

from PySide6.QtCore import QThread, Signal, QSize, Qt, QDir

def get_asset_path(filename):
    if getattr(sys, 'frozen', False):
        # Running from PyInstaller bundle
        base_dir = os.path.join(sys._MEIPASS, "assets")
    else:
        # Running from source
        base_dir = os.path.join(os.path.dirname(__file__), "assets")
    return os.path.join(base_dir, filename)

# Folder Icon Image
# Note: 'icons/folder.svg' needs to be included in the assets folder for PyInstaller
folder_icon_light = get_asset_path("icons/dark_folder.png")
folder_icon_dark = get_asset_path("icons/light_folder.png")

CONFIG_FILE = os.path.expanduser("~/.fast_copy_gui_config.json")

class CopyWorker(QThread):
    progress_signal = Signal(int)
    log_signal = Signal(str)
    
    # Removed 'threads' argument as it is no longer used by rsync
    def __init__(self, src, dst, move=False, invert=False, ignore_existing=True):
        super().__init__()
        
        # Handle Invert logic here by swapping src/dst internally
        if invert:
            self.src = dst
            self.dst = src
        else:
            self.src = src
            self.dst = dst

        self.move = move
        self.invert = invert
        self.ignore_existing = ignore_existing
        self._process = None
        self._cancel_requested = False
    
    def run(self):
        # --- 1. RSYNC COMMAND CONSTRUCTION AND PATH CHECK ---
        
        # Define the rsync executable path. 
        # On macOS, Homebrew versions are often preferred over the default system version.
        rsync_path = "rsync"
        
        # Check common Homebrew paths on macOS for Apple Silicon and Intel
        homebrew_paths = [
            "/opt/homebrew/bin/rsync",  # Apple Silicon default
            "/usr/local/bin/rsync"     # Intel default
        ]
        
        for path in homebrew_paths:
            if os.path.exists(path):
                rsync_path = path
                break

        # -a: archive mode
        # -h: human-readable numbers
        # -v: verbose output (keeps file names logging)
        # --info=progress2: Reports OVERALL job progress (total bytes transferred)
        
        rsync_cmd_base = [rsync_path, "-ahv", "--info=progress2", "--exclude=.DS_Store"]

        if self.move:
            rsync_cmd_base.append("--remove-source-files")
        
        if self.ignore_existing:
            rsync_cmd_base.append("--ignore-existing")

        # Crucially, append a trailing slash to the source to copy contents, not the parent folder.
        # This is the single rsync command for the entire operation.
        cmd = rsync_cmd_base + [
            os.path.join(self.src, ""), 
            self.dst
        ]
        
        try:
            if rsync_path != "rsync":
                self.log_signal.emit(f"Using Homebrew rsync: {rsync_path}")
                
            self.log_signal.emit(f"Starting rsync from '{self.src}' → '{self.dst}'")
            self.log_signal.emit(f"Command: {' '.join(cmd)}\n")
        except RuntimeError:
            pass
            
        # --- 2. EXECUTION ---
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
        except FileNotFoundError:
            self.log_signal.emit(f"Error: rsync command not found at path: {rsync_path}. Ensure rsync is installed and accessible.")
            return

        # --- 3. PROGRESS PARSING (Using Regex for Robustness) ---
        # Look for the progress2 line format: e.g., 1,234,567,890 2,000,000,000 10.00M/s 61% 0:00:20
        
        for raw_line in self._process.stdout:
            if self._cancel_requested:
                # Signal the process to terminate
                self._process.terminate() 
                try:
                    self.log_signal.emit("Copy canceled by user.")
                except RuntimeError:
                    pass
                return

            line = raw_line.strip()
            
            # --- PROGRESS LINES (Filter and extract overall progress) ---
            # Identify the overall progress line by presence of B/s, %, and time remaining (:)
            if 'B/s' in line and '%' in line and ':' in line:
                try:
                    # Use regex to find the percentage number (\d+) followed by %
                    match = re.search(r'\s(\d+)%', line)
                    
                    if match:
                        percent = int(match.group(1))
                        self.progress_signal.emit(percent)
                except:
                    # Ignore lines that look like progress but fail parsing
                    pass
                # Crucial: Skip logging the continuous progress line to avoid spam
                continue 

            # --- EVERYTHING ELSE ---
            # Log all other output (file names from -v, initial lists, error messages)
            if line:
                try:
                    self.log_signal.emit(line)
                except RuntimeError:
                    pass

        self._process.wait()
        
        # --- 4. COMPLETION / ERROR CHECK ---
        return_code = self._process.returncode
        
        if return_code == 0:
            message = "\nCopy complete!"
        elif self._cancel_requested:
            message = "\nCanceled."
        else:
            message = f"\nCopy failed with exit code {return_code}. Check log for details."

        try:
            self.log_signal.emit(message)
        except RuntimeError:
            pass
    
    def cancel(self):
        self._cancel_requested = True
        if self._process:
            # Send a termination signal
            self._process.terminate()

def apply_dark_palette(app):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(240, 240, 240))
    palette.setColor(QPalette.Base, QColor(20, 20, 20))
    palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ToolTipBase, QColor(240, 240, 240))
    palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.Text, QColor(240, 240, 240))
    palette.setColor(QPalette.Button, QColor(50, 50, 50))
    palette.setColor(QPalette.ButtonText, QColor(240, 240, 240))
    palette.setColor(QPalette.Highlight, QColor(50, 100, 200))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

class CopyGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fast Copy GUI")
        self.resize(700, 500)
        self.theme_toggle = False
        self.copying = False
        self.move = False
        self.invert = False
        self.ignore_existing = True
        self.log_font_size = 12  # Default font size
        self.setFocus(Qt.OtherFocusReason)

        main_layout = QVBoxLayout(self)

        # === Row 1: Header (Start/Cancel, Options, Settings) ===
        header_layout = QHBoxLayout()
        self.start_cancel_btn = QPushButton("Start Copy")
        header_layout.addWidget(self.start_cancel_btn)

        # Move
        self.move_checkbox = QCheckBox("Move")
        header_layout.addWidget(self.move_checkbox)

        # Invert
        self.invert_checkbox = QCheckBox("Invert")
        header_layout.addWidget(self.invert_checkbox)

        # Ignore Existing
        self.ignore_existing_checkbox = QCheckBox("Ignore Existing")
        header_layout.addWidget(self.ignore_existing_checkbox)

        # Separator 
        header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        # --- Font Size Widget ---
        self.font_size_label = QLabel("Font Size:")
        header_layout.addWidget(self.font_size_label)
        
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 24)
        self.font_size_spinbox.setValue(self.log_font_size)
        header_layout.addWidget(self.font_size_spinbox)
        
        # Dark Theme Toggle
        self.theme_checkbox = QCheckBox("Theme: Light")
        header_layout.addWidget(self.theme_checkbox)
        
        main_layout.addLayout(header_layout)

        # Parent layout for the source row
        src_row_layout = QHBoxLayout()
        src_row_layout.setAlignment(Qt.AlignTop)

        # --- Left side: fixed label + button ---
        left_src_layout = QHBoxLayout()
        left_src_layout.setAlignment(Qt.AlignTop)
        self.src_text_label = QLabel("Source")
        self.src_text_label.setFixedWidth(75)
        self.src_text_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Source btn
        self.src_btn = QPushButton("")
        self.src_btn.setIconSize(QSize(30, 30))
        self.src_btn.setFixedSize(QSize(30, 30))

        # Source text label
        left_src_layout.addWidget(self.src_text_label)
        left_src_layout.addWidget(self.src_btn)
        src_row_layout.addLayout(left_src_layout)

        # --- Right side: only the source path label scrolls ---
        self.src_label = QLabel("None")
        self.src_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.src_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        src_scroll_area = QScrollArea()
        src_scroll_area.setWidgetResizable(True)
        src_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        src_scroll_area.setFixedHeight(self.src_label.sizeHint().height()+16)
        src_scroll_area.setWidget(self.src_label)
        src_row_layout.addWidget(src_scroll_area)

        main_layout.addLayout(src_row_layout)


        # --- Destination row ---
        dst_row_layout = QHBoxLayout()
        dst_row_layout.setAlignment(Qt.AlignTop)

        left_dst_layout = QHBoxLayout()
        left_dst_layout.setAlignment(Qt.AlignTop)
        self.dst_text_label = QLabel("Destination")
        self.dst_text_label.setFixedWidth(75)
        
        self.dst_btn = QPushButton("")

        self.dst_btn.setIconSize(QSize(30, 30))
        self.dst_btn.setFixedSize(QSize(30, 30))

        left_dst_layout.addWidget(self.dst_text_label)
        left_dst_layout.addWidget(self.dst_btn)
        dst_row_layout.addLayout(left_dst_layout)

        self.dst_label = QLabel("None")
        self.dst_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dst_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        dst_scroll_area = QScrollArea()
        dst_scroll_area.setWidgetResizable(True)
        dst_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        dst_scroll_area.setFixedHeight(self.dst_label.sizeHint().height()+16)
        dst_scroll_area.setWidget(self.dst_label)

        dst_row_layout.addWidget(dst_scroll_area)
        main_layout.addLayout(dst_row_layout)

        # === Log ===
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.log, 1)  # stretch factor = 1

        # === Progress bar ===
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.hide()
        main_layout.addWidget(self.progress)

        # Signals
        self.src_btn.clicked.connect(self.select_src)
        self.dst_btn.clicked.connect(self.select_dst)
        self.start_cancel_btn.clicked.connect(self.toggle_copy)
        self.theme_checkbox.clicked.connect(self.toggle_theme)
        self.move_checkbox.clicked.connect(self.toggle_move)
        self.invert_checkbox.clicked.connect(self.toggle_invert)
        self.ignore_existing_checkbox.clicked.connect(self.toggle_ignore_existing)
        self.font_size_spinbox.valueChanged.connect(self.set_log_font_size) # New connection

        # Config
        self.src_dir = ""
        self.dst_dir = ""
        self.load_config()
        self.update_labels()
        self.apply_theme()
        # Initial application of loaded font size to all elements
        self.set_log_font_size(self.log_font_size) 

    # Method to set font size globally
    def set_log_font_size(self, size):
        self.log_font_size = size
        
        # 1. Create a new font based on the current system font, but with the new size
        new_font = self.font()
        new_font.setPointSize(size)
        
        # 2. Apply the new font to the main widget, which propagates to most child widgets 
        # (Labels, Buttons, Checkboxes, Spinbox)
        self.setFont(new_font)
        
        # 3. Explicitly handle the QTextEdit (log) as it often needs direct font point size setting
        self.log.setFontPointSize(size)

        # 4. Ensure the spinbox reflects the set value (for config loading consistency)
        self.font_size_spinbox.setValue(size) 
        
        self.save_config()

    # Handle keyboard shortcuts for zooming
    def keyPressEvent(self, event):
        # Check for Ctrl (Linux/Win) or Command (Mac) modifier
        if event.modifiers() & Qt.ControlModifier:
            current_size = self.log_font_size
            
            # Ctrl/Cmd + Minus (Zoom Out)
            if event.key() == Qt.Key_Minus:
                new_size = max(8, current_size - 1)
                self.set_log_font_size(new_size)
                event.accept()
                return

            # Ctrl/Cmd + Plus or Ctrl/Cmd + Equals (Zoom In)
            # Qt.Key_Equal often handles the '+' key for zoom shortcuts
            elif event.key() == Qt.Key_Equal or event.key() == Qt.Key_Plus:
                new_size = min(24, current_size + 1)
                self.set_log_font_size(new_size)
                event.accept()
                return

        super().keyPressEvent(event)

    # Toggle Move
    def toggle_move(self):
        self.move = self.move_checkbox.isChecked()
        self.save_config()

    # Toggle Invert
    def toggle_invert(self):
        self.invert = self.invert_checkbox.isChecked()
        self.save_config()

    # Toggle Ignore Existing
    def toggle_ignore_existing(self):
        self.ignore_existing = self.ignore_existing_checkbox.isChecked()
        self.save_config()

    # Theme Apply
    def apply_theme(self):
        if self.theme_toggle:
            apply_dark_palette(app)
        else:
            app.setPalette(QPalette())

    # Theme Toggle
    def toggle_theme(self):
        self.theme_toggle = self.theme_checkbox.isChecked()
        self.save_config()
        self.apply_theme()

        if self.theme_toggle:
            self.theme_checkbox.setText("Theme: Dark")
            self.src_btn.setIcon(QIcon(folder_icon_dark))
            self.dst_btn.setIcon(QIcon(folder_icon_dark))
        else:
            self.theme_checkbox.setText("Theme: Light")
            self.src_btn.setIcon(QIcon(folder_icon_light))
            self.dst_btn.setIcon(QIcon(folder_icon_light))

    # Update folder labels
    def update_labels(self):
        self.src_label.setText(self.src_dir or "None")
        self.dst_label.setText(self.dst_dir or "None")

    # Source Selection
    def select_src(self):
        # Start in current source directory if it exists
        start_dir = self.src_dir if os.path.exists(self.src_dir) else str(QDir.homePath())
        dir_ = QFileDialog.getExistingDirectory(self, "Select Source Folder", start_dir)
        if dir_:
            self.src_dir = dir_
            self.save_config()
            self.update_labels()

    # Destination Selection
    def select_dst(self):
        # Start in current destination directory if it exists
        start_dir = self.dst_dir if os.path.exists(self.dst_dir) else str(QDir.homePath())
        dir_ = QFileDialog.getExistingDirectory(self, "Select Destination Folder", start_dir)
        if dir_:
            self.dst_dir = dir_
            self.save_config()
            self.update_labels()

    # Config persistence
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                src, dst, theme_toggle = data.get("src"), data.get("dst"), data.get("theme_toggle")
                
                if src and os.path.exists(src):
                    self.src_dir = src
                if dst and os.path.exists(dst):
                    self.dst_dir = dst
                    
                self.theme_toggle = theme_toggle
                if self.theme_toggle:
                    self.theme_checkbox.setText("Theme: Dark")
                else:
                    self.theme_checkbox.setText("Theme: Light")
                
                theme_toggle = data.get("theme_toggle", True)
                self.theme_checkbox.setChecked(theme_toggle)

                move = data.get("move", False)
                self.move_checkbox.setChecked(move)
                self.move = move

                invert = data.get("invert", False)
                self.invert_checkbox.setChecked(invert)
                self.invert = invert

                ignore_existing = data.get("ignore_existing", True)
                self.ignore_existing_checkbox.setChecked(ignore_existing)
                self.ignore_existing = ignore_existing
                
                # Load font size setting
                self.log_font_size = data.get("log_font_size", 12)
                self.font_size_spinbox.setValue(self.log_font_size)


                if self.theme_toggle:
                    self.src_btn.setIcon(QIcon(folder_icon_dark))
                    self.dst_btn.setIcon(QIcon(folder_icon_dark))
                else:
                    self.src_btn.setIcon(QIcon(folder_icon_light))
                    self.dst_btn.setIcon(QIcon(folder_icon_light))
            except:
                pass

    def save_config(self):
        data = {
            "src": self.src_dir,
            "dst": self.dst_dir,
            "theme_toggle": self.theme_toggle,
            "move": self.move_checkbox.isChecked(),
            "invert": self.invert_checkbox.isChecked(),
            "ignore_existing": self.ignore_existing_checkbox.isChecked(),
            "log_font_size": self.log_font_size  # Save font size
            }
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)

    # Start/Cancel toggle
    def toggle_copy(self):
        if not self.copying:
            self.start_copy()
        else:
            self.cancel_copy()

    def start_copy(self):
        self.log.clear()

        if hasattr(self, "worker") and self.worker.isRunning():
            self.log.append("\nCopy already running.")
            return

        self.copying = True
        self.start_cancel_btn.setText("Cancel Copy")
        self.progress.setValue(0)
        self.progress.show()
        
        # Pass current UI settings to the worker (Removed threads argument)
        self.worker = CopyWorker(
            self.src_dir, 
            self.dst_dir, 
            move=self.move_checkbox.isChecked(), 
            invert=self.invert_checkbox.isChecked(),
            ignore_existing=self.ignore_existing_checkbox.isChecked()
        )

        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def cancel_copy(self):
        self.log.append("\nCancelling Copy...\nTerminating rsync process now.\n")
        if hasattr(self, "worker"):
            self.worker.cancel()
            self.copying = False
            self.start_cancel_btn.setText("Start Copy")
            self.progress.hide()
    
    def on_finished(self):
        self.copying = False
        self.start_cancel_btn.setText("Start Copy")
        self.progress.setValue(0)
        self.progress.hide()

    def closeEvent(self, event):
        if hasattr(self, "worker") and self.worker.isRunning():
            # Warn the user and ignore the close
            self.log.append("\nCannot close the app while a copy is running.\nPlease cancel the copy first.\n")
            event.ignore()  # Prevent the window from closing
        else:
            event.accept()  # Allow closing

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Ensure folder assets exist for folder icons, or remove if you use built-in icons
    gui = CopyGUI()
    gui.show()
    sys.exit(app.exec())