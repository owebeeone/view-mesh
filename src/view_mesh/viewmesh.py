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
    QHBoxLayout, QPushButton, QFrame, QTextEdit, QScrollArea, QFileDialog
)
from PySide6.QtCore import (
    Qt, QDir, QModelIndex, QSize, QPoint, QSettings, 
    QEvent, QFile, QStandardPaths, Signal, QTimer, QRect, QObject
)
from PySide6.QtGui import (
    QIcon, QAction, QKeySequence, QCloseEvent, QFont, 
    QMouseEvent, QColor, QPalette, QResizeEvent, QPainter, QCursor, QFontMetrics, 
    QPen, QPaintEvent, QPixmap
)
from abc import ABC, abstractmethod

# Define an Enum for handle positions
import enum

DEBUG_LOGS=False

class WindowGeometryManager:
    """Manages saving and restoring window geometry, handling multi-screen setups."""
    def __init__(self, window: QMainWindow, settings_object: Any, main_app_window_ref: Optional[QMainWindow] = None):
        self.window = window
        self.settings = settings_object # This will be an instance of WindowSettings or InspectorWindowSettings
        self.main_app_window_ref = main_app_window_ref if main_app_window_ref else window # For inspector, main_app_window is different

    def restore_geometry(self):
        """Restores the window's size and position based on stored settings."""
        self.window.resize(QSize(*self.settings.size))

        screens = QApplication.screens()
        target_screen = None

        # 1. Try to find the saved screen by name
        if self.settings.screen_name:
            for screen in screens:
                if screen.name() == self.settings.screen_name:
                    target_screen = screen
                    break
        
        # 2. If not found, try to find a screen that contains the saved absolute position
        if not target_screen and self.settings.position != (0,0): # (0,0) can be an uninitialized default
            # Create a QRect of minimal size at the saved position to check containment
            saved_point_rect = QRect(self.settings.position[0], self.settings.position[1], 1, 1)
            for screen in screens:
                if screen.geometry().intersects(saved_point_rect): # Check if point is within screen
                    target_screen = screen
                    break
        
        # 3. Fallback: use the main application window's screen (if this isn't the main app window itself)
        #    or the primary screen.
        if not target_screen:
            if self.main_app_window_ref is not self.window and self.main_app_window_ref and self.main_app_window_ref.isVisible():
                 target_screen = self.main_app_window_ref.screen()
            else: # For main window itself or if main_app_window_ref is not useful
                target_screen = QApplication.primaryScreen()

        if not target_screen: # Should be extremely rare
            print(f"WindowGeometryManager ({self.window.windowTitle()}): Critical - No target screen found. Using primary screen.")
            target_screen = QApplication.primaryScreen()
            if not target_screen: # Even rarer, e.g. no screens connected
                 print(f"WindowGeometryManager ({self.window.windowTitle()}): Critical - No primary screen available.")
                 self.window.move(self.settings.position[0], self.settings.position[1]) # Basic move
                 return


        screen_geo = target_screen.geometry()
        avail_geo = target_screen.availableGeometry()

        pos_x, pos_y = 0, 0
        
        # Prioritize relative positioning if screen context was meaningfully saved
        use_relative = bool(self.settings.screen_name and self.settings.screen_geometry != (0,0,0,0) and hasattr(self.settings, 'relative_position'))

        if use_relative:
            rel_x, rel_y = self.settings.relative_position
            pos_x = avail_geo.x() + int(rel_x * avail_geo.width())
            pos_y = avail_geo.y() + int(rel_y * avail_geo.height())
        else:
            pos_x, pos_y = self.settings.position

        # Boundary checks: Ensure the window is placed visibly on the target screen
        # Adjust so at least a small part of the window is visible if it's off-screen.
        # A common strategy is to ensure its top-left is within screen bounds,
        # and then adjust if bottom-right goes out.

        # Ensure top-left is not way off screen
        pos_x = max(avail_geo.x() - self.window.width() + 20, min(pos_x, avail_geo.x() + avail_geo.width() - 20))
        pos_y = max(avail_geo.y() - self.window.height() + 20, min(pos_y, avail_geo.y() + avail_geo.height() - 20))

        # Ensure it's not completely outside the available geometry
        pos_x = max(avail_geo.x(), min(pos_x, avail_geo.x() + avail_geo.width() - self.window.width()))
        pos_y = max(avail_geo.y(), min(pos_y, avail_geo.y() + avail_geo.height() - self.window.height()))
        
        self.window.move(pos_x, pos_y)

    def save_geometry(self):
        """Saves the window's current size, position, and screen information to settings."""
        if not self.window.isVisible() and not self.window.isMinimized(): # Don't save if hidden unless minimized
            # If minimized, geometry is still valid, but if just hidden, it might be (0,0) or irrelevant
            if not self.window.isMinimized():
                 # print(f"WindowGeometryManager ({self.window.windowTitle()}): Window not visible or minimized, not saving geometry.")
                return

        # For minimized windows, self.pos() and self.size() might return unhelpful values
        # QWidget.normalGeometry() gives the geometry it would have if shown normally.
        current_geometry = self.window.normalGeometry() if self.window.isMinimized() else self.window.geometry()

        self.settings.size = (current_geometry.width(), current_geometry.height())
        self.settings.position = (current_geometry.x(), current_geometry.y())

        current_screen = QApplication.screenAt(current_geometry.center()) # More robust way to get screen for a geometry
        if not current_screen: # Fallback if center is somehow off-screen
            current_screen = self.window.screen()


        if current_screen:
            self.settings.screen_name = current_screen.name()
            screen_geo_actual = current_screen.geometry()
            avail_geo = current_screen.availableGeometry()
            
            self.settings.screen_geometry = (
                screen_geo_actual.x(), screen_geo_actual.y(), 
                screen_geo_actual.width(), screen_geo_actual.height()
            )

            if hasattr(self.settings, 'relative_position'):
                if avail_geo.width() > 0 and avail_geo.height() > 0:
                    # Calculate relative to the *actual position* which might be from normalGeometry()
                    rel_x = float(current_geometry.x() - avail_geo.x()) / float(avail_geo.width())
                    rel_y = float(current_geometry.y() - avail_geo.y()) / float(avail_geo.height())
                    self.settings.relative_position = (max(0.0, min(1.0, rel_x)), max(0.0, min(1.0, rel_y)))
                else: # Should not happen with a valid screen
                    self.settings.relative_position = (0.1, 0.1) # Fallback
        else:
            # Clear screen-specifics if no screen found (highly unlikely for a visible/minimized window)
            self.settings.screen_name = ""
            self.settings.screen_geometry = (0,0,0,0)
            if hasattr(self.settings, 'relative_position'):
                self.settings.relative_position = (0.1, 0.1) # Fallback


class HandlePosition(enum.Enum):
    TOP_LEFT = 0
    TOP = 1
    TOP_RIGHT = 2
    LEFT = 3
    RIGHT = 4
    BOTTOM_LEFT = 5
    BOTTOM = 6
    BOTTOM_RIGHT = 7

