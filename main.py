import sys
import os
import subprocess
import json
import re 
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QProgressBar, QTextEdit,
    QVBoxLayout, QHBoxLayout, QLabel, QFileDialog, QSpinBox, 
    QSpacerItem, QSizePolicy, QScrollArea, QCheckBox, QStackedWidget,
    QStyleFactory, QGridLayout, QGroupBox, QMessageBox
)

from PySide6.QtGui import (
    QPalette, QColor, QIcon
)

from PySide6.QtCore import (
    QThread, Signal, QSize, Qt, QDir, QCoreApplication,
    QSignalBlocker
    )

default_config={
    "src":"",
    "dst":"",
    "theme_toggle":True,
    "log_font_size":13,
    "dpi_font_size":78,
    "move":False,
    "invert":False,
    "ignore_existing":True,
    "compress":False,
    "delete":False,
    }

def get_asset_path(filename):
    # Determine the correct path for assets, supporting both bundled (PyInstaller) and non-bundled execution.
    if getattr(sys, 'frozen', False):
        base_dir = os.path.join(sys._MEIPASS, "assets")
    else:
        base_dir = os.path.join(os.path.dirname(__file__), "assets")
    return os.path.join(base_dir, filename)

# Placeholder assets, assuming they exist or using system defaults if they don't
# NOTE: The file paths below rely on the assets folder being structured:
# assets/icons/dark_folder.png, etc.
try:
    # Folder Icon
    folder_icon_light = get_asset_path("icons/dark_folder.png")
    folder_icon_dark = get_asset_path("icons/light_folder.png")

    # Arrow Up (Inverted State: DST -> SRC)
    arrow_up_icon_light = get_asset_path("icons/arrow_up_dark.png")
    arrow_up_icon_dark = get_asset_path("icons/arrow_up_light.png")

    # Arrow Down (Normal State: SRC -> DST)
    arrow_down_icon_light = get_asset_path("icons/arrow_down_dark.png")
    arrow_down_icon_dark = get_asset_path("icons/arrow_down_light.png")

    # Settings Gear)
    settings_icon_light = get_asset_path("icons/settings_dark.png")
    settings_icon_dark = get_asset_path("icons/settings_light.png")
except:
    # Fallback paths if get_asset_path fails in a non-bundled environment
    
    # Folder Icon (Using system-like icons as fallback if custom assets fail)
    folder_icon_light = "" 
    folder_icon_dark = ""

    # Arrow Up
    arrow_up_icon_light = ""
    arrow_up_icon_dark = ""

    # Arrow Down
    arrow_down_icon_light = ""
    arrow_down_icon_dark = ""

    # Settings Gear)
    settings_icon_light = ""
    settings_icon_dark = ""


CONFIG_FILE = os.path.expanduser("~/.fast_copy_gui_config.json")

# --- UTILITY FUNCTION: CHECK FOR RECURSIVE COPY DANGER ---
def is_recursive_copy(src, dst):
    """
    Checks if one path is a subdirectory of the other, which would lead to
    an infinite recursive copy operation.
    """
    try:
        # Resolve paths to handle symlinks and relative notation (like '.' or '..')
        src_path = os.path.realpath(src)
        dst_path = os.path.realpath(dst)
    except Exception:
        # If paths are invalid or inaccessible, return False and let the copy process
        # handle the failure later.
        return False 
    
    # If the paths are identical, it's not a recursive copy but it's pointless.
    if src_path == dst_path:
        return False
        
    # Check if src is inside dst (common path is dst)
    if src_path.startswith(dst_path + os.sep):
        return True
    
    # Check if dst is inside src (common path is src)
    if dst_path.startswith(src_path + os.sep):
        return True

    return False
# --- END UTILITY FUNCTION ---


