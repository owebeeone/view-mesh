import argparse
import asyncio
import json
import os
import sys
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Tuple, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QFileSystemModel, 
    QTreeView, QVBoxLayout, QWidget, QMenuBar, QMenu, QStatusBar,
    QSplitter, QTabWidget, QToolBar, QMessageBox, QLabel,
    QHBoxLayout, QPushButton, QFrame
)
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, QSize, QPoint, QSettings, 
    QEvent, QFile, QStandardPaths, Signal, QTimer, QRect, QObject
)
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QCloseEvent, QFont, 
    QMouseEvent, QColor, QPalette, QResizeEvent, QPainter, QCursor, QFontMetrics
)

@dataclass
class WindowSettings:
    """Store window position, size and state."""
    size: Tuple[int, int] = (1024, 768)
    position: Tuple[int, int] = (100, 100)
    relative_position: Tuple[float, float] = (0.1, 0.1)  # As percentage of screen width/height
    is_maximized: bool = False
    explorer_width: int = 250
    state: Optional[bytes] = None
    screen_name: str = ""  # Store screen identifier
    screen_geometry: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height of screen
    global_font_size_adjust: int = 0 # New field
    
    @staticmethod
    def _parse_tuple_setting(
        settings: QSettings, 
        key: str, 
        element_type: type, 
        num_elements: int,
        default_tuple_value: Tuple 
    ) -> Tuple:
        raw_value = settings.value(key) # QSettings.value() returns None if key not found

        if raw_value is None: # Key not found
            # Optional: print(f"Setting '{key}' not found. Using default {default_tuple_value}.")
            return default_tuple_value

        try:
            # Ensure the value is treated as a string for parsing
            value_str = str(raw_value)
            if not isinstance(raw_value, str):
                # Log a warning if the original type wasn't a string, as it's unexpected for this parsing logic.
                print(f"Warning: Setting '{key}' (original value: '{raw_value}') had type {type(raw_value)}, parsed as string '{value_str}'.")

            parts = value_str.strip("()").split(",")
            if len(parts) != num_elements:
                raise ValueError(f"String '{value_str}' derived from setting '{key}' does not have {num_elements} parts after splitting")
            
            # Construct the tuple with the specified element type, stripping whitespace from each part
            parsed_elements = tuple(element_type(p.strip()) for p in parts)
            return parsed_elements
        except Exception as e:
            print(f"Error parsing setting '{key}' (raw value: '{raw_value}'): {e}. Using default {default_tuple_value}.")
            return default_tuple_value

    @classmethod
    def from_settings(cls, settings: QSettings) -> 'WindowSettings':
        """Load window settings from QSettings."""
        result = cls()
        if settings.contains("window/size"):
            size = settings.value("window/size")
            if isinstance(size, QSize):
                result.size = (size.width(), size.height())
            elif isinstance(size, str):
                # Handle potential string serialization
                parts = size.strip("()").split(",")
                if len(parts) == 2:
                    result.size = (int(parts[0]), int(parts[1]))
        
        if settings.contains("window/position"):
            pos = settings.value("window/position")
            if isinstance(pos, QPoint):
                result.position = (pos.x(), pos.y())
            elif isinstance(pos, str):
                # Handle potential string serialization
                parts = pos.strip("()").split(",")
                if len(parts) == 2:
                    result.position = (int(parts[0]), int(parts[1]))
        
        # Replace the previous block for relative_position with a call to the helper
        # result.relative_position already holds the dataclass default (e.g., (0.1, 0.1))
        # This default is passed to the helper to be returned if key is missing or parsing fails.
        result.relative_position = cls._parse_tuple_setting(
            settings,
            "window/relative_position",
            element_type=float,
            num_elements=2,
            default_tuple_value=result.relative_position # Pass current default as the fallback
        )
        
        if settings.contains("window/is_maximized"):
            result.is_maximized = settings.value("window/is_maximized", False, type=bool)
        
        if settings.contains("window/explorer_width"):
            result.explorer_width = settings.value("window/explorer_width", 250, type=int)
        
        if settings.contains("window/state"):
            result.state = settings.value("window/state")
        
        if settings.contains("window/screen_name"):
            result.screen_name = settings.value("window/screen_name", "")
        
        # Replace the previous block for screen_geometry with a call to the helper
        # result.screen_geometry already holds the dataclass default (e.g., (0,0,0,0))
        result.screen_geometry = cls._parse_tuple_setting(
            settings,
            "window/screen_geometry",
            element_type=int,
            num_elements=4,
            default_tuple_value=result.screen_geometry # Pass current default as fallback
        )
        
        if settings.contains("window/global_font_size_adjust"):
            result.global_font_size_adjust = settings.value("window/global_font_size_adjust", 0, type=int)
        
        return result
    
    def save_to_settings(self, settings: QSettings) -> None:
        """Save window settings to QSettings."""
        settings.setValue("window/size", QSize(*self.size))
        settings.setValue("window/position", QPoint(*self.position))
        settings.setValue("window/relative_position", str(self.relative_position))
        settings.setValue("window/is_maximized", self.is_maximized)
        settings.setValue("window/explorer_width", self.explorer_width)
        settings.setValue("window/screen_name", self.screen_name)
        # Store screen geometry as a string to avoid Qt serialization issues
        settings.setValue("window/screen_geometry", str(self.screen_geometry))
        settings.setValue("window/global_font_size_adjust", self.global_font_size_adjust) # Save new field
        if self.state:
            settings.setValue("window/state", self.state)

@dataclass
class AppConfig:
    """Application configuration."""
    app_name: str = "ViewMesh"
    org_name: str = "AnchorSCAD"
    settings: WindowSettings = field(default_factory=WindowSettings)
    initial_dir: str = field(default_factory=lambda: str(Path.home()))
    
    @classmethod
    def load(cls) -> 'AppConfig':
        """Load configuration from settings."""
        config = cls()
        settings = QSettings(config.org_name, config.app_name)
        config.settings = WindowSettings.from_settings(settings)
        if settings.contains("app/initial_dir"):
            config.initial_dir = settings.value("app/initial_dir")
        return config
    
    def save(self) -> None:
        """Save configuration to settings."""
        settings = QSettings(self.org_name, self.app_name)
        self.settings.save_to_settings(settings)
        settings.setValue("app/initial_dir", self.initial_dir)

