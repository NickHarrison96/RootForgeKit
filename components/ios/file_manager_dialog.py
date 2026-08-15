# =============================================================================
# RootForgeKit — iOS Files & Apps Manager Modal (PySide6)
# Multi-tab AFC File Browser, App Container Inspector, and DCIM Media Manager
# =============================================================================

import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QLabel, QFileDialog, QTabWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QWidget, QFrame
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from utils.ios_core.file_system import FileSystemManager, AFCException
from utils.resource_manager import safe_run_command


class IosFileLoadWorker(QThread):
    items_loaded = Signal(list, str)   # items [(name, is_dir)], path
    error_signal = Signal(str)

    def __init__(self, path="/"):
        super().__init__()
        self.path = path

    def run(self):
        try:
            fs = FileSystemManager()
            names = fs.list_dir(self.path)
            items = []
            for name in names:
                if name in (".", ".."):
                    continue
                item_path = (self.path.rstrip("/") + "/" + name).replace("//", "/")
                is_directory = fs.is_dir(item_path)
                items.append((name, is_directory))
            items.sort(key=lambda x: (not x[1], x[0].lower()))
            self.items_loaded.emit(items, self.path)
        except Exception as e:
            self.error_signal.emit(str(e))


class IosAppsWorker(QThread):
    apps_loaded = Signal(list)
    error_signal = Signal(str)

    def run(self):
        ok, out = safe_run_command(["pymobiledevice3", "apps", "list"], timeout=15)
        if not ok:
            # Fallback to python module execution
            import sys
            ok, out = safe_run_command([sys.executable, "-m", "pymobiledevice3", "apps", "list"], timeout=15)
        
        if not ok:
            self.error_signal.emit(f"Failed to query installed apps: {out}")
            return

        import json
        try:
            data = json.loads(out)
            apps = []
            if isinstance(data, dict):
                for bundle_id, info in data.items():
                    if isinstance(info, dict):
                        apps.append({
                            "name": info.get("CFBundleDisplayName") or info.get("CFBundleName", bundle_id),
                            "bundle_id": bundle_id,
                            "version": info.get("CFBundleShortVersionString", "Unknown"),
                            "type": info.get("ApplicationType", "User"),
                            "container": info.get("Container", info.get("Path", "N/A"))
                        })
            apps.sort(key=lambda x: str(x["name"]).lower())
            self.apps_loaded.emit(apps)
        except Exception as e:
            self.error_signal.emit(f"Failed parsing apps list: {e}")