class CopyWorker(QThread):
    progress_signal = Signal(int)
    log_signal = Signal(str)
    
    def __init__(self, src, dst, move=False, invert=False, ignore_existing=True, compress=False, delete=False):
        super().__init__()
        
        # Determine effective source and destination after checking for invert flag
        if invert:
            self.src = dst
            self.dst = src
        else:
            self.src = src
            self.dst = dst

        self.move = move
        self.invert = invert
        self.ignore_existing = ignore_existing
        self.compress = compress
        self.delete = delete
        self._process = None
        self._cancel_requested = False
        
    # --- Recursive Empty Folder Deletion ---
    def delete_empty_folders_recursive(self, path):
        """Recursively removes empty directories within the given path."""
        if not os.path.isdir(path):
            return

        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                self.delete_empty_folders_recursive(full_path)

        # After recursively checking children, check if this directory is empty.
        try:
            if not os.listdir(path):
                os.rmdir(path)
                self.log_signal.emit(f"[Cleanup] Removed empty directory: {path}")
        except OSError as e:
            # Handle permission denied or other OS errors
            self.log_signal.emit(f"[Cleanup Error] Failed to remove {path}: {e}")
    # --- END CLEANUP ---

    def run(self):
        # --- 1. COMMAND CONSTRUCTION (Cross-Platform) ---
        
        # Windows: Use Robocopy
        if sys.platform.startswith('win'):
            # robocopy source destination [file [file]...] [options]
            cmd_base = ["robocopy", self.src, self.dst]
            
            # /E: Copy subdirectories, including empty ones (similar to rsync's archive mode)
            cmd_base.append("/E") 
            
            # /NFL /NDL /NJH /NJS: Suppress logging of file lists and job headers for cleaner output
            cmd_base.extend(["/NFL", "/NDL", "/NJH", "/NJS"])
            
            # /XJ: Exclude Junction points (important for system stability)
            cmd_base.append("/XJ")
            
            # Move flag: /MOV (moves files and deletes from source after copy)
            if self.move:
                cmd_base.append("/MOV") 
            
            # Ignore Existing: /XO (Excludes Older files - similar to ignoring existing)
            if self.ignore_existing:
                cmd_base.append("/XO") 
            
            # Compression (-z) is not directly supported by robocopy
            if self.compress:
                 self.log_signal.emit("Warning: Compression (-z) is not available with robocopy on Windows.")
            
            # Delete/Mirror: /MIR (Mirrors a directory tree - deletes extraneous files from destination)
            if self.delete:
                cmd_base.append("/MIR")
                self.log_signal.emit("Warning: Using /MIR flag will delete files in the destination that do not exist in the source.")
            # elif not self.delete:
                # If not mirroring, use /S to copy subdirectories but not empty ones, to avoid purging.
                # cmd_base.append("/S")
            
            cmd = cmd_base
            copy_tool = "robocopy"

        # Unix-like (macOS/Linux): Use Rsync
        else:
            rsync_path = "rsync"
            
            # macOS specific path checks (keep this for macOS environment stability)
            if sys.platform == 'darwin':
                homebrew_paths = [
                    "/opt/homebrew/bin/rsync",
                    "/usr/local/bin/rsync"
                ]
                for path in homebrew_paths:
                    if os.path.exists(path):
                        rsync_path = path
                        break

            # Base command with archive, human-readable, verbose, progress reporting, and exclusion
            rsync_cmd_base = [rsync_path, "-ahv", "--info=progress2", "--exclude=.DS_Store"]

            if self.move:
                # This flag removes source files that were successfully transferred.
                rsync_cmd_base.append("--remove-source-files")
            
            if self.ignore_existing:
                # This flag skips files that exist on the receiver, preventing --remove-source-files from deleting them.
                rsync_cmd_base.append("--ignore-existing")
                
            if self.compress: 
                rsync_cmd_base.append("-z")

            if self.delete:
                rsync_cmd_base.append("--delete") 

            # The trailing slash on self.src tells rsync to copy the *contents* of the source folder.
            cmd = rsync_cmd_base + [
                os.path.join(self.src, ""), 
                self.dst
            ]
            copy_tool = "rsync"
            if rsync_path != "rsync":
                self.log_signal.emit(f"Using rsync path: {rsync_path}")
                
        # --- 2. EXECUTION ---
        try:
            self.log_signal.emit(f"Starting copy from '{self.src}' → '{self.dst}' using {copy_tool}")
            self.log_signal.emit(f"Command: {' '.join(cmd)}\n")
        except RuntimeError:
            pass # Ignore if signal fails during cleanup

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=False 
            )
        except FileNotFoundError:
            if sys.platform.startswith('win'):
                error_msg = "Error: robocopy command not found. This should be available on Windows 10/11."
            else:
                error_msg = f"Error: rsync command not found. Ensure rsync is installed and accessible."
            self.log_signal.emit(error_msg)
            return

        # --- 3. PROGRESS PARSING ---
        
        for raw_line in self._process.stdout:
            if self._cancel_requested:
                self._process.terminate() 
                try:
                    self.log_signal.emit("Copy canceled by user.")
                except RuntimeError:
                    pass
                return

            line = raw_line.strip()
            
            if sys.platform.startswith('win'):
                # Robocopy progress is file-by-file and hard to parse for overall % completion.
                # We will only log the output line by line.
                if line and not line.startswith("----------") and not line.startswith("Total"):
                    try:
                        self.log_signal.emit(line)
                    except RuntimeError:
                        pass
                continue

            # Rsync progress parsing (macOS/Linux)
            if 'B/s' in line and '%' in line and ':' in line:
                try:
                    match = re.search(r'\s(\d+)%', line)
                    
                    if match:
                        percent = int(match.group(1))
                        self.progress_signal.emit(percent)
                except:
                    pass
                continue 

            if line:
                try:
                    self.log_signal.emit(line)
                except RuntimeError:
                    pass

        self._process.wait()
        
        # --- 4. COMPLETION / ERROR CHECK ---
        return_code = self._process.returncode
        
        is_success = False
        if sys.platform.startswith('win'):
             # Robocopy returns 0-7 for success (0=no changes, 1=copied, 2=extra files, etc.)
             if 0 <= return_code <= 7:
                 is_success = True
        else:
            # Rsync only returns 0 for success
            if return_code == 0:
                is_success = True
                
        if is_success:
            message = "\nCopy complete!"
            
            # --- Empty Folder Cleanup (Windows + Move only) ---
            if self.move and sys.platform.startswith('win'):
                self.log_signal.emit("\nStarting post-copy empty directory cleanup (Robocopy fix)...")
                # Clean up empty folders left behind by Robocopy /MOV
                self.delete_empty_folders_recursive(self.src)

                # Re-Add deleted folder
                try:
                    os.makedirs(self.src, exist_ok=True)
                    self.log_signal.emit(f"Source folder '{self.src}' guaranteed to exist.")
                except Exception as e:
                    self.log_signal.emit(f"Warning: Could not guarantee source folder exists: {e}")
                    
                self.log_signal.emit("Empty directory cleanup finished.")
            # --- END CLEANUP ---

        elif self._cancel_requested:
            message = "\nCanceled."
        else:
            message = f"\nCopy failed with exit code {return_code}. Check log for details."
            if sys.platform.startswith('win'):
                message += " (Robocopy error codes 8+ indicate failure)."


        try:
            self.log_signal.emit(message)
        except RuntimeError:
            pass
    
    def cancel(self):
        self._cancel_requested = True
        if self._process:
            self._process.terminate()

