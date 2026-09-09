"""
Pymobile3-GUI - Native Window Shell
Implements a frameless desktop window with Windows 10/11 DWM glass backdrop,
Aero Snap, edge resizing, and native drop shadow.
"""

import sys
import ctypes
from ctypes import c_int, byref, sizeof, Structure, c_void_p, c_ulong, POINTER
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QPoint, QRect, Signal
from PySide6.QtGui import QColor, QPainter

# Win32 Constants
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
WM_GETMINMAXINFO = 0x0024

HTNOWHERE = 0
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 2       # Mica
DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
DWMSBT_TABBEDWINDOW = 4     # Mica Alt


class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]


class POINT(Structure):
    _fields_ = [("x", c_int), ("y", c_int)]


class MINMAXINFO(Structure):
    _fields_ = [
        ("ptReserved", POINT),
        ("ptMaxSize", POINT),
        ("ptMaxPosition", POINT),
        ("ptMinTrackSize", POINT),
        ("ptMaxTrackSize", POINT),
    ]


def apply_windows_glass(hwnd: int) -> bool:
    """Applies Windows 11 Mica / Acrylic or Windows 10 dark mode backdrop."""
    if sys.platform != "win32":
        return False

    success = False
    try:
        dwmapi = ctypes.windll.dwmapi

        # 1. Enable Immersive Dark Mode
        dark_mode = c_int(1)
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            byref(dark_mode),
            sizeof(dark_mode),
        )

        # 2. Windows 11 Backdrop (Mica)
        backdrop_type = c_int(DWMSBT_MAINWINDOW)
        hr = dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            byref(backdrop_type),
            sizeof(backdrop_type),
        )
        if hr == 0:
            success = True

        # 3. Extend Frame into Client Area for native drop shadow
        margins = MARGINS(1, 1, 1, 1)
        dwmapi.DwmExtendFrameIntoClientArea(hwnd, byref(margins))

    except Exception:
        pass

    return success


class NativeFramelessWindow(QMainWindow):
    """
    Frameless QMainWindow that preserves native Aero Snap,
    edge resizing, and Windows 11 Mica/Acrylic styling.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resize_border_width = 8
        self.title_bar_widget = None
        self._is_glass_active = False

        # Set Window Flags
        self.setWindowFlags(
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )

        # Translucent background allows DWM glass to shine through
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._is_glass_active:
            hwnd = int(self.winId())
            self._is_glass_active = apply_windows_glass(hwnd)

    def set_title_bar(self, widget: QWidget):
        """Register the title bar widget for drag / hit-testing."""
        self.title_bar_widget = widget

    def nativeEvent(self, eventType, message):
        """
        Intercept Win32 messages to handle border resizing,
        Aero snap, and custom title bar dragging.
        """
        if eventType == b"windows_generic_MSG" and sys.platform == "win32":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())

            # Prevent frame flicker & enable custom non-client client area
            if msg.message == WM_NCCALCSIZE:
                return True, 0

            # Hit-Testing for resizing, dragging, and caption
            if msg.message == WM_NCHITTEST:
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                if x > 32767:
                    x -= 65536
                if y > 32767:
                    y -= 65536

                local_pt = self.mapFromGlobal(QPoint(x, y))
                bw = self.resize_border_width
                w = self.width()
                h = self.height()

                # Don't resize if maximized
                if not self.isMaximized():
                    # Corners
                    if local_pt.x() < bw and local_pt.y() < bw:
                        return True, HTTOPLEFT
                    if local_pt.x() > w - bw and local_pt.y() < bw:
                        return True, HTTOPRIGHT
                    if local_pt.x() < bw and local_pt.y() > h - bw:
                        return True, HTBOTTOMLEFT
                    if local_pt.x() > w - bw and local_pt.y() > h - bw:
                        return True, HTBOTTOMRIGHT

                    # Edges
                    if local_pt.x() < bw:
                        return True, HTLEFT
                    if local_pt.x() > w - bw:
                        return True, HTRIGHT
                    if local_pt.y() < bw:
                        return True, HTTOP
                    if local_pt.y() > h - bw:
                        return True, HTBOTTOM

                # Title Bar Dragging Zone
                if self.title_bar_widget and self.title_bar_widget.isVisible():
                    tb_rect = self.title_bar_widget.rect()
                    tb_local_pt = self.title_bar_widget.mapFromGlobal(QPoint(x, y))

                    if tb_rect.contains(tb_local_pt):
                        # Check if over child buttons (close, min, max, chips)
                        child = self.title_bar_widget.childAt(tb_local_pt)
                        if child is None or child == self.title_bar_widget:
                            return True, HTCAPTION
                        else:
                            # Let Qt handle child button clicks
                            return True, HTCLIENT

                return True, HTCLIENT

            # Maintain correct minimum track size
            if msg.message == WM_GETMINMAXINFO:
                mmi = MINMAXINFO.from_address(msg.lParam)
                mmi.ptMinTrackSize.x = 960
                mmi.ptMinTrackSize.y = 620
                return True, 0

        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        """
        Draw subtle translucent tinted background if glass is active,
        or solid dark background if DWM glass is unavailable.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_glass_active:
            # Subtle dark tint over Mica
            painter.fillRect(self.rect(), QColor(10, 11, 16, 215))
        else:
            # Fallback opaque dark canvas
            painter.fillRect(self.rect(), QColor(10, 11, 16, 255))
