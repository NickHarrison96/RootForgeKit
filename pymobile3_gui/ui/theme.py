"""
Pymobile3-GUI - Theme and Styling Configuration
Quiet Precision: Apple-inspired restraint, deep contrast, refined typography, and subtle micro-borders.
"""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtCore import Qt

class Colors:
    # Canvas & Surface
    BG_WINDOW = "#0a0b10"
    BG_SIDEBAR = "#10131b"
    BG_SURFACE = "#12151e"
    BG_CARD = "#171b25"
    BG_CARD_HOVER = "#1d2330"
    BG_CARD_ACTIVE = "#222a3a"
    BG_DOCK = "rgba(17, 22, 31, 0.95)"
    BG_DRAWER = "#0f121a"
    BG_TERMINAL = "#090c12"

    # Borders
    BORDER_SUBTLE = "#222632"
    BORDER_DEFAULT = "#2c313e"
    BORDER_MUTED = "#353c4d"
    BORDER_HOVER = "#506385"
    BORDER_FOCUS = "#3d7aff"

    # Accents & States
    ACCENT_PRIMARY = "#2563eb"
    ACCENT_PRIMARY_HOVER = "#3b82f6"
    ACCENT_GLOW = "rgba(37, 99, 235, 0.35)"
    
    SUCCESS = "#8ae0b5"
    SUCCESS_BG = "#13231c"
    SUCCESS_BORDER = "#274033"

    WARNING = "#fcd34d"
    WARNING_BG = "#2a2211"
    WARNING_BORDER = "#4e3e1d"

    DANGER = "#ff5f57"
    DANGER_BG = "#2b1414"
    DANGER_BORDER = "#532525"

    # Text Colors
    TEXT_PRIMARY = "#f6f7fb"
    TEXT_SECONDARY = "#9ca6ba"
    TEXT_MUTED = "#6e788d"
    TEXT_INVERTED = "#0a0b10"

    # Traffic light buttons
    TRAFFIC_CLOSE = "#ff5f57"
    TRAFFIC_MIN = "#febc2e"
    TRAFFIC_MAX = "#28c840"


def get_application_stylesheet() -> str:
    """Returns the primary QSS stylesheet for the application."""
    return f"""
    QWidget {{
        color: {Colors.TEXT_PRIMARY};
        font-family: 'Inter', 'Segoe UI Variable Text', 'Segoe UI', -apple-system, sans-serif;
        font-size: 13px;
        outline: none;
    }}

    QMainWindow {{
        background-color: transparent;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #2a3140;
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #3e485e;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        border: none;
        background: none;
        height: 0px;
    }}

    QScrollBar:horizontal {{
        border: none;
        background: transparent;
        height: 8px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: #2a3140;
        min-width: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: #3e485e;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        border: none;
        background: none;
        width: 0px;
    }}

    /* Buttons */
    QPushButton {{
        background-color: #1a202c;
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 8px;
        padding: 7px 14px;
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton:hover {{
        background-color: #242c3d;
        border-color: {Colors.BORDER_HOVER};
    }}
    QPushButton:pressed {{
        background-color: #161b26;
        border-color: {Colors.ACCENT_PRIMARY};
    }}
    QPushButton:disabled {{
        background-color: #12151d;
        color: {Colors.TEXT_MUTED};
        border-color: {Colors.BORDER_SUBTLE};
    }}

    QPushButton.primary {{
        background-color: {Colors.ACCENT_PRIMARY};
        color: white;
        border: 1px solid #3b82f6;
    }}
    QPushButton.primary:hover {{
        background-color: {Colors.ACCENT_PRIMARY_HOVER};
        border-color: #60a5fa;
    }}
    QPushButton.primary:pressed {{
        background-color: #1d4ed8;
    }}

    QPushButton.danger {{
        background-color: {Colors.DANGER_BG};
        color: {Colors.DANGER};
        border: 1px solid {Colors.DANGER_BORDER};
    }}
    QPushButton.danger:hover {{
        background-color: #3b1919;
        border-color: #7f3232;
    }}

    /* Line Edits */
    QLineEdit {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 8px;
        padding: 7px 12px;
        selection-background-color: {Colors.ACCENT_PRIMARY};
    }}
    QLineEdit:focus {{
        border-color: {Colors.BORDER_FOCUS};
    }}

    /* Tables & Tree Views */
    QTableWidget, QTreeView, QListWidget {{
        background-color: {Colors.BG_SURFACE};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 10px;
        gridline-color: {Colors.BORDER_SUBTLE};
        selection-background-color: #203354;
        selection-color: {Colors.TEXT_PRIMARY};
        outline: none;
    }}
    QHeaderView::section {{
        background-color: #121620;
        color: {Colors.TEXT_SECONDARY};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {Colors.BORDER_DEFAULT};
        border-right: 1px solid {Colors.BORDER_SUBTLE};
        font-weight: 600;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }}

    /* Progress Bar */
    QProgressBar {{
        border: 1px solid {Colors.BORDER_SUBTLE};
        border-radius: 5px;
        background-color: #131722;
        text-align: center;
        color: {Colors.TEXT_MUTED};
        font-size: 11px;
        font-weight: 600;
        height: 10px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #38bdf8, stop:1 #3b82f6);
        border-radius: 4px;
    }}

    /* Card Frames */
    QFrame.card {{
        background-color: {Colors.BG_CARD};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 14px;
    }}

    /* ComboBox */
    QComboBox {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_DEFAULT};
        border-radius: 8px;
        padding: 6px 12px;
        font-weight: 500;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {Colors.BG_CARD};
        color: {Colors.TEXT_PRIMARY};
        border: 1px solid {Colors.BORDER_MUTED};
        selection-background-color: #243552;
        border-radius: 6px;
        padding: 4px;
    }}

    QPlainTextEdit, QTextEdit {{
        font-family: 'JetBrains Mono', 'Consolas', monospace;
    }}
    """