@dataclass
class FileExplorerWidget(QWidget):
    """File explorer widget similar to VSCode."""
    parent: Optional[QWidget] = None
    initial_dir: str = field(default_factory=lambda: str(Path.home()))
    file_selected: ClassVar[Signal] = Signal(str)

    def __post_init__(self):
        super().__init__(self.parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create file system model
        self.model = QFileSystemModel()
        self.model.setRootPath(self.initial_dir)
        
        # Create tree view
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIndex(self.model.index(self.initial_dir))
        self.tree_view.setAnimated(False)
        self.tree_view.setIndentation(20)
        self.tree_view.setSortingEnabled(True)
        
        # Only show the file name column initially
        self.tree_view.setHeaderHidden(True)
        for i in range(1, self.model.columnCount()):
            self.tree_view.hideColumn(i)
        
        # Connect signals
        self.tree_view.clicked.connect(self._on_item_clicked)
        self.tree_view.doubleClicked.connect(self._on_item_double_clicked)
        
        # Set consistent font for tree view items - REMOVE FIXED SIZE
        # tree_font = self.tree_view.font()
        # tree_font.setPointSize(10) # Let it inherit from application font
        # self.tree_view.setFont(tree_font)
        
        # Visual improvements for the tree view
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setFrameStyle(0)  # Remove frame
        
        layout.addWidget(self.tree_view)
        self.setLayout(layout)
    
    def _on_item_clicked(self, index: QModelIndex):
        """Handle item clicked event."""
        file_path = self.model.filePath(index)
    
    def _on_item_double_clicked(self, index: QModelIndex):
        """Handle item double clicked event."""
        file_path = self.model.filePath(index)
        if os.path.isfile(file_path):
            self.file_selected.emit(file_path)
    
    def set_root_path(self, path: str):
        """Set the root path for the file explorer."""
        self.model.setRootPath(path)
        self.tree_view.setRootIndex(self.model.index(path))

class CustomTitleBar(QWidget):
    """Custom title bar for dock widgets to ensure consistent font styling."""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        
        # Set up layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)  # Reduced vertical padding
        layout.setSpacing(4)
        
        # Create a small "folder" icon for the Explorer
        # We'll use a unicode character instead of loading an image
        icon_label = QLabel("📁")
        icon_label.setFixedWidth(20)
        font = icon_label.font()
        # font.setPointSize(10) # Allow inheritance
        icon_label.setFont(font)
        icon_label.setStyleSheet("color: #ffffff;")  # Brighter color for better contrast
        
        # Title label
        self.title_label = QLabel(title)
        font = self.title_label.font()
        # font.setPointSize(10) # Allow inheritance
        font.setBold(True) 
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #ffffff;")  # Brighter color for better contrast
        
        layout.addWidget(icon_label)
        layout.addWidget(self.title_label)
        layout.addStretch()
        
        # Set background color with VS Code-like style
        self.setStyleSheet("""
            CustomTitleBar {
                background-color: #252526;
                border-bottom: 1px solid #1e1e1e;
            }
            QLabel {
                background: transparent;
            }
        """)
        
        # Set fixed height for consistency with VS Code
        self.setFixedHeight(24)  # Reduced from 30
        
        self.setLayout(layout)

class CustomWindowFrame(QWidget):
    """Custom window frame for VS Code-like appearance."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the UI components."""
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        
        # Title bar
        self.title_bar = QWidget(self)
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(10, 0, 0, 0)
        self.title_bar_layout.setSpacing(0)
        
        # Application icon
        self.icon_label = QLabel()
        self.icon_label.setText("🪟")  # Unicode symbol for window
        self.icon_label.setFixedSize(20, 20)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.title_bar_layout.addWidget(self.icon_label)
        self.title_bar_layout.addSpacing(5)
        
        # Window title
        self.title_label = QLabel("ViewMesh")
        title_font = self.title_label.font()
        title_font.setPointSize(9)
        self.title_label.setFont(title_font)
        self.title_bar_layout.addWidget(self.title_label)
        self.title_bar_layout.addStretch()
        
        # Window buttons
        button_size = 45  # Width slightly reduced
        button_height = 22  # Reduced from 30 to 22 for a more compact look
        
        # Minimize button
        self.minimize_button = QPushButton("─")
        self.minimize_button.setFixedSize(button_size, button_height)
        self.minimize_button.setFlat(True)
        self.minimize_button.clicked.connect(self.on_minimize)
        
        # Maximize/restore button
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(button_size, button_height)
        self.maximize_button.setFlat(True)
        self.maximize_button.clicked.connect(self.on_maximize_restore)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(button_size, button_height)
        self.close_button.setFlat(True)
        self.close_button.clicked.connect(self.on_close)
        
        # Add buttons to title bar
        self.title_bar_layout.addWidget(self.minimize_button)
        self.title_bar_layout.addWidget(self.maximize_button)
        self.title_bar_layout.addWidget(self.close_button)
        
        # Style title bar and buttons
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: #383838;
                color: #cccccc;
            }
            QPushButton {
                border: none;
                border-radius: 0px;
                background-color: #383838;
                color: #cccccc;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton#close_button:hover {
                background-color: #e81123;
                color: white;
            }
        """)
        self.close_button.setObjectName("close_button")
        
        # Content area
        self.content_area = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        # Add to main layout
        self.layout.addWidget(self.title_bar)
        self.layout.addWidget(self.content_area)
        
        # Border styling
        self.setStyleSheet("""
            CustomWindowFrame {
                border: 1px solid #1e1e1e;
                background-color: #252526;
            }
        """)
    
    def setTitle(self, title: str):
        """Set the window title."""
        self.title_label.setText(title)
    
    def addWidget(self, widget: QWidget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
    
    def on_minimize(self):
        """Minimize the window."""
        self.parent.showMinimized()
    
    def on_maximize_restore(self):
        """Maximize or restore the window."""
        if self.parent.isMaximized():
            self.parent.showNormal()
            self.maximize_button.setText("□")
        else:
            self.parent.showMaximized()
            self.maximize_button.setText("❐")
    
    def on_close(self):
        """Close the window."""
        self.parent.close()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for dragging the window."""
        # This event should be handled by the main ViewMeshApp window for frameless mode
        # when dragging the application's custom title bar.
        # If CustomWindowFrame were used as a standalone, non-frameless window's content,
        # then this might be relevant, but not for the main app window dragging.
        if event.button() == Qt.LeftButton and self.title_bar.geometry().contains(event.pos()):
            # Check if the click is on a button within the title bar
            for child in self.title_bar.findChildren(QPushButton):
                if child.geometry().contains(event.pos() - self.title_bar.pos()): # Adjust pos to child's coordinate system
                    # Let the button handle its own press
                    return super().mousePressEvent(event)
            
            # If not on a button, and if on Windows, try to initiate system drag
            if sys.platform == "win32":
                try:
                    # Ensure ReleaseCapture and SendMessage are available (might need to be class members or initialized)
                    # For this example, assuming they are initialized in ViewMeshApp and accessible
                    # Or, more directly:
                    ReleaseCapture = ctypes.windll.user32.ReleaseCapture
                    SendMessage = ctypes.windll.user32.SendMessageW
                    
                    ReleaseCapture()
                    # WM_NCLBUTTONDOWN = 0x00A1, HTCAPTION = 2
                    # Important: SendMessage should target the TOP-LEVEL window (self.parent in this context if parent is ViewMeshApp)
                    SendMessage(int(self.parent.winId()), 0x00A1, 2, 0)
                    event.accept()
                    return # Drag initiated by OS
                except AttributeError as e:
                    print(f"WinAPI functions not available or parent not set up for CustomWindowFrame drag: {e}")
                except Exception as e:
                    print(f"Error in CustomWindowFrame drag API: {e}")
            
            # Fallback or non-Windows: Delegate to parent if possible, or handle locally if this frame is meant to be independently draggable.
            # For the main application, ViewMeshApp should handle this.
            # If this CustomWindowFrame is truly independent and needs its own dragging:
            # self.is_dragging = True
            # self.drag_position = event.globalPos() - self.parent.frameGeometry().topLeft()
            # event.accept()
        super().mousePressEvent(event) # Pass on if not handled

