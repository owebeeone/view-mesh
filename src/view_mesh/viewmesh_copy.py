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
    QSplitter, QTabWidget, QToolBar, QMessageBox
)
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, QSize, QPoint, QSettings, 
    QEvent, QFile, QStandardPaths, Signal, QTimer
)
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QCloseEvent
)

@dataclass
class WindowSettings:
    """Store window position, size and state."""
    size: Tuple[int, int] = (1024, 768)
    position: Tuple[int, int] = (100, 100)
    is_maximized: bool = False
    explorer_width: int = 250
    state: Optional[bytes] = None
    screen_name: str = ""  # Store screen identifier
    screen_position: Tuple[int, int] = (0, 0)  # Store the screen's position in the virtual desktop
    
    @classmethod
    def from_settings(cls, settings: QSettings) -> 'WindowSettings':
        """Load window settings from QSettings."""
        result = cls()
        if settings.contains("window/size"):
            size = settings.value("window/size")
            result.size = (size.width(), size.height())
        if settings.contains("window/position"):
            pos = settings.value("window/position")
            result.position = (pos.x(), pos.y())
        if settings.contains("window/is_maximized"):
            result.is_maximized = settings.value("window/is_maximized", False, type=bool)
        if settings.contains("window/explorer_width"):
            result.explorer_width = settings.value("window/explorer_width", 250, type=int)
        if settings.contains("window/state"):
            result.state = settings.value("window/state")
        if settings.contains("window/screen_name"):
            result.screen_name = settings.value("window/screen_name", "")
        if settings.contains("window/screen_position"):
            pos = settings.value("window/screen_position")
            result.screen_position = (pos.x(), pos.y())
        return result
    
    def save_to_settings(self, settings: QSettings) -> None:
        """Save window settings to QSettings."""
        settings.setValue("window/size", QSize(*self.size))
        settings.setValue("window/position", QPoint(*self.position))
        settings.setValue("window/is_maximized", self.is_maximized)
        settings.setValue("window/explorer_width", self.explorer_width)
        settings.setValue("window/screen_name", self.screen_name)
        settings.setValue("window/screen_position", QPoint(*self.screen_position))
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


