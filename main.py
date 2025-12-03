import sys
import os
import signal
import subprocess
import json
import multiprocessing
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QProgressBar, QTextEdit,
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QSpinBox, QSpacerItem, QSizePolicy,
    QScrollArea, QCheckBox
)

from PySide6.QtGui import (
    QPalette, QColor, QIcon
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

CONFIG_FILE = os.path.expanduser("~/.fast_copy_gui_config.json")

class CopyWorker(QThread):
    progress_signal = Signal(int)
    log_signal = Signal(str)
    
    def __init__(self, src, dst, threads=1, move=False, invert=False):
        super().__init__()
        self.src = src
        self.dst = dst
        self.threads = threads
        self.move = move
        self.invert = invert
        self._process = None
        self._cancel_requested = False
    
    def run(self):
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(__file__)

        script_path = os.path.join(base_dir, "fast_copy.sh")
        cmd = [script_path, self.src, self.dst, "--thread", str(self.threads)]

        if self.move:
            cmd.append("--move")
            
        if self.invert:
            cmd.append("--invert")


        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            preexec_fn=os.setsid
        )

        for raw_line in self._process.stdout:
            if self._cancel_requested:
                self._process.terminate()
                try:
                    self.log_signal.emit("Copy canceled by user.")
                except RuntimeError:
                    pass
                return

            line = raw_line.strip()

            # --- PROGRESS LINES ---
            if line.startswith("PROGRESS"):
                try:
                    _, cur, tot = line.split()
                    current = int(cur)
                    total = int(tot)

                    if total > 0:
                        percent = int((current / total) * 100)
                        self.progress_signal.emit(percent)
                except:
                    pass
                continue  # DO NOT LOG IT

            # --- EVERYTHING ELSE ---
            try:
                self.log_signal.emit(line)
            except RuntimeError:
                pass

        self._process.wait()
        try:
            self.log_signal.emit("\nCopy complete!" if not self._cancel_requested else "Canceled.")
        except RuntimeError:
            pass
    
    def cancel(self):
        self._cancel_requested = True
        if self._process:
            self._process.terminate()
            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)  # kills parent + children

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

