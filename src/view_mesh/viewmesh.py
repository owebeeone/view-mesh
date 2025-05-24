import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QFileSystemModel, 
    QTreeView, QVBoxLayout, QWidget, QMenuBar, QMenu, QStatusBar,
    QSplitter, QTabWidget, QToolBar, QMessageBox, QLabel,
    QHBoxLayout, QPushButton, QFrame
)
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, QSize, QPoint, QSettings, 
    QEvent, QFile, QStandardPaths, Signal, QTimer, QRect
)
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QCloseEvent, QFont, 
    QMouseEvent, QColor, QPalette, QResizeEvent, QPainter
)

@dataclass
class WindowSettings:
    """Store window position, size and state."""
    size: Tuple[int, int] = (1024, 768)
    position: Tuple[int, int] = (100, 100)
    # Store position relative to screen (not global)
    relative_position: Tuple[float, float] = (0.1, 0.1)  # As percentage of screen width/height
    is_maximized: bool = False
    explorer_width: int = 250
    state: Optional[bytes] = None
    screen_name: str = ""  # Store screen identifier
    screen_geometry: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height of screen
    
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
        
        if settings.contains("window/relative_position"):
            rel_pos = settings.value("window/relative_position")
            if isinstance(rel_pos, str):
                try:
                    parts = rel_pos.strip("()").split(",")
                    if len(parts) == 2:
                        result.relative_position = (float(parts[0]), float(parts[1]))
                except:
                    pass
        
        if settings.contains("window/is_maximized"):
            result.is_maximized = settings.value("window/is_maximized", False, type=bool)
        
        if settings.contains("window/explorer_width"):
            result.explorer_width = settings.value("window/explorer_width", 250, type=int)
        
        if settings.contains("window/state"):
            result.state = settings.value("window/state")
        
        if settings.contains("window/screen_name"):
            result.screen_name = settings.value("window/screen_name", "")
        
        if settings.contains("window/screen_geometry"):
            geo = settings.value("window/screen_geometry")
            if isinstance(geo, str):
                # Parse string geometry 
                try:
                    parts = geo.strip("()").split(",")
                    if len(parts) == 4:
                        result.screen_geometry = tuple(int(p) for p in parts)
                except:
                    pass
        
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
    file_selected: Signal = field(default_factory=lambda: Signal(str))

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
        
        # Set consistent font for tree view items
        tree_font = self.tree_view.font()
        tree_font.setPointSize(10)
        self.tree_view.setFont(tree_font)
        
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
        font.setPointSize(10)
        icon_label.setFont(font)
        icon_label.setStyleSheet("color: #ffffff;")  # Brighter color for better contrast
        
        # Title label
        self.title_label = QLabel(title)
        font = self.title_label.font()
        font.setPointSize(10)
        font.setBold(True)  # Make it slightly bold for emphasis
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
        self.is_dragging = False
        self.drag_position = QPoint()
        
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
        if event.button() == Qt.LeftButton and self.title_bar.geometry().contains(event.pos()):
            self.is_dragging = True
            self.drag_position = event.globalPos() - self.parent.frameGeometry().topLeft()
            event.accept()
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events for dragging the window."""
        if event.button() == Qt.LeftButton:
            self.is_dragging = False
            event.accept()
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for dragging the window."""
        if self.is_dragging and event.buttons() & Qt.LeftButton:
            self.parent.move(event.globalPos() - self.drag_position)
            event.accept()
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click events on the title bar to maximize/restore."""
        if self.title_bar.geometry().contains(event.pos()):
            self.on_maximize_restore()
            event.accept()

class ViewMeshApp(QMainWindow):
    """Main ViewMesh application window."""
    
    def __init__(self, config: AppConfig):
        super().__init__(None, Qt.FramelessWindowHint)  # Make window frameless
        self.config = config
        
        # Set window title
        self.setWindowTitle(config.app_name)
        
        # Set up async event loop integration
        self.setup_async_loop()
        
        # Set up UI
        self.setup_ui()
        
        # Restore window state
        self.restore_window_state()
        
        # Set resize cursor for window edges
        self.setMouseTracking(True)
        self.resize_padding = 5  # Padding area for resizing
        self.resizing = False
        self.resize_direction = None
        
        # Window dragging variables
        self.dragging = False
        self.drag_start_position = None
    
    def setup_ui(self):
        """Set up the main UI components."""
        # Main container widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main layout for the UI
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(1, 1, 1, 1)  # Minimal margins for border
        self.main_layout.setSpacing(0)
        
        # Create title bar with integrated menu and window controls
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(24)  # Reduced to 24px total
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
        self.menu_bar.setMaximumHeight(22)  # Even smaller
        self.menu_bar.setObjectName("main_menu_bar")
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
        self.title_bar_layout.addWidget(self.menu_bar, 1)  # Stretches to fill space
        
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
        welcome_font.setPointSize(14)
        welcome_font.setBold(True)
        welcome_label.setFont(welcome_font)
        welcome_label.setAlignment(Qt.AlignCenter)
        welcome_label.setStyleSheet("color: #cccccc; margin-top: 40px; background-color: transparent;")
        
        placeholder_layout.addWidget(welcome_label)
        placeholder_layout.addStretch(1)
        self.tab_widget.addTab(placeholder, "Welcome")
        
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
        
        # Set border for frameless window
        self.setStyleSheet("""
            QMainWindow {
                border: 1px solid #252526;
                background-color: #1e1e1e;
            }
        """)
    
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
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events for resizing and dragging the window."""
        if not self.isMaximized():  # Only allow resize when not maximized
            # Check for resize edge areas
            direction = self.get_resize_direction(event.position().toPoint())
            if direction:
                self.resizing = True
                self.resize_direction = direction
                self.resize_start_position = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
                self.setCursor(self.get_resize_cursor(direction))
                event.accept()
                return
        
        # Check if we're in the title bar area for dragging
        if self.title_bar.underMouse() and event.button() == Qt.LeftButton:
            # Only start dragging if we're not clicking a child widget in the title bar
            # that handles its own mouse events (like menu items)
            for child in self.title_bar.findChildren(QWidget):
                if child.isVisible() and child.geometry().contains(event.position().toPoint() - self.title_bar.pos()):
                    if isinstance(child, QMenuBar) or isinstance(child, QPushButton):
                        # Let menu bar and buttons handle their own events
                        return super().mousePressEvent(event)
                    
            # Start dragging
            self.dragging = True
            self.drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
            
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release events for resizing and dragging the window."""
        if self.resizing:
            self.resizing = False
            self.resize_direction = None
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        
        if self.dragging:
            self.dragging = False
            event.accept()
            return
        
        super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move events for resizing and dragging the window."""
        if not self.isMaximized():  # Only allow resize/drag when not maximized
            if self.resizing and self.resize_direction:
                # Calculate new geometry based on resize direction and mouse position
                diff = event.globalPosition().toPoint() - self.resize_start_position
                new_geometry = QRect(self.resize_start_geometry)
                
                # Adjust geometry based on resize direction
                if 'left' in self.resize_direction:
                    new_geometry.setLeft(self.resize_start_geometry.left() + diff.x())
                if 'top' in self.resize_direction:
                    new_geometry.setTop(self.resize_start_geometry.top() + diff.y())
                if 'right' in self.resize_direction:
                    new_geometry.setRight(self.resize_start_geometry.right() + diff.x())
                if 'bottom' in self.resize_direction:
                    new_geometry.setBottom(self.resize_start_geometry.bottom() + diff.y())
                
                # Apply new geometry if it's valid
                if new_geometry.width() >= self.minimumWidth() and new_geometry.height() >= self.minimumHeight():
                    self.setGeometry(new_geometry)
                event.accept()
                return
            elif self.dragging and event.buttons() & Qt.LeftButton:
                # Move the window when dragging the title bar
                self.move(event.globalPosition().toPoint() - self.drag_start_position)
                event.accept()
                return
            else:
                # Update cursor based on mouse position for resize areas
                direction = self.get_resize_direction(event.position().toPoint())
                if direction:
                    self.setCursor(self.get_resize_cursor(direction))
                else:
                    self.setCursor(Qt.ArrowCursor)
        
        super().mouseMoveEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Handle double-click events on the title bar to maximize/restore."""
        if self.title_bar.underMouse() and event.button() == Qt.LeftButton:
            # Make sure we're not double-clicking a specific control in the title bar
            for child in self.title_bar.findChildren(QWidget):
                if child.isVisible() and child.geometry().contains(event.position().toPoint() - self.title_bar.pos()):
                    if isinstance(child, QMenuBar) or isinstance(child, QPushButton):
                        # Let menu bar and buttons handle their own events
                        return super().mouseDoubleClickEvent(event)
            
            # Toggle maximize state
            self.toggle_maximize()
            event.accept()
            return
        
        super().mouseDoubleClickEvent(event)
    
    def get_resize_direction(self, pos: QPoint) -> str:
        """Get the resize direction based on mouse position."""
        if not self.isMaximized():  # Only allow resize when not maximized
            rect = self.rect()
            padding = self.resize_padding
            
            # Check left edge
            if pos.x() <= padding:
                if pos.y() <= padding:
                    return 'top-left'
                elif pos.y() >= rect.height() - padding:
                    return 'bottom-left'
                else:
                    return 'left'
            
            # Check right edge
            elif pos.x() >= rect.width() - padding:
                if pos.y() <= padding:
                    return 'top-right'
                elif pos.y() >= rect.height() - padding:
                    return 'bottom-right'
                else:
                    return 'right'
            
            # Check top edge
            elif pos.y() <= padding:
                return 'top'
            
            # Check bottom edge
            elif pos.y() >= rect.height() - padding:
                return 'bottom'
        
        return ''

    def get_resize_cursor(self, direction: str) -> Qt.CursorShape:
        """Get the cursor shape for the resize direction."""
        if direction in ('top-left', 'bottom-right'):
            return Qt.SizeFDiagCursor
        elif direction in ('top-right', 'bottom-left'):
            return Qt.SizeBDiagCursor
        elif direction in ('left', 'right'):
            return Qt.SizeHorCursor
        elif direction in ('top', 'bottom'):
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def toggle_maximize(self):
        """Toggle maximize/restore window state."""
        if self.isMaximized():
            self.showNormal()
            self.maximize_button.setText("□")
        else:
            self.showMaximized()
            self.maximize_button.setText("❐")
    
    def setup_menu_items(self):
        """Set up the menu bar items."""
        # File menu
        self.file_menu = self.menu_bar.addMenu("&File")
        
        # New file action
        new_file_action = QAction("&New File", self)
        new_file_action.setShortcut(QKeySequence.New)
        new_file_action.triggered.connect(self.on_new_file)
        self.file_menu.addAction(new_file_action)
        
        # Open file action
        open_file_action = QAction("&Open File...", self)
        open_file_action.setShortcut(QKeySequence.Open)
        open_file_action.triggered.connect(self.on_open_file)
        self.file_menu.addAction(open_file_action)
        
        # Open folder action
        open_folder_action = QAction("Open F&older...", self)
        open_folder_action.triggered.connect(self.on_open_folder)
        self.file_menu.addAction(open_folder_action)
        
        self.file_menu.addSeparator()
        
        # Save action
        save_action = QAction("&Save", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.on_save)
        self.file_menu.addAction(save_action)
        
        # Save as action
        save_as_action = QAction("Save &As...", self)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(self.on_save_as)
        self.file_menu.addAction(save_as_action)
        
        self.file_menu.addSeparator()
        
        # Preferences submenu (VS Code style)
        preferences_menu = self.file_menu.addMenu("&Preferences")
        
        # Settings action
        settings_action = QAction("&Settings", self)
        settings_action.setShortcut("Ctrl+,")
        preferences_menu.addAction(settings_action)
        
        # Color Theme action
        color_theme_action = QAction("Color &Theme", self)
        preferences_menu.addAction(color_theme_action)
        
        self.file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        self.file_menu.addAction(exit_action)
        
        # Edit menu
        self.edit_menu = self.menu_bar.addMenu("&Edit")
        
        # Undo action
        undo_action = QAction("&Undo", self)
        undo_action.setShortcut(QKeySequence.Undo)
        self.edit_menu.addAction(undo_action)
        
        # Redo action
        redo_action = QAction("&Redo", self)
        redo_action.setShortcut(QKeySequence.Redo)
        self.edit_menu.addAction(redo_action)
        
        self.edit_menu.addSeparator()
        
        # Cut action
        cut_action = QAction("Cu&t", self)
        cut_action.setShortcut(QKeySequence.Cut)
        self.edit_menu.addAction(cut_action)
        
        # Copy action
        copy_action = QAction("&Copy", self)
        copy_action.setShortcut(QKeySequence.Copy)
        self.edit_menu.addAction(copy_action)
        
        # Paste action
        paste_action = QAction("&Paste", self)
        paste_action.setShortcut(QKeySequence.Paste)
        self.edit_menu.addAction(paste_action)
        
        self.edit_menu.addSeparator()
        
        # Find action (VS Code style)
        find_action = QAction("&Find", self)
        find_action.setShortcut(QKeySequence.Find)
        self.edit_menu.addAction(find_action)
        
        # Replace action
        replace_action = QAction("&Replace", self)
        replace_action.setShortcut(QKeySequence.Replace)
        self.edit_menu.addAction(replace_action)
        
        # View menu (VS Code style)
        self.view_menu = self.menu_bar.addMenu("&View")
        
        # Command Palette action
        cmd_palette_action = QAction("&Command Palette...", self)
        cmd_palette_action.setShortcut("Ctrl+Shift+P")
        self.view_menu.addAction(cmd_palette_action)
        
        self.view_menu.addSeparator()
        
        # Appearance submenu
        appearance_menu = self.view_menu.addMenu("&Appearance")
        
        # Full Screen action
        full_screen_action = QAction("&Full Screen", self)
        full_screen_action.setShortcut("F11")
        appearance_menu.addAction(full_screen_action)
        
        # Zoom In action
        zoom_in_action = QAction("Zoom &In", self)
        zoom_in_action.setShortcut(QKeySequence.ZoomIn)
        appearance_menu.addAction(zoom_in_action)
        
        # Zoom Out action
        zoom_out_action = QAction("Zoom &Out", self)
        zoom_out_action.setShortcut(QKeySequence.ZoomOut)
        appearance_menu.addAction(zoom_out_action)
        
        self.view_menu.addSeparator()
        
        # Explorer action
        toggle_explorer_action = QAction("&Explorer", self)
        toggle_explorer_action.setCheckable(True)
        toggle_explorer_action.setChecked(True)
        toggle_explorer_action.triggered.connect(self.toggle_explorer)
        self.view_menu.addAction(toggle_explorer_action)
        
        # Search action
        toggle_search_action = QAction("&Search", self)
        toggle_search_action.setCheckable(True)
        toggle_search_action.setChecked(False)
        self.view_menu.addAction(toggle_search_action)
        
        # Run menu (VS Code style)
        self.run_menu = self.menu_bar.addMenu("&Run")
        
        # Start action
        start_action = QAction("&Start", self)
        start_action.setShortcut("F5")
        self.run_menu.addAction(start_action)
        
        # Help menu
        self.help_menu = self.menu_bar.addMenu("&Help")
        
        # Get Started action
        get_started_action = QAction("&Get Started", self)
        self.help_menu.addAction(get_started_action)
        
        # Documentation action
        docs_action = QAction("&Documentation", self)
        self.help_menu.addAction(docs_action)
        
        self.help_menu.addSeparator()
        
        # About action
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.on_about)
        self.help_menu.addAction(about_action)
    
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
                
                print(f"Window position: {abs_x},{abs_y}")
                print(f"Window relative position: {self.config.settings.relative_position[0]:.2f},{self.config.settings.relative_position[1]:.2f}")
                print(f"Window size: {self.width()},{self.height()}")
        
        self.config.settings.is_maximized = self.isMaximized()
        self.config.settings.explorer_width = self.explorer_dock.width()
        self.config.settings.state = self.saveState()
        self.config.initial_dir = self.explorer.initial_dir
        
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
        font-size: {system_font_size}pt;
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