class ViewMeshApp(QMainWindow):
    """Main ViewMesh application window."""
    
    def __init__(self, config: AppConfig):
        super().__init__()
        self.config = config
        self.setWindowTitle(config.app_name)
        
        # Set up async event loop integration
        self.setup_async_loop()
        
        # Set up UI
        self.setup_ui()
        
        # Restore window state
        self.restore_window_state()
    
    def setup_ui(self):
        """Set up the main UI components."""
        # Central widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Main layout with splitter
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create splitter for sidebar and content
        self.splitter = QSplitter(Qt.Horizontal)
        
        # Explorer panel
        self.explorer = FileExplorerWidget(initial_dir=self.config.initial_dir)
        self.explorer_dock = QDockWidget("Explorer", self)
        self.explorer_dock.setObjectName("explorer_dock")
        self.explorer_dock.setWidget(self.explorer)
        self.explorer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer_dock)
        
        # Content area with tabs
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(True)
        self.tab_widget.setDocumentMode(True)
        
        # Add a placeholder tab for now
        placeholder = QWidget()
        placeholder_layout = QVBoxLayout(placeholder)
        placeholder_layout.addWidget(QWidget())
        self.tab_widget.addTab(placeholder, "Welcome")
        
        # Main content
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.addWidget(self.tab_widget)
        
        # Add to splitter
        self.splitter.addWidget(self.content_widget)
        self.main_layout.addWidget(self.splitter)
        
        # Menu bar
        self.setup_menu_bar()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Tool bar
        self.setup_tool_bar()
    
    def setup_menu_bar(self):
        """Set up the menu bar similar to VSCode."""
        self.menu_bar = self.menuBar()
        
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
        
        # View menu
        self.view_menu = self.menu_bar.addMenu("&View")
        
        # Toggle explorer action
        toggle_explorer_action = QAction("&Explorer", self)
        toggle_explorer_action.setCheckable(True)
        toggle_explorer_action.setChecked(True)
        toggle_explorer_action.triggered.connect(self.toggle_explorer)
        self.view_menu.addAction(toggle_explorer_action)
        
        # Help menu
        self.help_menu = self.menu_bar.addMenu("&Help")
        
        # About action
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.on_about)
        self.help_menu.addAction(about_action)
    
    def setup_tool_bar(self):
        """Set up the tool bar."""
        self.tool_bar = QToolBar("Main Toolbar")
        self.tool_bar.setObjectName("main_toolbar")
        self.tool_bar.setMovable(False)
        self.addToolBar(self.tool_bar)
        
        # Add some toolbar actions
        open_action = QAction("Open", self)
        open_action.triggered.connect(self.on_open_file)
        self.tool_bar.addAction(open_action)
        
        save_action = QAction("Save", self)
        save_action.triggered.connect(self.on_save)
        self.tool_bar.addAction(save_action)
    
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
        
        # Get the target screen geometry
        screen_geo = target_screen.geometry()
        
        # Restore window size 
        self.resize(QSize(*self.config.settings.size))
        
        # Calculate the window position properly for the current screen
        if self.config.settings.screen_name:
            # Get the saved position relative to the original screen
            saved_screen_pos = QPoint(*self.config.settings.screen_position)
            saved_pos = QPoint(*self.config.settings.position)
            
            # Calculate position relative to original screen
            relative_x = saved_pos.x() - saved_screen_pos.x()
            relative_y = saved_pos.y() - saved_screen_pos.y()
            
            # Apply this relative position to the current screen
            new_pos = QPoint(screen_geo.x() + relative_x, screen_geo.y() + relative_y)
            
            # Ensure the window is within screen bounds
            avail_geo = target_screen.availableGeometry()
            if new_pos.x() + self.width() > avail_geo.right():
                new_pos.setX(avail_geo.right() - self.width())
            if new_pos.y() + self.height() > avail_geo.bottom():
                new_pos.setY(avail_geo.bottom() - self.height())
            
            # Ensure minimum visibility
            if new_pos.x() < avail_geo.left():
                new_pos.setX(avail_geo.left())
            if new_pos.y() < avail_geo.top():
                new_pos.setY(avail_geo.top())
            
            self.move(new_pos)
        else:
            # Default positioning for first run
            center = target_screen.availableGeometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        
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
            screen_pos = current_screen.geometry().topLeft()
            self.config.settings.screen_position = (screen_pos.x(), screen_pos.y())
            
            # Save window position and size
            if not self.isMaximized():
                self.config.settings.size = (self.width(), self.height())
                self.config.settings.position = (self.x(), self.y())
        
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
        self.status_bar.showMessage("Creating new file...")
        # TODO: Implement new file functionality
    
    def on_open_file(self):
        """Handle open file action."""
        self.status_bar.showMessage("Opening file...")
        # TODO: Implement open file functionality
    
    def on_open_folder(self):
        """Handle open folder action."""
        self.status_bar.showMessage("Opening folder...")
        # TODO: Implement open folder functionality
    
    def on_save(self):
        """Handle save action."""
        self.status_bar.showMessage("Saving file...")
        # TODO: Implement save functionality
    
    def on_save_as(self):
        """Handle save as action."""
        self.status_bar.showMessage("Saving file as...")
        # TODO: Implement save as functionality
    
    def toggle_explorer(self, checked: bool):
        """Toggle the explorer panel."""
        self.explorer_dock.setVisible(checked)
    
    def on_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, 
            f"About {self.config.app_name}",
            f"{self.config.app_name} v0.1.0\n\n"
            f"A PySide6 application for viewing mesh files.\n\n"
            f"© {self.config.org_name}"
        )

async def async_main():
    """Main entry point for the application (async version)."""
    # Create application
    app = QApplication(sys.argv)
    
    # Load configuration
    config = AppConfig.load()
    
    # Create main window
    window = ViewMeshApp(config)
    window.show()
    
    # Run the Qt event loop
    exit_code = app.exec()
    
    # Return exit code
    return exit_code

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
    
    # Create main window
    window = ViewMeshApp(config)
    window.show()
    
    # Run the Qt event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 