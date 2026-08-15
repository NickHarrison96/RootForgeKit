from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal, Qt

class RequirementItemWidget(QWidget):
    verify_requested = Signal(str)

    def __init__(self, key: str, display_name: str):
        super().__init__()
        self.key = key
        self.display_name = display_name
        self.status = "unchecked"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)

        self.name_label = QLabel(f"• {display_name}")
        self.status_badge = QLabel("[ ? Unchecked ]")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setStyleSheet("color: gray; font-weight: bold;")

        self.verify_btn = QPushButton("Verify")
        self.verify_btn.setFixedWidth(75)
        self.verify_btn.clicked.connect(lambda: self.verify_requested.emit(self.key))

        layout.addWidget(self.name_label, stretch=1)
        layout.addWidget(self.status_badge)
        layout.addWidget(self.verify_btn)

    def set_status(self, is_ok: bool):
        if is_ok:
            self.status = "ok"
            self.status_badge.setText("[ ✓ Ready ]")
            self.status_badge.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status = "missing"
            self.status_badge.setText("[ ✗ Missing ]")
            self.status_badge.setStyleSheet("color: red; font-weight: bold;")