class ViewMeshApp(QMainWindow):
    """Main ViewMesh application window."""
    
    def __init__(self, config: AppConfig):
        super().__init__(None, Qt.FramelessWindowHint)  # Make window frameless
        self.config = config
        self.setObjectName("ViewMeshAppMainWindow") # Added for event filter logging
        self.was_maximized_before_fullscreen = False # Initialize flag
        
        # Flags and positions for context menu initiated move
        self.is_context_menu_moving = False
        self.context_menu_drag_start_position = None
        self.context_menu_window_start_position = None

        # Timer for context menu initiated move
        self.context_move_timer = QTimer(self)
        self.context_move_timer.setInterval(16) # Roughly 60 FPS
        self.context_move_timer.timeout.connect(self._perform_context_menu_move)

        # Font size adjustment - Initialize from saved config
        self.global_font_size_adjust = self.config.settings.global_font_size_adjust
        _app_font = QApplication.font() 
        self.initial_app_font_point_size = _app_font.pointSize()
        self.initial_app_font_family = _app_font.family()
        
        # Set window title
        self.setWindowTitle(config.app_name)
        
        # Set up async event loop integration
        self.setup_async_loop()
        
        # Set up UI (event filter for title_bar will be installed here)
        self.setup_ui()
        
        # Restore window state
        self.restore_window_state()
        
        # Apply initial font size adjustment if any (AFTER UI is set up and state restored)
        if self.global_font_size_adjust != 0:
            # print(f"[DEBUG __init__] Applying initial font adjustment: {self.global_font_size_adjust}")
            self._apply_global_font_change()
        
        # Set resize cursor for window edges
        self.setMouseTracking(True)
        self.resize_padding = 5
        
        self.dragging = False
        self.drag_start_position = None
        self.window_start_position = None
        
        if sys.platform == "win32":
            try:
                self.user32 = ctypes.windll.user32
                self.ReleaseCapture = self.user32.ReleaseCapture
                self.SendMessage = self.user32.SendMessageW
                self.PostMessage = self.user32.PostMessageW # Load PostMessageW
                # print("Windows API functions for window management initialized (SendMessage, PostMessage)")
            except Exception as e:
                print(f"Error initializing Windows API functions: {e}")
                self.ReleaseCapture = None
                self.SendMessage = None
                self.PostMessage = None # Ensure it's None on error
        else:
            self.ReleaseCapture = None
            self.SendMessage = None
            self.PostMessage = None # Ensure it's None on non-Windows
        
        self.installEventFilter(self) # Install event filter for ViewMeshApp itself
        # print(f"Event filter installed on {self.objectName()} in __init__") # DEBUG PRINT
    
    def setup_ui(self):
        """Set up the main UI components."""
        # Main container widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main layout for the UI
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)
        
        # Create title bar with integrated menu and window controls
        self.title_bar = QWidget()
        self.title_bar.setObjectName("custom_title_bar_widget")
        self.title_bar.installEventFilter(self)
        # print(f"Event filter installed on {self.title_bar.objectName()} in setup_ui")
        # self.title_bar.setFixedHeight(24) # Allow dynamic height based on content
        self.title_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.title_bar.customContextMenuRequested.connect(self.show_title_bar_context_menu) # Added this line back
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.title_bar_layout.setSpacing(0)
        
        # App icon
        self.icon_label = QLabel()
        self.icon_label.setText("🪟")  # Unicode symbol for window
        self.icon_label.setFixedSize(18, 18)  # Smaller icon
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("color: #cccccc; padding-left: 5px;")
        self.title_bar_layout.addWidget(self.icon_label)
        self.title_bar_layout.addSpacing(3)
        
        # Create menu bar (will be added to title bar)
        self.menu_bar = QMenuBar()
        # self.menu_bar.setMaximumHeight(22) # Allow dynamic height based on font
        self.menu_bar.setObjectName("title_bar_menu_bar_widget")
        self.menu_bar.installEventFilter(self)
        # print(f"Event filter installed on {self.menu_bar.objectName()} in setup_ui")
        self.menu_bar.setStyleSheet("""
            QMenuBar {
                background-color: #1e1e1e;
                color: #cccccc;
                border: none;
                padding: 0px;  /* No padding */
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 2px 8px;  /* Minimal padding */
                margin: 0px;
                color: #cccccc;
            }
            QMenuBar::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
        """)
        
        # Add menu bar to title bar (takes up stretch space)
        self.title_bar_layout.addWidget(self.menu_bar, 1)
        
        # Window control buttons
        button_size = 40  # Width reduced further
        button_height = 20  # Height reduced further
        
        # Minimize button
        self.minimize_button = QPushButton("─")
        self.minimize_button.setFixedSize(button_size, button_height)
        self.minimize_button.setFlat(True)
        self.minimize_button.clicked.connect(self.showMinimized)
        
        # Maximize/restore button
        self.maximize_button = QPushButton("□")
        self.maximize_button.setFixedSize(button_size, button_height)
        self.maximize_button.setFlat(True)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        
        # Close button
        self.close_button = QPushButton("✕")
        self.close_button.setFixedSize(button_size, button_height)
        self.close_button.setFlat(True)
        self.close_button.clicked.connect(self.close)
        
        # Style window control buttons
        control_buttons_style = """
            QPushButton {
                background-color: #1e1e1e;
                color: #cccccc;
                border: none;
                border-radius: 0px;
                padding: 0px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            #close_button:hover {
                background-color: #e81123;
                color: white;
            }
        """
        self.minimize_button.setStyleSheet(control_buttons_style)
        self.maximize_button.setStyleSheet(control_buttons_style)
        self.close_button.setStyleSheet(control_buttons_style)
        self.close_button.setObjectName("close_button")
        
        # Add window control buttons to title bar
        self.title_bar_layout.addWidget(self.minimize_button)
        self.title_bar_layout.addWidget(self.maximize_button)
        self.title_bar_layout.addWidget(self.close_button)
        
        # Add title bar to main layout
        self.main_layout.addWidget(self.title_bar)
        
        # Content layout below title bar
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        
        # Create a container for the explorer and its toolbar to ensure proper alignment
        self.left_panel = QWidget()
        self.left_panel_layout = QVBoxLayout(self.left_panel)
        self.left_panel_layout.setContentsMargins(0, 0, 0, 0)
        self.left_panel_layout.setSpacing(0)
        
        # Tool bar for explorer - create it here to ensure it aligns with explorer
        self.explorer_toolbar = QToolBar("Explorer Toolbar")
        self.explorer_toolbar.setObjectName("explorer_toolbar")
        self.explorer_toolbar.setMovable(False)
        self.explorer_toolbar.setIconSize(QSize(16, 16))
        self.explorer_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.explorer_toolbar.setStyleSheet("""
            QToolBar {
                background-color: #252526;
                border: none;
                padding: 2px;
                spacing: 2px;
            }
            QToolButton {
                background-color: transparent;
                border: none;
                border-radius: 3px;
                padding: 6px;
                margin: 0px;
                color: #cccccc;
            }
            QToolButton:hover {
                background-color: #37373d;
                color: #ffffff;
            }
        """)
        
        # Add explorer toolbar buttons
        open_folder_action = QAction("📂", self)
        open_folder_action.setToolTip("Open Folder")
        open_folder_action.triggered.connect(self.on_open_folder)
        self.explorer_toolbar.addAction(open_folder_action)
        
        refresh_action = QAction("🔄", self)
        refresh_action.setToolTip("Refresh Explorer")
        self.explorer_toolbar.addAction(refresh_action)
        
        collapse_action = QAction("◀", self)
        collapse_action.setToolTip("Collapse Folders")
        self.explorer_toolbar.addAction(collapse_action)
        
        # Add explorer toolbar to left panel
        self.left_panel_layout.addWidget(self.explorer_toolbar)
        
        # Explorer panel with custom container
        self.explorer = FileExplorerWidget(initial_dir=self.config.initial_dir)
        
        # Create explorer dock with custom title
        self.explorer_dock = QDockWidget(self)
        self.explorer_dock.setObjectName("explorer_dock")
        self.explorer_dock.setWidget(self.explorer)
        
        # Create and set custom title bar
        custom_title = CustomTitleBar("EXPLORER", self.explorer_dock)  # VS Code uses uppercase
        self.explorer_dock.setTitleBarWidget(custom_title)
        
        # Set dock features
        self.explorer_dock.setFeatures(
            QDockWidget.DockWidgetMovable | 
            QDockWidget.DockWidgetClosable |
            QDockWidget.DockWidgetFloatable
        )
        
        # Style to match VS Code's explorer panel
        self.explorer_dock.setStyleSheet("""
            QDockWidget {
                border: none;
                background-color: #252526;
                color: #ffffff;
            }
            QTreeView {
                border: none;
                background-color: #252526;
                color: #cccccc;
                alternate-background-color: #252526;  /* Make both alternating colors the same */
            }
            QTreeView::item:selected {
                background-color: #094771;
                color: #ffffff;
            }
            QTreeView::item:hover:!selected {
                background-color: #2a2d2e;
            }
        """)
        
        # Only allow docking in left or right areas
        self.explorer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        # Add dock to left panel
        self.left_panel_layout.addWidget(self.explorer_dock)
        
        # Create splitter for sidebar and content
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Add left panel to splitter
        self.splitter.addWidget(self.left_panel)
        
        # Content area with tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        
        # Add a placeholder tab for now - styled like VS Code welcome page
        placeholder = QWidget()
        placeholder.setStyleSheet("background-color: #1e1e1e;")  # Set dark background color
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        
        # VS Code-like placeholder content
        welcome_label = QLabel("Welcome to ViewMesh")
        welcome_font = welcome_label.font()
        # welcome_font.setPointSize(14) # Allow inheritance or set relative
        welcome_font.setBold(True)
        welcome_label.setFont(welcome_font)
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setStyleSheet("color: #cccccc; margin-top: 40px; background-color: transparent;")
        
        placeholder_layout.addWidget(welcome_label)
        placeholder_layout.addStretch(1)
        self.tab_widget.addTab(placeholder, "Welcome")
        
        # Add a placeholder tab for now - styled like VS Code welcome page
        placeholder1 = QWidget()
        placeholder1.setStyleSheet("background-color: #1e1e1e;")
        pl_layout1 = QVBoxLayout(placeholder1)
        pl_layout1.addWidget(QLabel("Editor Tab 1 Content"))
        self.tab_widget.addTab(placeholder1, "Editor 1")

        placeholder2 = QWidget()
        placeholder2.setStyleSheet("background-color: #1e1e1e;")
        pl_layout2 = QVBoxLayout(placeholder2)
        pl_layout2.addWidget(QLabel("Editor Tab 2 Content"))
        self.tab_widget.addTab(placeholder2, "Editor 2")

        # Ensure tab widget has proper styling
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #cccccc;
                border: none;
                padding: 6px 12px;
                margin: 0px 1px 0px 0px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                border-top: 1px solid #007acc;
            }
        """)
        
        # Main content
        self.content_widget = QWidget()
        self.content_layout_inner = QVBoxLayout(self.content_widget)
        self.content_layout_inner.setContentsMargins(0, 0, 0, 0)
        self.content_layout_inner.addWidget(self.tab_widget)
        
        # Add content widget to splitter
        self.splitter.addWidget(self.content_widget)
        self.content_layout.addWidget(self.splitter)
        
        # Set initial splitter sizes to match VS Code's default proportions
        self.splitter.setSizes([250, 750])  # Explorer width, Content width
        
        # Status bar
        self.setup_status_bar()
        
        # Add content to main layout
        self.main_layout.addWidget(self.content_container)
        
        # Setup menu items
        self.setup_menu_items()
        
        # Apply dark theme to match VS Code
        self.apply_vs_code_dark_theme()

        # Set initial title bar height correctly after all elements and styles are applied
        self._update_title_bar_height()
        
        # Set border for frameless window (already present, ensure it's after height calc)
        self.setStyleSheet("""
            QMainWindow {
                border: 1px solid #252526;
                background-color: #1e1e1e;
            }
        """)
    
    def _update_title_bar_height(self):
        """Calculates and sets the title bar height based on current menu bar font and content."""
        # Ensure menu_bar's font is current (it should be if app font is set)
        menu_bar_font = self.menu_bar.font()
        
        # Force style recomputation for menu_bar to update its sizeHint correctly
        self.menu_bar.style().unpolish(self.menu_bar)
        self.menu_bar.style().polish(self.menu_bar)
        self.menu_bar.updateGeometry() 
        # print(f"[DEBUG _update_title_bar_height] self.menu_bar unpolished, polished, updateGeometry called.")

        menu_bar_natural_height = self.menu_bar.sizeHint().height()
        # print(f"[DEBUG _update_title_bar_height] self.menu_bar.sizeHint().height(): {menu_bar_natural_height}")
        # print(f"[DEBUG _update_title_bar_height] self.menu_bar minHeight: {self.menu_bar.minimumHeight()}, maxHeight: {self.menu_bar.maximumHeight()}")

        title_bar_padding = 4 # e.g., 2px top, 2px bottom for the title_bar itself
        calculated_title_bar_height = menu_bar_natural_height + title_bar_padding
        
        # Ensure calculated height is not less than the tallest fixed element (e.g., buttons)
        min_control_height = self.minimize_button.height() # Assuming all buttons are same height
        if calculated_title_bar_height < min_control_height + title_bar_padding:
            # print(f"[DEBUG _update_title_bar_height] Calculated height ({calculated_title_bar_height}) < min control height. Adjusting.")
            calculated_title_bar_height = min_control_height + title_bar_padding
        
        # print(f"[DEBUG _update_title_bar_height] Current self.title_bar.height() before setFixed: {self.title_bar.height()}")
        self.title_bar.setFixedHeight(calculated_title_bar_height)
        # print(f"[DEBUG _update_title_bar_height] self.title_bar.setFixedHeight({calculated_title_bar_height}) called.")
        self.title_bar.adjustSize() # Tell the title bar to adjust its size

    def _apply_global_font_change(self):
        new_point_size = self.initial_app_font_point_size + self.global_font_size_adjust
        if new_point_size <= 0: 
            new_point_size = 1 
        # print(f"[DEBUG] _apply_global_font_change: Adjust: {self.global_font_size_adjust}, InitialPt: {self.initial_app_font_point_size}, NewPt: {new_point_size}")

        new_font = QFont(self.initial_app_font_family, new_point_size)
        QApplication.setFont(new_font)
        # print(f"[DEBUG] QApplication font set to pointSize: {QApplication.font().pointSize()}")

        # The menu_bar should pick up the new QApplication font automatically.
        # If its font was explicitly set before, ensure it follows app font or update it here too.
        # Forcing its font for safety, though ideally it inherits from QApplication.font()
        menu_bar_font_check = self.menu_bar.font()
        if menu_bar_font_check.pointSize() != new_point_size:
            menu_bar_font_check.setPointSize(new_point_size)
            self.menu_bar.setFont(menu_bar_font_check)
            # print(f"[DEBUG] self.menu_bar font explicitly set to pointSize: {self.menu_bar.font().pointSize()} in _apply_global_font_change")

        self._update_title_bar_height() # Call the new method to set heights

        self.apply_vs_code_dark_theme() 
        self.update() 
        QApplication.processEvents() 
        # print(f"[DEBUG] After processEvents, self.title_bar.height(): {self.title_bar.height()}")

    def apply_vs_code_dark_theme(self):
        """Apply VS Code dark theme styling to all widgets."""
        # VS Code dark theme colors
        dark_theme = {
            'background': '#1e1e1e',
            'foreground': '#cccccc',
            'sidebar': '#252526',
            'active_selection': '#094771',
            'inactive_selection': '#37373d',
            'toolbar': '#333333',
            'tab_background': '#2d2d2d',
            'tab_active': '#1e1e1e',
            'input_background': '#3c3c3c',
            'border': '#474747',
            'status_bar': '#007acc'
        }
        
        vs_code_style = f"""
        /* Global styles */
        QWidget {{
            background-color: {dark_theme['background']};
            color: {dark_theme['foreground']};
        }}
        
        /* Menu styling */
        QMenuBar {{
            background-color: {dark_theme['background']};
            color: {dark_theme['foreground']};
            border-bottom: 1px solid {dark_theme['border']};
        }}
        
        QMenuBar::item {{
            background: transparent;
            padding: 5px 10px;
        }}
        
        QMenuBar::item:selected {{
            background-color: {dark_theme['active_selection']};
        }}
        
        QMenu {{
            background-color: {dark_theme['sidebar']};
            color: {dark_theme['foreground']};
            border: 1px solid {dark_theme['border']};
        }}
        
        QMenu::item {{
            padding: 5px 20px 5px 20px;
        }}
        
        QMenu::item:selected {{
            background-color: {dark_theme['active_selection']};
        }}
        
        /* Tree view styling */
        QTreeView {{
            background-color: {dark_theme['sidebar']};
            color: {dark_theme['foreground']};
            border: none;
            alternate-background-color: {dark_theme['sidebar']};  /* Make alternating colors the same */
        }}
        
        QTreeView::item {{
            padding: 2px;
        }}
        
        QTreeView::item:selected {{
            background-color: {dark_theme['active_selection']};
        }}
        
        /* Status bar styling */
        QStatusBar {{
            background-color: {dark_theme['status_bar']};
            color: white;
            border-top: 1px solid {dark_theme['border']};
        }}
        
        /* Scroll bar styling */
        QScrollBar:vertical {{
            background-color: {dark_theme['background']};
            width: 14px;
            margin: 0px;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: #5a5a5a;
            min-height: 20px;
            border-radius: 7px;
            margin: 2px;
        }}
        
        QScrollBar:horizontal {{
            background-color: {dark_theme['background']};
            height: 14px;
            margin: 0px;
        }}
        
        QScrollBar::handle:horizontal {{
            background-color: #5a5a5a;
            min-width: 20px;
            border-radius: 7px;
            margin: 2px;
        }}
        
        /* Toolbar styling */
        QToolBar {{
            background-color: {dark_theme['sidebar']};
            border: none;
            spacing: 0px;
        }}
        
        QToolButton {{
            background-color: transparent;
            border: none;
            padding: 5px;
            color: {dark_theme['foreground']};
        }}
        
        QToolButton:hover {{
            background-color: {dark_theme['inactive_selection']};
        }}
        
        /* Dock widget styling */
        QDockWidget {{
            titlebar-close-icon: url(close.png);
            titlebar-normal-icon: url(undock.png);
        }}
        
        QDockWidget::title {{
            text-align: left;
            background-color: {dark_theme['sidebar']};
            color: #ffffff;  /* White color for better contrast */
            padding: 5px;
        }}
        
        QDockWidget::close-button, QDockWidget::float-button {{
            border: none;
            background: transparent;
            padding: 0px;
        }}
        """
        
        # Apply the style to all widgets except TabWidget which already has specific styling
        self.setStyleSheet(vs_code_style)
    
    def setup_async_loop(self):
        """Set up the asyncio event loop and integrate with PySide6."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # Create a timer to run the asyncio event loop
        self.async_timer = QTimer(self)
        self.async_timer.timeout.connect(self._process_asyncio_events)
        self.async_timer.start(10)  # 10ms interval
    
    def _process_asyncio_events(self):
        """Process pending asyncio events."""
        self.loop.call_soon(self._run_event_loop_iteration)
    
    def _run_event_loop_iteration(self):
        """Run a single iteration of the asyncio event loop."""
        try:
            self.loop.stop()
            self.loop.run_forever()
        except Exception as e:
            print(f"Error in asyncio event loop: {e}")
    
    async def run_async_task(self, coro):
        """Run an asynchronous task."""
        try:
            return await coro
        except Exception as e:
            print(f"Error in async task: {e}")
            return None
    
    def schedule_async_task(self, coro):
        """Schedule an asynchronous task to be run in the asyncio loop."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future
    
    def restore_window_state(self):
        """Restore the window state from the configuration."""
        # Get available screens
        screens = QApplication.screens()
        target_screen = None
        
        # Try to find the saved screen by name
        if self.config.settings.screen_name:
            for screen in screens:
                if screen.name() == self.config.settings.screen_name:
                    target_screen = screen
                    break
        
        # If the saved screen wasn't found, use the primary screen
        if not target_screen:
            target_screen = QApplication.primaryScreen()
        
        # Get screen geometries
        screen_geo = target_screen.geometry()
        avail_geo = target_screen.availableGeometry()
        
        # Restore window size 
        self.resize(QSize(*self.config.settings.size))
        
        # Make the window invisible before showing it to prevent flashing
        self.setWindowOpacity(0.0)
        
        # Show the window before moving to ensure Qt knows it exists
        self.show()
        
        # Position window at the center of the target screen first
        screen_center = screen_geo.center()
        self.move(screen_center.x() - self.width() // 2, screen_center.y() - self.height() // 2)
        
        # Allow Qt events to process
        QApplication.processEvents()
        
        # Now position the window at its saved location
        if self.config.settings.screen_name:
            # Get saved position with boundary checks
            saved_x, saved_y = self.config.settings.position
            
            # Safety check to ensure window is within screen
            if saved_x < screen_geo.left():
                saved_x = screen_geo.left() + 10
            elif saved_x + self.width() > screen_geo.right():
                saved_x = screen_geo.right() - self.width() - 10
            
            if saved_y < screen_geo.top():
                saved_y = screen_geo.top() + 10
            elif saved_y + self.height() > screen_geo.bottom():
                saved_y = screen_geo.bottom() - self.height() - 10
            
            self.move(saved_x, saved_y)
            
            # Process events again to ensure the window manager acknowledges this movement
            QApplication.processEvents()
        
        # Now make the window visible in its final position
        self.setWindowOpacity(1.0)
        
        # Restore maximized state
        if self.config.settings.is_maximized:
            self.showMaximized()
        
        # Restore dock widget sizes
        self.explorer_dock.setMinimumWidth(self.config.settings.explorer_width)
        self.explorer_dock.setMaximumWidth(self.config.settings.explorer_width)
        
        # Restore complete window state if available
        if self.config.settings.state:
            self.restoreState(self.config.settings.state)
        
        # Restore initial directory
        self.explorer.initial_dir = self.config.initial_dir
        
        # Save configuration
        self.config.save()
    
    def save_window_state(self):
        """Save the current window state to the configuration."""
        # Get current screen
        current_screen = self.screen()
        if current_screen:
            # Save screen information
            self.config.settings.screen_name = current_screen.name()
            screen_geo = current_screen.geometry()
            avail_geo = current_screen.availableGeometry()
            self.config.settings.screen_geometry = (
                screen_geo.x(), screen_geo.y(), 
                screen_geo.width(), screen_geo.height()
            )
            
            # Save window position and size
            if not self.isMaximized():
                self.config.settings.size = (self.width(), self.height())
                
                # Save absolute position
                abs_x, abs_y = self.x(), self.y()
                self.config.settings.position = (abs_x, abs_y)
                
                # Calculate and save position relative to available screen area
                # This is more reliable for multi-monitor setups with different resolutions
                if avail_geo.width() > 0 and avail_geo.height() > 0:
                    rel_x = float(abs_x - avail_geo.x()) / float(avail_geo.width())
                    rel_y = float(abs_y - avail_geo.y()) / float(avail_geo.height())
                    
                    # Constrain to valid range [0.0, 1.0]
                    rel_x = max(0.0, min(1.0, rel_x))
                    rel_y = max(0.0, min(1.0, rel_y))
                    
                    self.config.settings.relative_position = (rel_x, rel_y)
                else:
                    # If screen geometry is not valid, keep existing or default relative_position
                    # This prevents overwriting a valid relative_position with bad data if screen info is weird
                    pass # self.config.settings.relative_position remains as loaded/default
                
                # print(f"Window position: {abs_x},{abs_y}")
                # print(f"Window relative position: {self.config.settings.relative_position[0]:.2f},{self.config.settings.relative_position[1]:.2f}")
                # print(f"Window size: {self.width()},{self.height()}")
        
        self.config.settings.is_maximized = self.isMaximized()
        self.config.settings.explorer_width = self.explorer_dock.width()
        self.config.settings.state = self.saveState()
        self.config.initial_dir = self.explorer.initial_dir
        self.config.settings.global_font_size_adjust = self.global_font_size_adjust # Save current adjustment
        
        # Save configuration
        self.config.save()
    
    def closeEvent(self, event: QCloseEvent):
        """Handle window close event."""
        # Save window state
        self.save_window_state()
        
        # Clean up asyncio loop
        self.async_timer.stop()
        
        # Accept the close event
        event.accept()
    
    # Event handlers
    def on_new_file(self):
        """Handle new file action."""
        self.showMessage("Creating new file...")
        # TODO: Implement new file functionality
    
    def on_open_file(self):
        """Handle open file action."""
        self.showMessage("Opening file...")
        # TODO: Implement open file functionality
    
    def on_open_folder(self):
        """Handle open folder action."""
        self.showMessage("Opening folder...")
        # TODO: Implement open folder functionality
    
    def on_save(self):
        """Handle save action."""
        self.showMessage("Saving file...")
        # TODO: Implement save functionality
    
    def on_save_as(self):
        """Handle save as action."""
        self.showMessage("Saving file as...")
        # TODO: Implement save as functionality
    
    def toggle_explorer(self, checked: bool):
        """Toggle the explorer panel."""
        self.explorer_dock.setVisible(checked)
    
    def on_about(self):
        """Show about dialog."""
        # Create a custom about dialog with consistent styling
        about_text = f"""
        <div style='text-align: center;'>
            <h2>{self.config.app_name}</h2>
            <p>Version 0.1.0</p>
            <p>A PySide6 application for viewing mesh files.</p>
            <p>© {self.config.org_name}</p>
        </div>
        """
        
        QMessageBox.about(self, f"About {self.config.app_name}", about_text)

    def showMessage(self, message: str, timeout: int = 0):
        """Show a message in the status bar."""
        if hasattr(self, 'status_message'):
            self.status_message.setText(message)
        else:
            self.status_bar.showMessage(message, timeout)

    def setup_status_bar(self):
        """Set up a status bar similar to VS Code."""
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.setStatusBar(self.status_bar)
        
        # Style the status bar
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #007acc;
                color: white;
                padding: 0px;
                font-size: 9pt;
            }
            QLabel {
                padding: 3px 5px;
                margin: 0px;
            }
        """)
        
        # Add permanent widgets (from right to left, as VS Code does)
        
        # Encoding indicator (UTF-8)
        self.encoding_label = QLabel("UTF-8")
        self.encoding_label.setObjectName("encoding_label")
        self.encoding_label.setStyleSheet("padding: 3px 8px; border-left: 1px solid rgba(255, 255, 255, 0.3);")
        self.status_bar.addPermanentWidget(self.encoding_label)
        
        # Line/column indicator
        self.line_col_label = QLabel("Ln 1, Col 1")
        self.line_col_label.setObjectName("line_col_label")
        self.line_col_label.setStyleSheet("padding: 3px 8px; border-left: 1px solid rgba(255, 255, 255, 0.3);")
        self.status_bar.addPermanentWidget(self.line_col_label)
        
        # Indent size indicator
        self.indent_label = QLabel("Spaces: 4")
        self.indent_label.setObjectName("indent_label")
        self.indent_label.setStyleSheet("padding: 3px 8px; border-left: 1px solid rgba(255, 255, 255, 0.3);")
        self.status_bar.addPermanentWidget(self.indent_label)
        
        # Main status message (left-aligned)
        self.status_message = QLabel("Ready")
        self.status_message.setObjectName("status_message")
        self.status_message.setStyleSheet("padding: 3px 8px;")
        self.status_bar.addWidget(self.status_message)

    def show_title_bar_context_menu(self, pos):
        """Show context menu for the title bar when right-clicked."""
        context_menu = QMenu(self)
        
        restore_action = None
        maximize_action = None

        if self.isMaximized():
            restore_action = context_menu.addAction("Restore")
        else:
            maximize_action = context_menu.addAction("Maximize")
        
        move_action = context_menu.addAction("Move")
        
        size_action = None
        if not self.isMaximized():
            size_action = context_menu.addAction("Size")
        
        context_menu.addSeparator()
        
        app_menu = context_menu.addMenu("ViewMesh")
        open_file_action = app_menu.addAction("Open File...")
        open_folder_action = app_menu.addAction("Open Folder...")
        app_menu.addSeparator()
        settings_action = app_menu.addAction("Settings")
        
        context_menu.addSeparator()
        minimize_action = context_menu.addAction("Minimize")
        context_menu.addSeparator()
        close_action = context_menu.addAction("Close")
        
        # Map position to global for exec()
        action = context_menu.exec(self.title_bar.mapToGlobal(pos))
        
        if action:
            if restore_action and action == restore_action:
                self.showNormal()
                self.maximize_button.setText("□")
            elif maximize_action and action == maximize_action:
                self.showMaximized()
                self.maximize_button.setText("❐")
            elif action == move_action:
                # print("Context Menu: Activating manual move mode (timer-based).")
                self.is_context_menu_moving = True
                self.context_menu_drag_start_position = QCursor.pos()
                self.context_menu_window_start_position = self.pos()
                QApplication.setOverrideCursor(Qt.SizeAllCursor) 
                self.context_move_timer.start()
                self.grabMouse() # Grab all mouse events for the window
                # print("Context Menu: Mouse grabbed.")
            elif size_action and action == size_action:
                if sys.platform == "win32" and self.SendMessage and self.ReleaseCapture:
                    try:
                        # print("Context Menu: Attempting resize with WM_SYSCOMMAND | SC_SIZE (BottomRight)")
                        self.ReleaseCapture()
                        self.SendMessage(int(self.winId()), 0x0112, 0xF008, 0) # WM_SYSCOMMAND, SC_SIZE + WMSZ_BOTTOMRIGHT
                    except Exception as e:
                        print(f"Error initiating system resize from context menu with WM_SYSCOMMAND: {e}") # Keep error prints
            elif action == minimize_action:
                self.showMinimized()
            elif action == close_action:
                self.close()
            elif action == open_file_action: self.on_open_file()
            elif action == open_folder_action: self.on_open_folder()
            elif action == settings_action: self.showMessage("Settings not implemented yet")

    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for window dragging and terminating context menu move."""
        if self.is_context_menu_moving:
            # print("mousePressEvent: Click received, terminating timer-based context menu move mode.")
            self.context_move_timer.stop() 
            self.is_context_menu_moving = False
            self.releaseMouse() # Release the mouse grab
            QApplication.restoreOverrideCursor() 
            # print("mousePressEvent: Mouse released and cursor restored.")
            event.accept() 
            return

        if event.button() == Qt.LeftButton:
            # print(f"mousePressEvent: Left button pressed at global {event.globalPosition().toPoint()}")
            
            # Debugging coordinate systems:
            # print(f"mousePressEvent: self (QMainWindow).pos(): {self.pos()}")
            # print(f"mousePressEvent: self.central_widget.pos() (rel to QMainWindow client area): {self.central_widget.pos()}")
            # print(f"mousePressEvent: self.title_bar.pos() (rel to central_widget): {self.title_bar.pos()}")
            # mapped_global_title_bar_origin = self.title_bar.mapToGlobal(QPoint(0,0))
            # print(f"mousePressEvent: self.title_bar.mapToGlobal(QPoint(0,0)): {mapped_global_title_bar_origin}")

            title_bar_global_rect = QRect(self.title_bar.mapToGlobal(QPoint(0,0)), self.title_bar.size())
            event_global_pos = event.globalPosition().toPoint()
            # print(f"mousePressEvent: Title bar global rect: {title_bar_global_rect}, Event global pos: {event_global_pos}")

            if title_bar_global_rect.contains(event_global_pos) and self.title_bar.isVisible():
                # print("mousePressEvent: Click is within title bar global rect and title bar is visible.")
                
                on_control = False
                for child_widget in self.title_bar.findChildren(QWidget):
                    if not child_widget.isVisible():
                        continue
                    
                    child_global_origin = child_widget.mapToGlobal(QPoint(0,0))
                    child_global_rect = QRect(child_global_origin, child_widget.size())
                    # print(f"mousePressEvent: Checking child {child_widget.objectName()} ({type(child_widget)}) at global rect {child_global_rect}")

                    if child_global_rect.contains(event_global_pos):
                        # print(f"mousePressEvent: Click was on child {child_widget.objectName()}")
                        if isinstance(child_widget, QPushButton):
                            # print(f"mousePressEvent: Child {child_widget.objectName()} is a QPushButton. Passing event.")
                            on_control = True
                            break 
                        elif child_widget == self.menu_bar: 
                            local_pos_in_menubar = self.menu_bar.mapFromGlobal(event_global_pos)
                            active_action = self.menu_bar.actionAt(local_pos_in_menubar)
                            if active_action:
                                # print(f"mousePressEvent: Click was on an active action ('{active_action.text()}') in the QMenuBar. Passing event.")
                                on_control = True
                            # else:
                                # print(f"mousePressEvent: Click was on the QMenuBar background, not an action. Allowing drag.")
                                
                            break 
                
                if not on_control:
                    # print("mousePressEvent: Click was not on a defined control (or on menu bar background). Attempting system drag.")
                    if sys.platform == "win32" and self.SendMessage and self.ReleaseCapture:
                        try:
                            # print("Attempting drag with WM_SYSCOMMAND | SC_MOVE") 
                            self.ReleaseCapture()
                            self.SendMessage(int(self.winId()), 0x0112, 0xF012, 0)
                            event.accept()
                            return 
                        except Exception as e:
                            print(f"Error initiating system drag with WM_SYSCOMMAND: {e}") # Keep error print
                            self.dragging = True
                            self.drag_start_position = event.globalPosition().toPoint()
                            self.window_start_position = self.pos()
                            event.accept()
                            return
                    else:
                        # print("mousePressEvent: Fallback to manual drag.")
                        self.dragging = True
                        self.drag_start_position = event.globalPosition().toPoint()
                        self.window_start_position = self.pos()
                        event.accept()
                        return
                # else:
                    # print("mousePressEvent: Click was on a defined control (QPushButton or QMenuBar action), not starting drag.")
            # else:
                # print(f"mousePressEvent: Click NOT in title bar global rect OR title bar not visible. Title bar visible: {self.title_bar.isVisible()}")
        
        # print("mousePressEvent: Event not handled for dragging, passing to super().")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for window dragging (manual fallback).""" 
        # print(f"mouseMoveEvent entered. QCursor.pos(): {QCursor.pos()}, buttons: {event.buttons()}")

        if self.dragging and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self.drag_start_position
            new_pos = self.window_start_position + delta
            self.move(new_pos)
            event.accept()
            return
        
        # For non-Windows platforms, or if nativeEvent-based resizing isn't active,
        # set resize cursors manually.
        if not self.isMaximized():
            if sys.platform != "win32": # Primarily for non-Windows
                pos = event.position().toPoint()
                direction = self.get_resize_direction(pos)
                if direction:
                    self.setCursor(self.get_resize_cursor(direction))
                else:
                    self.setCursor(Qt.ArrowCursor)
            elif not self.ReleaseCapture: # Or if WinAPI calls are not available as a fallback
                pos = event.position().toPoint()
                direction = self.get_resize_direction(pos)
                if direction:
                    self.setCursor(self.get_resize_cursor(direction))
                else:
                    self.setCursor(Qt.ArrowCursor)
            else: # On Windows with API, usually OS handles cursors via WM_NCHITTEST
                self.setCursor(Qt.ArrowCursor) # Default unless nativeEvent overrides

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events for window dragging (manual fallback)."""
        if event.button() == Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_start_position = None
            self.window_start_position = None
            self.setCursor(Qt.ArrowCursor) # Reset cursor
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def get_resize_direction(self, pos: QPoint) -> str:
        """Get the resize direction based on mouse position."""
        if self.isMaximized(): return '' # No resize if maximized
        rect = self.rect()
        padding = self.resize_padding
        
        on_left = pos.x() >= 0 and pos.x() <= padding
        on_right = pos.x() >= rect.width() - padding and pos.x() <= rect.width()
        on_top = pos.y() >=0 and pos.y() <= padding
        on_bottom = pos.y() >= rect.height() - padding and pos.y() <= rect.height()

        if on_top and on_left: return 'top-left'
        if on_bottom and on_left: return 'bottom-left'
        if on_top and on_right: return 'top-right'
        if on_bottom and on_right: return 'bottom-right'
        if on_left: return 'left'
        if on_right: return 'right'
        if on_top: return 'top'
        if on_bottom: return 'bottom'
        return ''

    def get_resize_cursor(self, direction: str) -> Qt.CursorShape:
        """Get the cursor shape for the resize direction."""
        if direction in ('top-left', 'bottom-right'): return Qt.SizeFDiagCursor
        if direction in ('top-right', 'bottom-left'): return Qt.SizeBDiagCursor
        if direction in ('left', 'right'): return Qt.SizeHorCursor
        if direction in ('top', 'bottom'): return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click events for title bar maximize/restore."""
        if event.button() == Qt.LeftButton:
            global_title_bar_pos = self.title_bar.mapToGlobal(QPoint(0,0))
            local_event_pos_in_title_bar = self.title_bar.mapFromGlobal(event.globalPosition().toPoint())

            if self.title_bar.rect().contains(local_event_pos_in_title_bar) and self.title_bar.isVisible():
                on_control = False
                for child_widget in self.title_bar.findChildren(QWidget):
                    if child_widget.isVisible() and child_widget.rect().contains(child_widget.mapFromGlobal(event.globalPosition().toPoint())):
                        if isinstance(child_widget, (QPushButton, QMenuBar)):
                            on_control = True
                            break
                
                if not on_control:
                    self.toggle_maximize()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def nativeEvent(self, eventType, message):
        """Handle native window events for window resizing (Windows)."""
        if sys.platform == "win32" and not self.isMaximized():
            try:
                msg_ptr = int(message)
            except (TypeError, ValueError):
                return super().nativeEvent(eventType, message)

            msg = ctypes.c_uint.from_address(msg_ptr).value
            
            if msg == 0x0084:  # WM_NCHITTEST
                cursor_pos = QCursor.pos()
                local_pos = self.mapFromGlobal(cursor_pos)
                
                x = local_pos.x()
                y = local_pos.y()
                w = self.width()
                h = self.height()
                # Determine title bar rect in local QMainWindow coordinates
                # title_bar_local_y_end = self.title_bar.mapTo(self, self.title_bar.rect().bottomRight()).y()
                # A simpler way: title_bar height is fixed
                title_bar_height = self.title_bar.height() 

                p = self.resize_padding # For resize borders
                ht_result = 0

                # Check resize borders first
                if x >= 0 and x < p and y >= 0 and y < p: ht_result = 13 # HTTOPLEFT
                elif x > w - p and x <= w and y >= 0 and y < p: ht_result = 14 # HTTOPRIGHT
                elif x >= 0 and x < p and y > h - p and y <= h: ht_result = 16 # HTBOTTOMLEFT
                elif x > w - p and x <= w and y > h - p and y <= h: ht_result = 17 # HTBOTTOMRIGHT
                elif x >= 0 and x < p: ht_result = 10 # HTLEFT
                elif x > w - p and x <= w: ht_result = 11 # HTRIGHT
                elif y >= 0 and y < p: ht_result = 12 # HTTOP
                elif y > h - p and y <= h: ht_result = 15 # HTBOTTOM
                # Now check for title bar (caption) area if not a resize border
                # Ensure this check doesn't overlap with controls on the title bar; 
                # that distinction should be made in mousePressEvent.
                # nativeEvent is for telling Windows what *kind* of area the mouse is over.
                elif y > p and y < title_bar_height: # Click is below top resize border and within title bar height
                    ht_result = 2 # HTCAPTION
                
                if ht_result != 0:
                    # print(f"nativeEvent (WM_NCHITTEST) at local_pos ({x},{y}): Returning ht_result: {ht_result}")
                    return True, ht_result
                else:
                    # If not on border or our defined title bar area for HTCAPTION, let it be HTCLIENT or default
                    # print(f"nativeEvent (WM_NCHITTEST) at local_pos ({x},{y}): No specific ht_result, passing to super.")
                    pass # Fall through to super

        result = super().nativeEvent(eventType, message)
        # print(f"nativeEvent: type={eventType}, super_handled={result[0] if isinstance(result, tuple) else result}, super_result={result[1] if isinstance(result, tuple) and len(result) > 1 else None}")
        return result

    def toggle_maximize(self):
        """Toggle maximize/restore window state."""
        if self.isMaximized():
            self.showNormal()
            self.maximize_button.setText("□") # Update button text
        else:
            self.showMaximized()
            self.maximize_button.setText("❐") # Update button text
    
    def setup_menu_items(self):
        # File Menu
        file_menu = self.menu_bar.addMenu("&File")

        new_action = QAction("&New", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.on_new_file)
        file_menu.addAction(new_action)

        open_file_action = QAction("&Open File...", self)
        open_file_action.setShortcut(QKeySequence.Open)
        open_file_action.triggered.connect(self.on_open_file)
        file_menu.addAction(open_file_action)

        open_folder_action = QAction("Open &Folder...", self)
        # No standard shortcut, but often Ctrl+K Ctrl+O or similar in VS Code like apps
        open_folder_action.triggered.connect(self.on_open_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close) # Connect to QMainWindow.close
        file_menu.addAction(exit_action)

        # Edit Menu (placeholders for now)
        edit_menu = self.menu_bar.addMenu("&Edit")

        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(lambda: self.showMessage("Undo not implemented"))
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(lambda: self.showMessage("Redo not implemented"))
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(lambda: self.showMessage("Cut not implemented"))
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(lambda: self.showMessage("Copy not implemented"))
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(lambda: self.showMessage("Paste not implemented"))
        edit_menu.addAction(paste_action)

        # View Menu
        view_menu = self.menu_bar.addMenu("&View")

        self.toggle_explorer_action = QAction("Toggle &Explorer", self)
        self.toggle_explorer_action.setCheckable(True)
        self.toggle_explorer_action.setChecked(self.explorer_dock.isVisible())
        self.toggle_explorer_action.triggered.connect(self.toggle_explorer)
        view_menu.addAction(self.toggle_explorer_action)
        # Keep action state in sync if explorer is closed by other means (e.g., context menu, 'x' button on dock)
        self.explorer_dock.visibilityChanged.connect(self.toggle_explorer_action.setChecked)

        self.toggle_welcome_action = QAction("Show &Welcome", self)
        self.toggle_welcome_action.setCheckable(True)
        # self.toggle_welcome_action.setChecked(self.welcome_dock.isVisible()) # Set initial state
        self.toggle_welcome_action.triggered.connect(self.toggle_welcome_panel)
        view_menu.addAction(self.toggle_welcome_action)
        # if hasattr(self, 'welcome_dock'): # Ensure welcome_dock exists before connecting
            # self.welcome_dock.visibilityChanged.connect(self.toggle_welcome_action.setChecked)

        toggle_fullscreen_action = QAction("Toggle &Fullscreen", self)
        toggle_fullscreen_action.setShortcut(QKeySequence.FullScreen)
        toggle_fullscreen_action.triggered.connect(self.toggle_fullscreen)
        # Make it checkable to reflect state
        toggle_fullscreen_action.setCheckable(True)
        toggle_fullscreen_action.setChecked(self.isFullScreen())
        view_menu.addAction(toggle_fullscreen_action)

        view_menu.addSeparator()

        increase_font_action = QAction("Increase Font Size", self)
        # Using Ctrl+Shift+Plus (often on the same key as Equals)
        increase_font_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_Equal))
        increase_font_action.triggered.connect(self.increase_font_size)
        view_menu.addAction(increase_font_action)
        self.addAction(increase_font_action) 

        decrease_font_action = QAction("Decrease Font Size", self)
        decrease_font_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_Minus))
        decrease_font_action.triggered.connect(self.decrease_font_size)
        view_menu.addAction(decrease_font_action)
        self.addAction(decrease_font_action)

        # Help Menu
        help_menu = self.menu_bar.addMenu("&Help")

        about_action = QAction("&About ViewMesh", self)
        about_action.triggered.connect(self.on_about)
        help_menu.addAction(about_action)

    def increase_font_size(self):
        print("increase_font_size called") # Debug
        self.global_font_size_adjust += 1
        self._apply_global_font_change()

    def decrease_font_size(self):
        print("decrease_font_size called") # Debug
        # Prevent font size from becoming too small or negative
        if (self.initial_app_font_point_size + self.global_font_size_adjust) > 1:
            self.global_font_size_adjust -= 1
            self._apply_global_font_change()
        else:
            print("decrease_font_size: Font size too small to decrease further.") # Debug

    def toggle_welcome_panel(self, checked: bool):
        if hasattr(self, 'welcome_dock'):
            self.welcome_dock.setVisible(checked)

    def _perform_context_menu_move(self):
        if not self.is_context_menu_moving:
            return

        current_mouse_pos = QCursor.pos()
        delta = current_mouse_pos - self.context_menu_drag_start_position
        new_pos = self.context_menu_window_start_position + delta
        self.move(new_pos)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            # Update maximize button if we came from maximized state before fullscreen
            if self.was_maximized_before_fullscreen:
                self.maximize_button.setText("❐")
            else:
                self.maximize_button.setText("□")
        else:
            self.was_maximized_before_fullscreen = self.isMaximized()
            self.showFullScreen()
        # Update the check state of the menu action
        # Assuming the action is stored or can be found. For now, let's find it.
        for action in self.menu_bar.findChildren(QAction):
            if action.text() == "Toggle &Fullscreen":
                action.setChecked(self.isFullScreen())
                break

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Check for stopping context menu move first, as this should be global
        if self.is_context_menu_moving and event.type() == QEvent.Type.MouseButtonPress:
            # This event is a QMouseEvent, need to cast to access button()
            # However, any mouse button press should stop the mode.
            # print(f"eventFilter: MouseButtonPress detected during context_menu_moving. Stopping move.")
            self.context_move_timer.stop()
            self.is_context_menu_moving = False
            self.releaseMouse() # Release the mouse grab
            QApplication.restoreOverrideCursor()
            # print("eventFilter: Mouse released and cursor restored.")
            # Consume the event to prevent the underlying widget from processing it
            # (e.g., QTabWidget trying to change tabs on the click that stops the move)
            return True # Event handled

        # Existing eventFilter logic for logging and menu bar dragging
        if event.type() == QEvent.Type.MouseButtonPress:
            mouse_event = event # PySide6 handles the cast from QEvent to QMouseEvent here
            watched_name = watched.objectName() if watched.objectName() else type(watched).__name__
            button_name = "Unknown"
            if mouse_event.button() == Qt.MouseButton.LeftButton: button_name = "LeftButton"
            elif mouse_event.button() == Qt.MouseButton.RightButton: button_name = "RightButton"
            elif mouse_event.button() == Qt.MouseButton.MiddleButton: button_name = "MiddleButton"
            
            # print(f"eventFilter on '{watched_name}': MouseButtonPress, button: {button_name}, globalPos: {mouse_event.globalPosition().toPoint()}")

            # If the event is a left-click on the menu_bar, forward it to the main mousePressEvent
            # This is for allowing drag on the menubar background when it has no active action
            if watched == self.menu_bar and mouse_event.button() == Qt.MouseButton.LeftButton:
                # print(f"eventFilter: Forwarding MouseButtonPress on '{watched_name}' to self.mousePressEvent for potential drag")
                # Call the main handler. Note: mousePressEvent itself checks for is_context_menu_moving first.
                # If we are here, is_context_menu_moving was false, so this is for title bar drag.
                self.mousePressEvent(mouse_event) 
                
                if mouse_event.isAccepted():
                    # print(f"eventFilter: self.mousePressEvent accepted the event for '{watched_name}'. Returning True.")
                    return True # Event was handled (e.g., for dragging)
                else:
                    # print(f"eventFilter: self.mousePressEvent did NOT accept the event for '{watched_name}'. Returning False to allow widget's own processing.")
                    return False # Event not handled by drag logic, let the original widget (menu_bar) process it
        
        return False

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="ViewMesh application")
    parser.add_argument(
        "--dir", 
        "-d", 
        type=str, 
        help="Initial directory to open"
    )
    return parser.parse_args()