def apply_dark_palette(app):
    palette = QPalette()
    # Setting up the standard Dark Theme colors
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
    
    # Custom color for the settings sidebar background
    palette.setColor(QPalette.Dark, QColor(25, 25, 25))
    
    app.setPalette(palette)

class CopyGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fast Copy GUI")
        self.resize(700, 500)
        self.theme_toggle = True
        self.copying = False
        # Initialize new rsync flag properties
        self.move = False
        self.invert = False
        self.ignore_existing = True
        self.compress = False
        self.delete = False
        self.dpi_did_change = False

        self.log_font_size = 13
        self.dpi_font_size = 78

        self.setFocus(Qt.OtherFocusReason)

        main_layout = QVBoxLayout(self)
        
        # --- Main Stacked Widget: Switches between Copy View and Settings View ---
        self.main_stack = QStackedWidget()
        main_layout.addWidget(self.main_stack)
        
        # --- Initialize Settings Widgets (must be done early for config loading) ---
        self.init_setting_widgets()
        
        # --- Build Views ---
        self.main_copy_widget = self.create_main_copy_view()
        self.settings_widget = self.create_settings_view()
        
        self.main_stack.addWidget(self.main_copy_widget)
        self.main_stack.addWidget(self.settings_widget)
        
        # --- Signals and Config ---
        self.connect_signals()
        self.src_dir = ""
        self.dst_dir = ""
        self.load_config()
        self.update_labels()
        self.apply_theme()
        # Initial application of loaded font size to all elements
        self.set_log_font_size(self.log_font_size) 
        self.set_dpi_font_size(self.dpi_font_size)
        
    def init_setting_widgets(self):
        # Visuals Widgets
        self.theme_checkbox = QCheckBox("Dark Theme")

        self.font_size_label = QLabel("Global Font Size:")
        self.font_size_spinbox = QSpinBox()
        self.font_size_spinbox.setRange(8, 24)
        self.font_size_spinbox.setSuffix(" pt")

        # DPI Font Size
        self.dpi_font_size_label = QLabel("DPI Font Size:")
        self.dpi_font_size_spinbox = QSpinBox()
        self.dpi_font_size_spinbox.setRange(24, 96)
        self.dpi_font_size_spinbox.setSuffix("")

        # Copy Options Widgets
        self.move_checkbox = QCheckBox("Move (Remove source files)")
        self.invert_checkbox = QCheckBox("Invert (Swap src/dst)")
        self.ignore_existing_checkbox = QCheckBox("Ignore Existing Files (faster)")
        
        # RSYNC OPTIONS
        self.compress_checkbox = QCheckBox("Compress data during transfer (-z, Rsync only)")
        self.delete_checkbox = QCheckBox("Delete extraneous files from destination (--delete / Robocopy /MIR)")

    def create_main_copy_view(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # === Row 1: Header (Start/Cancel, Settings) ===
        header_layout = QHBoxLayout()
        self.start_cancel_btn = QPushButton("Start Copy")
        header_layout.addWidget(self.start_cancel_btn)

        # Move
        self.move_checkbox_main = QCheckBox("Move")
        header_layout.addWidget(self.move_checkbox_main)
        # We need to mirror the state between the main view and the settings view checkbox
        self.move_checkbox_main.stateChanged.connect(self.move_checkbox.setChecked)
        self.move_checkbox.stateChanged.connect(self.move_checkbox_main.setChecked)

        # Separator 
        header_layout.addSpacerItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        # Settings Button
        self.show_settings_btn = QPushButton("")
        self.show_settings_btn.setIconSize(QSize(30, 30))
        self.show_settings_btn.setFixedSize(QSize(30, 30))
        header_layout.addWidget(self.show_settings_btn)
        
        layout.addLayout(header_layout)

        # === Source Row ===
        src_row_layout = QHBoxLayout()
        src_row_layout.setAlignment(Qt.AlignTop)

        left_src_layout = QHBoxLayout()
        left_src_layout.setAlignment(Qt.AlignTop)

        # Source Folder Button
        self.src_btn = QPushButton("")
        self.src_btn.setIconSize(QSize(30, 30))
        self.src_btn.setFixedSize(QSize(30, 30))

        left_src_layout.addWidget(self.src_btn)
        src_row_layout.addLayout(left_src_layout)

        # Source Path Label
        self.src_label = QLabel("None")
        self.src_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.src_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        src_scroll_area = QScrollArea()
        src_scroll_area.setWidgetResizable(True)
        src_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff) # Use Off for this small label
        src_scroll_area.setFixedHeight(self.src_label.sizeHint().height()+16)
        src_scroll_area.setWidget(self.src_label)
        src_row_layout.addWidget(src_scroll_area)
        layout.addLayout(src_row_layout)

        # === Invert Arrow Button (New Position) ===
        invert_arrow_layout = QHBoxLayout()
        # The QCheckBox will now act as a centered icon
        self.invert_checkbox_icon = QPushButton("")
        self.invert_checkbox_icon.setIconSize(QSize(30, 30))
        self.invert_checkbox_icon.setFixedSize(QSize(30, 30))

        invert_arrow_layout.addWidget(self.invert_checkbox_icon)
        invert_arrow_layout.addStretch(1)
        
        layout.addLayout(invert_arrow_layout)

        # === Destination row ===
        dst_row_layout = QHBoxLayout()
        dst_row_layout.setAlignment(Qt.AlignTop)

        left_dst_layout = QHBoxLayout()
        left_dst_layout.setAlignment(Qt.AlignTop)

        # Destination Folder Button
        self.dst_btn = QPushButton("")
        self.dst_btn.setIconSize(QSize(30, 30))
        self.dst_btn.setFixedSize(QSize(30, 30))

        left_dst_layout.addWidget(self.dst_btn)
        dst_row_layout.addLayout(left_dst_layout)

        # Destination Path Label
        self.dst_label = QLabel("None")
        self.dst_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dst_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        dst_scroll_area = QScrollArea()
        dst_scroll_area.setWidgetResizable(True)
        dst_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dst_scroll_area.setFixedHeight(self.dst_label.sizeHint().height()+16)
        dst_scroll_area.setWidget(self.dst_label)

        dst_row_layout.addWidget(dst_scroll_area)
        layout.addLayout(dst_row_layout)

        # === Log ===
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.log, 1)

        # === Progress bar ===
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.hide()
        layout.addWidget(self.progress)
        
        return widget

    def create_settings_view(self):
        widget = QWidget()
        main_h_layout = QHBoxLayout(widget)
        
        # --- 1. Left Sidebar (Category Navigation) ---
        sidebar_layout = QVBoxLayout()
        sidebar_layout.setContentsMargins(0, 0, 10, 0)
        
        # Back Button
        self.back_to_main_btn = QPushButton("← Back to Copy")
        sidebar_layout.addWidget(self.back_to_main_btn)
        sidebar_layout.addSpacing(10)
        
        # Category Buttons
        self.category_stack = QStackedWidget()
        
        self.visuals_btn = QPushButton("Visuals")
        self.copy_options_btn = QPushButton("Copy Options")
        
        sidebar_layout.addWidget(self.visuals_btn)
        sidebar_layout.addWidget(self.copy_options_btn)
        sidebar_layout.addStretch(1) # Push buttons to the top
        
        main_h_layout.addLayout(sidebar_layout)
        
        # --- 2. Right Content Area (Stacked Widget for Categories) ---
        
        # Visuals Category (Index 0)
        visuals_page = self.create_visuals_category()
        self.category_stack.addWidget(visuals_page)
        
        # Copy Options Category (Index 1)
        copy_options_page = self.create_copy_options_category()
        self.category_stack.addWidget(copy_options_page)

        main_h_layout.addWidget(self.category_stack, 1) # Give the content area the stretch factor
        
        # Initial state: select the first category
        self.category_stack.setCurrentIndex(0)
        self.visuals_btn.setDisabled(True) # Visually indicate selection

        # Sidebar button logic
        self.visuals_btn.clicked.connect(lambda: self.switch_settings_category(0, self.visuals_btn))
        self.copy_options_btn.clicked.connect(lambda: self.switch_settings_category(1, self.copy_options_btn))
        
        return widget

    def create_visuals_category(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        
        grid_layout = QGridLayout(content_widget)
        grid_layout.setContentsMargins(10, 10, 10, 10)
        
        # Group Box for Aesthetics
        group_aesthetics = QGroupBox("Aesthetics")
        aesthetics_layout = QVBoxLayout(group_aesthetics)
        aesthetics_layout.addWidget(self.theme_checkbox)
        grid_layout.addWidget(group_aesthetics, 0, 0, 1, 2) # Row 0, Col 0, span 1 row, span 2 columns
        
        # 3. Group Box for HDPI (Row 2) - NEW GROUP BOX
        group_hdpi = QGroupBox("HDPI Scaling")
        
        # *** FIX: Use QGridLayout here for two columns (Label + Spinbox) ***
        hdpi_layout = QGridLayout(group_hdpi)
        
        # DPI Font Size (Row 0 of hdpi_layout)
        # *** FIX: Use QGridLayout's correct row/column indices ***
        hdpi_layout.addWidget(self.dpi_font_size_label, 0, 0) 
        hdpi_layout.addWidget(self.dpi_font_size_spinbox, 0, 1)
        
        # Add the HDPI group to the main grid_layout
        grid_layout.addWidget(group_hdpi, 1, 0, 1, 2) # Row 2, Col 0, span 1 row, span 2 columns

        # Group Box for Typography (Row 1)
        group_typography = QGroupBox("Typography")
        typography_layout = QGridLayout(group_typography)
        
        # 1. Standard Font Size (Row 0)
        typography_layout.addWidget(self.font_size_label, 0, 0)
        typography_layout.addWidget(self.font_size_spinbox, 0, 1)
        
        # 2. Shortcut Label (Row 1)
        typography_layout.addWidget(QLabel("Shortcut: Ctrl/Cmd + / -"), 1, 0, 1, 2)
        
        # Add the typography group to the main grid_layout
        grid_layout.addWidget(group_typography, 2, 0, 1, 2)
        
        # 4. Spacer to push content to the top (Row 3)
        # Use the next available row (Row 3) for the spacer
        grid_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 3, 0)
        
        return scroll_area

    def create_copy_options_category(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        content_widget = QWidget()
        scroll_area.setWidget(content_widget)
        
        grid_layout = QGridLayout(content_widget)
        grid_layout.setContentsMargins(10, 10, 10, 10)
        
        # Group Box for Core Operations
        group_operations = QGroupBox("Core Operation Flags")
        operations_layout = QVBoxLayout(group_operations)
        operations_layout.addWidget(self.move_checkbox)
        operations_layout.addWidget(self.invert_checkbox)
        grid_layout.addWidget(group_operations, 0, 0, 1, 2)
        
        # Group Box for Rsync Optimization & Network
        group_flags = QGroupBox("Optimization & Network Flags")
        flags_layout = QVBoxLayout(group_flags)
        
        flags_layout.addWidget(self.ignore_existing_checkbox)
        flags_layout.addWidget(self.compress_checkbox) 
        
        grid_layout.addWidget(group_flags, 1, 0, 1, 2)
        
        # Group Box for Sync/Mirroring (DANGER)
        group_sync = QGroupBox("Mirroring/Deletion (USE WITH CAUTION)")
        sync_layout = QVBoxLayout(group_sync)
        sync_layout.addWidget(self.delete_checkbox) 
        
        grid_layout.addWidget(group_sync, 2, 0, 1, 2)
        
        # Spacer to push content to the top
        grid_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 3, 0)
        
        return scroll_area

    def switch_settings_category(self, index, clicked_btn):
        # Disable the clicked button and enable the others
        for btn in [self.visuals_btn, self.copy_options_btn]:
            btn.setDisabled(btn == clicked_btn)
            
        self.category_stack.setCurrentIndex(index)

    def connect_signals(self):
        # Main View Signals
        self.src_btn.clicked.connect(self.select_src)
        self.dst_btn.clicked.connect(self.select_dst)
        self.start_cancel_btn.clicked.connect(self.toggle_copy)
        self.show_settings_btn.clicked.connect(lambda: self.main_stack.setCurrentIndex(1))
        
        # Settings View Signals
        self.back_to_main_btn.clicked.connect(lambda: self.main_stack.setCurrentIndex(0))
        
        # Setting Widgets Signals
        self.theme_checkbox.clicked.connect(self.toggle_theme)
        
        # Link main view checkboxes to state and save
        self.move_checkbox_main.stateChanged.connect(self.toggle_move)
        
        # Link settings view checkboxes to state and save
        self.move_checkbox.stateChanged.connect(self.toggle_move)
        self.invert_checkbox.stateChanged.connect(self.checkbox_invert_changed)
        self.invert_checkbox_icon.clicked.connect(self.icon_invert_clicked)
        
        self.ignore_existing_checkbox.stateChanged.connect(self.toggle_ignore_existing)
        self.compress_checkbox.stateChanged.connect(self.toggle_compress)
        self.delete_checkbox.stateChanged.connect(self.toggle_delete)     
        
        self.font_size_spinbox.valueChanged.connect(self.set_log_font_size)
        self.dpi_font_size_spinbox.valueChanged.connect(self.set_dpi_font_size)

    # --- Font and Theme Management ---

    def set_log_font_size(self, size):
        self.log_font_size = size
        
        # Apply font to the entire application widget hierarchy
        new_font = self.font()
        new_font.setPointSize(size)
        self.setFont(new_font)
        
        # Explicitly handle the QTextEdit (log) font
        self.log.setFontPointSize(size)

        # Update spinbox value (for consistency)
        self.font_size_spinbox.blockSignals(True)
        self.font_size_spinbox.setValue(size)
        self.font_size_spinbox.blockSignals(False)
        
        self.save_config()
    
    def set_dpi_font_size(self, size):
        if not size == int(os.environ["QT_FONT_DPI"]):
            self.dpi_did_change = True
            self.log.clear()
            self.log.append(
                f"Warning: DPI Font Size changed from {os.environ['QT_FONT_DPI']} to {size}\n"
                "Restart the application for this change to take effect."
            )
            # self.prompt_restart()
        else:
            if bool(self.dpi_did_change):
                self.log.clear()

        self.dpi_font_size = size
        self.save_config()

    def prompt_restart(self):
        """Displays a message box and offers to restart the application."""
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText("DPI change requires an application restart to take effect.")
        msg.setWindowTitle("Restart Required")
        
        # Add buttons for the user's choices
        restart_button = msg.addButton("Restart Now", QMessageBox.AcceptRole)
        cancel_button = msg.addButton("Restart Later", QMessageBox.RejectRole)
        
        msg.exec()
        
        if msg.clickedButton() == restart_button:
            self.restart_application()
        
    def restart_application(self):
        """Quits the current instance and launches a new one."""
        
        # Get the current executable path
        python = sys.executable
        # Get the path of the main script (if running as script) or the executable (if frozen)
        script = os.path.abspath(sys.argv[0]) 
        
        # Start a new process with the same arguments
        os.execl(python, python, script, *sys.argv[1:])
        
        # If execl fails (or as a fallback), exit the application gracefully
        QCoreApplication.quit()

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
            elif event.key() in (Qt.Key_Equal, Qt.Key_Plus):
                new_size = min(24, current_size + 1)
                self.set_log_font_size(new_size)
                event.accept()
                return

        super().keyPressEvent(event)

    def update_invert_icon(self):
        """
        Updates the icon on the main view's invert checkbox based on state and theme.
        This is the requested button system functionality.
        """
        
        # Determine icon based on theme
        if self.theme_toggle: # Dark Theme
            icon_up = arrow_up_icon_dark
            icon_down = arrow_down_icon_dark
        else: # Light Theme
            icon_up = arrow_up_icon_light
            icon_down = arrow_down_icon_light
            
        # Determine which direction arrow to show
        # True = Inverted (Destination -> Source, visually 'Up')
        if self.invert_checkbox.isChecked(): 
            icon_path = icon_up
            tooltip = "Copy direction is Inverted (Destination folder to Source folder)"
        else:
            # False = Normal (Source -> Destination, visually 'Down')
            icon_path = icon_down 
            tooltip = "Copy direction is Normal (Source folder to Destination folder)"
            
        if icon_path:
            self.invert_checkbox_icon.setIcon(QIcon(icon_path))
            self.invert_checkbox_icon.setToolTip(tooltip)
            
    def apply_theme(self):
        if self.theme_toggle:
            # Use a temporary local app if running outside the main block for testing
            current_app = QCoreApplication.instance() or QApplication.instance()
            if current_app:
                apply_dark_palette(current_app)
        else:
            current_app = QCoreApplication.instance() or QApplication.instance()
            if current_app:
                current_app.setPalette(QPalette())
        
        # Update folder icon colors based on theme
        icon = folder_icon_dark if self.theme_toggle else folder_icon_light
        # Check if icon path is valid before setting
        if icon:
            self.src_btn.setIcon(QIcon(icon))
            self.dst_btn.setIcon(QIcon(icon))

        # Update settings icon colors based on theme
        icon = settings_icon_dark if self.theme_toggle else settings_icon_light
        # Check if icon path is valid before setting
        if icon:
            self.show_settings_btn.setIcon(QIcon(icon))
            
        # Update the invert arrow icon (Essential part of the user request)
        self.update_invert_icon()

    def toggle_theme(self):
        self.theme_toggle = self.theme_checkbox.isChecked()
        self.save_config()
        self.apply_theme()

    # --- Copy Option Toggles (Reverted to full user control) ---
    def toggle_move(self):
        # Read the state from the settings checkbox as the source of truth
        self.move = self.move_checkbox.isChecked() 
        
        # Sync the main view checkbox state
        self.move_checkbox_main.setChecked(self.move)
        
        self.save_config()

    def checkbox_invert_changed(self, state):
        self.set_invert(bool(state))

    def icon_invert_clicked(self):
        self.set_invert(not self.invert)

    def set_invert(self, value):
        if self.invert == value:
            return  # No change → avoid loops

        self.invert = value

        # Update checkbox without causing another signal
        with QSignalBlocker(self.invert_checkbox):
            self.invert_checkbox.setChecked(self.invert)

        # Pick correct icon
        if self.theme_toggle:  # dark mode
            icon_path = arrow_up_icon_dark if self.invert else arrow_down_icon_dark
        else:                  # light mode
            icon_path = arrow_up_icon_light if self.invert else arrow_down_icon_light

        self.invert_checkbox_icon.setIcon(QIcon(icon_path))
        self.save_config()

    def toggle_ignore_existing(self):
        # Full user control: just update the internal state and save
        self.ignore_existing = self.ignore_existing_checkbox.isChecked()
        self.save_config()
        
    def toggle_compress(self): 
        self.compress = self.compress_checkbox.isChecked()
        self.save_config()
        
    def toggle_delete(self): 
        self.delete = self.delete_checkbox.isChecked()
        self.save_config()
        
    def toggle_copy(self):
        # Placeholder for starting/cancelling the copy thread
        if self.copying:
            self.worker.cancel()
            self.start_cancel_btn.setText("Start Copy")
            self.progress.hide()
            self.copying = False
            self.log.append("\nOperation halted.")
        else:
            # Basic validation
            if not os.path.isdir(self.src_dir) or not os.path.isdir(self.dst_dir):
                self.log.append("Error: Both Source and Destination directories must be set and valid.")
                return

            # Check for recursive danger before starting
            if is_recursive_copy(self.src_dir, self.dst_dir):
                self.log.append("DANGER: Recursive copy detected! The Source path is inside the Destination path, or vice versa. Aborting.")
                return

            self.copying = True
            self.start_cancel_btn.setText("Cancel Copy")
            self.progress.setValue(0)
            self.progress.show()
            self.log.clear()

            # The worker handles the actual path swapping based on self.invert
            self.worker = CopyWorker(
                src=self.src_dir, 
                dst=self.dst_dir, 
                move=self.move,
                invert=self.invert,
                ignore_existing=self.ignore_existing,
                compress=self.compress,
                delete=self.delete
            )
            self.worker.progress_signal.connect(self.progress.setValue)
            self.worker.log_signal.connect(self.log.append)
            self.worker.finished.connect(self._copy_finished)
            self.worker.start()

    def _copy_finished(self):
        self.copying = False
        self.start_cancel_btn.setText("Start Copy")
        self.progress.setValue(100)
        # Note: Progress bar remains visible until next start/cancel, allowing user to see final state.


    # --- Directory Management ---

    def update_labels(self):
        self.src_label.setText(self.src_dir or "None")
        self.dst_label.setText(self.dst_dir or "None")
        
        # Update main view checkboxes from persistent state on load
        self.move_checkbox_main.setChecked(self.move)
        
        # Also ensure the settings checkboxes are synced (important after load_config)
        self.move_checkbox.setChecked(self.move)
        self.invert_checkbox.setChecked(self.invert)
        self.ignore_existing_checkbox.setChecked(self.ignore_existing)
        self.compress_checkbox.setChecked(self.compress)
        self.delete_checkbox.setChecked(self.delete)


    def select_src(self):
        start_dir = self.src_dir if os.path.exists(self.src_dir) else str(QDir.homePath())
        dir_ = QFileDialog.getExistingDirectory(self, "Select Source Folder", start_dir)
        if dir_:
            self.src_dir = dir_
            self.save_config()
            self.update_labels()

    def select_dst(self):
        start_dir = self.dst_dir if os.path.exists(self.dst_dir) else str(QDir.homePath())
        dir_ = QFileDialog.getExistingDirectory(self, "Select Destination Folder", start_dir)
        if dir_:
            self.dst_dir = dir_
            self.save_config()
            self.update_labels()

    # --- Config Persistence ---

    def set_config_data( self, data={} ):
        # Directories
        self.src_dir = data.get("src", "")
        self.dst_dir = data.get("dst", "")
            
        # Visuals
        self.theme_toggle = data.get("theme_toggle", False)
        self.theme_checkbox.setChecked(self.theme_toggle)

        # Font Size
        self.log_font_size = data.get("log_font_size", 13)
        self.font_size_spinbox.setValue(self.log_font_size)

        # DPI Font Size
        self.dpi_font_size = data.get("dpi_font_size", 78)
        self.dpi_font_size_spinbox.setValue(self.dpi_font_size)
        
        # Move
        self.move = data.get("move", False)
        self.move_checkbox.setChecked(self.move)
        
        # Invert
        self.invert = data.get("invert", False)
        # self.invert_checkbox.setChecked(self.invert)

        # Ignore Existing
        self.ignore_existing = data.get("ignore_existing", True)
        self.ignore_existing_checkbox.setChecked(self.ignore_existing)
        
        # Compress On Copy
        self.compress = data.get("compress", False) 
        self.compress_checkbox.setChecked(self.compress)
        
        # Delete On Copy
        self.delete = data.get("delete", False)
        self.delete_checkbox.setChecked(self.delete)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.set_config_data( data )
                    self.set_invert(self.invert_state)

            except Exception as e:
                # print(f"Error loading config: {e}")
                pass

        else:
            self.set_config_data( default_config )
            self.save_config()

    def save_config(self):
        data = {
            "src": self.src_dir,
            "dst": self.dst_dir,
            "theme_toggle": self.theme_toggle,
            "move": self.move_checkbox.isChecked(),
            "invert": self.invert_checkbox.isChecked(),
            "ignore_existing": self.ignore_existing_checkbox.isChecked(),
            "compress": self.compress_checkbox.isChecked(), 
            "delete": self.delete_checkbox.isChecked(),     
            "log_font_size": self.log_font_size,
            "dpi_font_size": self.dpi_font_size
            }
        
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)

    # --- Copy Logic ---

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

        if bool(self.src_dir == "" or self.src_dir == "None" and self.dst_dir == "" or self.dst_dir == "None"):
            self.log.append("Please select both top and bottom directories")
            return
        
        elif bool(self.src_dir == "" or self.src_dir == "None"):
            self.log.append("Please select a top directory")
            return
        
        elif bool(self.dst_dir == "" or self.dst_dir == "None"):
            self.log.append("Please select a bottom directory")
            return
        
        # Use the settings checkbox state as the source of truth
        move_state = self.move_checkbox.isChecked()
        invert_state = self.invert_checkbox.isChecked()
        ignore_existing_state = self.ignore_existing_checkbox.isChecked()
        compress_state = self.compress_checkbox.isChecked()
        delete_state = self.delete_checkbox.isChecked()

        self.copying = True
        self.start_cancel_btn.setText("Cancel Copy")
        self.progress.setValue(0)
        
        # Hide progress bar on Windows as robocopy progress is hard to parse
        if sys.platform.startswith('win'):
            self.progress.hide()
            self.log.append("Note: Progress bar is disabled on Windows as robocopy does not provide incremental overall progress.")
        else:
            self.progress.show()

        # Pass all settings states to the worker
        self.worker = CopyWorker(
            self.src_dir, 
            self.dst_dir, 
            move=move_state, 
            invert=invert_state,
            ignore_existing=ignore_existing_state,
            compress=compress_state, 
            delete=delete_state      
        )

        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.log_signal.connect(self.log.append)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def cancel_copy(self):
        self.log.append("\nCancelling Copy...\nTerminating process now.\n")
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
            self.log.append("\nCannot close the app while a copy is running.\nPlease cancel the copy first.\n")
            event.ignore()
        else:
            event.accept()