class EdgeResizeHandle(QWidget):
    def __init__(self, parent_window: QMainWindow, position: HandlePosition, thickness: int = 5):
        super().__init__(parent_window) # Parent is the main window
        self.parent_window = parent_window
        self.position = position
        self.thickness = thickness
        self.setMouseTracking(True)
        # self.setAttribute(Qt.WA_StyledBackground, True) # May not be needed with direct stylesheet

        # For debugging, give it a color via stylesheet:
        # debug_colors = {
        #     HandlePosition.TOP_LEFT: "red",
        #     HandlePosition.TOP: "blue",
        #     HandlePosition.TOP_RIGHT: "magenta",
        #     HandlePosition.LEFT: "green",
        #     HandlePosition.RIGHT: "cyan",
        #     HandlePosition.BOTTOM_LEFT: "yellow",
        #     HandlePosition.BOTTOM: "orange",
        #     HandlePosition.BOTTOM_RIGHT: "pink",
        # }
        # color_name = debug_colors.get(self.position, "gray")
        # self.setStyleSheet(f"background-color: {color_name};")
        # self.setStyleSheet("background-color: red;") # Force all to red for this test - REMOVED FOR INVISIBILITY
        
        # self.setAutoFillBackground(True) # Not needed when using stylesheet for background
        # self.setPalette(palette) # Palette method removed
        
        # Ensure a minimum visible size for debugging, even if thickness is small
        # self.setMinimumSize(max(1, self.thickness), max(1, self.thickness)) # Not strictly needed if invisible

        self.is_dragging = False
        self.drag_start_pos = None
        self.parent_window_start_geometry = None

        self.update_geometry() # Call after setting palette, ensure it has a size before show
        # print(f"[DEBUG EdgeHandle Init] Pos: {self.position}, Initial Geometry: {self.geometry()}")

    def update_geometry(self):
        parent_rect = self.parent_window.rect()
        x, y, w, h = 0, 0, 0, 0
        th = self.thickness # Alias for thickness

        if self.position == HandlePosition.TOP_LEFT:
            x, y, w, h = 0, 0, th, th
        elif self.position == HandlePosition.TOP:
            # Starts after top-left corner, ends before top-right corner
            x, y, w, h = th, 0, parent_rect.width() - (2 * th), th
        elif self.position == HandlePosition.TOP_RIGHT:
            x, y, w, h = parent_rect.width() - th, 0, th, th
        elif self.position == HandlePosition.LEFT:
            # Starts after top-left corner, ends before bottom-left corner
            x, y, w, h = 0, th, th, parent_rect.height() - (2 * th)
        elif self.position == HandlePosition.RIGHT:
            # Starts after top-right corner, ends before bottom-right corner
            x, y, w, h = parent_rect.width() - th, th, th, parent_rect.height() - (2 * th)
        elif self.position == HandlePosition.BOTTOM_LEFT:
            x, y, w, h = 0, parent_rect.height() - th, th, th
        elif self.position == HandlePosition.BOTTOM:
            # Starts after bottom-left corner, ends before bottom-right corner
            x, y, w, h = th, parent_rect.height() - th, parent_rect.width() - (2 * th), th
        elif self.position == HandlePosition.BOTTOM_RIGHT:
            x, y, w, h = parent_rect.width() - th, parent_rect.height() - th, th, th
        
        # Ensure width and height are not negative if window is too small
        if w < 0: w = 0
        if h < 0: h = 0

        if DEBUG_LOGS: print(f"[DEBUG update_geometry] Pos: {self.position}, Geom: x={x},y={y},w={w},h={h}, ParentRect: {parent_rect}") # DEBUG
        self.setGeometry(x, y, w, h)
        self.raise_() # Ensure it's on top

    def enterEvent(self, event: QEvent):
        cursor_shape = Qt.ArrowCursor
        if self.position in [HandlePosition.TOP_LEFT, HandlePosition.BOTTOM_RIGHT]:
            cursor_shape = Qt.SizeFDiagCursor
        elif self.position in [HandlePosition.TOP_RIGHT, HandlePosition.BOTTOM_LEFT]:
            cursor_shape = Qt.SizeBDiagCursor
        elif self.position in [HandlePosition.TOP, HandlePosition.BOTTOM]:
            cursor_shape = Qt.SizeVerCursor
        elif self.position in [HandlePosition.LEFT, HandlePosition.RIGHT]:
            cursor_shape = Qt.SizeHorCursor
        
        self.parent_window.setCursor(cursor_shape)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent):
        self.parent_window.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    # We will need mousePress, mouseMove, mouseRelease here later for actual resizing.
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self.parent_window.isMaximized():
            self.is_dragging = True
            self.drag_start_pos = event.globalPosition().toPoint()
            self.parent_window_start_geometry = self.parent_window.geometry() # QRect
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging and event.buttons() & Qt.LeftButton and self.parent_window_start_geometry:
            current_global_pos = event.globalPosition().toPoint()
            delta = current_global_pos - self.drag_start_pos

            new_geometry = QRect(self.parent_window_start_geometry) # Make a copy

            min_width = self.parent_window.minimumSizeHint().width()
            min_height = self.parent_window.minimumSizeHint().height()
            # Fallback if minimumSizeHint is not good (e.g. (0,0) or (-1,-1))
            if min_width <=0: min_width = 100 
            if min_height <=0: min_height = 100

            # Adjust geometry based on handle position
            if self.position == HandlePosition.LEFT:
                new_width = self.parent_window_start_geometry.width() - delta.x()
                if new_width >= min_width:
                    new_geometry.setX(self.parent_window_start_geometry.x() + delta.x())
                    new_geometry.setWidth(new_width)
            elif self.position == HandlePosition.RIGHT:
                new_geometry.setWidth(self.parent_window_start_geometry.width() + delta.x())
            elif self.position == HandlePosition.TOP:
                new_height = self.parent_window_start_geometry.height() - delta.y()
                if new_height >= min_height:
                    new_geometry.setY(self.parent_window_start_geometry.y() + delta.y())
                    new_geometry.setHeight(new_height)
            elif self.position == HandlePosition.BOTTOM:
                new_geometry.setHeight(self.parent_window_start_geometry.height() + delta.y())
            elif self.position == HandlePosition.TOP_LEFT:
                new_width = self.parent_window_start_geometry.width() - delta.x()
                new_height = self.parent_window_start_geometry.height() - delta.y()
                if new_width >= min_width:
                    new_geometry.setX(self.parent_window_start_geometry.x() + delta.x())
                    new_geometry.setWidth(new_width)
                if new_height >= min_height:
                    new_geometry.setY(self.parent_window_start_geometry.y() + delta.y())
                    new_geometry.setHeight(new_height)
            elif self.position == HandlePosition.TOP_RIGHT:
                new_height = self.parent_window_start_geometry.height() - delta.y()
                new_geometry.setWidth(self.parent_window_start_geometry.width() + delta.x())
                if new_height >= min_height:
                    new_geometry.setY(self.parent_window_start_geometry.y() + delta.y())
                    new_geometry.setHeight(new_height)
            elif self.position == HandlePosition.BOTTOM_LEFT:
                new_width = self.parent_window_start_geometry.width() - delta.x()
                new_geometry.setHeight(self.parent_window_start_geometry.height() + delta.y())
                if new_width >= min_width:
                    new_geometry.setX(self.parent_window_start_geometry.x() + delta.x())
                    new_geometry.setWidth(new_width)
            elif self.position == HandlePosition.BOTTOM_RIGHT:
                new_geometry.setWidth(self.parent_window_start_geometry.width() + delta.x())
                new_geometry.setHeight(self.parent_window_start_geometry.height() + delta.y())

            # Enforce minimum size on the final calculated geometry
            if new_geometry.width() < min_width: new_geometry.setWidth(min_width)
            if new_geometry.height() < min_height: new_geometry.setHeight(min_height)
            
            self.parent_window.setGeometry(new_geometry)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.is_dragging:
            self.is_dragging = False
            self.drag_start_pos = None
            self.parent_window_start_geometry = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

class InteractiveHierarchyLabel(QLabel):
    """A QLabel that emits signals on hover and click, and stores a target widget."""
    hover_enter = Signal(QWidget)  # Signal to emit when mouse enters, passes target widget
    hover_leave = Signal(QWidget)  # Signal to emit when mouse leaves, passes target widget
    clicked = Signal(QWidget)      # Signal to emit when clicked, passes target widget

    def __init__(self, target_widget: QWidget, text: str, parent=None):
        super().__init__(text, parent)
        if isinstance(target_widget, QMenu):
            action = target_widget.menuAction()
            self.target_widget = target_widget
        else:
            self.target_widget = target_widget
        self.setMouseTracking(True) 
        self.setStyleSheet("color: #cccccc; background-color: transparent; padding: 1px;")

    def enterEvent(self, event: QEvent):
        if DEBUG_LOGS: print(f"[Label Hover Enter] Target: {self.target_widget.metaObject().className()} '{self.target_widget.objectName()}'") # Debug ACTIVE
        self.hover_enter.emit(self.target_widget)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent):
        if DEBUG_LOGS: print(f"[Label Hover Leave] Target: {self.target_widget.metaObject().className()} '{self.target_widget.objectName()}'") # Debug ACTIVE
        self.hover_leave.emit(self.target_widget)
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            if DEBUG_LOGS: print(f"[Label Clicked] Target: {self.target_widget.metaObject().className()} '{self.target_widget.objectName()}'") # Debug ACTIVE
            self.clicked.emit(self.target_widget)
        super().mousePressEvent(event)