class IosFileManagerDialog(QDialog):
    """
    Comprehensive iOS Files & Apps Manager dialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 iOS Files & Apps Manager (AFC / HouseArrest)")
        self.resize(880, 580)
        self.current_path = "/"
        self._init_ui()
        self._load_afc_directory("/")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setFont(QFont("Segoe UI", 10))

        # ── Tab 1: AFC File System ──────────────────────────────────────────
        afc_tab = QWidget()
        afc_layout = QVBoxLayout(afc_tab)
        afc_layout.setContentsMargins(10, 10, 10, 10)
        afc_layout.setSpacing(8)

        # Nav bar
        nav_layout = QHBoxLayout()
        btn_up = QPushButton("⬆ Up")
        btn_up.clicked.connect(self._navigate_up)
        nav_layout.addWidget(btn_up)

        self.path_input = QLineEdit(self.current_path)
        self.path_input.returnPressed.connect(self._on_go_clicked)
        nav_layout.addWidget(self.path_input, stretch=1)

        btn_go = QPushButton("Go")
        btn_go.clicked.connect(self._on_go_clicked)
        nav_layout.addWidget(btn_go)

        btn_refresh = QPushButton("🔄")
        btn_refresh.setToolTip("Refresh current directory")
        btn_refresh.clicked.connect(lambda: self._load_afc_directory(self.current_path))
        nav_layout.addWidget(btn_refresh)
        afc_layout.addLayout(nav_layout)

        # File list
        self.file_list = QListWidget()
        self.file_list.setFont(QFont("Consolas", 10))
        self.file_list.setStyleSheet(
            "background-color: #161b22; color: #e6edf3; border: 1px solid #30363d; "
            "border-radius: 6px; padding: 6px;"
        )
        self.file_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        afc_layout.addWidget(self.file_list, stretch=1)

        # Action toolbar
        action_bar = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #8b949e;")
        action_bar.addWidget(self.status_label, stretch=1)

        btn_pull = QPushButton("📥 Pull File")
        btn_pull.setToolTip("Download selected file to PC")
        btn_pull.clicked.connect(self._pull_file)
        action_bar.addWidget(btn_pull)

        btn_push = QPushButton("📤 Push File")
        btn_push.setToolTip("Upload file from PC to device")
        btn_push.clicked.connect(self._push_file)
        action_bar.addWidget(btn_push)

        btn_mkdir = QPushButton("📁 New Folder")
        btn_mkdir.clicked.connect(self._make_folder)
        action_bar.addWidget(btn_mkdir)

        afc_layout.addLayout(action_bar)
        self.tabs.addTab(afc_tab, "📂 File System (AFC)")

        # ── Tab 2: Apps & Containers ────────────────────────────────────────
        apps_tab = QWidget()
        apps_layout = QVBoxLayout(apps_tab)
        apps_layout.setContentsMargins(10, 10, 10, 10)
        apps_layout.setSpacing(8)

        apps_top = QHBoxLayout()
        self.apps_status = QLabel("Click 'Load Installed Apps' to query device applications.")
        self.apps_status.setStyleSheet("color: #8b949e;")
        apps_top.addWidget(self.apps_status, stretch=1)

        btn_load_apps = QPushButton("🔄 Load Installed Apps")
        btn_load_apps.clicked.connect(self._load_apps)
        apps_top.addWidget(btn_load_apps)
        apps_layout.addLayout(apps_top)

        self.apps_table = QTableWidget(0, 5)
        self.apps_table.setHorizontalHeaderLabels(["App Name", "Bundle ID", "Version", "Type", "Container Path"])
        self.apps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.apps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.apps_table.setStyleSheet("background-color: #161b22; color: #e6edf3; gridline-color: #30363d;")
        apps_layout.addWidget(self.apps_table, stretch=1)

        self.tabs.addTab(apps_tab, "📦 Apps & Containers")

        # ── Tab 3: DCIM Media ────────────────────────────────────────────────
        media_tab = QWidget()
        media_layout = QVBoxLayout(media_tab)
        media_layout.setContentsMargins(10, 10, 10, 10)

        lbl_media = QLabel("📷 DCIM Media Quick Access")
        lbl_media.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        media_layout.addWidget(lbl_media)

        lbl_media_desc = QLabel("Quickly browse and download photos and videos stored in /Media/DCIM.")
        lbl_media_desc.setStyleSheet("color: #8b949e;")
        media_layout.addWidget(lbl_media_desc)

        btn_open_dcim = QPushButton("🖼️ Open /Media/DCIM Folder")
        btn_open_dcim.clicked.connect(lambda: self._load_afc_directory("/Media/DCIM"))
        media_layout.addWidget(btn_open_dcim)
        media_layout.addStretch()

        self.tabs.addTab(media_tab, "📷 DCIM Media")

        layout.addWidget(self.tabs, stretch=1)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _load_afc_directory(self, path: str):
        self.status_label.setText(f"Loading {path}...")
        self.file_list.clear()

        self._worker = IosFileLoadWorker(path)
        self._worker.items_loaded.connect(self._on_afc_loaded)
        self._worker.error_signal.connect(self._on_afc_error)
        self._worker.start()

    def _on_afc_loaded(self, items, path):
        self.current_path = path
        self.path_input.setText(path)
        self.file_list.clear()

        for filename, is_dir in items:
            icon = "📁 " if is_dir else "📄 "
            item = QListWidgetItem(f"{icon}{filename}")
            item.setData(Qt.ItemDataRole.UserRole, (filename, is_dir))
            self.file_list.addItem(item)

        self.status_label.setText(f"Loaded {len(items)} item(s)")

    def _on_afc_error(self, err_msg):
        self.status_label.setText(f"Error: {err_msg}")
        QMessageBox.warning(self, "AFC Error", f"Failed to list directory:\n{err_msg}")

    def _navigate_up(self):
        if self.current_path == "/" or not self.current_path:
            return
        parent_dir = os.path.dirname(self.current_path.rstrip("/"))
        self._load_afc_directory(parent_dir or "/")

    def _on_go_clicked(self):
        target = self.path_input.text().strip()
        self._load_afc_directory(target)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        filename, is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            new_path = (self.current_path.rstrip("/") + "/" + filename).replace("//", "/")
            self._load_afc_directory(new_path)
        else:
            self._pull_file()

    def _pull_file(self):
        item = self.file_list.currentItem()
        if not item:
            QMessageBox.information(self, "Select File", "Select a file to download.")
            return

        filename, is_dir = item.data(Qt.ItemDataRole.UserRole)
        if is_dir:
            QMessageBox.warning(self, "Folder Selected", "Please select a file, not a directory.")
            return

        remote_path = (self.current_path.rstrip("/") + "/" + filename).replace("//", "/")
        save_path, _ = QFileDialog.getSaveFileName(self, "Save File", filename)
        if not save_path:
            return

        self.status_label.setText(f"Pulling {filename}...")
        try:
            fs = FileSystemManager()
            fs.download_file(remote_path, save_path)
            self.status_label.setText(f"Successfully downloaded to {save_path}")
            QMessageBox.information(self, "Success", f"File saved to:\n{save_path}")
        except Exception as e:
            self.status_label.setText("Pull failed")
            QMessageBox.critical(self, "Error", f"Failed to download file:\n{e}")

    def _push_file(self):
        local_path, _ = QFileDialog.getOpenFileName(self, "Select File to Upload")
        if not local_path:
            return

        filename = os.path.basename(local_path)
        remote_target = (self.current_path.rstrip("/") + "/" + filename).replace("//", "/")

        self.status_label.setText(f"Uploading {filename}...")
        try:
            fs = FileSystemManager()
            fs.upload_file(local_path, remote_target)
            self.status_label.setText(f"Uploaded {filename}")
            QMessageBox.information(self, "Success", f"File uploaded to:\n{remote_target}")
            self._load_afc_directory(self.current_path)
        except Exception as e:
            self.status_label.setText("Upload failed")
            QMessageBox.critical(self, "Error", f"Failed to upload file:\n{e}")

    def _make_folder(self):
        from PySide6.QtWidgets import QInputDialog
        folder_name, ok = QInputDialog.getText(self, "New Folder", "Enter new folder name:")
        if ok and folder_name.strip():
            new_path = (self.current_path.rstrip("/") + "/" + folder_name.strip()).replace("//", "/")
            try:
                fs = FileSystemManager()
                fs.make_dir(new_path)
                self._load_afc_directory(self.current_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to create directory:\n{e}")

    def _load_apps(self):
        self.apps_status.setText("Querying installed applications via pymobiledevice3...")
        self.apps_table.setRowCount(0)

        self._apps_worker = IosAppsWorker()
        self._apps_worker.apps_loaded.connect(self._on_apps_loaded)
        self._apps_worker.error_signal.connect(self._on_apps_error)
        self._apps_worker.start()

    def _on_apps_loaded(self, apps):
        self.apps_table.setRowCount(len(apps))
        for row, app in enumerate(apps):
            self.apps_table.setItem(row, 0, QTableWidgetItem(str(app["name"])))
            self.apps_table.setItem(row, 1, QTableWidgetItem(str(app["bundle_id"])))
            self.apps_table.setItem(row, 2, QTableWidgetItem(str(app["version"])))
            self.apps_table.setItem(row, 3, QTableWidgetItem(str(app["type"])))
            self.apps_table.setItem(row, 4, QTableWidgetItem(str(app["container"])))
        self.apps_status.setText(f"Loaded {len(apps)} installed app(s)")

    def _on_apps_error(self, err_msg):
        self.apps_status.setText(f"Error loading apps")
        QMessageBox.warning(self, "Apps Query Error", err_msg)
