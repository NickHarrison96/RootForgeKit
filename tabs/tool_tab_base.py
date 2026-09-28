# =============================================================================
# RootForgeKit — Shared scaffold for the Tech / Gamer tool tabs.
#
# Both tabs are the same shape: a scrollable stack of CollapsibleSections
# holding ToolCards, split above a live terminal console. This base owns that
# layout, the CommandBuilder lookup, URL launching, winget install/launch, and
# the one-shot background winget inventory used to show real install states.
# =============================================================================

import os
import subprocess
import threading
import time
import webbrowser

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSplitter,
    QVBoxLayout, QWidget,
)

from components.collapsible_section import CollapsibleSection
from components.terminal_widget import TerminalConsoleWidget
from components.tool_card import ToolCard
from utils.batch_installer import PRESET_PROFILES, BatchInstallWorker
from utils.command_builder import CommandBuilder, requires_admin
from utils.host_inventory import read_installed_programs


# Console palette. Kept as module constants so every narration line uses the
# same meaning for a colour instead of ad-hoc hex strings.
INFO = "#00e5ff"   # what the tab is doing right now
OK = "#00e676"     # succeeded
WARN = "#f0a500"   # succeeded but worth your attention (updates, skips)
ERR = "#ff5252"    # failed
DIM = "#78909c"    # background detail (counts, raw tool chatter)


def _arp_match(card_name: str, arp_name: str) -> bool:
    """Does an Add/Remove Programs entry correspond to this card?

    winget reports packages installed outside winget under an `ARP\\` pseudo-id
    with only their DisplayName — "Discord", "MSYS2", "7-Zip 26.03 (x64)",
    "Ollama version 0.33.3". The card only knows a clean name ("Discord",
    "7-Zip", "Ollama"), so match on exact text or on the clean name followed
    by a version/qualifier.

    The length floor and the "next char must be a digit, space or paren"
    check exist to stop "Git" from claiming "GitHub Desktop".
    """
    card = card_name.strip().lower()
    arp = arp_name.strip().lower()
    if not card or not arp:
        return False
    if arp == card:
        return True
    if len(card) >= 3 and arp.startswith(card):
        rest = arp[len(card):]
        return rest[0].isdigit() or rest[0] in " ("
    return False


class _WingetMissing(Exception):
    """winget.exe is not installed (or not on PATH)."""


class _WingetTimeout(Exception):
    """winget list exceeded its time budget."""