class HighlightOverlay(QWidget):
    """A transparent widget to draw a highlight border around a target widget."""
    def __init__(self, parent_to_overlay: QMainWindow):
        super().__init__(parent_to_overlay)
        self.parent_to_overlay = parent_to_overlay
        self.target_rect = QRect()  
        self.is_sticky = False
        self.is_highlighting = False

        self.setAttribute(Qt.WA_TransparentForMouseEvents) 
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Change window flags: Remove Qt.Tool and Qt.WindowStaysOnTopHint
        # Make it a simple frameless widget. Qt.SubWindow might also be an option
        # but a direct child with FramelessWindowHint should work.
        self.setWindowFlags(Qt.FramelessWindowHint)
        # self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow) # Alternative if needed
        
        # Geometry is now relative to parent, so set it to cover parent
        self.setGeometry(parent_to_overlay.rect()) 
        self.hide() 
        # Silencing debug log from __init__ as requested by user previously
        # print("[HighlightOverlay __init__] Initialized. Geometry:", self.geometry())

    def update_geometry(self):
        """Ensure overlay covers and aligns with the parent window."""
        if self.parent_to_overlay:
            # Now a child widget, geometry is relative to parent's content rect.
            self.setGeometry(self.parent_to_overlay.rect())
            self.raise_() # Ensure it's on top of other children in the main window
            # Silencing debug log as requested
            # print(f"[HighlightOverlay update_geometry] Updated. Relative Geometry set to: {self.geometry()}")

    def highlight_widget(self, target_widget: Optional[QWidget], sticky: bool = False):
        widget_class_name = target_widget.metaObject().className() if target_widget else "None"
        widget_object_name = target_widget.objectName() if target_widget else "N/A"
        widget_is_visible = target_widget.isVisible() if target_widget else False

        if DEBUG_LOGS: print(f"[HighlightOverlay highlight_widget] Called for: Class='{widget_class_name}', Name='{widget_object_name}', IsVisible: {widget_is_visible}") # Debug ACTIVE

        proceed_with_highlight = target_widget and widget_is_visible

        if proceed_with_highlight: 
            global_top_left = target_widget.mapToGlobal(QPoint(0, 0))
            
            self.target_rect = QRect(self.parent_to_overlay.mapFromGlobal(global_top_left),
                                     target_widget.size())
            
            # Enhanced Debugging for coordinates
            parent_global_tl = self.parent_to_overlay.mapToGlobal(QPoint(0,0))
            overlay_global_tl = self.mapToGlobal(QPoint(0,0)) # Overlay's own global top-left

            # print(f"    TargetWidget '{widget_object_name}' ({widget_class_name}):")
            # print(f"        Global Top-Left: {global_top_left}")
            # print(f"        Size: {target_widget.size()}")
            # print(f"    ParentToOverlay (QMainWindow '{self.parent_to_overlay.objectName()}'):")
            # print(f"        Global Top-Left: {parent_global_tl}")
            # print(f"    HighlightOverlay (self):")
            # print(f"        Global Top-Left: {overlay_global_tl}") # Should match parent_to_overlay's global top-left
            # print(f"        Current Geometry (should match parent): {self.geometry()}")
            # print(f"    Calculated TargetRect (local to overlay): {self.target_rect}")

            self.update_geometry() # Ensure overlay is positioned correctly relative to parent
            self.is_sticky = sticky
            self.is_highlighting = True
            self.update()  
            self.show()
            self.raise_() 
            if DEBUG_LOGS: print(f"[HighlightOverlay highlight_widget] Highlighting. TargetRect: {self.target_rect}, Sticky: {sticky}, IsVisibleOnScreen: {self.isVisible()}, Final Overlay Geom: {self.geometry()}") # Debug ACTIVE
        else:
            if DEBUG_LOGS: print(f"[HighlightOverlay highlight_widget] Target None or not visible (Class='{widget_class_name}', Name='{widget_object_name}', IsVisible: {widget_is_visible}), clearing.") # Debug ACTIVE
            self.clear_highlight()

    def clear_highlight(self, force_clear_sticky: bool = False):
        if DEBUG_LOGS: print(f"[HighlightOverlay clear_highlight] Called. IsSticky: {self.is_sticky}, ForceClear: {force_clear_sticky}") # Debug ACTIVE
        if self.is_sticky and not force_clear_sticky:
            if DEBUG_LOGS: print("[HighlightOverlay clear_highlight] Preserving sticky highlight.") # Debug ACTIVE
            return 
        
        self.is_highlighting = False
        self.is_sticky = False 
        self.target_rect = QRect()
        self.update()  
        self.hide()
        if DEBUG_LOGS: print("[HighlightOverlay clear_highlight] Cleared and hidden.") # Debug ACTIVE

    def paintEvent(self, event: QPaintEvent):
        # print(f"[HighlightOverlay paintEvent] Called. IsHighlighting: {self.is_highlighting}, TargetRect: {self.target_rect}") # Debug - can be noisy
        if not self.is_highlighting or self.target_rect.isNull():
            if DEBUG_LOGS: print("[HighlightOverlay paintEvent] Not highlighting or rect is null.") # Debug
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        border_color = QColor(255, 0, 0, 200) 
        if self.is_sticky:
            border_color = QColor(200, 0, 0, 220) 
        
        pen_width = 2
        pen = QPen(border_color, pen_width)
        pen.setJoinStyle(Qt.MiterJoin) 
        painter.setPen(pen)
        
        draw_rect = self.target_rect.adjusted(pen_width // 2, pen_width // 2, -pen_width // 2, -pen_width // 2)
        painter.drawRect(draw_rect)
        if DEBUG_LOGS: print(f"[HighlightOverlay paintEvent] Drawing rect {draw_rect} with color {border_color.name()}") # Debug ACTIVE
        super().paintEvent(event)

class DrawableScreenshotLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.base_pixmap = QPixmap() # The original screenshot
        self.drawing_paths = [] # List of QPainterPath objects for user drawings
        self.current_path = None # The path currently being drawn
        self.drawing_pen = QPen(QColor("red"), 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        self.is_drawing = False

        self.setMinimumSize(200, 150) # Ensure it has a size
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft) # Align pixmap to top-left for drawing

    def setPixmap(self, pixmap: QPixmap):
        self.base_pixmap = pixmap.copy() if pixmap else QPixmap()
        self.drawing_paths = [] # Clear previous drawings when new pixmap is set
        self.update() # Trigger a repaint
        super().setPixmap(self.base_pixmap) # Show the base pixmap

    def clearDrawings(self):
        self.drawing_paths = []
        self.update()

    def getPixmapWithDrawings(self) -> QPixmap:
        if self.base_pixmap.isNull():
            return QPixmap() # Return empty if no base

        # Create a new pixmap to draw on, matching the base pixmap's size
        output_pixmap = self.base_pixmap.copy()
        painter = QPainter(output_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw existing paths
        painter.setPen(self.drawing_pen)
        for path in self.drawing_paths:
            painter.drawPath(path)
        
        painter.end()
        return output_pixmap

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and not self.base_pixmap.isNull():
            self.is_drawing = True
            # Use QPainterPath for smooth lines
            from PySide6.QtGui import QPainterPath # Local import for clarity
            self.current_path = QPainterPath()
            self.current_path.moveTo(event.position().toPoint())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_drawing and self.current_path:
            self.current_path.lineTo(event.position().toPoint())
            self.update() # Repaint to show live drawing
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self.is_drawing and self.current_path:
            self.is_drawing = False
            if not self.current_path.isEmpty():
                self.drawing_paths.append(self.current_path)
            self.current_path = None
            self.update() # Final repaint of the completed path
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event) # Draw the base pixmap (already set by QLabel.setPixmap)
        
        if not self.base_pixmap.isNull():
            painter = QPainter(self) # Paint on top of the QLabel itself
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(self.drawing_pen)

            # Draw completed paths
            for path in self.drawing_paths:
                painter.drawPath(path)
            
            # Draw the current path being drawn (live preview)
            if self.current_path and not self.current_path.isEmpty():
                painter.drawPath(self.current_path)

class InspectorWindow(QMainWindow):
    def __init__(self, main_app_window: QMainWindow, parent=None):
        super().__init__(parent)
        self.main_app_window = main_app_window
        self.config = main_app_window.config
        self.geometry_manager = WindowGeometryManager(self, self.config.inspector_settings, self.main_app_window)
        self.highlight_overlay = HighlightOverlay(self.main_app_window)
        self.sticky_highlighted_widget: Optional[QWidget] = None

        self.setWindowTitle("ViewMesh Inspector")
        
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        self.hierarchy_tab = QWidget()
        self.hierarchy_layout = QVBoxLayout(self.hierarchy_tab)
        
        self.hierarchy_button_layout = QHBoxLayout()
        self.refresh_xml_button = QPushButton("Refresh XML Hierarchy")
        self.refresh_xml_button.clicked.connect(self._refresh_xml_hierarchy_view)
        self.hierarchy_button_layout.addWidget(self.refresh_xml_button)

        self.show_visual_tree_button = QPushButton("Show Visual Tree")
        self.show_visual_tree_button.clicked.connect(self._refresh_visual_tree_view)
        self.hierarchy_button_layout.addWidget(self.show_visual_tree_button)
        self.hierarchy_layout.addLayout(self.hierarchy_button_layout)
        
        self.xml_hierarchy_text_edit = QTextEdit()
        self.xml_hierarchy_text_edit.setReadOnly(True)
        self.xml_hierarchy_text_edit.setFontFamily("monospace")
        self.hierarchy_layout.addWidget(self.xml_hierarchy_text_edit)
        
        self.visual_tree_scroll_area = QScrollArea()
        self.visual_tree_scroll_area.setWidgetResizable(True)
        self.visual_tree_scroll_area.setMouseTracking(True) # Enable for scroll area viewport
        if self.visual_tree_scroll_area.viewport():
            self.visual_tree_scroll_area.viewport().setMouseTracking(True)

        self.visual_tree_content_widget = QWidget() 
        self.visual_tree_content_widget.setStyleSheet("background-color: #252526;") 
        self.visual_tree_content_widget.setMouseTracking(True) # Enable for content widget
        self.visual_tree_layout = QVBoxLayout(self.visual_tree_content_widget)
        self.visual_tree_layout.setAlignment(Qt.AlignTop)
        self.visual_tree_content_widget.setLayout(self.visual_tree_layout)
        self.visual_tree_scroll_area.setWidget(self.visual_tree_content_widget)
        self.hierarchy_layout.addWidget(self.visual_tree_scroll_area)
        self.visual_tree_scroll_area.setVisible(False)
        
        self.tab_widget.addTab(self.hierarchy_tab, "Hierarchy")

        # --- Console Tab ---
        self.console_tab = QWidget()
        self.console_layout = QVBoxLayout(self.console_tab)
        self.console_layout.addWidget(QLabel("Application Console Output (Placeholder)")) # Placeholder
        self.tab_widget.addTab(self.console_tab, "Console")

        # --- Screenshot Tab ---
        self.screenshot_tab = QWidget()
        self.screenshot_tab_layout = QVBoxLayout(self.screenshot_tab)
        
        self.screenshot_button_layout = QHBoxLayout() # Layout for buttons

        self.take_screenshot_button = QPushButton("Take Screenshot")
        self.take_screenshot_button.clicked.connect(self._take_screenshot)
        self.screenshot_button_layout.addWidget(self.take_screenshot_button)

        self.save_screenshot_button = QPushButton("Save Screenshot")
        self.save_screenshot_button.clicked.connect(self._save_screenshot)
        self.screenshot_button_layout.addWidget(self.save_screenshot_button)
        self.save_screenshot_button.setEnabled(False) # Disabled until a screenshot is taken

        self.clear_drawings_button = QPushButton("Clear Drawings")
        self.clear_drawings_button.clicked.connect(self._clear_drawings_on_label)
        self.screenshot_button_layout.addWidget(self.clear_drawings_button)
        self.clear_drawings_button.setEnabled(False) # Disabled until a screenshot is taken/drawn on

        self.screenshot_tab_layout.addLayout(self.screenshot_button_layout)
        
        self.screenshot_display_label = DrawableScreenshotLabel()
        self.screenshot_display_label.setAlignment(Qt.AlignCenter)
        self.screenshot_display_label.setMinimumSize(200, 150) 
        self.screenshot_display_label.setStyleSheet("QLabel { border: 1px solid #474747; background-color: #2d2d2d; }")
        
        self.screenshot_scroll_area = QScrollArea()
        self.screenshot_scroll_area.setWidgetResizable(True)
        self.screenshot_scroll_area.setWidget(self.screenshot_display_label)
        self.screenshot_tab_layout.addWidget(self.screenshot_scroll_area)

        self.tab_widget.addTab(self.screenshot_tab, "Screenshot")

        # Apply overall dark theme to InspectorWindow and its main components
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; color: #cccccc; }
            QTabWidget::pane { border: 1px solid #474747; background-color: #1e1e1e; }
            QTabBar::tab { background-color: #2d2d2d; color: #cccccc; border: 1px solid #474747; padding: 6px 12px; margin-right: 1px; }
            QTabBar::tab:selected { background-color: #1e1e1e; border-bottom-color: #1e1e1e; }
            QLabel { background-color: transparent; color: #cccccc; } /* Default for labels */
            QTextEdit { background-color: #252526; color: #cccccc; border: 1px solid #474747; }
            QPushButton { background-color: #3c3c3c; color: #cccccc; border: 1px solid #555555; padding: 5px; }
            QPushButton:hover { background-color: #4c4c4c; }
            QScrollArea { border: none; background-color: #252526; } /* Style scroll area itself */
        """)

    def _refresh_xml_hierarchy_view(self):
        self.xml_hierarchy_text_edit.setVisible(True)
        self.visual_tree_scroll_area.setVisible(False)
        xml_data = self._generate_widget_hierarchy_xml()
        self.xml_hierarchy_text_edit.setPlainText(xml_data)

    def _refresh_visual_tree_view(self):
        self.xml_hierarchy_text_edit.setVisible(False)
        self.visual_tree_scroll_area.setVisible(True)
        
        # Clear previous visual tree content
        while self.visual_tree_layout.count():
            child = self.visual_tree_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not self.main_app_window:
            # Add a label indicating error or unavailability
            error_label = QLabel("<Main window not available>")
            error_label.setStyleSheet("color: #ffcc00;") # Warning color
            self.visual_tree_layout.addWidget(error_label)
            return

        # Start building the visual tree UI from the main_app_window
        # prefix_parts will store the "│   " or "    " for each indent level
        self._build_visual_widget_ui(self.main_app_window, 0, self.visual_tree_layout, []) 

    def _build_visual_widget_ui(self, widget: QWidget, indent_level: int, parent_layout: QVBoxLayout, prefix_parts: list[str]):
        class_name = widget.metaObject().className()
        object_name = widget.objectName() or ""
        geom = widget.geometry()
        
        # Construct text for the label, including geometry and specific attributes
        attributes = []
        if object_name:
            attributes.append(f"name=\"{object_name.replace('\"', '&quot;')}\"")
        attributes.append(f"geom=({geom.x()},{geom.y()},{geom.width()},{geom.height()})")
        
        if hasattr(widget, 'text') and callable(widget.text):
            try:
                widget_text = widget.text()
                if widget_text and isinstance(widget_text, str) and "\n" not in widget_text[:20]: # Simple, short text
                    attributes.append(f"text=\"{widget_text.replace('\"', '&quot;')[:30]}\"") # Limit length
            except Exception: pass
        
        attr_string = " ".join(attributes)
        current_prefix = "".join(prefix_parts)
        label_text_content = f"{class_name} [{attr_string}]"

        # Create and add the interactive label
        if object_name == "title_bar_menu_bar_widget":
            if DEBUG_LOGS: print(f"[DEBUG _build_visual_widget_ui] Creating InteractiveHierarchyLabel for QMenuBar: {label_text_content}")
            if DEBUG_LOGS: print(f"    isVisible: {widget.isVisible()}, isVisibleTo_parent: {widget.isVisibleTo(self.main_app_window)}")
            if DEBUG_LOGS: print(f"    geometry: {widget.geometry()}, mapToGlobal(0,0): {widget.mapToGlobal(QPoint(0,0))}")

        hierarchy_label = InteractiveHierarchyLabel(widget, f"{current_prefix}{label_text_content}")
        hierarchy_label.hover_enter.connect(self._on_hierarchy_label_hover_enter)
        hierarchy_label.hover_leave.connect(self._on_hierarchy_label_hover_leave)
        hierarchy_label.clicked.connect(self._on_hierarchy_label_clicked)
        parent_layout.addWidget(hierarchy_label)

        # Discover children
        children_qwidgets = []
        potential_children = widget.children()
        if potential_children:
            for child_obj in potential_children:
                if isinstance(child_obj, QWidget):
                    children_qwidgets.append(child_obj)
                elif isinstance(child_obj, QAction):
                    #children_qwidgets.append()
                    action: QAction = child_obj
                    menu = action.menu()
                    if menu:
                        menu_parent = menu.parent()
                    else:
                        menu_parent = None
                    title = action.text()
                    print(f"    Skipping QAction child: {type(child_obj)} parent: {type(widget)} menu: {type(menu)} menu_parent: {type(menu_parent)} title: {title}") 
                else:
                    print(f"    Skipping non-QWidget child: {type(child_obj)}") 

        # Recursively process children
        num_children = len(children_qwidgets)
        for i, child_widget in enumerate(children_qwidgets):
            if child_widget == self or (hasattr(child_widget, 'parent_window') and child_widget.parent_window == self):
                continue
            if isinstance(child_widget, EdgeResizeHandle):
                continue 

            is_last_child = (i == num_children - 1)
            
            new_prefix_parts = prefix_parts.copy()
            if indent_level > 0: # For children of the root, their prefix is based on their parent's state
                 # This logic might need refinement if prefix_parts wasn't managed correctly by caller for root
                 # For simplicity, let's adjust the last element of prefix_parts before passing down
                 pass # The logic for updating prefix_parts for drawing lines will be more complex
           
            # Simplified prefix for now, actual line drawing characters need more state
            # For the text label, we just add standard indent for now
            # The visual lines would typically be drawn *by* the label or a container
           
            # Determine the correct prefix characters for text representation
            # This is a simplified text representation of tree lines
            line_prefix = "    " * indent_level
            if indent_level > 0: # Not for root
                if is_last_child:
                    line_prefix = ("    " * (indent_level -1)) + "└── " 
                else:
                    line_prefix = ("    " * (indent_level -1)) + "├── " 
           
            # Re-create the label with the tree structure characters
            # This is a bit redundant with current structure; ideally, the label itself handles this.
            # For now, we reconstruct the text for the label being added to the layout.
            # This is incorrect: hierarchy_label was already added. We need to set its text again or create new.
            # Let's simplify: the label text will be set once with current_prefix, which needs to be built correctly.

            # Correct approach: build the full prefix string for *this* level before creating the label
            # The `prefix_parts` passed down should reflect parent connections
           
            # Let's defer complex line drawing logic. For now, use simple spacing for indentation in text label.
            # The earlier label creation already uses `current_prefix` which is `"    " * indent_level` effectively
            # We need to pass child_prefix_parts to the recursive call.

            child_prefix_parts = prefix_parts.copy()
            if is_last_child:
                child_prefix_parts.append("    ")
            else:
                child_prefix_parts.append("│   ") # Vertical line and space

            # The label for the current widget should use the current prefix_parts correctly
            # Let's refine the label text creation for the current widget
            current_branch_char = ""
            if indent_level > 0: # Not for root
                if prefix_parts: # Safety check
                    # Determine current widget's branch based on its parent's prefix part that corresponds to this level
                    # This is tricky because prefix_parts is for *children*. We need to know if *current* is last.
                    # This requires knowing if the widget itself is the last child of ITS parent.
                    # This information needs to be passed into _build_visual_widget_ui. Let's add `is_parent_last_child`
                    # Or simpler: `is_current_widget_last_child`
                    pass # Deferring complex line drawing to focus on hover

            # Update the label that was already created, or create it with proper prefix
            # For now, the previous label creation is what stands. Complex lines are for later. 
            # The text in the InteractiveHierarchyLabel will just use space indentation from `current_prefix`
            # For the recursive call, we manage `prefix_parts` to guide children.

            self._build_visual_widget_ui(child_widget, indent_level + 1, parent_layout, child_prefix_parts)

    def _generate_widget_hierarchy_xml(self) -> str:
        if not self.main_app_window:
            return "<error>Main application window not available.</error>"
        
        # Start recursion from the main_app_window itself
        return self._build_widget_xml_string(self.main_app_window, 0)

    def _build_widget_xml_string(self, widget: QWidget, indent_level: int) -> str:
        indent = "  " * indent_level
        class_name = widget.metaObject().className()
        object_name = widget.objectName()
        geometry = widget.geometry()

        # DEBUG: Print current widget being processed (ACTIVE BY DEFAULT)
        print(f"{indent}Processing: {class_name} name='{object_name or ''}' geom={geometry}")

        xml_string = f'''{indent}<{class_name} '''
        if object_name:
            safe_object_name = object_name.replace('"', '&quot;') 
            xml_string += f'name="{safe_object_name}" '
        
        has_internal_content = False

        if hasattr(widget, 'text') and callable(widget.text):
            # print(f"{indent}  Checking text for {class_name} ('{object_name}'). Has text attr: True")
            try:
                widget_text = widget.text()
                if widget_text and isinstance(widget_text, str):
                    # print(f"{indent}    Found text: '{widget_text[:50]}'")
                    safe_widget_text = widget_text.replace('"', '&quot;').replace('\n', ' ')
                    xml_string += f'text="{safe_widget_text}" '
            except Exception as e:
                # print(f"{indent}    Error getting text: {e}")
                pass
        # else:
            # print(f"{indent}  No callable 'text' attribute for {class_name} ('{object_name}')")

        if hasattr(widget, 'windowTitle') and callable(widget.windowTitle):
            try:
                title = widget.windowTitle()
                if title and isinstance(title, str):
                    safe_title = title.replace('"', '&quot;')
                    xml_string += f'windowTitle="{safe_title}" '
            except Exception:
                pass

        xml_string += f'geometry="({geometry.x()},{geometry.y()},{geometry.width()},{geometry.height()})">' 
        xml_string += '\n'
        
        if isinstance(widget, QTabWidget):
            if widget.count() > 0:
                has_internal_content = True
            for i in range(widget.count()):
                tab_text = widget.tabText(i).replace('"', '&quot;')
                tab_tooltip = widget.tabToolTip(i).replace('"', '&quot;')
                tab_info_str = f'{indent}  <Tab index="{i}" title="{tab_text}"'
                if tab_tooltip:
                    tab_info_str += f' tooltip="{tab_tooltip}"'
                tab_info_str += ' />\n'
                xml_string += tab_info_str

        # Use widget.children() and filter for QWidget, then check if they are direct children.
        # This is a more robust way to find all QWidget children.
        potential_children = widget.children()
        actual_qwidget_children = []
        if potential_children:
            for child_obj in potential_children:
                if isinstance(child_obj, QWidget):
                    # Crucially, ensure it's a direct child for a clean hierarchy display
                    # If child_obj.parent() is not widget, it might be a grandchild through a non-QWidget parent, or complex parenting.
                    # However, for typical UI structures, child_obj.parent() == widget is expected for direct children.
                    # Let's assume for now that if it's in .children() and is a QWidget, it's relevant for inspection.
                    # Qt.FindDirectChildrenOnly with findChildren is usually better for strict direct children.
                    # If this still doesn't work, the issue might be deeper in widget parenting.
                    actual_qwidget_children.append(child_obj)
        
        # DEBUG: Print found children (ACTIVE BY DEFAULT)
        if actual_qwidget_children:
            print(f"{indent}  Children of {class_name} ('{object_name or ''}'): {[c.metaObject().className() + (' ('+c.objectName()+')' if c.objectName() else '') for c in actual_qwidget_children]}")
        else:
            print(f"{indent}  No QWidget children for {class_name} ('{object_name or ''}') found via .children() filtering")


        if actual_qwidget_children:
            has_internal_content = True
            for child_widget in actual_qwidget_children:
                # print(f"{indent}    Looping to child: {child_widget.metaObject().className()} name='{child_widget.objectName() or ''}'")
                if child_widget == self or (hasattr(child_widget, 'parent_window') and child_widget.parent_window == self):
                    continue
                if isinstance(child_widget, EdgeResizeHandle):
                    child_obj_name = child_widget.objectName() if child_widget.objectName() else ''
                    safe_child_obj_name = child_obj_name.replace('"', '&quot;')
                    pos_name = child_widget.position.name if hasattr(child_widget, 'position') and child_widget.position else 'N/A'
                    child_geom = child_widget.geometry()
                    geom_str = f"({child_geom.x()},{child_geom.y()},{child_geom.width()},{child_geom.height()})"
                    xml_string += f'''{indent}  <{child_widget.metaObject().className()} name="{safe_child_obj_name}" geometry="{geom_str}" position="{pos_name}" />\n'''
                    continue
                xml_string += self._build_widget_xml_string(child_widget, indent_level + 1)
        
        if has_internal_content:
            xml_string += f"{indent}</{class_name}>\n"
        else:
            xml_string = xml_string.rstrip('\n').rstrip('>') + ' />\n'
            
        return xml_string

    def _restore_geometry_and_position(self):
        # This method is now replaced by WindowGeometryManager
        pass
        
    def _save_geometry_and_position(self):
        # This method is now replaced by WindowGeometryManager
        pass

    def _on_hierarchy_label_hover_enter(self, target_widget: QWidget):
        if DEBUG_LOGS: print(f"[Inspector Hover Enter] Target: {target_widget.metaObject().className()} (Name: '{target_widget.objectName()}')") # Debug ACTIVE
        if self.sticky_highlighted_widget == target_widget:
            # If hovering over the currently sticky widget, ensure it's shown stickily.
            # This call also ensures it's raised and visible if somehow obscured.
            self.highlight_overlay.highlight_widget(target_widget, sticky=True)
        else:
            # Hovering over a new widget, show non-sticky highlight
            self.highlight_overlay.highlight_widget(target_widget, sticky=False)

    def _on_hierarchy_label_hover_leave(self, target_widget: QWidget):
        if DEBUG_LOGS: print(f"[Inspector Hover Leave] Target: {target_widget.metaObject().className()} (Name: '{target_widget.objectName()}')") # Debug ACTIVE
        if self.sticky_highlighted_widget == target_widget:
            # Leaving the sticky widget, it should remain highlighted stickily.
            # We can re-assert its highlight to ensure it's on top if other hovers occurred.
            self.highlight_overlay.highlight_widget(self.sticky_highlighted_widget, sticky=True)
            return
        else:
            # Leaving a non-sticky widget.
            # If there's another widget that IS sticky, re-highlight it.
            # Otherwise, clear any temporary hover highlight.
            if self.sticky_highlighted_widget:
                self.highlight_overlay.highlight_widget(self.sticky_highlighted_widget, sticky=True)
            else:
                # Clear any non-sticky hover highlight, ensuring overlay's internal stickiness is also cleared.
                self.highlight_overlay.clear_highlight(force_clear_sticky=True) 

    def _on_hierarchy_label_clicked(self, target_widget: QWidget):
        if DEBUG_LOGS: print(f"[Inspector Clicked] Target: {target_widget.metaObject().className()} (Name: '{target_widget.objectName()}')") # Debug ACTIVE
        if self.sticky_highlighted_widget == target_widget:
            # Clicked on already sticky widget: un-stick it and clear highlight
            self.sticky_highlighted_widget = None
            self.highlight_overlay.clear_highlight(force_clear_sticky=True)
        else:
            # New widget clicked or different widget clicked: make it sticky
            # This implicitly clears any previous sticky highlight by overlaying with a new one.
            self.sticky_highlighted_widget = target_widget
            self.highlight_overlay.highlight_widget(target_widget, sticky=True)
    
    def closeEvent(self, event: QCloseEvent):
        # Ensure overlay is hidden when inspector closes
        if self.highlight_overlay:
            self.highlight_overlay.hide()
        self.geometry_manager.save_geometry() 
        self.config.save() 
        if hasattr(self.main_app_window, 'inspector_window_instance'):
            self.main_app_window.inspector_window_instance = None
        super().closeEvent(event)    
        
    def _take_screenshot(self):
        if not self.main_app_window:
            self.screenshot_display_label.setText("Main application window not available.")
            return

        # Ensure the overlay has a chance to be up-to-date.
        QApplication.processEvents() 

        try:
            pixmap = self.main_app_window.grab()
            
            viewport_size = self.screenshot_scroll_area.viewport().size()
            max_width = viewport_size.width() - 2 
            max_height = viewport_size.height() - 2

            if pixmap.width() > max_width or pixmap.height() > max_height:
                scaled_pixmap = pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.screenshot_display_label.setPixmap(scaled_pixmap)
            else:
                self.screenshot_display_label.setPixmap(pixmap)
            self.save_screenshot_button.setEnabled(True) # Enable save after successful grab
            self.clear_drawings_button.setEnabled(True) # Also enable clear drawings
            
        except Exception as e:
            error_message = f"Error taking screenshot: {e}"
            print(f"Screenshot Error: {error_message}") # Keep a print for debugging
            self.screenshot_display_label.setText(error_message)
            self.save_screenshot_button.setEnabled(False)
            self.clear_drawings_button.setEnabled(False)

    def _clear_drawings_on_label(self):
        if isinstance(self.screenshot_display_label, DrawableScreenshotLabel):
            self.screenshot_display_label.clearDrawings()
            # Keep save button enabled as the base screenshot is still there

    def _save_screenshot(self):
        # Ensure the label is the drawable type and has a pixmap to save
        if not isinstance(self.screenshot_display_label, DrawableScreenshotLabel) or \
           self.screenshot_display_label.base_pixmap.isNull():
            QMessageBox.warning(self, "Save Screenshot", "No screenshot to save. Please take a screenshot first.")
            return

        # Suggest a filename
        default_path = str(Path(QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)) / "ViewMesh_Screenshot.png")
        
        # Open file dialog
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self, 
            "Save Screenshot As", 
            default_path,
            "PNG Images (*.png);;JPEG Images (*.jpg *.jpeg);;All Files (*)"
        )

        if file_name:
            pixmap_to_save = self.screenshot_display_label.getPixmapWithDrawings() # Get with drawings
            if not pixmap_to_save.save(file_name):
                QMessageBox.critical(self, "Save Screenshot", f"Failed to save screenshot to {file_name}.")
            else:
                # Optionally, provide feedback
                # self.main_app_window.showMessage(f"Screenshot saved to {file_name}", 3000) 
                pass # No explicit message needed, dialog closing is enough

    # Add a resize event handler to ensure the overlay is resized if the inspector window is resized (and overlay is child of main)
    # This is more relevant if the overlay is a direct child of the MAIN window, so it can resize with it.
    # For now, HighlightOverlay.update_geometry() is called when main window might resize (e.g. InspectorWindow.showEvent maybe)
    # Let's add it to the main window's resize event to be safe

# Need to modify ViewMeshApp to call overlay.update_geometry() during its resizeEvent
# And also potentially when the inspector is first shown.

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
class InspectorWindowSettings:
    """Store inspector window position and size."""
    size: Tuple[int, int] = (800, 600)
    position: Tuple[int, int] = (150, 150) # Absolute position, used as fallback or if screen info is lost
    relative_position: Tuple[float, float] = (0.15, 0.15) # Relative to screen, similar to main window
    screen_name: str = "" # Store screen identifier
    screen_geometry: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, width, height of screen it was on

    @classmethod
    def from_settings(cls, settings: QSettings, prefix: str = "inspector_window/") -> 'InspectorWindowSettings':
        """Load inspector window settings from QSettings."""
        result = cls()
        size_key = f"{prefix}size"
        pos_key = f"{prefix}position"
        rel_pos_key = f"{prefix}relative_position"
        screen_name_key = f"{prefix}screen_name"
        screen_geom_key = f"{prefix}screen_geometry"

        if settings.contains(size_key):
            size_val = settings.value(size_key)
            if isinstance(size_val, QSize):
                result.size = (size_val.width(), size_val.height())
            elif isinstance(size_val, str):
                try:
                    parts = size_val.strip("()").split(",")
                    if len(parts) == 2:
                        result.size = (int(parts[0].strip()), int(parts[1].strip()))
                except ValueError:
                    print(f"Warning: Could not parse inspector size string: {size_val}")
            elif isinstance(size_val, (list, tuple)) and len(size_val) == 2:
                 result.size = (int(size_val[0]), int(size_val[1]))

        if settings.contains(pos_key):
            pos_val = settings.value(pos_key)
            if isinstance(pos_val, QPoint):
                result.position = (pos_val.x(), pos_val.y())
            elif isinstance(pos_val, str):
                try:
                    parts = pos_val.strip("()").split(",")
                    if len(parts) == 2:
                        result.position = (int(parts[0].strip()), int(parts[1].strip()))
                except ValueError:
                    print(f"Warning: Could not parse inspector position string: {pos_val}")
            elif isinstance(pos_val, (list, tuple)) and len(pos_val) == 2:
                result.position = (int(pos_val[0]), int(pos_val[1]))

        # Use the helper from WindowSettings for tuple parsing
        result.relative_position = WindowSettings._parse_tuple_setting(
            settings,
            rel_pos_key,
            element_type=float,
            num_elements=2,
            default_tuple_value=result.relative_position
        )

        if settings.contains(screen_name_key):
            result.screen_name = settings.value(screen_name_key, "", type=str)

        result.screen_geometry = WindowSettings._parse_tuple_setting(
            settings,
            screen_geom_key,
            element_type=int,
            num_elements=4,
            default_tuple_value=result.screen_geometry
        )
        return result

    def save_to_settings(self, settings: QSettings, prefix: str = "inspector_window/") -> None:
        """Save inspector window settings to QSettings."""
        settings.setValue(f"{prefix}size", QSize(*self.size))
        settings.setValue(f"{prefix}position", QPoint(*self.position)) # Save absolute as well
        settings.setValue(f"{prefix}relative_position", str(self.relative_position))
        settings.setValue(f"{prefix}screen_name", self.screen_name)
        settings.setValue(f"{prefix}screen_geometry", str(self.screen_geometry))

@dataclass
class AppConfig:
    """Application configuration."""
    app_name: str = "ViewMesh"
    org_name: str = "AnchorSCAD"
    settings: WindowSettings = field(default_factory=WindowSettings)
    inspector_settings: InspectorWindowSettings = field(default_factory=InspectorWindowSettings) # Added
    initial_dir: str = field(default_factory=lambda: str(Path.home()))
    
    @classmethod
    def load(cls) -> 'AppConfig':
        """Load configuration from settings."""
        config = cls()
        settings = QSettings(config.org_name, config.app_name)
        config.settings = WindowSettings.from_settings(settings)
        config.inspector_settings = InspectorWindowSettings.from_settings(settings) # Added
        if settings.contains("app/initial_dir"):
            config.initial_dir = settings.value("app/initial_dir")
        return config
    
    def save(self) -> None:
        """Save configuration to settings."""
        settings = QSettings(self.org_name, self.app_name)
        self.settings.save_to_settings(settings)
        self.inspector_settings.save_to_settings(settings) # Added
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
        

class AppCustomizer(ABC):

    @abstractmethod
    def customise(self, app: 'ViewMeshApp'):
        pass
    
    # Helper methods to create common actions
    def create_font_size_actions(self, app_window: 'ViewMeshApp') -> Tuple[QAction, QAction]:
        """Creates and returns 'Increase Font Size' and 'Decrease Font Size' actions."""
        increase_font_action = QAction("Increase Font Size", app_window) # Parent to app_window for lifetime
        increase_font_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_Equal))
        increase_font_action.triggered.connect(app_window.increase_font_size)
        # Add to app_window's actions to make shortcut work globally if not in a visible menu
        app_window.addAction(increase_font_action)

        decrease_font_action = QAction("Decrease Font Size", app_window)
        decrease_font_action.setShortcut(QKeySequence(Qt.CTRL | Qt.SHIFT | Qt.Key_Minus))
        decrease_font_action.triggered.connect(app_window.decrease_font_size)
        app_window.addAction(decrease_font_action)
        return increase_font_action, decrease_font_action

    def create_toggle_fullscreen_action(self, app_window: 'ViewMeshApp') -> QAction:
        """Creates and returns a 'Toggle Fullscreen' action."""
        toggle_fullscreen_action = QAction("Toggle &Fullscreen", app_window)
        toggle_fullscreen_action.setShortcut(QKeySequence.FullScreen)
        toggle_fullscreen_action.triggered.connect(app_window.toggle_fullscreen)
        toggle_fullscreen_action.setCheckable(True)
        # Set initial check state (important if menu is created after window is shown/state restored)
        # It might be better for ViewMeshApp.toggle_fullscreen to manage the action's check state if passed.
        # For now, let's assume it's set here. The action itself should be updated by toggle_fullscreen.
        # The ViewMeshApp.toggle_fullscreen already updates a found action. 
        # For robustness, the action could be passed to toggle_fullscreen or toggle_fullscreen finds it by text.
        # For now, this is okay, but ViewMeshApp.toggle_fullscreen needs to reliably find this action if it's to update its state.
        toggle_fullscreen_action.setChecked(app_window.isFullScreen()) 
        return toggle_fullscreen_action
    
class DefaultAppCustomizer(AppCustomizer):

    def _populate_menus(self, menu_bar: QMenuBar, app_window: 'ViewMeshApp'):
        # File Menu
        file_menu = menu_bar.addMenu("&File")

        new_action = QAction("&New", app_window)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(app_window.on_new_file)
        file_menu.addAction(new_action)

        open_file_action = QAction("&Open File...", app_window)
        open_file_action.setShortcut(QKeySequence.Open)
        open_file_action.triggered.connect(app_window.on_open_file)
        file_menu.addAction(open_file_action)

        open_folder_action = QAction("Open &Folder...", app_window)
        open_folder_action.triggered.connect(app_window.on_open_folder)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()

        save_action = QAction("&Save", app_window)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(app_window.on_save)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save &As...", app_window)
        save_as_action.setShortcut(QKeySequence.SaveAs)
        save_as_action.triggered.connect(app_window.on_save_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", app_window)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(app_window.close) 
        file_menu.addAction(exit_action)

        # Edit Menu (placeholders for now)
        edit_menu = menu_bar.addMenu("&Edit")
        undo_action = QAction("&Undo", app_window)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.triggered.connect(lambda: app_window.showMessage("Undo not implemented"))
        edit_menu.addAction(undo_action)
        # ... (add other Edit menu items similarly) ...
        redo_action = QAction("&Redo", app_window)
        redo_action.setShortcut(QKeySequence.Redo)
        redo_action.triggered.connect(lambda: app_window.showMessage("Redo not implemented"))
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        cut_action = QAction("Cu&t", app_window)
        cut_action.setShortcut(QKeySequence.Cut)
        cut_action.triggered.connect(lambda: app_window.showMessage("Cut not implemented"))
        edit_menu.addAction(cut_action)

        copy_action = QAction("&Copy", app_window)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(lambda: app_window.showMessage("Copy not implemented"))
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", app_window)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.triggered.connect(lambda: app_window.showMessage("Paste not implemented"))
        edit_menu.addAction(paste_action)

        # View Menu
        view_menu = menu_bar.addMenu("&View")
        
        toggle_explorer_action = QAction("Toggle &Explorer", app_window)
        toggle_explorer_action.setCheckable(True)
        # toggle_explorer_action.setChecked(app_window.explorer_dock.isVisible()) # Handled by connection
        toggle_explorer_action.triggered.connect(app_window.toggle_explorer)
        view_menu.addAction(toggle_explorer_action)
        if hasattr(app_window, 'explorer_dock'): # Connect only if explorer_dock exists
            app_window.explorer_dock.visibilityChanged.connect(toggle_explorer_action.setChecked)

        toggle_welcome_action = QAction("Show &Welcome", app_window)
        toggle_welcome_action.setCheckable(True)
        if hasattr(app_window, 'welcome_dock'): # Check before accessing isVisible and connecting
            # toggle_welcome_action.setChecked(app_window.welcome_dock.isVisible()) # Handled by connection
            app_window.welcome_dock.visibilityChanged.connect(toggle_welcome_action.setChecked)
        else: # If no welcome_dock, disable this menu item perhaps, or set default checked state false
            toggle_welcome_action.setChecked(False)
            toggle_welcome_action.setEnabled(False)
        toggle_welcome_action.triggered.connect(app_window.toggle_welcome_panel)
        view_menu.addAction(toggle_welcome_action)

        increase_action, decrease_action = self.create_font_size_actions(app_window)
        view_menu.addAction(increase_action)
        view_menu.addAction(decrease_action)

        fullscreen_action = self.create_toggle_fullscreen_action(app_window)
        view_menu.addAction(fullscreen_action)

        # Help Menu
        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About ViewMesh", app_window)
        about_action.triggered.connect(app_window.on_about)
        help_menu.addAction(about_action)

    def customise(self, app: 'ViewMeshApp'):
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
        
        # Add a placeholder tab for now - styled like VS Code welcome page
        placeholder1 = QWidget()
        placeholder1.setStyleSheet("background-color: #1e1e1e;")
        pl_layout1 = QVBoxLayout(placeholder1)
        pl_layout1.addWidget(QLabel("Editor Tab 1 Content"))

        placeholder2 = QWidget()
        placeholder2.setStyleSheet("background-color: #1e1e1e;")
        pl_layout2 = QVBoxLayout(placeholder2)
        pl_layout2.addWidget(QLabel("Editor Tab 2 Content"))
        
        app.add_tab("Editor 1", placeholder1)
        app.add_tab("Editor 2", placeholder2)
        app.add_tab("Welcome", placeholder)

        # Setup status bar widgets (copied from previous state, ensure it's correct)
        encoding_label = QLabel("UTF-8")
        encoding_label.setObjectName("encoding_label")
        encoding_label.setStyleSheet("padding: 3px 8px; border-left: 1px solid rgba(255, 255, 255, 0.3); background-color: transparent; color: white;")
        app.add_status_bar_permanent_widget(encoding_label)
        
        line_col_label = QLabel("Ln 1, Col 1")
        line_col_label.setObjectName("line_col_label")
        line_col_label.setStyleSheet("padding: 3px 8px; border-left: 1px solid rgba(255, 255, 255, 0.3); background-color: transparent; color: white;")
        app.add_status_bar_permanent_widget(line_col_label)
        
        indent_label = QLabel("Spaces: 4")
        indent_label.setObjectName("indent_label")
        indent_label.setStyleSheet("padding: 3px 8px 3px 8px; margin-right: 3px; border-left: 1px solid rgba(255, 255, 255, 0.3); background-color: transparent; color: white;")
        app.add_status_bar_permanent_widget(indent_label)
        
        status_message = QLabel("Ready")
        status_message.setObjectName("status_message")
        status_message.setStyleSheet("padding: 3px 8px; background-color: transparent; color: white;")
        app.set_main_status_message_label(status_message)
        app.add_status_bar_widget(status_message)

        # Populate menus
        if hasattr(app, 'menu_bar'): # Ensure menu_bar exists on app
            self._populate_menus(app.menu_bar, app)
            # After populating menus, update the title bar height to reflect the menu bar's content
            if hasattr(app, '_update_title_bar_height') and callable(app._update_title_bar_height):
                app._update_title_bar_height()
        else:
            print("Warning: ViewMeshApp instance does not have 'menu_bar' attribute. Menus not populated.")

class ViewMeshApp(QMainWindow):
    """Main ViewMesh application window."""
    
    def __init__(self, config: AppConfig):
        super().__init__(None, Qt.FramelessWindowHint)  # Make window frameless
        self.config = config
        self.setObjectName("ViewMeshAppMainWindow") 
        self.was_maximized_before_fullscreen = False 
        self.resize_handle_thickness = 5 
        self.inspector_window_instance = None 
        self.geometry_manager = WindowGeometryManager(self, self.config.settings) # Initialize manager
        self._main_status_message_label: Optional[QLabel] = None # For status message updates
        
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
        
        # Restore window state using the manager
        # self.restore_window_state() # Old method call
        self.setWindowOpacity(0.0) # Prevent flicker
        self.show() # Show before moving to ensure Qt knows it exists
        self.geometry_manager.restore_geometry()
        QApplication.processEvents() # Allow Qt to process move/resize
        self.setWindowOpacity(1.0)

        # Restore maximized state (after geometry is set)
        if self.config.settings.is_maximized:
            self.showMaximized()
        
        # Restore dock widget sizes (specific to ViewMeshApp)
        self.explorer_dock.setMinimumWidth(self.config.settings.explorer_width)
        self.explorer_dock.setMaximumWidth(self.config.settings.explorer_width)
        
        # Restore complete window state if available (specific to ViewMeshApp)
        if self.config.settings.state:
            self.restoreState(self.config.settings.state)
        
        # Restore initial directory (specific to ViewMeshApp)
        if hasattr(self.explorer, 'initial_dir'): # Check if explorer exists
            self.explorer.initial_dir = self.config.initial_dir
        
        # Apply initial font size adjustment if any (AFTER UI is set up and state restored)
        if self.global_font_size_adjust != 0:
            self._apply_global_font_change()
        
        self._create_resize_handles()

        # Set resize cursor for window edges (now handled by EdgeResizeHandle)
        # self.setMouseTracking(True)
        # self.resize_padding = 5 # replaced by resize_handle_thickness
        
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
        
    def add_tab(self, tab_name: str, widget: QWidget):
        self.tab_widget.addTab(widget, tab_name)
        self.tab_widget.setCurrentWidget(widget)
    
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
    
    def _create_resize_handles(self):
        self.edge_handles = []
        positions = [
            HandlePosition.TOP_LEFT, HandlePosition.TOP, HandlePosition.TOP_RIGHT,
            HandlePosition.LEFT, HandlePosition.RIGHT,
            HandlePosition.BOTTOM_LEFT, HandlePosition.BOTTOM, HandlePosition.BOTTOM_RIGHT
        ]
        for pos in positions:
            handle = EdgeResizeHandle(self, pos, self.resize_handle_thickness)
            self.edge_handles.append(handle)
            handle.show() # Ensure they are visible
            handle.raise_() # Explicitly raise it after showing
            # print(f"[DEBUG _create_resize_handles] Created handle: {pos}, Visible: {handle.isVisible()}, Geom: {handle.geometry()}")

    def resizeEvent(self, event: QResizeEvent):
        """Handle window resize event to update handle geometries."""
        super().resizeEvent(event)
        if hasattr(self, 'edge_handles'): # Ensure handles are created
            for handle in self.edge_handles:
                handle.update_geometry()
        
        # Update title bar height as well, as font changes can affect it via resize
        self._update_title_bar_height()

        # Update highlight overlay geometry if inspector is open
        if hasattr(self, 'inspector_window_instance') and self.inspector_window_instance and \
           hasattr(self.inspector_window_instance, 'highlight_overlay') and self.inspector_window_instance.highlight_overlay:
            self.inspector_window_instance.highlight_overlay.update_geometry()
    
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
        # This method is now largely replaced by WindowGeometryManager
        # but parts related to maximized state, dockwidgets, and QMainWindow.restoreState
        # will be called directly after the geometry_manager.restore_geometry()
        pass # Keep the method for now, but its core is moved
    
    def save_window_state(self):
        """Save the current window state to the configuration."""
        # Use the geometry manager
        self.geometry_manager.save_geometry()

        # Save other ViewMeshApp-specific states
        self.config.settings.is_maximized = self.isMaximized()
        if hasattr(self.explorer_dock, 'width'): # Check if dock exists
            self.config.settings.explorer_width = self.explorer_dock.width()
        self.config.settings.state = self.saveState()
        if hasattr(self.explorer, 'initial_dir'): # Check if explorer exists
            self.config.initial_dir = self.explorer.initial_dir
        self.config.settings.global_font_size_adjust = self.global_font_size_adjust
        
        # Save configuration (the manager doesn't call config.save() itself)
        self.config.save()
    
    def closeEvent(self, event: QCloseEvent):
        """Handle window close event."""
        # Close the inspector window if it exists
        if self.inspector_window_instance is not None:
            self.inspector_window_instance.close() # This will trigger its own save routines
            self.inspector_window_instance = None # Ensure reference is cleared here too

        # Save main window state
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
        if self._main_status_message_label is not None:
            self._main_status_message_label.setText(message)
            # QStatusBar.showMessage also has a timeout feature for temporary messages.
            # If we want to replicate that, we'd need a QTimer here when timeout > 0.
            # For now, setText makes it persistent until the next call.
            if timeout > 0:
                # Simple way to clear after timeout, could be more robust
                QTimer.singleShot(timeout, lambda: self._main_status_message_label.setText("") if self._main_status_message_label.text() == message else None)
        elif hasattr(self, 'status_bar'): # Fallback if no specific label is set
            self.status_bar.showMessage(message, timeout)

    def setup_status_bar(self):
        """Set up a status bar similar to VS Code."""
        self.status_bar = QStatusBar()
        self.status_bar.setObjectName("status_bar")
        self.status_bar.setSizeGripEnabled(False)
        self.setStatusBar(self.status_bar)
        
        # Style the status bar
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #007acc;
                color: white;
                padding: 0px;
                font-size: 9pt;
            }
            QLabel { /* Default for labels within status bar if not overridden */
                padding: 3px 5px;
                margin: 0px;
                background-color: transparent; /* Ensure transparency against blue bar */
                color: white; /* Ensure white text */
            }
        """)
        
        # Permanent widgets and main status message will be added by the customizer

    def add_status_bar_widget(self, widget: QWidget, stretch: int = 0):
        """Adds a widget to the status bar (typically left side)."""
        if hasattr(self, 'status_bar'):
            self.status_bar.addWidget(widget, stretch)

    def add_status_bar_permanent_widget(self, widget: QWidget, stretch: int = 0):
        """Adds a permanent widget to the status bar (typically right side)."""
        if hasattr(self, 'status_bar'):
            self.status_bar.addPermanentWidget(widget, stretch)

    def set_main_status_message_label(self, label: QLabel):
        """Sets the QLabel instance that should be used for showMessage()."""
        self._main_status_message_label = label

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
        
        open_inspector_action_ctx = context_menu.addAction("Open Inspector") # Added here

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
            elif open_inspector_action_ctx and action == open_inspector_action_ctx: # Added condition
                self.on_open_inspector() # Connect to existing handler
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
        rect = self.rect() # Client rectangle
        padding = self.resize_handle_thickness
        
        # Corrected conditions for 0-indexed client area coordinates
        # Max valid x is rect.width() - 1, max valid y is rect.height() - 1
        on_left = pos.x() < padding # For x in [0, padding-1]
        on_right = pos.x() >= rect.width() - padding # For x in [width-padding, width-1]
        on_top = pos.y() < padding # For y in [0, padding-1]
        on_bottom = pos.y() >= rect.height() - padding # For y in [height-padding, height-1]

        # Ensure position is within the window bounds for edge detection to be valid
        # Although mapFromGlobal in nativeEvent handles this, good for general purpose fn
        if not rect.contains(pos):
             # If outside the main client rect, but could be on a thicker conceptual border,
             # the simple padding checks might still be relevant if padding is interpreted broadly.
             # However, for strict client area padding, this check is useful.
             # For now, let the simple boundary checks decide, as WM_NCHITTEST operates on window coords.
             pass 

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
        """Handle native window events (simplified)."""
        # Reverted to simple pass-through. Resize and custom cursor logic via native events is removed.
        return super().nativeEvent(eventType, message)

    def toggle_maximize(self):
        """Toggle maximize/restore window state."""
        if self.isMaximized():
            self.showNormal()
            self.maximize_button.setText("□") # Update button text
        else:
            self.showMaximized()
            self.maximize_button.setText("❐") # Update button text
    
    def setup_menu_items(self):
        # Menu bar is created in ViewMeshApp.setup_ui and attached to title_bar_layout
        # Populating the menu bar is now the responsibility of the AppCustomizer
        pass

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

    def on_open_inspector(self):
        if self.inspector_window_instance is None:
            self.inspector_window_instance = InspectorWindow(main_app_window=self)
            self.inspector_window_instance.show()
            # Restore geometry AFTER showing the window for the first time
            self.inspector_window_instance.geometry_manager.restore_geometry()
            QApplication.processEvents() # Allow Qt to process show and move/resize
        else:
            # If already exists, its geometry should be current from last session or use.
            # Just ensure it's visible and brought to the front.
            self.inspector_window_instance.show() 
            self.inspector_window_instance.activateWindow()

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

def main(customerizer: AppCustomizer):
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
    customerizer.customise(window)
    window.show()
    
    # Run the Qt event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    asyncio.run(main(DefaultAppCustomizer())) 