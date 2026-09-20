"""
Plethora Keraunos — Approachable, human-friendly Windows system orchestrator.

Layout (QStackedWidget pages):
  Page 0 — Hero (prompt entry)
  Page 1 — Friendly Action Cards / Diff Review + Apply
  Page 2 — History (Timeline view)
  Page 3 — Drift Scan
  Page 4 — Settings drawer
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, QSize, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPixmap, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QStackedWidget,
    QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget, QHeaderView,
)

from keraunos.compiler import OfflineIntentCompiler, ResolutionDiagnostic
from keraunos.drift import DriftDetector
from keraunos.executor import ExecutionEngine
from keraunos.git_store import StateRepository, generate_deterministic_commit_msg
from keraunos.schema import KeraunosState
from keraunos.ui.styles import APP_QSS

# --- paths & constants --------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ICON_PATH = _PROJECT_ROOT / "keraunosICON.png"

# Page indices
PAGE_HERO = 0
PAGE_DIFF = 1
PAGE_HISTORY = 2
PAGE_DRIFT = 3
PAGE_SETTINGS = 4

FRIENDLY_PKG_NAMES: Dict[str, str] = {
    "microsoft.visualstudiocode": "VS Code",
    "7zip.7zip": "7-Zip Compression Tool",
    "google.chrome": "Google Chrome",
    "mozilla.firefox": "Mozilla Firefox",
    "github.cli": "GitHub CLI",
    "github.githubdesktop": "GitHub Desktop",
    "git.git": "Git for Windows",
    "neovim.neovim": "Neovim",
    "notepad++.notepad++": "Notepad++",
    "brave.brave": "Brave Browser",
    "microsoft.windowsterminal": "Windows Terminal",
    "microsoft.powershell": "PowerShell 7",
    "docker.dockerdesktop": "Docker Desktop",
    "sublimehq.sublimetext.4": "Sublime Text",
    "starship.starship": "Starship Prompt",
}

FRIENDLY_SYSTEM_TWEAKS: Dict[str, Tuple[str, str]] = {
    "dark_mode": ("Switch Windows theme to Dark Mode", "Switch Windows theme to Light Mode"),
    "light_mode": ("Switch Windows theme to Light Mode", "Switch Windows theme to Dark Mode"),
    "hide_taskbar_search": ("Hide taskbar search bar", "Show taskbar search bar"),
    "disable_bing_in_start_search": ("Disable Bing web search in Start Menu", "Enable Bing search in Start Menu"),
    "show_file_extensions": ("Show known file extensions in File Explorer", "Hide known file extensions in File Explorer"),
    "show_hidden_files": ("Show hidden and system files in File Explorer", "Hide hidden files in File Explorer"),
    "compact_explorer_view": ("Enable compact view in File Explorer", "Enable comfortable spacing in File Explorer"),
    "enable_long_paths": ("Enable Win32 Long Path support (>260 characters)", "Disable Win32 Long Path support"),
    "disable_game_bar": ("Disable Xbox Game Bar background services", "Enable Xbox Game Bar"),
}


# ─── Settings persistence ──────────────────────────────────────────────────

_SETTINGS_DEFAULTS: Dict[str, Any] = {
    "elevation": "raise",
    "shell_refresh": "env_only",
    "create_restore_point": False,
    "auto_accept_agreements": True,
    "install_scope": "user",
    "scoop_fallback": True,
    "git_remote_url": "",
    "auto_push": False,
    "start_with_windows": False,
    "typo_threshold": 75,
    "auto_check_updates": True,
}


class AppSettings:
    """Read/write ~/.keraunos/settings.json; live dict access."""

    def __init__(self, state_dir: Path):
        self._path = state_dir / "settings.json"
        self._data: Dict[str, Any] = dict(_SETTINGS_DEFAULTS)
        self._load()

    def _load(self) -> None:
        try:
            if self._path.exists():
                saved = json.loads(self._path.read_text(encoding="utf-8"))
                self._data.update(saved)
        except Exception:
            pass

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def all(self) -> Dict[str, Any]:
        return dict(self._data)


# ─── Background worker ─────────────────────────────────────────────────────

class _Worker(QThread):
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self):
        try:
            self.finished_ok.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:
            self.finished_err.emit(f"{exc}\n\n{traceback.format_exc(limit=5)}")


class ApplyWorker(QThread):
    progress = Signal(str, int, int)
    log_line = Signal(str)
    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, engine: ExecutionEngine, state: KeraunosState, elevation: str):
        super().__init__()
        self.engine = engine
        self.state = state
        self.elevation = elevation

    def run(self):
        try:
            logs: List[str] = []
            diff = self.engine.calculate_diff(self.state)
            total_steps = (
                len(diff.get("winget_add", []))
                + len(diff.get("winget_remove", []))
                + len(diff.get("scoop_add", []))
                + len(diff.get("scoop_remove", []))
                + len(diff.get("system_tweaks", {}))
                + len(diff.get("custom_registry", []))
                + len(diff.get("custom_actions", []))
                + (1 if diff.get("dotfiles", {}).get("powershell_profile") else 0)
            )
            total_steps = max(total_steps, 1)
            current_step = [0]

            def _callback(msg: str):
                logs.append(msg)
                self.log_line.emit(msg)
                if any(msg.startswith(prefix) for prefix in ("[WinGet]", "[Scoop]", "[System]", "[Registry]", "[Display]", "[Dotfiles]")):
                    current_step[0] = min(current_step[0] + 1, total_steps)
                    self.progress.emit(f"Applying configuration ({current_step[0]} of {total_steps})...", current_step[0], total_steps)

            applied_diff = self.engine.apply_state(
                self.state,
                status_callback=_callback,
                elevation=self.elevation,
            )
            self.finished_ok.emit((applied_diff, logs))
        except Exception as exc:
            self.finished_err.emit(f"{exc}\n\n{traceback.format_exc(limit=5)}")


# ─── Non-hijacking Controls ────────────────────────────────────────────────

class NoScrollComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events unless the popup list is actively open."""

    def wheelEvent(self, event):
        if not self.view() or not self.view().isVisible():
            event.ignore()
        else:
            super().wheelEvent(event)


class NoScrollSlider(QSlider):
    """QSlider that ignores mouse wheel events to prevent scroll hijacking."""

    def wheelEvent(self, event):
        event.ignore()


