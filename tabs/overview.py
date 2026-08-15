# =============================================================================
# RootForgeKit — Overview Dashboard Tab
# Sleek Phone-Style Modular Widget Dashboard
#   Left Panel:  Neofetch-style OS badge (ASCII logo, hostname, kernel, uptime)
#   Right Panel: Moveable & resizable widget cards (CPU, GPU, RAM, Storage, Network, BIOS)
# =============================================================================

import json
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QGridLayout, QProgressBar, QScrollArea, QSizePolicy,
    QPushButton, QApplication,
)
from PySide6.QtCore import Qt, QTimer, QSettings, QMimeData, QPoint
from PySide6.QtGui import QFont, QDrag, QPixmap, QColor, QCursor

from utils.sys_info import SystemInfoWorker
from utils.system_info import get_system_summary
from utils.os_logo import (
    detect_os_key, render_logo, LOGO_ACCENTS, DISPLAY_NAMES,
)

SETTINGS_ORG = "KushNick420"
SETTINGS_APP = "OverviewWidgets"
MIME_TYPE_CARD = "application/x-rootforgekit-card"


class WidgetCard(QFrame):
    """
    Phone-style dark widget card that supports:
      - Drag-and-drop repositioning (upward & downward)
      - Resizing between 1-column (half width) and 2-column (full width)
      - Collapse / expand
    """

    def __init__(self, card_id: str, title: str, parent_dashboard=None):
        super().__init__()
        self.card_id = card_id
        self.card_title = title
        self.dashboard = parent_dashboard
        self.col_span = 2       # 2 = full-width, 1 = half-width
        self.is_collapsed = False
        self._drag_start_pos = None

        self.setObjectName("SpecCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setAcceptDrops(True)

        self._setup_ui()

    def _setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(8)

        # Header bar
        self.header = QWidget()
        self.header.setObjectName("WidgetHeader")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        # Drag handle icon
        self.drag_handle = QLabel("⋮⋮")
        self.drag_handle.setObjectName("WidgetDragHandle")
        self.drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self.drag_handle.setToolTip("Drag to rearrange widget position")
        header_layout.addWidget(self.drag_handle)

        # Title
        self.title_label = QLabel(self.card_title)
        self.title_label.setObjectName("SpecCardTitle")
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        # Move Up button
        self.btn_up = QPushButton("▲")
        self.btn_up.setObjectName("WidgetMiniBtn")
        self.btn_up.setToolTip("Move widget up")
        self.btn_up.setFixedSize(24, 22)
        self.btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_up.clicked.connect(lambda: self.dashboard.move_card(self.card_id, -1))
        header_layout.addWidget(self.btn_up)

        # Move Down button
        self.btn_down = QPushButton("▼")
        self.btn_down.setObjectName("WidgetMiniBtn")
        self.btn_down.setToolTip("Move widget down")
        self.btn_down.setFixedSize(24, 22)
        self.btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_down.clicked.connect(lambda: self.dashboard.move_card(self.card_id, 1))
        header_layout.addWidget(self.btn_down)

        # Size toggle button (Half width vs Full width)
        self.btn_size = QPushButton("Wide" if self.col_span == 2 else "Half")
        self.btn_size.setObjectName("WidgetMiniBtn")
        self.btn_size.setToolTip("Toggle widget width (Full Wide / Half width)")
        self.btn_size.setFixedSize(48, 22)
        self.btn_size.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_size.clicked.connect(self.toggle_size)
        header_layout.addWidget(self.btn_size)

        # Collapse / Expand button
        self.btn_collapse = QPushButton("▾")
        self.btn_collapse.setObjectName("WidgetMiniBtn")
        self.btn_collapse.setToolTip("Collapse / Expand content")
        self.btn_collapse.setFixedSize(24, 22)
        self.btn_collapse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_collapse.clicked.connect(self.toggle_collapse)
        header_layout.addWidget(self.btn_collapse)

        self.main_layout.addWidget(self.header)

        # Content container
        self.body_container = QWidget()
        self.body_container.setObjectName("WidgetBody")
        # Ensure child body doesn't swallow drag-and-drop events
        self.body_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.body_layout = QVBoxLayout(self.body_container)
        self.body_layout.setContentsMargins(0, 4, 0, 0)
        self.body_layout.setSpacing(6)

        self.content_label = QLabel("Scanning...")
        self.content_label.setObjectName("SpecCardContent")
        self.content_label.setFont(QFont("Segoe UI", 10))
        self.content_label.setWordWrap(True)
        self.content_label.setTextFormat(Qt.TextFormat.RichText)
        self.body_layout.addWidget(self.content_label)

        self.main_layout.addWidget(self.body_container)

    def set_content_html(self, html: str):
        self.content_label.setText(html)

    def toggle_size(self):
        """Toggle between 2 columns (full width) and 1 column (half width)."""
        self.col_span = 1 if self.col_span == 2 else 2
        self.btn_size.setText("Wide" if self.col_span == 2 else "Half")
        if self.dashboard:
            self.dashboard.relayout_cards()

    def toggle_collapse(self):
        """Toggle collapse/expand state."""
        self.is_collapsed = not self.is_collapsed
        self.body_container.setVisible(not self.is_collapsed)
        self.btn_collapse.setText("▸" if self.is_collapsed else "▾")
        if self.dashboard:
            self.dashboard.save_state()

    def set_state(self, col_span: int, is_collapsed: bool):
        self.col_span = 2 if col_span == 2 else 1
        self.btn_size.setText("Wide" if self.col_span == 2 else "Half")
        self.is_collapsed = bool(is_collapsed)
        self.body_container.setVisible(not self.is_collapsed)
        self.btn_collapse.setText("▸" if self.is_collapsed else "▾")

    # ---- Mouse & Drag/Drop Handling ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Drag can be started anywhere on the header or card body (except child buttons)
            child = self.childAt(event.position().toPoint())
            if child not in (self.btn_up, self.btn_down, self.btn_size, self.btn_collapse):
                self._drag_start_pos = event.position().toPoint()
                self.drag_handle.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self._drag_start_pos:
            return super().mouseMoveEvent(event)

        dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
        if dist >= QApplication.startDragDistance():
            self._start_drag()
            self._drag_start_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self.drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_TYPE_CARD, self.card_id.encode("utf-8"))
        drag.setMimeData(mime)

        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        self.render(pixmap)

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(min(pixmap.width() // 2, 80), 18))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE_CARD):
            event.acceptProposedAction()
            self.setProperty("dragTarget", "true")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE_CARD):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragTarget", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        event.accept()

    def dropEvent(self, event):
        self.setProperty("dragTarget", "false")
        self.style().unpolish(self)
        self.style().polish(self)

        if event.mimeData().hasFormat(MIME_TYPE_CARD):
            source_id = bytes(event.mimeData().data(MIME_TYPE_CARD)).decode("utf-8")
            if source_id != self.card_id and self.dashboard:
                self.dashboard.reorder_cards_by_drop(source_id, self.card_id)
                event.acceptProposedAction()
                return
        event.ignore()


class RamWidgetCard(WidgetCard):
    """Specialized RAM Widget Card with an interactive gradient usage bar."""

    def __init__(self, parent_dashboard=None):
        super().__init__("ram", "🧠  RAM", parent_dashboard)
        self.ram_bar = QProgressBar()
        self.ram_bar.setObjectName("RamBar")
        self.ram_bar.setMinimum(0)
        self.ram_bar.setMaximum(100)
        self.ram_bar.setValue(0)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setFixedHeight(12)
        self.body_layout.addWidget(self.ram_bar)

    def update_ram(self, used_gb: float, total_gb: float, percent: float):
        html = (
            f"<span style='color:#ffffff; font-size:11pt; font-weight:bold;'>{used_gb} GB</span> "
            f"<span style='color:#a6b9d0;'>/ {total_gb} GB</span>  "
            f"<span style='color:#00f0ff; font-weight:bold;'>({percent}%)</span>"
        )
        self.content_label.setText(html)
        self.ram_bar.setValue(int(percent))


# Rows rendered in the Neofetch system identity panel: (caption, sys_info key)
INFO_ROWS = [
    ("OS",          "OS"),
    ("Host",        "Host"),
    ("Kernel",      "Kernel"),
    ("Uptime",      "Uptime"),
    ("Resolution",  "Resolution"),
    ("DE / Theme",  "Theme"),
    ("Shell",       "Shell"),
    ("Terminal",    "Terminal"),
    ("CPU",         "CPU"),
    ("GPU",         "GPU"),
    ("Memory",      "Memory"),
    ("Swap / Page", "Swap"),
    ("Disk (Root)", "Disk"),
    ("Local IP",    "Local IP"),
    ("Python",      "Python"),
    ("Timezone",    "Timezone"),
]

DEFAULT_CARD_ORDER = ["cpu", "gpu", "ram", "disk", "network", "mobo"]


class OverviewTab(QWidget):
    """
    Split dashboard view showing Neofetch-level system identity (left) and
    reorderable / resizable phone-style widget cards (right).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._info_data = {}
        self._card_order = list(DEFAULT_CARD_ORDER)
        self._cards: dict[str, WidgetCard] = {}
        self._setup_ui()
        self._load_saved_layout()
        self._start_polling()

    def _setup_ui(self):
        """Build the split-pane overview layout."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)

        # ---- Left Panel: Neofetch OS Identity Badge ----
        self.left_panel = QFrame()
        self.left_panel.setObjectName("OverviewLeftPanel")
        self.left_panel.setFixedWidth(510)
        self.left_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(18, 18, 18, 18)
        left_layout.setSpacing(10)

        # Logo + identity header
        self.os_key = detect_os_key()
        accent = LOGO_ACCENTS.get(self.os_key, "#00f0ff")

        top_header = QHBoxLayout()
        top_header.setSpacing(16)
        top_header.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.logo_label = QLabel()
        self.logo_label.setObjectName("OsLogo")
        self.logo_label.setFixedSize(110, 110)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = render_logo(self.os_key, size=110)
        if pixmap:
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText(DISPLAY_NAMES.get(self.os_key, "?"))
            self.logo_label.setStyleSheet(f"color: {accent}; font-size: 15px; font-weight: 700;")
        top_header.addWidget(self.logo_label)

        identity = QVBoxLayout()
        identity.setSpacing(2)
        identity.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.host_label = QLabel("…")
        self.host_label.setObjectName("OverviewHost")
        self.host_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self.host_label.setStyleSheet("color: #00f0ff;")
        identity.addWidget(self.host_label)

        self.platform_label = QLabel(DISPLAY_NAMES.get(self.os_key, ""))
        self.platform_label.setObjectName("OverviewPlatform")
        self.platform_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.platform_label.setStyleSheet("color: #d8e2ed;")
        identity.addWidget(self.platform_label)

        badge_sub = QLabel("⚡ System Telemetry & Environment")
        badge_sub.setFont(QFont("Segoe UI", 9))
        badge_sub.setStyleSheet("color: #7e93af;")
        identity.addWidget(badge_sub)

        top_header.addLayout(identity, stretch=1)
        left_layout.addLayout(top_header)

        # Separator line
        rule = QFrame()
        rule.setFixedHeight(1)
        rule.setStyleSheet("background-color: #2f3e58;")
        left_layout.addWidget(rule)

        # Scrollable Neofetch spec list
        info_scroll = QScrollArea()
        info_scroll.setObjectName("NeofetchScrollArea")
        info_scroll.setWidgetResizable(True)
        info_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_scroll.setStyleSheet("background-color: transparent; border: none;")

        info_container = QWidget()
        info_container.setStyleSheet("background-color: transparent;")
        info_grid = QGridLayout(info_container)
        info_grid.setContentsMargins(4, 4, 6, 4)
        info_grid.setHorizontalSpacing(12)
        info_grid.setVerticalSpacing(6)

        self.info_values: dict[str, QLabel] = {}

        for row, (caption, key) in enumerate(INFO_ROWS):
            key_label = QLabel(caption)
            key_label.setObjectName("InfoKey")
            key_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            key_label.setStyleSheet("color: #00f0ff;")
            key_label.setFixedWidth(80)

            value_label = QLabel("…")
            value_label.setObjectName("InfoValue")
            value_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
            value_label.setWordWrap(True)
            value_label.setStyleSheet("color: #ffffff;")

            info_grid.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignTop)
            info_grid.addWidget(value_label, row, 1)
            self.info_values[key] = value_label

        info_grid.setColumnStretch(1, 1)
        info_scroll.setWidget(info_container)
        left_layout.addWidget(info_scroll, stretch=1)

        # Signature Neofetch ANSI Color Bar at bottom
        palette_frame = QFrame()
        palette_layout = QHBoxLayout(palette_frame)
        palette_layout.setContentsMargins(4, 6, 4, 2)
        palette_layout.setSpacing(6)

        ansi_colors = [
            "#282c34", "#e06c75", "#98c379", "#e5c07b",
            "#61afef", "#c678dd", "#56b6c2", "#abb2bf"
        ]
        for color in ansi_colors:
            block = QFrame()
            block.setFixedHeight(12)
            block.setStyleSheet(f"background-color: {color}; border-radius: 3px;")
            palette_layout.addWidget(block)

        left_layout.addWidget(palette_frame)
        main_layout.addWidget(self.left_panel)

        # ---- Right Panel: Hardware Spec Widgets ----
        right_panel = QWidget()
        right_panel_layout = QVBoxLayout(right_panel)
        right_panel_layout.setContentsMargins(0, 0, 0, 0)
        right_panel_layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        dashboard_title = QLabel("📱  Hardware Widgets")
        dashboard_title.setObjectName("DashboardSectionTitle")
        dashboard_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        dashboard_title.setStyleSheet("color: #00f0ff;")
        toolbar.addWidget(dashboard_title)

        toolbar.addStretch()

        reset_btn = QPushButton("↺  Reset Layout")
        reset_btn.setObjectName("ResetLayoutBtn")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setToolTip("Restore widgets to their default phone order and full width")
        reset_btn.clicked.connect(self.reset_layout)
        toolbar.addWidget(reset_btn)

        right_panel_layout.addLayout(toolbar)

        # Scroll area containing widget grid
        self.scroll = QScrollArea()
        self.scroll.setObjectName("OverviewScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("OverviewGridContainer")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 0, 8, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setColumnStretch(0, 1)
        self.grid_layout.setColumnStretch(1, 1)

        self.scroll.setWidget(self.grid_container)
        right_panel_layout.addWidget(self.scroll, stretch=1)

        main_layout.addWidget(right_panel, stretch=1)

        # Initialize cards
        self._cards["cpu"] = WidgetCard("cpu", "🔲  CPU", self)
        self._cards["gpu"] = WidgetCard("gpu", "🎮  GPU", self)
        self._cards["ram"] = RamWidgetCard(self)
        self._cards["disk"] = WidgetCard("disk", "💾  Storage", self)
        self._cards["network"] = WidgetCard("network", "🌐  Network", self)
        self._cards["mobo"] = WidgetCard("mobo", "🖥️  Motherboard / BIOS", self)

    def relayout_cards(self):
        """Re-populate grid according to current card order and column spans."""
        self.grid_container.setUpdatesEnabled(False)
        try:
            while self.grid_layout.count() > 0:
                self.grid_layout.takeAt(0)

            current_row = 0
            current_col = 0

            for card_id in self._card_order:
                card = self._cards.get(card_id)
                if not card:
                    continue

                if card.col_span == 2:
                    # Full width card must start on a new row
                    if current_col != 0:
                        current_row += 1
                        current_col = 0
                    self.grid_layout.addWidget(card, current_row, 0, 1, 2)
                    current_row += 1
                    current_col = 0
                else:
                    # Half width card takes 1 slot
                    self.grid_layout.addWidget(card, current_row, current_col, 1, 1)
                    current_col += 1
                    if current_col >= 2:
                        current_col = 0
                        current_row += 1

            # Add vertical stretch at the bottom
            self.grid_layout.setRowStretch(current_row + (1 if current_col != 0 else 0), 1)
        finally:
            self.grid_container.setUpdatesEnabled(True)
        self.save_state()

    def move_card(self, card_id: str, direction: int):
        """Move card up (-1) or down (+1) in order."""
        if card_id not in self._card_order:
            return
        idx = self._card_order.index(card_id)
        new_idx = idx + direction
        if 0 <= new_idx < len(self._card_order):
            self._card_order.pop(idx)
            self._card_order.insert(new_idx, card_id)
            self.relayout_cards()

    def reorder_cards_by_drop(self, source_id: str, target_id: str):
        """
        Reorder cards when one card is dropped onto another.
        Handles both upward and downward dragging seamlessly.
        """
        if source_id not in self._card_order or target_id not in self._card_order:
            return
        src_idx = self._card_order.index(source_id)
        tgt_idx = self._card_order.index(target_id)
        if src_idx == tgt_idx:
            return

        self._card_order.pop(src_idx)
        self._card_order.insert(tgt_idx, source_id)
        self.relayout_cards()

    def reset_layout(self):
        """Reset layout back to default."""
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.clear()
        self._card_order = list(DEFAULT_CARD_ORDER)
        for card in self._cards.values():
            card.set_state(col_span=2, is_collapsed=False)
        self.relayout_cards()

    def save_state(self):
        """Persist card order and widget states into QSettings."""
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        settings.setValue("card_order", json.dumps(self._card_order))
        card_data = {}
        for card_id, card in self._cards.items():
            card_data[card_id] = {
                "col_span": card.col_span,
                "is_collapsed": card.is_collapsed,
            }
        settings.setValue("card_states", json.dumps(card_data))

    def _load_saved_layout(self):
        """Restore layout from QSettings if available."""
        settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        raw_order = settings.value("card_order")
        if raw_order:
            try:
                saved_order = json.loads(raw_order)
                valid_order = [cid for cid in saved_order if cid in self._cards]
                for missing in DEFAULT_CARD_ORDER:
                    if missing not in valid_order:
                        valid_order.append(missing)
                self._card_order = valid_order
            except Exception:
                self._card_order = list(DEFAULT_CARD_ORDER)

        raw_states = settings.value("card_states")
        if raw_states:
            try:
                states = json.loads(raw_states)
                for card_id, st in states.items():
                    if card_id in self._cards:
                        self._cards[card_id].set_state(
                            col_span=st.get("col_span", 2),
                            is_collapsed=st.get("is_collapsed", False),
                        )
            except Exception:
                pass

        self.relayout_cards()

    # -------------------------------------------------------------------------
    # Data Polling & UI Updates
    # -------------------------------------------------------------------------

    def _start_polling(self):
        """Start background worker and set up auto-refresh every 10 seconds."""
        self._worker = SystemInfoWorker()
        self._worker.info_ready.connect(self._update_display)
        self._worker.start()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(10_000)

    def _refresh(self):
        if not self._worker.isRunning():
            self._worker = SystemInfoWorker()
            self._worker.info_ready.connect(self._update_display)
            self._worker.start()

    def _update_display(self, data: dict):
        """Receive telemetry dict and update all UI elements with high-contrast text."""
        self._info_data = data

        # Left panel: OS badge
        summary = get_system_summary()
        self.host_label.setText(summary.get("user_host", "unknown"))
        for key, label in self.info_values.items():
            label.setText(str(summary.get(key, "—")))

        # Right panel: Cards
        # CPU
        cpu = data.get("cpu", {})
        cpu_text = (
            f"<span style='color:#ffffff; font-size:11pt; font-weight:bold;'>{cpu.get('name', 'N/A')}</span><br>"
            f"<span style='color:#a6b9d0;'>Cores:</span> <b style='color:#ffffff;'>{cpu.get('physical_cores', '?')}</b> physical / "
            f"<b style='color:#ffffff;'>{cpu.get('logical_cores', '?')}</b> logical<br>"
            f"<span style='color:#a6b9d0;'>Frequency:</span> <b style='color:#ffffff;'>{cpu.get('current_freq_mhz', 0)} MHz</b> "
            f"<span style='color:#7e93af;'>(max {cpu.get('max_freq_mhz', 0)} MHz)</span><br>"
            f"<span style='color:#a6b9d0;'>Usage:</span> <span style='color:#00f0ff; font-weight:bold; font-size:10.5pt;'>{cpu.get('usage_percent', 0)}%</span>"
        )
        self._cards["cpu"].set_content_html(cpu_text)

        # GPU
        gpus = data.get("gpu", [])
        gpu_lines = []
        for gpu in gpus:
            temp = gpu.get('temp_c', 'N/A')
            temp_color = "#ffab40" if str(temp).isdigit() and int(temp) > 70 else "#00f0ff"
            gpu_lines.append(
                f"<span style='color:#ffffff; font-size:11pt; font-weight:bold;'>{gpu.get('name', 'N/A')}</span><br>"
                f"<span style='color:#a6b9d0;'>VRAM:</span> <b style='color:#ffffff;'>{gpu.get('vram_total_mb', 'N/A')} MB</b> "
                f"<span style='color:#a6b9d0;'>(Used: <b style='color:#ffffff;'>{gpu.get('vram_used_mb', 'N/A')} MB</b>)</span><br>"
                f"<span style='color:#a6b9d0;'>Temp:</span> <span style='color:{temp_color}; font-weight:bold;'>{temp}°C</span>"
            )
        self._cards["gpu"].set_content_html("<br><br>".join(gpu_lines) if gpu_lines else "<span style='color:#a6b9d0;'>No GPU detected</span>")

        # RAM
        ram = data.get("ram", {})
        ram_card = self._cards.get("ram")
        if isinstance(ram_card, RamWidgetCard):
            ram_card.update_ram(
                used_gb=ram.get("used_gb", 0),
                total_gb=ram.get("total_gb", 0),
                percent=ram.get("percent", 0),
            )

        # Storage
        disks = data.get("disks", [])
        disk_lines = []
        for d in disks:
            disk_lines.append(
                f"<b style='color:#ffffff; font-size:10.5pt;'>{d.get('device', 'N/A')}</b> "
                f"<span style='color:#00f0ff;'>→ {d.get('mountpoint', '')}</span><br>"
                f"<span style='color:#a6b9d0;'>Type:</span> <b style='color:#ffffff;'>{d.get('fstype', 'N/A')}</b> | "
                f"<span style='color:#a6b9d0;'>Used:</span> <b style='color:#ffffff;'>{d.get('used_gb', 0)}</b> / "
                f"<b style='color:#ffffff;'>{d.get('total_gb', 0)} GB</b> "
                f"<span style='color:#00f0ff; font-weight:bold;'>({d.get('percent', 0)}%)</span>"
            )
        self._cards["disk"].set_content_html("<br><br>".join(disk_lines) if disk_lines else "<span style='color:#a6b9d0;'>No disks found</span>")

        # Network
        nets = data.get("network", [])
        net_lines = []
        for n in nets:
            status = "<span style='color:#00e676; font-weight:bold;'>🟢 UP</span>" if n.get("is_up") else "<span style='color:#ff5252; font-weight:bold;'>🔴 DOWN</span>"
            ipv4 = n.get("ipv4", "—")
            if ipv4 and ipv4 != "—":
                net_lines.append(
                    f"<b style='color:#ffffff; font-size:10.5pt;'>{n.get('name', 'N/A')}</b> {status}<br>"
                    f"<span style='color:#a6b9d0;'>IPv4:</span> <b style='color:#00f0ff;'>{ipv4}</b> | "
                    f"<span style='color:#a6b9d0;'>MAC:</span> <b style='color:#ffffff;'>{n.get('mac', 'N/A')}</b> | "
                    f"<span style='color:#a6b9d0;'>Speed:</span> <b style='color:#ffffff;'>{n.get('speed_mbps', 0)} Mbps</b>"
                )
        self._cards["network"].set_content_html("<br><br>".join(net_lines) if net_lines else "<span style='color:#a6b9d0;'>No active interfaces</span>")

        # Motherboard / BIOS
        mobo = data.get("motherboard", {})
        mobo_text = (
            f"<span style='color:#ffffff; font-size:11pt; font-weight:bold;'>{mobo.get('manufacturer', 'N/A')} — {mobo.get('product', 'N/A')}</span><br>"
            f"<span style='color:#a6b9d0;'>BIOS:</span> <b style='color:#ffffff;'>{mobo.get('bios_vendor', 'N/A')}</b> "
            f"<span style='color:#00f0ff; font-weight:bold;'>v{mobo.get('bios_version', 'N/A')}</span>"
        )
        self._cards["mobo"].set_content_html(mobo_text)