def main():
    """Main entry point for the application."""
    # Parse command line arguments
    args = parse_args()
    
    # Update config based on arguments
    config = AppConfig.load()
    if args.dir:
        if os.path.isdir(args.dir):
            config.initial_dir = args.dir
    
    # Create application
    app = QApplication(sys.argv)
    app.setOrganizationName(config.org_name)
    app.setApplicationName(config.app_name)
    
    # Get system font and size for consistency
    system_font = app.font()
    system_font_family = system_font.family()
    system_font_size = 10  # Default consistent size
    
    # Create a consistent application font
    default_font = QFont(system_font_family, system_font_size)
    app.setFont(default_font)
    
    # Set specific font sizes for different widget classes
    # This directly sets font for specific widget classes
    app.setFont(default_font, "QDockWidget")
    app.setFont(QFont(system_font_family, system_font_size - 1), "QStatusBar")
    
    # Apply VS Code-like style to the application
    # Using light theme colors similar to VS Code
    vs_code_style = f"""
    /* Global application style */
    QWidget {{
        font-family: {system_font_family};
        /* font-size: {system_font_size}pt; */ /* Commented out to allow QApplication.setFont to control base size */
        color: #333333;
        background-color: #ffffff;
    }}
    
    /* Main window styling */
    QMainWindow {{
        background-color: #f3f3f3;
    }}
    
    /* Menu bar styling */
    QMenuBar {{
        background-color: #f3f3f3;
        border-bottom: 1px solid #e7e7e7;
        padding: 2px;
        spacing: 5px;
    }}
    
    QMenuBar::item {{
        background-color: transparent;
        padding: 5px 8px;
        border-radius: 3px;
    }}
    
    QMenuBar::item:selected {{
        background-color: #e0e0e0;
    }}
    
    QMenuBar::item:pressed {{
        background-color: #d0d0d0;
    }}
    
    /* Menu styling */
    QMenu {{
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 3px;
    }}
    
    QMenu::item {{
        padding: 5px 20px 5px 20px;
        border-radius: 3px;
    }}
    
    QMenu::item:selected {{
        background-color: #e8e8f2;
        color: #333333;
    }}
    
    /* Status bar styling */
    QStatusBar {{
        background-color: #007acc;
        color: white;
        padding: 3px;
        font-size: 9pt;
    }}
    
    /* Toolbar styling */
    QToolBar {{
        background-color: #f3f3f3;
        border-bottom: 1px solid #e7e7e7;
        spacing: 3px;
        padding: 3px;
    }}
    
    QToolButton {{
        background-color: transparent;
        border: none;
        padding: 5px;
        border-radius: 3px;
    }}
    
    QToolButton:hover {{
        background-color: #e0e0e0;
    }}
    
    QToolButton:pressed {{
        background-color: #d0d0d0;
    }}
    
    /* Dock widget styling */
    QDockWidget {{
        border: 1px solid #e0e0e0;
        font-size: {system_font_size}pt;
    }}
    
    QDockWidget::title {{
        font-size: {system_font_size}pt;
        padding: 5px;
        background-color: #f0f0f0;
        border: 1px solid #ddd;
    }}
    
    /* Tab widget styling */
    QTabWidget::pane {{
        border: 1px solid #e0e0e0;
        border-top: none;
    }}
    
    QTabBar::tab {{
        background-color: #f3f3f3;
        border: 1px solid #e0e0e0;
        border-bottom: none;
        padding: 6px 12px;
        margin: 0px 2px 0px 0px;
        border-top-left-radius: 3px;
        border-top-right-radius: 3px;
    }}
    
    QTabBar::tab:selected {{
        background-color: #ffffff;
        border-bottom: 1px solid #ffffff;
    }}
    
    QTabBar::tab:hover:!selected {{
        background-color: #e8e8e8;
    }}
    
    /* Tree view styling (for file explorer) */
    QTreeView {{
        border: none;
        background-color: #f8f8f8;
        alternate-background-color: #f0f0f0;
        padding: 2px;
    }}
    
    QTreeView::item {{
        padding: 2px;
        border-radius: 2px;
    }}
    
    QTreeView::item:selected {{
        background-color: #e0e7ff;
        color: #333333;
    }}
    
    QTreeView::item:hover:!selected {{
        background-color: #edf2fc;
    }}
    
    /* Scrollbar styling */
    QScrollBar:vertical {{
        border: none;
        background-color: #f0f0f0;
        width: 12px;
        margin: 0px;
    }}
    
    QScrollBar::handle:vertical {{
        background-color: #cdcdcd;
        border-radius: 6px;
        min-height: 20px;
        margin: 2px;
    }}
    
    QScrollBar::handle:vertical:hover {{
        background-color: #b0b0b0;
    }}
    
    QScrollBar:horizontal {{
        border: none;
        background-color: #f0f0f0;
        height: 12px;
        margin: 0px;
    }}
    
    QScrollBar::handle:horizontal {{
        background-color: #cdcdcd;
        border-radius: 6px;
        min-width: 20px;
        margin: 2px;
    }}
    
    QScrollBar::handle:horizontal:hover {{
        background-color: #b0b0b0;
    }}
    
    /* Splitter styling */
    QSplitter::handle {{
        background-color: #e0e0e0;
    }}
    
    QSplitter::handle:horizontal {{
        width: 1px;
    }}
    
    QSplitter::handle:vertical {{
        height: 1px;
    }}
    
    /* Message boxes */
    QMessageBox {{
        font-size: {system_font_size}pt;
    }}
    
    QMessageBox QLabel {{
        min-width: 300px;
    }}
    
    /* Dialog styling */
    QDialog {{
        font-size: {system_font_size}pt;
        background-color: #f5f5f5;
    }}
    
    /* Tooltip styling */
    QToolTip {{
        font-size: {system_font_size - 1}pt;
        padding: 2px;
        border: 1px solid #e0e0e0;
        background-color: #ffffff;
        color: #333333;
    }}
    """
    
    app.setStyleSheet(vs_code_style)
    
    # Create main window
    window = ViewMeshApp(config)
    window.show()
    
    # Run the Qt event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    asyncio.run(main()) 