def apply_preferred_style(app, preferred_styles):
    available = set(QStyleFactory.keys())
    print("Available styles:", available)

    for style_name in preferred_styles:
        if style_name in available:
            print(f"Applying style: {style_name}")
            app.setStyle(QStyleFactory.create(style_name))
            return style_name

    print("No preferred styles found. Using default Qt style.")
    return None

CONFIG_FILE = os.path.expanduser("~/.fast_copy_gui_config.json")

def load_config_early():
    """Load configuration from file and set environment variables needed at startup."""
    config = default_config.copy()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            user_config = json.load(f)
            # Update the default config with any saved user values
            config.update(user_config)
            
    except FileNotFoundError:
        # If no config file exists, use defaults
        pass 
    except Exception as e:
        # Handle JSON parse errors, etc.
        print(f"Warning: Could not load configuration file. Using defaults. Error: {e}")
        
    
    # --- CRITICAL: Set the DPI environment variable BEFORE QApplication starts ---
    dpi_size = config.get("dpi_font_size", default_config["dpi_font_size"])
    os.environ["QT_FONT_DPI"] = f"{dpi_size}"
    
    return config

if __name__ == "__main__":
    initial_config = load_config_early()

    app = QApplication(sys.argv)

    # Try styles in order: macOS → windows → Fusion
    apply_preferred_style(app, ["macOS", "windows", "Fusion"])

    gui = CopyGUI()
    gui.show()
    sys.exit(app.exec())