class WingetIndexWorker(QThread):
    """
    One `winget list` for every package, off the UI thread.

    Deliberately NOT run with `--source winget`: that flag filters the result
    down to packages winget itself manages, which silently drops anything the
    user installed from a vendor's own installer. On this test machine Discord
    and MSYS2 were both present in Add/Remove Programs yet reported as
    "missing" because of it. Without the flag winget lists the host's own
    inventory too, under an `ARP\\` pseudo-id.

    Columns are read by slicing at the header's offsets rather than splitting
    on runs of spaces — some DisplayNames genuinely contain a double space
    ("Microsoft Visual C++ 2010  x86 Redistributable"), which breaks a naive
    split and shifts every field to the left of it.

    Returns a dict:
        {"by_id": {id: (version, available)}, "arp": [(name, version), ...]}
    or, on failure, {"error": "<human-readable reason>"}.
    """

    index_ready = Signal(dict)

    _COLUMNS = ("Name", "Id", "Version", "Available", "Source")

    def __init__(self, parent=None):
        super().__init__(parent)

    @classmethod
    def _offsets(cls, header: str) -> list[tuple[str, int]]:
        found = [(name, header.find(name)) for name in cls._COLUMNS]
        # Sort by OFFSET, not by column name — a bare sorted() on these
        # tuples orders them alphabetically (Available, Id, Name, ...)
        # and every slice then reads the wrong span of the line.
        return sorted(((n, i) for n, i in found if i >= 0),
                      key=lambda kv: kv[1])

    @staticmethod
    def _field(line: str, offsets: list[tuple[str, int]], wanted: str) -> str:
        for idx, (name, start) in enumerate(offsets):
            if name != wanted:
                continue
            if start >= len(line):
                return ""
            end = offsets[idx + 1][1] if idx + 1 < len(offsets) else None
            return line[start:end].strip()
        return ""

    @classmethod
    def _parse(cls, stdout: str) -> dict:
        by_id: dict[str, tuple] = {}
        arp: list[tuple[str, str]] = []
        offsets: list[tuple[str, int]] | None = None

        for raw in stdout.splitlines():
            line = raw.rstrip()
            if not line.strip():
                continue

            if offsets is None:
                # The header is the first line carrying an "Available" column
                # label; winget prints warnings before it when a source is
                # unhealthy, so this can't assume line 1.
                if line.lstrip().startswith("Name") and "Available" in line:
                    offsets = cls._offsets(line)
                continue

            if set(line.strip()) <= {"-"}:
                continue

            name = cls._field(line, offsets, "Name")
            pkg_id = cls._field(line, offsets, "Id")
            if not name or not pkg_id:
                continue

            if pkg_id.startswith("ARP\\"):
                # Installed on this PC by something other than winget.
                arp.append((name, cls._field(line, offsets, "Version")))
                continue
            if pkg_id.startswith("MSIX\\"):
                continue

            by_id[pkg_id.lower()] = (
                cls._field(line, offsets, "Version"),
                cls._field(line, offsets, "Available"),
            )

        return {"by_id": by_id, "arp": arp}

    def _run_winget(self, timeout: int = 90):
        """Run `winget list` in a way that can actually be cancelled.

        subprocess.run() blocks this thread for the whole call, so
        requestInterruption() had no effect: closing the app mid-scan left a
        QThread holding a live child process, and the interpreter then never
        finished shutting down. That is the process that survives the window
        and stacks up on every relaunch.

        So: Popen, but the pipes MUST be drained while we wait. Polling
        proc.poll() and only calling communicate() at the end deadlocks --
        `winget list` writes more than a pipe buffer holds, blocks on the write,
        and therefore never exits, so poll() never returns. Measured on this
        machine: that version timed out at 90s on a command that otherwise
        finishes in 1.2s. Two reader threads fix it and keep the wait
        interruptible.

        Returns (stdout, stderr, returncode).
        """
        try:
            proc = subprocess.Popen(
                ["winget", "list", "--disable-interactivity"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except FileNotFoundError:
            raise _WingetMissing()

        out_chunks, err_chunks = [], []
        drain_out = threading.Thread(
            target=lambda: out_chunks.append(proc.stdout.read()), daemon=True)
        drain_err = threading.Thread(
            target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
        drain_out.start()
        drain_err.start()

        deadline = time.monotonic() + timeout
        timed_out = False
        while proc.poll() is None:
            if self.isInterruptionRequested():
                self._terminate(proc)
                break
            if time.monotonic() > deadline:
                timed_out = True
                self._terminate(proc)
                break
            time.sleep(0.1)

        drain_out.join(timeout=5)
        drain_err.join(timeout=5)

        if timed_out:
            raise _WingetTimeout()

        stdout = out_chunks[0] if out_chunks else ""
        stderr = err_chunks[0] if err_chunks else ""
        return stdout, stderr, proc.returncode

    @staticmethod
    def _terminate(proc) -> None:
        """Kill the child, escalating to the whole process tree if it ignores us.

        taskkill /T is needed because winget can spawn helpers of its own; killing
        only the parent would leave those running and still holding the pipes.
        """
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=10,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            else:
                proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass

    def run(self):
        # Read the host's own Add/Remove Programs list first — it is cheap
        # and, unlike winget, complete. winget's view is a second opinion
        # layered on top of it, used only for versions and available upgrades.
        try:
            registry = read_installed_programs()
        except Exception:
            registry = []

        try:
            stdout, stderr, returncode = self._run_winget()
        except _WingetMissing:
            self.index_ready.emit({
                "error": "winget.exe not found — install 'App Installer' "
                         "from the Microsoft Store, then press Refresh.",
                "by_id": {},
                "arp": registry,
            })
            return
        except _WingetTimeout:
            self.index_ready.emit({
                "error": "winget list did not finish within 90 seconds.",
                "by_id": {},
                "arp": registry,
            })
            return
        except Exception as exc:
            self.index_ready.emit({
                "error": f"{type(exc).__name__}: {exc}",
                "by_id": {},
                "arp": registry,
            })
            return

        if self.isInterruptionRequested():
            return

        payload = self._parse(stdout)
        if not payload["by_id"] and not payload["arp"]:
            err_lines = (stderr or "").strip().splitlines()
            detail = err_lines[-1] if err_lines else f"exit code {returncode}"
            payload = {"error": f"winget list returned nothing — {detail}",
                       "by_id": {}, "arp": registry}
        else:
            payload["returncode"] = returncode
            payload["stderr"] = (stderr or "").strip()

        # Union the two. The registry is authoritative for presence (it has
        # entries winget never surfaces, TeamViewer being the example that
        # prompted this), so its version wins on a name collision.
        merged = {name.lower(): (name, version)
                  for name, version in payload.get("arp", [])}
        merged.update({name.lower(): (name, version)
                       for name, version in registry})
        payload["arp"] = list(merged.values())
        payload["registry_count"] = len(registry)
        self.index_ready.emit(payload)


class ToolTabBase(QWidget):
    """Common layout + action plumbing for TechToolsTab and GamerToolsTab."""

    # Sections are dealt round-robin across at most this many columns. 3 puts
    # a nine-section tab into a clean 3x3 grid instead of one very long list.
    MAX_COLUMNS = 3

    def __init__(self, title: str, subtitle: str, console_label: str, parent=None):
        super().__init__(parent)
        self.cmd_builder = CommandBuilder()
        self._cards: dict[str, ToolCard] = {}
        self._winget_ids: dict[str, str] = {}
        self._batch_btns: dict[str, QPushButton] = {}
        self._index_worker: WingetIndexWorker | None = None
        self._status_index: dict = {}
        self._status_started = False
        self._sections: list[CollapsibleSection] = []
        self._columns: list[tuple[QWidget, QVBoxLayout]] = []
        self._grid_cols = 0
        self._batch_label = ""
        self._batch_total = 0
        self._batch_done = 0

        self._build_scaffold(title, subtitle, console_label)

    # ------------------------------------------------------------------
    # Scaffold
    # ------------------------------------------------------------------

    def _build_scaffold(self, title: str, subtitle: str, console_label: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("TabSectionTitle")
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.addWidget(title_lbl)
        header.addStretch()

        # The arrows match CollapsibleSection's own glyphs (▼ open, ▶ shut),
        # so the two read as the same control applied to everything.
        self.collapse_all_btn = QPushButton("▼  Collapse all")
        self.collapse_all_btn.setObjectName("ToolToggleBtn")
        self.collapse_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.collapse_all_btn.setToolTip("Close every category on this tab")
        self.collapse_all_btn.clicked.connect(
            lambda _checked=False: self.set_all_sections(False))
        header.addWidget(self.collapse_all_btn)

        self.expand_all_btn = QPushButton("▶  Expand all")
        self.expand_all_btn.setObjectName("ToolToggleBtn")
        self.expand_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand_all_btn.setToolTip("Open every category on this tab")
        self.expand_all_btn.clicked.connect(
            lambda _checked=False: self.set_all_sections(True))
        header.addWidget(self.expand_all_btn)

        self.refresh_btn = QPushButton("⟳  Refresh statuses")
        self.refresh_btn.setObjectName("ToolRefreshBtn")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Re-scan installed packages with winget")
        self.refresh_btn.clicked.connect(self.refresh_app_statuses)
        self.refresh_btn.hide()
        header.addWidget(self.refresh_btn)
        root.addLayout(header)

        root.addSpacing(2)
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("TabSubtitle")
        subtitle_lbl.setWordWrap(True)
        root.addWidget(subtitle_lbl)
        root.addSpacing(12)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._page = QWidget()
        self._page_layout = QVBoxLayout(self._page)
        self._page_layout.setContentsMargins(0, 0, 8, 0)
        self._page_layout.setSpacing(8)

        # The grid that holds the category cards. Sections are dealt
        # round-robin across these columns (see _apply_grid), which keeps the
        # 1-2-3, 4-5-6, 7-8-9 reading order of a grid while letting each
        # column keep its own height — so opening one category grows only its
        # column instead of shoving the whole row's worth of collapsed
        # headers around. Each column ends with a stretch, which is what
        # pins its sections to the top of an uneven column.
        self._grid_host = QWidget()
        self._grid_layout = QHBoxLayout(self._grid_host)
        self._grid_layout.setContentsMargins(0, 0, 0, 0)
        self._grid_layout.setSpacing(10)
        for _ in range(self.MAX_COLUMNS):
            column = QWidget()
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(8)
            self._grid_layout.addWidget(column, 1)  # equal stretch = equal width
            self._columns.append((column, column_layout))
        self._page_layout.addWidget(self._grid_host)

        scroll.setWidget(self._page)
        splitter.addWidget(scroll)

        pane = QFrame()
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(0, 8, 0, 0)
        pane_layout.setSpacing(4)
        console_title = QLabel(console_label)
        console_title.setObjectName("TerminalSectionLabel")
        console_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        pane_layout.addWidget(console_title)
        self.terminal = TerminalConsoleWidget()
        self.terminal.command_finished.connect(self._on_command_finished)
        pane_layout.addWidget(self.terminal)
        splitter.addWidget(pane)

        splitter.setSizes([430, 250])
        root.addWidget(splitter, stretch=1)

    # ------------------------------------------------------------------
    # Section grid
    # ------------------------------------------------------------------

    def add_section(self, title: str, expanded: bool = False) -> CollapsibleSection:
        """Create a category. It joins the grid when finish_sections runs."""
        section = CollapsibleSection(title, expanded=expanded)
        self._sections.append(section)
        return section

    def finish_sections(self) -> None:
        """Deal the collected sections into the grid, then fill the page."""
        self._apply_grid()
        self._page_layout.addStretch()

    def set_all_sections(self, expanded: bool) -> None:
        """Open or close every category on this tab at once."""
        for section in self._sections:
            section.set_expanded(expanded)
        verb = "Expanded" if expanded else "Collapsed"
        self._log(f"[GRID] {verb} all {len(self._sections)} categories.",
                  INFO)

    def _column_count(self) -> int:
        if not self._sections:
            return 1
        width = self.width() or 1200
        if width >= 1180:
            cols = 3
        elif width >= 760:
            cols = 2
        else:
            cols = 1
        return max(1, min(cols, self.MAX_COLUMNS, len(self._sections)))

    def _apply_grid(self) -> None:
        """(Re)place sections into columns. Cheap no-op when nothing changed."""
        if not self._sections:
            return
        cols = self._column_count()
        if cols == self._grid_cols:
            return
        self._grid_cols = cols

        # Empty every column first. takeAt() rather than removeWidget() so
        # the trailing stretch goes too and every rebuild starts identical.
        for _column, layout in self._columns:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setVisible(False)

        for index, section in enumerate(self._sections):
            _column, layout = self._columns[index % cols]
            layout.addWidget(section)
            section.setVisible(True)

        for index, (_column, layout) in enumerate(self._columns):
            layout.addStretch(1)
            _column.setVisible(index < cols)

    def resizeEvent(self, event) -> None:
        """Drop to two columns (then one) as the window narrows."""
        super().resizeEvent(event)
        self._apply_grid()

    # ------------------------------------------------------------------
    # Cards
    # ------------------------------------------------------------------

    def run_command(self, key: str) -> None:
        """Run a command by its registry key without a card click.

        Used by the elevated instance: RootForgeKit is relaunched as
        Administrator with --command <key>, and this method fires the
        corresponding card's command so the user does not have to navigate
        back to the right tab and click again.
        """
        card = self._cards.get(key)
        if card is None:
            return
        previous = (card.status_key, card.status_detail)
        self._log(f"[RUN] {card.name.text()}", INFO)
        started = self.terminal.execute_command(
            command=card._command,
            description=card.desc.text(),
            risk_level=card._risk,
            command_key=key,
            skip_confirm=getattr(card, "_skip_confirm", False),
            requires_admin=getattr(card, "_admin", False),
        )
        if started:
            card.set_status("running", "started - output below")
            card.set_action(".  Running", enabled=False)
            self._begin_progress(f"Running {card.name.text()}.")
        else:
            card.set_status(*previous)
            card.set_action("?  Run", enabled=True)
            self._end_progress()

    def _register(self, key: str, card: ToolCard) -> ToolCard:
        self._cards[key] = card
        card._key = key
        card.actionRequested.connect(lambda c, k=key: self._on_card_action(k))
        return card

    def add_command_card(self, section: CollapsibleSection, key: str,
                         icon: str, name: str, description: str,
                         skip_confirm: bool = False) -> ToolCard | None:
        try:
            command, builder_desc, risk = self.cmd_builder.get(key)
        except KeyError:
            return None
        card = ToolCard(icon, name, description or builder_desc,
                        action_text="▶  Run", risk=risk)
        card.set_status("ready")
        card._command = command
        card._risk = risk
        card._admin = requires_admin(key)
        card._skip_confirm = skip_confirm
        section.content_layout().addWidget(card)
        return self._register(key, card)

    def add_raw_card(self, section: CollapsibleSection, key: str, icon: str,
                     name: str, description: str, command: str, risk: str,
                     skip_confirm: bool = False,
                     requires_admin_flag: bool = False) -> ToolCard:
        card = ToolCard(icon, name, description, action_text="▶  Run", risk=risk)
        card.set_status("ready")
        card._command = command
        card._risk = risk
        card._admin = requires_admin_flag
        card._skip_confirm = skip_confirm
        section.content_layout().addWidget(card)
        return self._register(key, card)

    def add_url_card(self, section: CollapsibleSection, key: str, icon: str,
                     name: str, description: str, url: str) -> ToolCard:
        card = ToolCard(icon, name, description, action_text="↗  Open")
        card.set_status("ready")
        card._url = url
        section.content_layout().addWidget(card)
        return self._register(key, card)

    def add_app_card(self, section: CollapsibleSection, key: str, icon: str,
                      name: str, description: str, winget_id: str,
                      requires_admin: bool = False) -> ToolCard | None:
        card = ToolCard(icon, name, description, action_text="⟳  Check",
                        risk="medium")
        card.set_status("checking", "waiting for the first scan")
        card._winget_id = winget_id
        card._app_name = name
        card._requires_admin = requires_admin
        section.content_layout().addWidget(card)
        self._winget_ids[key] = winget_id
        if not self.refresh_btn.isVisible():
            self.refresh_btn.show()
        return self._register(key, card)

    def add_batch_button(self, section: CollapsibleSection, profile_key: str,
                         icon: str, name: str, description: str) -> QPushButton:
        card = ToolCard(icon, name, description, action_text="▶  Install",
                        risk="medium")
        card.set_status("ready")
        section.content_layout().addWidget(card)
        card.actionRequested.connect(
            lambda _c, pk=profile_key: self._run_batch(pk)
        )
        self._batch_btns[profile_key] = card.action_btn
        return card.action_btn

    # ------------------------------------------------------------------
    # Status inventory
    # ------------------------------------------------------------------

    def showEvent(self, event) -> None:
        """First time the tab becomes visible, kick off the winget inventory.

        Deferred rather than run in __init__ so opening the app doesn't spawn
        a winget scan for a tab the user may never click, and so only the tab
        actually on screen pays for it.
        """
        super().showEvent(event)

        # Re-deal the grid. A tab that has never been shown still reports the
        # QWidget default width (640), which would collapse it to a single
        # column and never correct itself if no resizeEvent follows.
        self._apply_grid()

        if not self._status_started and self._winget_ids:
            self._status_started = True
            self.refresh_app_statuses()

    def shutdown(self) -> None:
        """Stop background work on app close. See RootForgeKitMainWindow.closeEvent.

        Both workers spawn child processes (winget, the batch installer). Left
        running, they keep the interpreter alive after the window is gone, so
        the process survives and stacks up on every relaunch. ask them to stop
        and give them a moment to notice; the window-level watchdog covers
        anything that does not.
        """
        for attr in ("_index_worker", "_batch_worker"):
            worker = getattr(self, attr, None)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(1500)
        if getattr(self, "terminal", None) is not None:
            self.terminal.shutdown()

    def refresh_app_statuses(self, note: str = "") -> None:
        caption = (f"{note} — re-checking this PC…"
                   if note else
                   "Checking this PC for installed programs…")
        # Claim the bottom bar first. A caller may be handing over from a
        # finished operation while a scan is already in flight; leaving the
        # finished operation's caption up would be a lie.
        self._begin_progress(caption)

        if self._index_worker is not None and self._index_worker.isRunning():
            self._log("[SCAN] A scan is already running — waiting for it to finish.", WARN)
            return

        for key in self._winget_ids:
            self._cards[key].set_status("checking", "reading this PC's installed programs")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⟳  Scanning…")
        self._log(
            f"[SCAN] Checking this PC for {len(self._winget_ids)} package(s) "
            f"— reading the installed-programs registry and winget…",
            INFO,
        )
        self._index_worker = WingetIndexWorker(self)
        self._index_worker.index_ready.connect(self._on_index_ready)
        self._index_worker.start()

    def _on_index_ready(self, payload: dict) -> None:
        self._status_index = payload
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("⟳  Refresh statuses")

        error = payload.get("error")
        by_id: dict = payload.get("by_id", {})
        arp: list = payload.get("arp", [])
        registry_count = payload.get("registry_count", 0)
        counts = {"installed": 0, "arp": 0, "update": 0,
                  "missing": 0, "unknown": 0}

        # winget being unreadable only costs us versions and upgrade checks.
        # The registry read still answers "is it present", so keep reporting
        # that instead of blanking every card to "unknown".
        if error:
            self._log(f"[SCAN] winget could not be read — {error}", ERR)
            self._log("[SCAN] Falling back to this PC's own installed-programs "
                      "list: presence is still accurate, versions and "
                      "upgrades are unavailable until winget works.", WARN)

        for key, winget_id in self._winget_ids.items():
            card = self._cards[key]
            entry = by_id.get(winget_id.lower())

            # 1. winget knows this package and manages the install — this is
            #    the only path that can offer an upgrade.
            if entry is not None:
                version, available = entry
                if available:
                    card.set_status("update", f"{version} → {available}")
                    card.set_action("⬆  Update")
                    counts["update"] += 1
                    self._log(f"[UPDATE] {card._app_name}: {version} → {available}", WARN)
                else:
                    card.set_status("installed", version)
                    card.set_action("▶  Launch")
                    counts["installed"] += 1
                continue

            # 2. Present on this host but installed outside winget. Check the
            #    registry before declaring anything absent — winget's own ARP
            #    pseudo-rows are incomplete, and some entries (TeamViewer) it
            #    doesn't list at all.
            hit = next(((name, ver) for name, ver in arp
                        if _arp_match(card._app_name, name)), None)
            if hit is not None:
                detail = f"{hit[1] or 'version unknown'}"
                detail += (" — present, version from registry" if error
                           else " — not installed via winget")
                card.set_status("arp", detail)
                card.set_action("✓  Installed", enabled=False)
                counts["arp"] += 1
                note = ("installed outside winget, so winget can't upgrade "
                        "it here" if not error else "installed outside winget")
                self._log(
                    f"[FOUND] {card._app_name}: present on this PC "
                    f"({hit[1] or 'version unknown'}), {note}.", INFO)
                continue

            # 3. Neither source has it.
            if error:
                card.set_status("unknown", error)
                card.set_action("?  Retry")
                counts["unknown"] += 1
            else:
                card.set_status("missing", "not present on this PC")
                card.set_action("⬇  Install")
                counts["missing"] += 1

        self._log(
            f"[SCAN] winget reported {len(by_id)} managed package(s); the "
            f"host registry returned {registry_count} installed programs "
            f"({len(arp)} unique after merge).", DIM)

        summary = (
            f"[SCAN] {len(self._winget_ids)} tracked → "
            f"{counts['installed']} installed, {counts['arp']} installed "
            f"(non-winget), {counts['update']} update(s) available, "
            f"{counts['missing']} not installed"
        )
        if counts["unknown"]:
            summary += f", {counts['unknown']} unknown"
        self._log(
            summary + ".",
            ERR if (counts["missing"] or counts["unknown"]) else OK)

        # Bottom bar: flash the tally, then drop back to idle. Only a failed
        # read counts as a failure — "not installed" is just information.
        self._end_progress(
            f"Scan done: {counts['installed'] + counts['arp']} present, "
            f"{counts['update']} update(s), {counts['missing']} absent",
            ok=not counts["unknown"],
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_card_action(self, key: str) -> None:
        card = self._cards[key]

        if hasattr(card, "_url"):
            ok = webbrowser.open(card._url)
            if ok:
                self._log(f"[LINK] {card.name.text()} → {card._url}", INFO)
                card.set_status("done", "opened in your browser")
            else:
                self._log(f"[LINK] FAILED to open {card.name.text()} → {card._url}", ERR)
                card.set_status("failed", "your browser did not open")
            return

        if hasattr(card, "_winget_id"):
            self._run_winget(card)
            return

        if hasattr(card, "_command"):
            # Remember where we were: execute_command returns False for
            # three different reasons (busy, elevation declined, user hit
            # No) and _on_command_finished never fires for any of them, so
            # the card has to put itself back.
            previous = (card.status_key, card.status_detail)
            self._log(f"[RUN] {card.name.text()}", INFO)
            started = self.terminal.execute_command(
                command=card._command,
                description=card.desc.text(),
                risk_level=card._risk,
                command_key=key,
                skip_confirm=getattr(card, "_skip_confirm", False),
                requires_admin=getattr(card, "_admin", False),
            )
            if started:
                card.set_status("running", "started — output below")
                card.set_action("…  Running", enabled=False)
                self._begin_progress(f"Running {card.name.text()}…")
            else:
                card.set_status(*previous)
                card.set_action("▶  Run", enabled=True)
                self._end_progress()
                self._log(
                    f"[BLOCKED] {card.name.text()} did not start — see the "
                    f"line above for why.", WARN)
            return

        self._log(f"[??] {card.name.text()} has no action wired up.", ERR)

    def _run_winget(self, card: ToolCard) -> None:
        state = card.status_key
        name = card._app_name

        if state == "checking":
            self._log(f"[WAIT] {name}: still checking this PC — "
                      f"wait for the scan to finish before acting.", WARN)
            return
        if state == "arp":
            self._log(f"[SKIP] {name} is installed on this PC but not through "
                      f"winget, so winget can't upgrade it here.", WARN)
            return

        winget_id = card._winget_id
        if state == "installed":
            command = f"winget run --id {winget_id} -e"
            description = f"Launch {name}"
            risk, skip = "low", True
        elif state == "update":
            command = (
                f"winget upgrade --id {winget_id} -e "
                "--accept-package-agreements --accept-source-agreements "
                "--force --silent"
            )
            description = f"Update {name} to the latest version"
            risk, skip = "medium", False
        else:
            command = (
                f"winget install --id {winget_id} -e "
                "--accept-package-agreements --accept-source-agreements "
                "--force --silent"
            )
            description = f"Install {name} from the winget repository"
            risk, skip = "medium", False

        previous = (card.status_key, card.status_detail)
        self._log(f"[APP] {description}  [{winget_id}]", INFO)
        started = self.terminal.execute_command(
            command=command, description=description, risk_level=risk,
            command_key=card._key, skip_confirm=skip,
            requires_admin=getattr(card, "_requires_admin", False),
        )
        if started:
            card.set_status("running", "winget working…")
            card.set_action("…  Working", enabled=False)
            self._begin_progress(f"{description}…")
        else:
            card.set_status(*previous)
            card.set_action("⟳  Refresh", enabled=True)
            self._end_progress()
            self._log(f"[BLOCKED] {name} did not start — see the line above "
                      f"for why.", WARN)

    def _on_command_finished(self, exit_code: int, command_key: str) -> None:
        card = self._cards.get(command_key)
        if card is None:
            return
        name = card.name.text()

        if hasattr(card, "_winget_id"):
            if exit_code == 0:
                self._log(f"[APP] {name} winget finished — re-reading this "
                          f"PC to confirm the result…", OK)
                note = f"{name} finished"
            else:
                self._log(f"[APP] {name} winget exited with code "
                          f"{exit_code} — the output above is the reason. "
                          f"Re-checking anyway…", ERR)
                note = f"{name} exited {exit_code}"
            card.set_action("⟳  Refresh", enabled=True)
            # The rescan immediately takes over the bar, so fold the result
            # into its caption rather than flashing a line that would be
            # replaced a frame later.
            self.refresh_app_statuses(note=note)
            return

        if exit_code == 0:
            card.set_status("done", "completed, exit 0")
            card.set_action("▶  Run", enabled=True)
            self._log(f"[OK] {name} finished successfully.", OK)
            self._end_progress(f"✓ {name} — exit 0", ok=True)
        else:
            card.set_status("failed", f"exited with code {exit_code}")
            card.set_action("▶  Retry", enabled=True)
            self._log(f"[FAIL] {name} exited with code {exit_code} — see the "
                      f"output above.", ERR)
            self._end_progress(f"✗ {name} — exit {exit_code}", ok=False)

    def _run_batch(self, profile_key: str) -> None:
        running = getattr(self, "_batch_worker", None)
        if running is not None and running.isRunning():
            self._log("[BATCH] Another batch install is still running — "
                      "wait for it to finish.", WARN)
            return

        profile = PRESET_PROFILES.get(profile_key, {})
        display = profile.get("name", profile_key)
        packages = profile.get("windows_packages") or profile.get("darwin_packages") or []

        btn = self._batch_btns[profile_key]
        btn.setEnabled(False)
        btn.setText("…  Installing")
        self._log(f"[BATCH] Starting {display} — {len(packages)} package(s): "
                  f"{profile.get('description', '')}", INFO)
        self._log("[BATCH] Each package prints [+] or [-] below. This can take "
                  "several minutes on a cold cache.", DIM)

        # A batch is the one operation whose length is actually known, so it
        # drives a real count instead of the indeterminate animation.
        self._batch_label = display
        self._batch_total = len(packages)
        self._batch_done = 0
        self._begin_progress(f"{display}: 0/{len(packages)}",
                             indeterminate=False, maximum=len(packages))

        self._batch_worker = BatchInstallWorker(profile_key)
        self._batch_worker.log_line.connect(self._batch_log_line)
        self._batch_worker.finished_profile.connect(
            lambda ok, pk=profile_key: self._on_batch_finished(pk, ok)
        )
        self._batch_worker.start()

    def _batch_log_line(self, message: str) -> None:
        """Colour the installer's chatter and turn it into bar progress."""
        stripped = message.lstrip()
        if stripped.startswith("[-]"):
            colour = "#ff8a80"
        elif stripped.startswith("[+]"):
            colour = OK
        elif stripped.startswith("[*]") or stripped.startswith("🚀"):
            colour = INFO
        else:
            colour = DIM
        self.terminal.log(message, colour)

        if stripped.startswith("[*] Installing package"):
            self._batch_done += 1
            package = stripped.split(":", 1)[-1].strip().rstrip(".").strip()
            self._set_progress(
                self._batch_done,
                f"{self._batch_label}: {self._batch_done}/{self._batch_total}"
                f"  {package}",
            )

    def _on_batch_finished(self, profile_key: str, success: bool) -> None:
        btn = self._batch_btns[profile_key]
        btn.setEnabled(True)
        btn.setText("✓  Installed" if success else "▶  Retry")
        display = PRESET_PROFILES.get(profile_key, {}).get("name", profile_key)
        if success:
            self._log(f"[BATCH] {display} finished — every package succeeded.", OK)
            outcome = f"{display}: all {self._batch_total} installed"
        else:
            self._log(f"[BATCH] {display} finished with failures — every [-] "
                      f"line above is a package that did not install.", ERR)
            outcome = f"{display}: finished with failures"
        # Hand the bar straight to the rescan with the outcome folded into
        # its caption — a flash here would be replaced a frame later.
        self.refresh_app_statuses(note=outcome)

    # ------------------------------------------------------------------
    # Bottom-bar progress
    # ------------------------------------------------------------------

    def _status_bar(self):
        bar = getattr(self.window(), "status_bar", None)
        return bar if hasattr(bar, "begin_operation") else None

    def _begin_progress(self, label: str, *, indeterminate: bool = True,
                        maximum: int = 0) -> None:
        bar = self._status_bar()
        if bar is not None:
            bar.begin_operation(label, indeterminate=indeterminate,
                                maximum=maximum)

    def _set_progress(self, value: int, label: str | None = None) -> None:
        bar = self._status_bar()
        if bar is not None:
            bar.set_progress(value, label)

    def _end_progress(self, message: str = "", ok: bool = True) -> None:
        bar = self._status_bar()
        if bar is not None:
            bar.end_operation(message, ok)

    def _log(self, message: str, colour: str = DIM) -> None:
        self.terminal.log(message, colour)