# ─── Squircle icon label ───────────────────────────────────────────────────

class SquircleIcon(QLabel):
    """Renders a QPixmap clipped to a rounded-rect squircle."""

    def __init__(self, pixmap: QPixmap, size: int = 64, radius: int = 14,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._px = pixmap
        self._radius = radius
        self.setObjectName("IconCard")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(),
                            self._radius, self._radius)
        painter.setClipPath(path)

        # Background
        painter.fillRect(self.rect(), QColor("#15131C"))

        # Scaled icon
        scaled = self._px.scaled(
            QSize(self.width(), self.height()),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

        # Border overlay
        painter.setClipping(False)
        painter.setPen(QColor("#262235"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(0, 0, self.width() - 1, self.height() - 1,
                                self._radius, self._radius)
        painter.end()


# ─── Main Window ───────────────────────────────────────────────────────────

class KeraunosWindow(QMainWindow):
    def __init__(self, state_dir: Optional[Path] = None):
        super().__init__()
        self._sd = state_dir or (Path.home() / ".keraunos")
        self.engine = ExecutionEngine(self._sd)
        self.settings = AppSettings(self._sd)

        try:
            self.repo = StateRepository(self.engine.state_dir)
        except Exception:
            self.repo = None  # type: ignore

        self.pending_state: Optional[KeraunosState] = None
        self.pending_diagnostics: List[ResolutionDiagnostic] = []
        self._worker: Optional[_Worker] = None
        self._apply_worker: Optional[ApplyWorker] = None
        self._drag_pos = None

        # Load icon (user's custom PNG)
        self._icon_px = QPixmap(str(_ICON_PATH)) if _ICON_PATH.exists() else QPixmap()

        self._build()

        # Background pre-warm SLM to avoid cold-start latency
        self._prewarm_thread = _Worker(self._prewarm_slm)
        self._prewarm_thread.start()

        # Startup auto-update check
        if self.settings.get("auto_check_updates", True):
            QTimer.singleShot(2500, lambda: self._on_check_updates_clicked(silent=True))

    @staticmethod
    def _prewarm_slm():
        try:
            from keraunos.slm import get_slm
            get_slm()
        except Exception:
            pass

    # ── Build layout ──────────────────────────────────────────────────────

    def _build(self):
        self.setWindowTitle("Plethora Keraunos")
        self.setFixedSize(740, 440)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        if not self._icon_px.isNull():
            self.setWindowIcon(QIcon(self._icon_px))

        root = QWidget(objectName="Root")
        root.setFixedSize(740, 440)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        outer.addWidget(self._build_header())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #1A1A1F; max-height: 1px; border: none;")
        outer.addWidget(sep)

        # Pages
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_hero())        # 0
        self.stack.addWidget(self._build_diff())        # 1
        self.stack.addWidget(self._build_history())     # 2
        self.stack.addWidget(self._build_drift())       # 3
        self.stack.addWidget(self._build_settings())    # 4
        outer.addWidget(self.stack, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(APP_QSS)

    def _make_icon_btn(self, glyph: str, tooltip: str) -> QPushButton:
        btn = QPushButton(glyph, objectName="IconBtn")
        btn.setFixedSize(28, 28)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        return btn

    def _build_header(self) -> QWidget:
        bar = QWidget(objectName="HeaderBar")
        bar.setFixedHeight(42)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(6)

        # Left: mini icon + app name
        if not self._icon_px.isNull():
            thumb = SquircleIcon(self._icon_px, size=22, radius=5)
            lay.addWidget(thumb)
        lay.addSpacing(4)

        name_lbl = QLabel("Plethora Keraunos", objectName="AppName")
        lay.addWidget(name_lbl)
        lay.addStretch(1)

        # Right: action buttons
        self._drift_btn = self._make_icon_btn("🔄", "Drift Scan")
        self._drift_btn.clicked.connect(self._show_drift)
        lay.addWidget(self._drift_btn)

        self._hist_btn = self._make_icon_btn("🕒", "History")
        self._hist_btn.clicked.connect(self._show_history)
        lay.addWidget(self._hist_btn)

        self._settings_btn = self._make_icon_btn("⚙", "Settings")
        self._settings_btn.clicked.connect(self._show_settings)
        lay.addWidget(self._settings_btn)

        lay.addSpacing(4)

        self._min_btn = self._make_icon_btn("—", "Minimize")
        self._min_btn.clicked.connect(self.showMinimized)
        lay.addWidget(self._min_btn)

        self._close_btn = self._make_icon_btn("✕", "Close")
        self._close_btn.clicked.connect(self.close)
        lay.addWidget(self._close_btn)

        return bar

    # ── Page 0: Hero ──────────────────────────────────────────────────────

    def _build_hero(self) -> QWidget:
        page = QWidget(objectName="Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        col = QWidget()
        col.setFixedWidth(460)
        col_lay = QVBoxLayout(col)
        col_lay.setContentsMargins(0, 0, 0, 0)
        col_lay.setSpacing(0)
        col_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # App icon squircle
        if not self._icon_px.isNull():
            icon_w = SquircleIcon(self._icon_px, size=64, radius=14)
        else:
            icon_w = QLabel("⚡")
            icon_w.setFixedSize(64, 64)
            icon_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_w.setStyleSheet(
                "background:#15131C; border:1px solid #262235; border-radius:14px;"
                "font-size:28px;")
        icon_w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_lay.addWidget(icon_w, alignment=Qt.AlignmentFlag.AlignCenter)

        col_lay.addSpacing(18)

        title = QLabel("Get started", objectName="HeroTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col_lay.addWidget(title)

        col_lay.addSpacing(20)

        # Input card
        card = QWidget(objectName="InputCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 10, 14, 10)
        card_lay.setSpacing(6)

        self.prompt_edit = QPlainTextEdit(objectName="HeroInput")
        self.prompt_edit.setPlaceholderText(
            "Install VS Code, enable dark mode, hide taskbar search…")
        self.prompt_edit.setFixedHeight(64)
        self.prompt_edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        card_lay.addWidget(self.prompt_edit)

        # Submit button
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addStretch(1)
        self._submit_btn = QPushButton("↑", objectName="SubmitBtn")
        self._submit_btn.setFixedSize(32, 32)
        self._submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._submit_btn.clicked.connect(self.on_generate)
        btn_row.addWidget(self._submit_btn)
        card_lay.addLayout(btn_row)

        col_lay.addWidget(card)

        hint = QLabel("Press Enter or ↑ to compile and preview changes")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #52505E; font-size: 11px;")
        col_lay.addSpacing(10)
        col_lay.addWidget(hint)

        lay.addWidget(col, alignment=Qt.AlignmentFlag.AlignCenter)

        self.prompt_edit.installEventFilter(self)
        return page

    # ── Page 1: Friendly Action Cards / Diff Review ─────────────────────────

    def _build_diff(self) -> QWidget:
        page = QWidget(objectName="Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        # Back row
        back_row = QHBoxLayout()
        back = QPushButton("← Back to Home", objectName="BackBtn")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_HERO))
        back_row.addWidget(back)
        back_row.addStretch(1)
        lay.addLayout(back_row)

        # Diff / Friendly cards view
        self.diff_view = QTextEdit(objectName="DiffView")
        self.diff_view.setReadOnly(True)
        self.diff_view.setPlaceholderText(
            "No pending changes — describe your desired setup on the Home tab.")
        lay.addWidget(self.diff_view, 3)

        # Conversational Suggestion Pills (visible on welcome/greeting)
        self.pills_container = QWidget()
        pills_lay = QHBoxLayout(self.pills_container)
        pills_lay.setContentsMargins(0, 0, 0, 0)
        pills_lay.setSpacing(8)

        pill1 = QPushButton("• Install Chrome, VS Code & 7-Zip", objectName="PillBtn")
        pill1.clicked.connect(lambda: self._run_sample_prompt("Install Chrome, VS Code, and 7zip"))
        pills_lay.addWidget(pill1)

        pill2 = QPushButton("• Enable Dark Mode & Hide Search", objectName="PillBtn")
        pill2.clicked.connect(lambda: self._run_sample_prompt("Enable dark mode and hide search bar"))
        pills_lay.addWidget(pill2)

        pill3 = QPushButton("• Update All Apps", objectName="PillBtn")
        pill3.clicked.connect(lambda: self._run_sample_prompt("Update all my apps"))
        pills_lay.addWidget(pill3)
        pills_lay.addStretch(1)
        self.pills_container.setVisible(False)
        lay.addWidget(self.pills_container)

        # Collapsible technical details container
        self.tech_details_container = QWidget()
        tech_lay = QVBoxLayout(self.tech_details_container)
        tech_lay.setContentsMargins(0, 0, 0, 0)
        tech_lay.setSpacing(4)

        self.term_view = QPlainTextEdit(objectName="TermView")
        self.term_view.setReadOnly(True)
        self.term_view.setFixedHeight(75)
        tech_lay.addWidget(QLabel("Terminal Log & Raw Details:", styleSheet="color: #71717A; font-size: 11px;"))
        tech_lay.addWidget(self.term_view)
        self.tech_details_container.setVisible(False)
        lay.addWidget(self.tech_details_container)

        # Button row
        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply Changes", objectName="PrimaryBtn")
        self.apply_btn.clicked.connect(self.on_apply)
        self.commit_btn = QPushButton("Commit to Git", objectName="GhostBtn")
        self.commit_btn.clicked.connect(lambda: self.on_commit())
        self.tech_btn = QPushButton("Show Technical Details", objectName="GhostBtn")
        self.tech_btn.clicked.connect(self._toggle_tech_details)

        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.commit_btn)
        btn_row.addWidget(self.tech_btn)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        return page

    def _toggle_tech_details(self) -> None:
        visible = not self.tech_details_container.isVisible()
        self.tech_details_container.setVisible(visible)
        self.tech_btn.setText("Hide Technical Details" if visible else "Show Technical Details")

    def _run_sample_prompt(self, text: str) -> None:
        self.prompt_edit.setPlainText(text)
        self.on_generate()

    # ── Page 2: History (Friendly Timeline) ───────────────────────────────

    def _build_history(self) -> QWidget:
        page = QWidget(objectName="Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        back_row = QHBoxLayout()
        back = QPushButton("← Back to Home", objectName="BackBtn")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_HERO))
        back_row.addWidget(back)
        back_row.addStretch(1)
        lay.addLayout(back_row)

        title = QLabel("State Evolution History")
        title.setStyleSheet("font-size:15px; font-weight:600; color:#EEEEF0;")
        lay.addWidget(title)

        self.history_list = QListWidget(objectName="HistoryList")
        lay.addWidget(self.history_list, 1)

        btn_row = QHBoxLayout()
        refresh = QPushButton("Refresh", objectName="GhostBtn")
        refresh.clicked.connect(self.on_history_refresh)
        restore = QPushButton("Revert to this Point", objectName="PrimaryBtn")
        restore.clicked.connect(self.on_history_restore)
        btn_row.addWidget(refresh)
        btn_row.addWidget(restore)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)

        return page

    # ── Page 3: Drift ─────────────────────────────────────────────────────

    def _build_drift(self) -> QWidget:
        page = QWidget(objectName="Page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        back_row = QHBoxLayout()
        back = QPushButton("← Back to Home", objectName="BackBtn")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_HERO))
        back_row.addWidget(back)
        back_row.addStretch(1)
        lay.addLayout(back_row)

        title = QLabel("System Drift Scan")
        title.setStyleSheet("font-size:15px; font-weight:600; color:#EEEEF0;")
        lay.addWidget(title)

        self.drift_table = QTableWidget(0, 4, objectName="DriftTable")
        self.drift_table.setHorizontalHeaderLabels(
            ["Category", "Key", "Expected", "Actual"])
        self.drift_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self.drift_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.drift_table.verticalHeader().setVisible(False)
        lay.addWidget(self.drift_table, 1)

        scan_btn = QPushButton("Run Drift Scan", objectName="PrimaryBtn")
        scan_btn.clicked.connect(self.on_drift)
        lay.addWidget(scan_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        return page

    # ── Page 4: Settings ──────────────────────────────────────────────────

    def _build_settings(self) -> QWidget:
        page = QWidget(objectName="SettingsPage")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)

        top_row = QHBoxLayout()
        back = QPushButton("← Back to Home", objectName="BackBtn")
        back.clicked.connect(lambda: self.stack.setCurrentIndex(PAGE_HERO))
        top_row.addWidget(back)
        top_row.addStretch(1)
        outer.addLayout(top_row)

        hdr = QLabel("Engine Preferences")
        hdr.setStyleSheet("font-size:15px; font-weight:600; color:#EEEEF0;")
        outer.addWidget(hdr)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        vlay = QVBoxLayout(content)
        vlay.setContentsMargins(0, 0, 8, 0)
        vlay.setSpacing(12)

        # ── Group 1: Execution & Elevation ────────────────────────────────
        vlay.addWidget(self._settings_group_label("Execution & Elevation"))
        g1 = self._settings_card()
        g1_lay = g1.layout()

        self._elevation_box = self._add_combo(
            g1_lay, "Elevation Strategy",
            ["Prompt UAC when needed (RunAs)",
             "Fail fast if non-admin",
             "Warn and skip HKLM modifications"],
            key="elevation",
            values=["relaunch", "raise", "warn"],
        )
        self._add_divider(g1_lay)
        self._shell_refresh_box = self._add_combo(
            g1_lay, "Shell Refresh Mode",
            ["Broadcast environment change only",
             "Soft restart File Explorer if Taskbar tweaks change"],
            key="shell_refresh",
            values=["env_only", "explorer_restart"],
        )
        self._add_divider(g1_lay)
        self._restore_point_cb = self._add_checkbox(
            g1_lay,
            "Create Windows Restore Point before applying major state changes",
            key="create_restore_point",
        )
        vlay.addWidget(g1)

        # ── Group 2: Package Management ───────────────────────────────────
        vlay.addWidget(self._settings_group_label("Package Management"))
        g2 = self._settings_card()
        g2_lay = g2.layout()

        self._auto_agree_cb = self._add_checkbox(
            g2_lay,
            "Auto-accept package and source agreements (--accept-package-agreements)",
            key="auto_accept_agreements",
        )
        self._add_divider(g2_lay)
        self._scope_box = self._add_combo(
            g2_lay, "Install Scope",
            ["User (per-user directory)", "Machine (all users, requires admin)"],
            key="install_scope",
            values=["user", "machine"],
        )
        self._add_divider(g2_lay)
        self._scoop_cb = self._add_checkbox(
            g2_lay,
            "Enable Scoop catalog fallback for developer CLI tools",
            key="scoop_fallback",
        )
        vlay.addWidget(g2)

        # ── Group 3: Git & Dotfile Sync ───────────────────────────────────
        vlay.addWidget(self._settings_group_label("Git & Dotfile Synchronization"))
        g3 = self._settings_card()
        g3_lay = g3.layout()

        url_row = QWidget()
        url_row_lay = QVBoxLayout(url_row)
        url_row_lay.setContentsMargins(0, 0, 0, 0)
        url_row_lay.setSpacing(4)
        url_row_lay.addWidget(QLabel("Remote Git URL", objectName="SettingLabel"))
        url_input_row = QHBoxLayout()
        self._git_url_edit = QLineEdit()
        self._git_url_edit.setPlaceholderText(
            "https://github.com/username/my-windows-state.git")
        self._git_url_edit.setText(self.settings.get("git_remote_url", ""))
        url_input_row.addWidget(self._git_url_edit, 1)
        save_btn = QPushButton("Save & Test", objectName="GhostBtn")
        save_btn.setFixedHeight(32)
        save_btn.clicked.connect(self._on_save_git_remote)
        url_input_row.addWidget(save_btn)
        url_row_lay.addLayout(url_input_row)
        g3_lay.addWidget(url_row)

        self._add_divider(g3_lay)
        self._auto_push_cb = self._add_checkbox(
            g3_lay,
            "Automatically push state commits to origin after applying",
            key="auto_push",
        )
        vlay.addWidget(g3)

        # ── Group 4: System Integration ───────────────────────────────────
        vlay.addWidget(self._settings_group_label("System Integration"))
        g4 = self._settings_card()
        g4_lay = g4.layout()

        self._startup_cb = self._add_checkbox(
            g4_lay,
            "Launch Plethora Keraunos at Windows startup",
            key="start_with_windows",
            on_change=self._on_startup_toggled,
        )
        self._add_divider(g4_lay)

        slider_row = QWidget()
        sl_lay = QVBoxLayout(slider_row)
        sl_lay.setContentsMargins(0, 0, 0, 0)
        sl_lay.setSpacing(4)
        sl_top = QHBoxLayout()
        sl_top.addWidget(QLabel("Typo Matching Tolerance", objectName="SettingLabel"))
        sl_top.addStretch(1)
        self._threshold_lbl = QLabel(
            f"{self.settings.get('typo_threshold', 75)}%",
            objectName="SliderValue")
        sl_top.addWidget(self._threshold_lbl)
        sl_lay.addLayout(sl_top)
        desc = QLabel(
            "Minimum fuzzy-match confidence for package resolution (60–90%)",
            objectName="SettingDesc")
        sl_lay.addWidget(desc)
        self._threshold_slider = NoScrollSlider(Qt.Orientation.Horizontal)
        self._threshold_slider.setRange(60, 90)
        self._threshold_slider.setValue(self.settings.get("typo_threshold", 75))
        self._threshold_slider.setTickInterval(5)
        self._threshold_slider.valueChanged.connect(self._on_threshold_changed)
        sl_lay.addWidget(self._threshold_slider)
        vlay.addWidget(g4)

        # -- Group 5: Updates & Version --
        g5 = self._settings_card()
        g5_lay = g5.layout()
        g5_lay.addWidget(self._settings_group_label("App Updates & Version"))

        update_top = QHBoxLayout()
        from keraunos.config import APP_VERSION
        self._version_lbl = QLabel(f"Plethora Keraunos v{APP_VERSION}", objectName="SettingLabel")
        self._update_status_lbl = QLabel("Up to date", objectName="SliderValue")
        self._update_status_lbl.setStyleSheet("color: #A78BFA; font-weight: 600;")
        update_top.addWidget(self._version_lbl)
        update_top.addStretch(1)
        update_top.addWidget(self._update_status_lbl)
        g5_lay.addLayout(update_top)

        self._add_checkbox(g5_lay, "Automatically check for updates on startup", key="auto_check_updates")

        self._check_update_btn = QPushButton("Check for Updates")
        self._check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_update_btn.setStyleSheet(
            "background: #252033; color: #EDE9FE; border: 1px solid #3F3356; border-radius: 6px; padding: 6px 14px; font-weight: 500;"
        )
        self._check_update_btn.clicked.connect(lambda: self._on_check_updates_clicked(silent=False))
        g5_lay.addWidget(self._check_update_btn)

        vlay.addWidget(g5)
        vlay.addStretch(1)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        return page


    # ── Settings builder helpers ───────────────────────────────────────────

    def _settings_group_label(self, text: str) -> QLabel:
        return QLabel(text.upper(), objectName="SettingsGroup")

    def _settings_card(self) -> QWidget:
        card = QWidget(objectName="SettingsCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        return card

    def _add_divider(self, lay: QVBoxLayout) -> None:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background: #1E1C28; max-height: 1px; border: none;")
        lay.addWidget(line)

    def _add_checkbox(self, lay: QVBoxLayout, text: str, *,
                      key: str, on_change=None) -> QCheckBox:
        cb = QCheckBox(text)
        cb.setChecked(bool(self.settings.get(key, False)))

        def _toggled(state):
            self.settings.set(key, bool(state))
            if on_change:
                on_change(bool(state))

        cb.stateChanged.connect(_toggled)
        lay.addWidget(cb)
        return cb

    def _add_combo(self, lay: QVBoxLayout, label: str,
                   options: List[str], *, key: str,
                   values: Optional[List[str]] = None) -> QComboBox:
        row = QWidget()
        row_lay = QVBoxLayout(row)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(4)
        row_lay.addWidget(QLabel(label, objectName="SettingLabel"))
        combo = NoScrollComboBox()
        for opt in options:
            combo.addItem(opt)
        vals = values or options
        current_val = self.settings.get(key, vals[0])
        try:
            combo.setCurrentIndex(vals.index(current_val))
        except ValueError:
            combo.setCurrentIndex(0)

        def _changed(idx: int):
            self.settings.set(key, vals[idx])

        combo.currentIndexChanged.connect(_changed)
        row_lay.addWidget(combo)
        lay.addWidget(row)
        return combo

    # ── Settings callbacks ─────────────────────────────────────────────────

    def _on_save_git_remote(self) -> None:
        url = self._git_url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Enter a remote URL first.")
            return
        self.settings.set("git_remote_url", url)
        if self.repo is None:
            QMessageBox.warning(self, "No repo",
                                "Git repo unavailable. Run a compile first.")
            return
        try:
            self.repo.set_remote(url)
            QMessageBox.information(self, "Remote saved",
                                    f"Remote 'origin' set to:\n{url}")
        except Exception as exc:
            QMessageBox.critical(self, "Failed", str(exc))

    def _on_startup_toggled(self, enabled: bool) -> None:
        startup_folder = Path(os.environ.get("APPDATA", "")) / \
            "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        shortcut = startup_folder / "PlethoraKeraunos.bat"
        if enabled:
            try:
                py = sys.executable
                script = str(Path(__file__).resolve().parent.parent.parent / "keraunos.py")
                shortcut.write_text(
                    f'@echo off\n"{py}" "{script}" ui\n', encoding="utf-8")
            except Exception as exc:
                QMessageBox.warning(self, "Startup",
                                    f"Could not create startup batch: {exc}")
        else:
            try:
                if shortcut.exists():
                    shortcut.unlink()
            except Exception as exc:
                QMessageBox.warning(self, "Startup",
                                    f"Could not remove startup batch: {exc}")

    def _on_threshold_changed(self, value: int) -> None:
        self._threshold_lbl.setText(f"{value}%")
        self.settings.set("typo_threshold", value)

    def _on_check_updates_clicked(self, silent: bool = False) -> None:
        if hasattr(self, "_check_update_btn"):
            self._check_update_btn.setEnabled(False)
            self._check_update_btn.setText("Checking for updates...")
        if hasattr(self, "_update_status_lbl"):
            self._update_status_lbl.setText("Checking...")

        def _do_check():
            from keraunos.updater import check_for_updates
            return check_for_updates()

        def _ok(info: object):
            if hasattr(self, "_check_update_btn"):
                self._check_update_btn.setEnabled(True)
                self._check_update_btn.setText("Check for Updates")
            if not isinstance(info, dict):
                if hasattr(self, "_update_status_lbl"):
                    self._update_status_lbl.setText("Check failed")
                if not silent:
                    QMessageBox.warning(self, "Update Check", "Unable to connect to update server.")
                return

            if info.get("has_update"):
                latest = info.get("latest_version")
                download_url = info.get("download_url")
                asset_name = info.get("asset_name")
                if hasattr(self, "_update_status_lbl"):
                    self._update_status_lbl.setText(f"Update Available: v{latest}")
                    self._update_status_lbl.setStyleSheet("color: #FBBF24; font-weight: 600;")

                reply = QMessageBox.question(
                    self,
                    "Update Available",
                    f"A new version of Plethora Keraunos (v{latest}) is available!\n\n"
                    f"Release Notes:\n{info.get('release_notes', '')[:300]}\n\n"
                    f"Would you like to download and install this update now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes and download_url:
                    self._start_download_and_install(download_url, asset_name)
            else:
                from keraunos.config import APP_VERSION
                if hasattr(self, "_update_status_lbl"):
                    self._update_status_lbl.setText(f"v{APP_VERSION} (Latest)")
                    self._update_status_lbl.setStyleSheet("color: #10B981; font-weight: 600;")
                if not silent:
                    QMessageBox.information(
                        self,
                        "Up to Date",
                        f"Plethora Keraunos is up to date (v{APP_VERSION}).",
                    )

        def _err(e: str):
            if hasattr(self, "_check_update_btn"):
                self._check_update_btn.setEnabled(True)
                self._check_update_btn.setText("Check for Updates")
            if hasattr(self, "_update_status_lbl"):
                self._update_status_lbl.setText("Check failed")
            if not silent:
                QMessageBox.warning(self, "Update Check", f"Update check failed: {e}")

        self._run_bg(_do_check, _ok, _err)

    def _start_download_and_install(self, download_url: str, asset_name: str) -> None:
        if hasattr(self, "_check_update_btn"):
            self._check_update_btn.setEnabled(False)
            self._check_update_btn.setText("Downloading update...")
        if hasattr(self, "_update_status_lbl"):
            self._update_status_lbl.setText("Downloading...")

        def _do_download():
            from keraunos.updater import download_update
            return download_update(download_url, asset_name)

        def _ok(dest_path: object):
            if hasattr(self, "_check_update_btn"):
                self._check_update_btn.setText("Installing...")
            if hasattr(self, "_update_status_lbl"):
                self._update_status_lbl.setText("Installing...")
            from keraunos.updater import launch_installer_and_exit
            launch_installer_and_exit(str(dest_path), silent=False)

        def _err(e: str):
            if hasattr(self, "_check_update_btn"):
                self._check_update_btn.setEnabled(True)
                self._check_update_btn.setText("Check for Updates")
            if hasattr(self, "_update_status_lbl"):
                self._update_status_lbl.setText("Download failed")
            QMessageBox.critical(self, "Download Failed", f"Failed to download update:\n{e}")

        self._run_bg(_do_download, _ok, _err)

    # ── Navigation shortcuts ───────────────────────────────────────────────

    def _show_drift(self) -> None:
        self.stack.setCurrentIndex(PAGE_DRIFT)

    def _show_history(self) -> None:
        self.on_history_refresh()
        self.stack.setCurrentIndex(PAGE_HISTORY)

    def _show_settings(self) -> None:
        self.stack.setCurrentIndex(PAGE_SETTINGS)

    # ── Event filter (Enter key in hero input) ────────────────────────────

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if (obj is self.prompt_edit and
                event.type() == QEvent.Type.KeyPress and
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and
                not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)):
            self.on_generate()
            return True
        return super().eventFilter(obj, event)

    # ── Helpers ──────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        self.term_view.appendPlainText(msg)
        QApplication.processEvents()

    def _run_bg(self, fn, ok, err, *args, **kwargs) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another operation is still running.")
            return
        self._worker = _Worker(fn, *args, **kwargs)
        self._worker.finished_ok.connect(ok)
        self._worker.finished_err.connect(err)
        self._worker.start()

    def _on_failed(self, err: str) -> None:
        self._log("[Error]\n" + err)
        QMessageBox.critical(self, "Operation failed", err[:2000])

    @staticmethod
    def _friendly_pkg_markup(pkg_id: str) -> str:
        low = pkg_id.lower()
        name = FRIENDLY_PKG_NAMES.get(low)
        if not name:
            parts = pkg_id.split(".")
            name = parts[-1] if len(parts) > 1 else pkg_id
        return f"<strong>{html.escape(name)}</strong> <span style='color: #71717A; font-size: 12px;'>({html.escape(pkg_id)})</span>"

    # ── Core slots ────────────────────────────────────────────────────────

    def on_generate(self) -> None:
        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "Empty prompt",
                                "Describe your desired setup first.")
            return

        threshold = self.settings.get("typo_threshold", 75)
        compiler = OfflineIntentCompiler()
        try:
            state, diagnostics = compiler.compile(
                prompt,
                base_state=self.engine.load_current_state(),
                auto_apply_threshold=85.0,
                suggestion_threshold=float(threshold),
            )
        except Exception as exc:
            self._log(f"[Compiler] Error: {exc}")
            QMessageBox.critical(self, "Compilation failed", str(exc))
            return

        self.pending_state = state
        self.pending_diagnostics = diagnostics

        diff = self.engine.calculate_diff(state)
        diff_text = self.engine.render_diff_text(diff)
        unresolved = compiler.find_unresolved(prompt, diagnostics)

        is_greeting = any(d.target_type == "greeting" for d in diagnostics)

        cards_html: List[str] = []

        if is_greeting:
            # Friendly Welcome Card
            self.pills_container.setVisible(True)
            self.apply_btn.setEnabled(False)
            cards_html.append(
                """
                <div style="background: #141220; border: 1px solid #2B2345; border-radius: 12px; padding: 18px; margin-bottom: 12px;">
                  <div style="font-size: 17px; font-weight: 600; color: #FFFFFF; margin-bottom: 8px;">
                    👋 Hi there! I'm Keraunos.
                  </div>
                  <div style="font-size: 13px; color: #A1A1AA; line-height: 1.5; margin-bottom: 14px;">
                    Tell me what you'd like to do with your PC. I'll turn your plain-English instructions into a safe, automated Windows configuration.
                  </div>
                  <div style="font-size: 12px; font-weight: 600; color: #A78BFA; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px;">
                    Try clicking one of the sample actions below or type your own:
                  </div>
                  <div style="font-size: 13px; color: #D4D4D8; line-height: 1.8;">
                    • <strong>"Install Chrome, VS Code, and 7zip"</strong><br/>
                    • <strong>"Enable dark mode and hide search bar"</strong><br/>
                    • <strong>"Update all my apps"</strong>
                  </div>
                </div>
                """
            )
        else:
            self.pills_container.setVisible(False)
            self.apply_btn.setEnabled(True)

            # Gentle, friendly unresolved notice (no harsh red banner)
            if unresolved:
                quoted = ", ".join(f"'{html.escape(u)}'" for u in unresolved)
                cards_html.append(
                    f'<div style="background-color: #151A24; color: #94A3B8; border: 1px solid #28334E; '
                    f'border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 13px;">'
                    f'ℹ️ I didn\'t recognize {quoted}. Did you mean a specific app or setting? '
                    f'Everything else is ready to apply.'
                    f'</div>'
                )

            # Clean Human-Readable Action Cards
            has_action_cards = False

            # Applications to Install
            winget_add = diff.get("winget_add", [])
            if winget_add:
                has_action_cards = True
                items_html = "".join(
                    f'<li style="margin: 4px 0;">{self._friendly_pkg_markup(p)}</li>'
                    for p in winget_add
                )
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'📥 Applications to Install'
                    f'</div>'
                    f'<ul style="margin: 0; padding-left: 20px; color: #E4E4E7;">{items_html}</ul>'
                    f'</div>'
                )

            # Applications to Update
            winget_up = diff.get("winget_upgrade", [])
            if winget_up:
                has_action_cards = True
                items_html = "".join(
                    f'<li style="margin: 4px 0;">{self._friendly_pkg_markup(p)}</li>'
                    for p in winget_up
                )
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'🔄 Applications to Update'
                    f'</div>'
                    f'<ul style="margin: 0; padding-left: 20px; color: #E4E4E7;">{items_html}</ul>'
                    f'</div>'
                )

            # Applications to Remove
            winget_rem = diff.get("winget_remove", [])
            if winget_rem:
                has_action_cards = True
                items_html = "".join(
                    f'<li style="margin: 4px 0;">{self._friendly_pkg_markup(p)}</li>'
                    for p in winget_rem
                )
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'🗑️ Applications to Remove'
                    f'</div>'
                    f'<ul style="margin: 0; padding-left: 20px; color: #E4E4E7;">{items_html}</ul>'
                    f'</div>'
                )

            # Windows Personalization
            system_tweaks = diff.get("system_tweaks", {})
            if system_tweaks:
                has_action_cards = True
                tweak_items = []
                for k, v in system_tweaks.items():
                    if k in FRIENDLY_SYSTEM_TWEAKS:
                        tweak_text = FRIENDLY_SYSTEM_TWEAKS[k][0] if v else FRIENDLY_SYSTEM_TWEAKS[k][1]
                    else:
                        action = "Enable" if v else "Disable"
                        tweak_text = f"{action} {k.replace('_', ' ')}"
                    tweak_items.append(f'<li style="margin: 4px 0;"><strong>{html.escape(tweak_text)}</strong></li>')
                items_html = "".join(tweak_items)
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'⚙️ Windows Personalization'
                    f'</div>'
                    f'<ul style="margin: 0; padding-left: 20px; color: #E4E4E7;">{items_html}</ul>'
                    f'</div>'
                )

            # System sweep update
            sweep_actions = [d for d in diagnostics if d.target_type == "system_sweep" or d.resolved_target == "all_packages"]
            if sweep_actions:
                has_action_cards = True
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2D1D4E; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #A78BFA; font-size: 14px; margin-bottom: 4px;">'
                    f'🔄 System-Wide Software Update'
                    f'</div>'
                    f'<div style="color: #9E9EAA; font-size: 12px; line-height: 1.5;">'
                    f'Scan and upgrade all installed WinGet applications to their latest available versions.'
                    f'</div>'
                    f'</div>'
                )

            # Hardware Display Configuration
            display_actions = [d for d in diagnostics if d.target_type == "hardware_display"]
            if display_actions:
                has_action_cards = True
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'🖥️ Display & Monitor Configuration'
                    f'</div>'
                    f'<ul style="margin: 0; padding-left: 20px; color: #E4E4E7;">'
                    + "".join(f'<li style="margin: 4px 0;"><strong>{html.escape(d.resolved_target)}</strong></li>' for d in display_actions)
                    + '</ul></div>'
                )

            # Git actions
            git_actions = [d for d in diagnostics if d.target_type == "action" and d.resolved_target == "git_sync"]
            if git_actions:
                has_action_cards = True
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #FFFFFF; font-size: 14px; margin-bottom: 6px;">'
                    f'☁️ Git Synchronization'
                    f'</div>'
                    f'<div style="color: #E4E4E7;">Sync configuration evolution to remote Git origin</div>'
                    f'</div>'
                )

            # App update action
            app_update_actions = [d for d in diagnostics if d.resolved_target == "check_app_updates"]
            if app_update_actions:
                has_action_cards = True
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #3F3356; border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;">'
                    f'<div style="font-weight: 600; color: #A78BFA; font-size: 14px; margin-bottom: 4px;">'
                    f'🔄 Plethora Keraunos Update Check'
                    f'</div>'
                    f'<div style="color: #9E9EAA; font-size: 12px; line-height: 1.5;">'
                    f'Checking GitHub repository for newer version releases and installer packages.'
                    f'</div>'
                    f'</div>'
                )
                QTimer.singleShot(400, lambda: self._on_check_updates_clicked(silent=False))


            # Resolution diagnostics / suggestions
            if diagnostics:
                diag_lines: List[str] = []
                for d in diagnostics:
                    if d.target_type == "greeting":
                        continue
                    conf = int(round(d.confidence))
                    tok = html.escape(d.original_token)
                    tgt = html.escape(d.resolved_target)
                    if d.applied:
                        diag_lines.append(
                            f'<div style="color:#A78BFA;font-size:12px;margin:2px 0;">'
                            f'● {tok} → {tgt} ({conf}%)</div>')
                    elif d.confidence >= float(threshold):
                        diag_lines.append(
                            f'<div style="color:#FBBF24;font-size:12px;margin:2px 0;">'
                            f"◐ '{tok}' → {tgt} ({conf}%) — Suggested: Did you mean {tgt}? (Not applied)</div>")
                if diag_lines:
                    cards_html.append(
                        '<div style="margin-top: 10px; padding: 6px 2px;">'
                        '<span style="color:#71717A;font-size:11px;font-weight:600;text-transform:uppercase;">Matched Components:</span><br/>'
                        + "".join(diag_lines) + '</div>'
                    )

            if not has_action_cards and not unresolved:
                cards_html.append(
                    f'<div style="background: #14121E; border: 1px solid #2A243C; border-radius: 10px; padding: 18px; text-align: center; color: #A1A1AA;">'
                    f'✨ Your system is already in the desired state. No changes needed.'
                    f'</div>'
                )

        self.diff_view.setHtml("".join(cards_html))
        self.term_view.setPlainText(diff_text or "(No technical diff)")
        self._log("[Compiler] Plan ready.")
        self.stack.setCurrentIndex(PAGE_DIFF)

    def on_apply(self) -> None:
        if not self.pending_state and not self.pending_diagnostics:
            QMessageBox.warning(self, "Nothing to apply",
                                "Generate a plan from the Home tab first.")
            return

        is_sweep = any(d.target_type == "system_sweep" or d.resolved_target == "all_packages" for d in (self.pending_diagnostics or []))
        if is_sweep:
            self.apply_btn.setEnabled(False)
            self.apply_btn.setText("Updating system packages...")

            def _apply_sweep():
                import subprocess
                from keraunos.executor import CREATE_NO_WINDOW
                logs: List[str] = ["[WinGet] Starting system-wide software upgrade sweep..."]
                try:
                    cmd = ["winget", "upgrade", "--all", "--accept-package-agreements", "--accept-source-agreements", "--include-unknown"]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=600, creationflags=CREATE_NO_WINDOW)
                    if res.stdout:
                        logs.append(res.stdout)
                    if res.stderr:
                        logs.append(res.stderr)
                    logs.append("[WinGet] System upgrade sweep complete.")
                except Exception as exc:
                    logs.append(f"[WinGet] System upgrade sweep finished/handled: {exc}")
                return "\n".join(logs)

            def _ok_sweep(logs: object):
                self.apply_btn.setEnabled(True)
                self.apply_btn.setText("Apply Changes")
                self._log(str(logs))
                QMessageBox.information(self, "Applied", "System-wide software upgrade completed successfully.")

            def _err_sweep(e: str):
                self.apply_btn.setEnabled(True)
                self.apply_btn.setText("Apply Changes")
                self._on_failed(e)

            self._run_bg(_apply_sweep, _ok_sweep, _err_sweep)
            return

        state = self.pending_state
        if not state:
            return
        elevation = self.settings.get("elevation", "raise")
        self.apply_btn.setEnabled(False)
        self.apply_btn.setText("Applying configuration...")

        self._apply_worker = ApplyWorker(self.engine, state, elevation)

        def _on_progress(status_text: str, current: int, total: int):
            self.apply_btn.setText(status_text)

        def _on_log(line: str):
            self._log(line)

        def _ok(result: object):
            applied_diff, logs = result
            self.apply_btn.setEnabled(True)
            self.apply_btn.setText("Apply Changes")
            msg = generate_deterministic_commit_msg(applied_diff)
            self.on_commit(message=msg, silent=True)
            if self.settings.get("auto_push") and self.repo is not None:
                try:
                    self.repo.push()
                    self._log("[Git] Auto-pushed to origin.")
                except Exception as exc:
                    self._log(f"[Git] Auto-push failed: {exc}")
            QMessageBox.information(self, "Applied",
                                    "All changes applied successfully!")

        def _err(e: str):
            self.apply_btn.setEnabled(True)
            self.apply_btn.setText("Apply Changes")
            self._on_failed(e)

        self._apply_worker.progress.connect(_on_progress)
        self._apply_worker.log_line.connect(_on_log)
        self._apply_worker.finished_ok.connect(_ok)
        self._apply_worker.finished_err.connect(_err)
        self._apply_worker.start()

    def on_commit(self, message: Optional[str] = None,
                  silent: bool = False) -> None:
        if self.repo is None:
            if not silent:
                QMessageBox.warning(self, "No git repo",
                                    "Git repository unavailable.")
            return
        try:
            if not message:
                d = self.engine.calculate_diff(
                    self.pending_state) if self.pending_state else {}
                message = generate_deterministic_commit_msg(d)
            sha = self.repo.commit_evolution(message)
            self._log(f"[Git] Snapshot saved: {message}")
            self.on_history_refresh()
        except Exception as exc:
            if not silent:
                QMessageBox.critical(self, "Commit failed", str(exc))

    @staticmethod
    def _format_friendly_history(message: str, date_str: str) -> str:
        parts = [p.strip() for p in message.split(";") if p.strip()]
        friendly_actions = []
        for part in parts:
            if part.startswith("feat(packages): add "):
                pkgs = part[len("feat(packages): add "):].strip()
                friendly_actions.append(f"Install {pkgs}")
            elif part.startswith("feat(packages): remove "):
                pkgs = part[len("feat(packages): remove "):].strip()
                friendly_actions.append(f"Uninstall {pkgs}")
            elif part.startswith("chore(system): configure "):
                tweaks = part[len("chore(system): configure "):].strip().replace("_", " ")
                friendly_actions.append(f"Personalize Windows ({tweaks})")
            elif part.startswith("chore: "):
                friendly_actions.append(part[len("chore: "):].capitalize())
            else:
                friendly_actions.append(part)

        title = " & ".join(friendly_actions) if friendly_actions else "System Snapshot"

        try:
            dt = datetime.fromisoformat(date_str[:16].replace(" ", "T"))
            formatted_date = dt.strftime("%b %d, %Y · %I:%M %p")
        except Exception:
            formatted_date = date_str[:16]

        return f"{title}\n  {formatted_date}"

    def on_history_refresh(self) -> None:
        self.history_list.clear()
        if self.repo is None:
            return
        for entry in self.repo.log(50):
            friendly_label = self._format_friendly_history(entry["message"], entry["date"])
            item = QListWidgetItem(friendly_label)
            item.setData(Qt.ItemDataRole.UserRole, entry["sha"])
            self.history_list.addItem(item)

    def on_history_restore(self) -> None:
        item = self.history_list.currentItem()
        if not item:
            QMessageBox.warning(self, "No selection", "Select a snapshot first.")
            return
        sha: str = item.data(Qt.ItemDataRole.UserRole)
        try:
            assert self.repo is not None
            content = self.repo.show_file_at(sha)
            state = KeraunosState.from_yaml(content)
            self.pending_state = state
            self.on_generate()
            self._log(f"[Git] Restored snapshot {sha[:8]} — click Apply Changes to enforce.")
        except Exception as exc:
            QMessageBox.critical(self, "Restore failed", str(exc))

    def on_drift(self) -> None:
        desired = self.pending_state or self.engine.load_current_state()
        self._run_bg(DriftDetector.compare, self._on_drift_ok,
                     self._on_failed, desired)

    def _on_drift_ok(self, report: object) -> None:
        from keraunos.drift import DriftReport
        assert isinstance(report, DriftReport)
        self.drift_table.setRowCount(len(report.items))
        for i, it in enumerate(report.items):
            self.drift_table.setItem(i, 0, QTableWidgetItem(it.category))
            self.drift_table.setItem(i, 1, QTableWidgetItem(it.key))
            self.drift_table.setItem(i, 2, QTableWidgetItem(it.expected))
            self.drift_table.setItem(i, 3, QTableWidgetItem(it.actual))
        self._log("[Drift] " + report.summary())

    # ── Frameless drag ────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (event.globalPosition().toPoint()
                              - self.frameGeometry().topLeft())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton
                and self._drag_pos is not None):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)


# ─── Entry point ───────────────────────────────────────────────────────────

def main(state_dir: Optional[Path] = None) -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Plethora Keraunos")
    win = KeraunosWindow(state_dir)
    win.show()
    win.on_history_refresh()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