class NoSelectSpinBox(QSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        # Clear selection immediately when focused
        self.lineEdit().deselect()

class CopyGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fast Copy GUI")
        self.resize(700, 500)
        self.dark_mode = False
        self.copying = False
        self.move = False
        self.invert = False
        self.setFocus(Qt.OtherFocusReason)

        # Folder Icon Image
        folder_icon = get_asset_path("icons/folder.svg")

        main_layout = QVBoxLayout(self)

        # === Row 1: Header (Start/Cancel, Theme Toggle, Thread Count) ===
        header_layout = QHBoxLayout()
        self.start_cancel_btn = QPushButton("Start Copy")
        header_layout.addWidget(self.start_cancel_btn)

        # Move
        self.move_checkbox = QCheckBox("Move")
        header_layout.addWidget(self.move_checkbox)

        # Invert
        self.invert_checkbox = QCheckBox("Invert")
        header_layout.addWidget(self.invert_checkbox)

        # Dark Theme Toggle
        self.theme_btn = QCheckBox("Light")
        header_layout.addWidget(self.theme_btn)

        # Separator
        header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        threads_layout = QHBoxLayout()
        
        # Threads
        self.thread_label = QLabel("Threads:")
        self.thread_spin = NoSelectSpinBox()
        self.thread_spin.setMinimum(1)
        self.thread_spin.setMaximum(multiprocessing.cpu_count())
        self.thread_spin.setValue(2)
        self.thread_spin.lineEdit().setReadOnly(True)
        self.thread_spin.setFocusPolicy(Qt.NoFocus)
        threads_layout.addWidget(self.thread_label)
        threads_layout.addWidget(self.thread_spin)
        header_layout.addLayout(threads_layout)
        main_layout.addLayout(header_layout)

        # Parent layout for the source row
        src_row_layout = QHBoxLayout()
        src_row_layout.setAlignment(Qt.AlignTop)  # Align all children to top

        # --- Left side: fixed label + button ---
        left_src_layout = QHBoxLayout()
        left_src_layout.setAlignment(Qt.AlignTop)
        self.src_text_label = QLabel("Source")
        self.src_text_label.setFixedWidth(75)
        self.src_text_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # Fix vertical

        # Source btn
        self.src_btn = QPushButton("")
        self.src_btn.setIcon(QIcon(folder_icon))
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
        # src_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        src_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        src_scroll_area.setFixedHeight(self.src_label.sizeHint().height()+16)  # fix vertical height
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
        # self.dst_text_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        self.dst_btn = QPushButton("")
        self.dst_btn.setIcon(QIcon(folder_icon))
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
        # dst_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
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
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.move_checkbox.clicked.connect(self.toggle_move)
        self.invert_checkbox.clicked.connect(self.toggle_invert)
        self.thread_spin.valueChanged.connect(self.thread_changed)

        # Config
        self.src_dir = ""
        self.dst_dir = ""
        self.load_config()
        self.update_labels()
        self.apply_theme()

    # Toggle Move
    def toggle_move(self):
        self.move = self.move_checkbox.isChecked()

        self.save_config()

    # Toggle Invert
    def toggle_invert(self):
        self.invert = self.invert_checkbox.isChecked()

        self.save_config()

    # Theme Apply
    def apply_theme(self):
        if self.dark_mode:
            apply_dark_palette(app)
        else:
            app.setPalette(QPalette())


    # Thread Changed
    def thread_changed(self):
        self.save_config()
        self.setFocus(Qt.OtherFocusReason)

    # Theme Toggle
    def toggle_theme(self):
        self.dark_mode = self.theme_btn.isChecked()

        self.save_config()
        self.apply_theme()

        if self.dark_mode:
            self.theme_btn.setText("Dark")
        else:
            self.theme_btn.setText("Light")

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
                src, dst, theme_toggle, threads, move, invert = data.get("src"), data.get("dst"), data.get("theme_toggle"), data.get("threads"), data.get("move"), data.get("invert")
                if src and os.path.exists(src):
                    self.src_dir = src
                if dst and os.path.exists(dst):
                    self.dst_dir = dst
                # if theme_toggle:
                self.dark_mode = theme_toggle
                if self.dark_mode:
                    self.theme_btn.setText("Dark")
                else:
                    self.theme_btn.setText("Light")
                
                move = data.get("move", False)
                self.move_checkbox.setChecked(move)

                invert = data.get("invert", False)
                self.invert_checkbox.setChecked(invert)

                # if threads and os.path.exists(threads):
                threads = data.get("threads")
                if isinstance(threads, int) and 1 <= threads <= multiprocessing.cpu_count():
                    self.thread_spin.setValue(threads)
            except:
                pass

    def save_config(self):
        data = {
            "src": self.src_dir,
            "dst": self.dst_dir,
            "theme_toggle": self.dark_mode,
            "threads": self.thread_spin.value(),
            "move": self.move_checkbox.isChecked(),
            "invert": self.invert_checkbox.isChecked()
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

        threads = self.thread_spin.value()
        self.copying = True
        self.start_cancel_btn.setText("Cancel Copy")
        self.progress.setValue(0)
        self.progress.show()
        self.worker = CopyWorker(self.src_dir, self.dst_dir, threads=threads, move=self.move_checkbox.isChecked(), invert=self.invert_checkbox.isChecked())
        move=self.move_checkbox.isChecked()
        self.worker.progress_signal.connect(self.progress.setValue)

        # if line.startswith("PROGRESS"):
        self.worker.log_signal.connect(lambda text: self.log.append('%s' % text))
        # self.worker.log_signal.connect(lambda text: self.log.append('%s\n' % text))
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def cancel_copy(self):
        self.log.append("\nCancelling Copy...\nClosing active threads now\nDon't close the app until finished\n")
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
    gui = CopyGUI()
    gui.show()
    sys.exit(app.exec())
