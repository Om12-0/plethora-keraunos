"""Electric Purple nixmac-style stylesheet for the Keraunos overlay."""

APP_QSS = """
/* ── Global reset ─────────────────────────────────────────── */
* {
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
    color: #EEEEF0;
    outline: none;
}

/* ── Window container ─────────────────────────────────────── */
QMainWindow { background: transparent; }

QWidget#Root {
    background-color: #0D0D0E;
    border: 1px solid #232328;
    border-radius: 14px;
}

/* ── Header bar ───────────────────────────────────────────── */
QWidget#HeaderBar {
    background-color: transparent;
    border-bottom: 1px solid #1A1A1F;
}

QLabel#AppName {
    font-size: 11px;
    color: #8E8E98;
    font-weight: 500;
    letter-spacing: 0.2px;
}

/* Icon action buttons (top-right bar) */
QPushButton#IconBtn {
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 0px;
    color: #71717A;
    font-size: 14px;
}
QPushButton#IconBtn:hover {
    background-color: #1A1A22;
    color: #EEEEF0;
}

/* ── Stacked pages shared ─────────────────────────────────── */
QWidget#Page {
    background-color: transparent;
}

/* ── Hero page ────────────────────────────────────────────── */
QLabel#HeroTitle {
    font-size: 20px;
    font-weight: 600;
    color: #EEEEF0;
}

QWidget#IconCard {
    background-color: #15131C;
    border: 1px solid #262235;
    border-radius: 14px;
}

QWidget#InputCard {
    background-color: #121117;
    border: 1px solid #221F2D;
    border-radius: 12px;
}

QPlainTextEdit#HeroInput {
    background-color: transparent;
    border: none;
    color: #EEEEF0;
    font-size: 14px;
    padding: 0px;
    selection-background-color: #3B1B75;
}

QPlainTextEdit#HeroInput:focus {
    border: none;
    outline: none;
}

QPushButton#SubmitBtn {
    background-color: #8B5CF6;
    color: #FFFFFF;
    border: none;
    border-radius: 16px;
    font-size: 16px;
    font-weight: 700;
    padding: 0px;
}
QPushButton#SubmitBtn:hover {
    background-color: #7C3AED;
}
QPushButton#SubmitBtn:pressed {
    background-color: #6D28D9;
}

/* ── Action cards & Review page ───────────────────────────── */
QTextEdit#DiffView {
    background-color: #0A0A0E;
    border: 1px solid #1E1C28;
    border-radius: 10px;
    color: #EEEEF0;
    font-size: 13px;
    padding: 10px;
    selection-background-color: #3B1B75;
}

QPlainTextEdit#TermView {
    background-color: #0A0A0E;
    border: 1px solid #1E1C28;
    border-radius: 8px;
    color: #A78BFA;
    font-family: 'Consolas', 'Cascadia Code', monospace;
    font-size: 12px;
    padding: 8px;
}

QPushButton#PrimaryBtn {
    background-color: #8B5CF6;
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 9px 20px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton#PrimaryBtn:hover { background-color: #7C3AED; }
QPushButton#PrimaryBtn:pressed { background-color: #6D28D9; }
QPushButton#PrimaryBtn:disabled { background-color: #2A2833; color: #555360; }

QPushButton#GhostBtn {
    background-color: transparent;
    color: #A1A1AA;
    border: 1px solid #2E2C38;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton#GhostBtn:hover { border-color: #8B5CF6; color: #EEEEF0; }

QPushButton#PillBtn {
    background-color: #171424;
    color: #C4B5FD;
    border: 1px solid #38295E;
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 12px;
}
QPushButton#PillBtn:hover {
    background-color: #241D3B;
    border-color: #8B5CF6;
    color: #FFFFFF;
}

/* ── History page ─────────────────────────────────────────── */
QListWidget#HistoryList {
    background: #0A0A0E;
    border: 1px solid #1E1C28;
    border-radius: 10px;
    color: #EEEEF0;
    padding: 4px;
}
QListWidget#HistoryList::item { padding: 10px 12px; border-radius: 6px; }
QListWidget#HistoryList::item:hover { background: #161422; }
QListWidget#HistoryList::item:selected { background: #2D1D4E; color: #C4B5FD; }

/* ── Drift page ───────────────────────────────────────────── */
QTableWidget#DriftTable {
    background: #0A0A0E;
    border: 1px solid #1E1C28;
    border-radius: 10px;
    color: #EEEEF0;
    gridline-color: #1A1824;
}
QHeaderView::section {
    background: #111018;
    color: #8E8E98;
    border: none;
    padding: 8px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Settings page ────────────────────────────────────────── */
QWidget#SettingsPage {
    background-color: transparent;
}

QWidget#SettingsCard {
    background-color: #111018;
    border: 1px solid #1E1C28;
    border-radius: 10px;
}

QLabel#SettingsGroup {
    font-size: 10px;
    font-weight: 700;
    color: #A78BFA;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}

QLabel#SettingLabel {
    font-size: 13px;
    color: #CBCBD0;
}

QLabel#SettingDesc {
    font-size: 11px;
    color: #6E6D7A;
}

QLabel#SliderValue {
    font-size: 12px;
    font-weight: 600;
    color: #A78BFA;
    min-width: 36px;
}

QComboBox {
    background-color: #0D0D12;
    border: 1px solid #282535;
    border-radius: 7px;
    padding: 6px 10px;
    color: #CBCBD0;
    font-size: 13px;
    min-height: 28px;
}
QComboBox:focus { border-color: #8B5CF6; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #161420;
    border: 1px solid #282535;
    border-radius: 6px;
    selection-background-color: #2D1D4E;
    color: #CBCBD0;
}

QLineEdit {
    background-color: #0D0D12;
    border: 1px solid #282535;
    border-radius: 7px;
    padding: 7px 10px;
    color: #CBCBD0;
    font-size: 13px;
}
QLineEdit:focus { border-color: #8B5CF6; }
QLineEdit::placeholder { color: #52505E; }

QCheckBox {
    color: #CBCBD0;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #363245;
    background: #0D0D12;
}
QCheckBox::indicator:checked {
    background-color: #8B5CF6;
    border-color: #8B5CF6;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #252230;
    border-radius: 2px;
}
QSlider::sub-page:horizontal {
    background: #8B5CF6;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #8B5CF6;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

/* ── Scrollbar ────────────────────────────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #282436;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #38324C; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

/* Back button */
QPushButton#BackBtn {
    background-color: transparent;
    color: #71717A;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
    text-align: left;
}
QPushButton#BackBtn:hover { color: #A78BFA; }
"""
