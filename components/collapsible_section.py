# =============================================================================
# RootForgeKit — Collapsible Section Widget
# Header button + content container, used for accordion-style grouping of
# tool cards. Plain show/hide: no height animation, so the expanded height is
# always whatever the layout actually computes (the previous dropdown widget
# animated maximumHeight against a hand-measured height that skipped every
# layout-held child, and clipped its own content to ~100px).
# =============================================================================

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QPushButton, QVBoxLayout, QWidget


class CollapsibleSection(QWidget):
    """A widget that can be collapsed/expanded via its header button."""

    def __init__(self, title: str, expanded: bool = False, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = QPushButton()
        self._header.setObjectName("CollapsibleHeader")
        self._header.setCheckable(True)
        self._header.setChecked(expanded)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        self._update_header_text()
        outer.addWidget(self._header)

        self._content = QFrame()
        self._content.setObjectName("CollapsibleContent")
        self._content.setVisible(expanded)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 10, 12, 10)
        self._content_layout.setSpacing(8)
        outer.addWidget(self._content)

    def _update_header_text(self) -> None:
        arrow = "▼" if self._expanded else "▶"
        self._header.setText(f"  {arrow}  {self._title}")

    def _toggle(self) -> None:
        self.set_expanded(not self._expanded)
        # setChecked would re-emit clicked; block it for the duration.
        self._header.blockSignals(True)
        self._header.setChecked(self._expanded)
        self._header.blockSignals(False)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_expanded(self, value: bool) -> None:
        if value == self._expanded:
            return
        self._expanded = value
        self._content.setVisible(value)
        self._update_header_text()
        self._header.setChecked(value)
