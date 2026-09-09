"""Pymobile3-GUI - Native window shell: native frame kept, frame extended into client area for a custom titlebar + DWM backdrop."""
import sys, ctypes
from ctypes import c_int, byref, sizeof, Structure
from PySide6.QtWidgets import QMainWindow, QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_MAINWINDOW = 2
WM_NCCALCSIZE = 0x0083


class MARGINS(Structure):
    _fields_ = [("cxLeftWidth", c_int), ("cxRightWidth", c_int),
                ("cyTopHeight", c_int), ("cyBottomHeight", c_int)]


def _win_build() -> int:
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def apply_windows_glass(hwnd: int) -> bool:
    """True when a real Mica backdrop was applied (Win11 build 22000+)."""
    if sys.platform != "win32":
        return False
    try:
        dwm = ctypes.windll.dwmapi
        dark = c_int(1)
        dwm.DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(dark), sizeof(dark))
        dwm.DwmExtendFrameIntoClientArea(hwnd, byref(MARGINS(-1, -1, -1, -1)))
        if _win_build() >= 22000:
            bd = c_int(DWMSBT_MAINWINDOW)
            hr = dwm.DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, byref(bd), sizeof(bd))
            return hr == 0
        return False
    except Exception:
        return False


class NativeFramelessWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.title_bar_widget = None
        self._is_glass_active = False
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMinimumSize(960, 620)

    def set_title_bar(self, widget: QWidget):
        self.title_bar_widget = widget

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32" and not self._is_glass_active:
            self._is_glass_active = apply_windows_glass(int(self.winId()))
            self.update()

    def nativeEvent(self, eventType, message):
        if eventType == b"windows_generic_MSG" and sys.platform == "win32":
            import ctypes.wintypes
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                return True, 0
        return super().nativeEvent(eventType, message)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._is_glass_active:
            p.fillRect(self.rect(), QColor(10, 11, 16, 40))
        else:
            p.fillRect(self.rect(), QColor(10, 11, 16, 255))
