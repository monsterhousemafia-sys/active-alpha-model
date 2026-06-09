"""Unified Marktanalyse Investment Cockpit visual theme (P18) — Windows accent blue."""
from __future__ import annotations

import os
import sys

# Windows 11 accent palette
WIN_BLUE = "#0078D4"
WIN_BLUE_HOVER = "#1A8CFF"
WIN_BLUE_PRESSED = "#005A9E"
WIN_BLUE_GLOW = "#3399FF"
WIN_BLUE_SOFT = "#1A3D5C"
WIN_BLUE_MIST = "#0D2840"

# Core palette — dark professional (broker-terminal inspired)
BG_APP = "#0f1419"
BG_PANEL = "#1a2332"
BG_ELEVATED = "#243044"
BG_INPUT = "#1e2a3a"
BORDER = "#3d5166"
BORDER_FOCUS = WIN_BLUE_GLOW
TEXT_PRIMARY = "#e8eef5"
TEXT_SECONDARY = "#9eb0c4"
TEXT_MUTED = "#6b7d92"
ACCENT = WIN_BLUE

# Semantic surfaces
SAFETY_BANNER = f"background:{BG_ELEVATED};color:#ffcccc;padding:10px;border:1px solid #884444;font-weight:bold;"
INFO_PANEL = f"background:{BG_PANEL};color:{TEXT_PRIMARY};padding:8px;border:1px solid {BORDER};"
MARKET_STATUS = f"padding:8px;background:{BG_PANEL};color:#d0e8ff;border:1px solid {BORDER};"
CARD_SUBTITLE = f"color:{TEXT_MUTED};font-size:11px;"

WARNING_BANNER = f"background:#3d3010;color:#ffe0a0;padding:8px;border:1px solid #886622;"
ERROR_BANNER = f"background:#4a2020;color:#ffcccc;padding:8px;font-weight:bold;border:1px solid #884444;"
SUCCESS_BANNER = f"background:#1a2a1a;color:#ccffcc;padding:6px;border:1px solid #336633;"
TICKET_WARN = f"background:#3d3010;color:#ffe0a0;padding:8px;border:1px solid #886622;"

SEVERITY_STYLES = {
    "CRITICAL": f"background:#4a1010;color:#ffcccc;border:1px solid #aa4444;padding:8px;",
    "ERROR": f"background:#4a2010;color:#ffd0c0;border:1px solid #aa6644;padding:8px;",
    "WARNING": f"background:#3d3010;color:#ffe8a0;border:1px solid #886622;padding:8px;",
    "INFO": f"background:{BG_PANEL};color:#cce0ff;border:1px solid {BORDER};padding:8px;",
}

MODE_BADGE_STYLES = {
    "REAL_READONLY": f"background:{BG_PANEL};color:#cce5ff;padding:4px 8px;font-weight:bold;border:1px solid {BORDER};",
    "PAPER": f"background:#2a2a1a;color:#ffffcc;padding:4px 8px;font-weight:bold;border:1px solid #666633;",
    "PLANNING": f"background:{BG_ELEVATED};color:{TEXT_PRIMARY};padding:4px 8px;font-weight:bold;border:1px solid {BORDER};",
    "LIVE_LOCKED": f"background:#4a2020;color:#ffcccc;padding:4px 8px;font-weight:bold;border:1px solid #884444;",
    "INTRADAY_PAPER": f"background:#1a3a2a;color:#ccffdd;padding:4px 8px;font-weight:bold;border:1px solid #336633;",
    "FRESH": f"background:#1a3a2a;color:#ccffdd;padding:4px 8px;font-weight:bold;border:1px solid #336633;",
    "STALE": f"background:#3d3010;color:#ffe0a0;padding:4px 8px;font-weight:bold;border:1px solid #886622;",
}

KILL_SWITCH_BTN = "background:#660000;color:white;font-weight:bold;border:1px solid #880000;padding:6px 12px;"

# Windows 11 control hierarchy — clickable BEFORE hover; selected nav stays latent
COCKPIT_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_APP};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", "Segoe UI Variable Text", sans-serif;
    font-size: 10pt;
}}
QFrame {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 4px;
}}
QGroupBox {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {TEXT_PRIMARY};
}}

/* —— Default = secondary (sichtbar klickbar, Win11 outline) —— */
QPushButton {{
    background-color: {WIN_BLUE_MIST};
    color: #d6ebff;
    border: 1px solid #4a90c9;
    padding: 8px 16px;
    border-radius: 4px;
    min-height: 32px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {WIN_BLUE_SOFT};
    border: 1px solid {WIN_BLUE_HOVER};
    color: #ffffff;
}}
QPushButton:pressed {{
    background-color: {WIN_BLUE_PRESSED};
    border: 1px solid {WIN_BLUE};
    color: #ffffff;
}}
QPushButton:focus {{
    border: 2px solid {WIN_BLUE_GLOW};
    outline: none;
}}
QPushButton:disabled {{
    background-color: {BG_ELEVATED};
    color: {TEXT_MUTED};
    border: 1px solid {BORDER};
}}

/* Primary — Hauptaktion, sofort erkennbar (Fluent accent fill) */
QPushButton#primaryButton {{
    background-color: {WIN_BLUE};
    color: #ffffff;
    border: 1px solid {WIN_BLUE_GLOW};
    font-weight: 600;
    min-height: 34px;
    padding: 8px 18px;
}}
QPushButton#primaryButton:hover {{
    background-color: {WIN_BLUE_HOVER};
    border: 1px solid #5eb3ff;
}}
QPushButton#primaryButton:pressed {{
    background-color: {WIN_BLUE_PRESSED};
    border: 1px solid {WIN_BLUE};
}}

/* Secondary — explizite Outline-Aktion */
QPushButton#secondaryButton {{
    background-color: {WIN_BLUE_MIST};
    color: #cce8ff;
    border: 1px solid {WIN_BLUE};
    font-weight: 500;
}}
QPushButton#secondaryButton:hover {{
    background-color: {WIN_BLUE_SOFT};
    color: #ffffff;
    border: 1px solid {WIN_BLUE_HOVER};
}}
QPushButton#secondaryButton:pressed {{
    background-color: {WIN_BLUE_PRESSED};
    color: #ffffff;
}}

/* Tertiary — weniger dominant, aber sichtbar (Entfernen, Zurücksetzen) */
QPushButton#tertiaryButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px dashed #4a6580;
    font-weight: 400;
}}
QPushButton#tertiaryButton:hover {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid #5a7896;
}}
QPushButton#tertiaryButton:pressed {{
    background-color: {BG_PANEL};
}}

/* Navigation — vor Klick einladend; nach Auswahl latent/statisch */
QPushButton#navButton {{
    text-align: left;
    padding: 10px 12px 10px 10px;
    border-radius: 4px;
    font-weight: 500;
    background-color: {BG_PANEL};
    color: #b8d9f5;
    border: 1px solid #355a7a;
    border-left: 3px solid #355a7a;
    min-height: 28px;
}}
QPushButton#navButton:hover {{
    background-color: {WIN_BLUE_MIST};
    border: 1px solid {WIN_BLUE};
    border-left: 3px solid {WIN_BLUE_HOVER};
    color: #ffffff;
}}
QPushButton#navButton:pressed {{
    background-color: {WIN_BLUE_SOFT};
    border-left: 3px solid {WIN_BLUE};
}}
QPushButton#navButton:checked {{
    background-color: #151c28;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-left: 3px solid {WIN_BLUE};
    font-weight: 600;
}}
QPushButton#navButton:checked:hover {{
    background-color: #181f2d;
    border: 1px solid {BORDER};
    border-left: 3px solid {WIN_BLUE};
    color: {TEXT_PRIMARY};
}}

/* Hyperlink-Aktionen */
QPushButton#linkButton {{
    background-color: {WIN_BLUE_MIST};
    border: 1px solid transparent;
    color: {WIN_BLUE_HOVER};
    text-decoration: underline;
    padding: 6px 10px;
    font-weight: 500;
}}
QPushButton#linkButton:hover {{
    background-color: {WIN_BLUE_SOFT};
    border: 1px solid {WIN_BLUE};
    color: #ffffff;
    text-decoration: none;
}}

/* Gefahr — Kill Switch */
QPushButton#dangerButton {{
    background-color: #5c1010;
    color: #ffe0e0;
    border: 1px solid #aa3333;
    font-weight: 700;
}}
QPushButton#dangerButton:hover {{
    background-color: #7a1515;
    border: 1px solid #cc4444;
    color: #ffffff;
}}
QPushButton#dangerButton:pressed {{
    background-color: #4a0c0c;
}}

QTabBar::tab {{
    background: {BG_ELEVATED};
    color: {TEXT_SECONDARY};
    padding: 8px 14px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}}
QTabBar::tab:hover {{
    background: {WIN_BLUE_MIST};
    color: #ffffff;
    border: 1px solid {WIN_BLUE};
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {BG_PANEL};
    color: #ffffff;
    border: 1px solid {WIN_BLUE};
    border-bottom: 2px solid {WIN_BLUE};
}}

QLineEdit, QSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 3px;
}}
QLineEdit:hover, QSpinBox:hover {{
    border: 1px solid {WIN_BLUE};
}}
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 3px;
    min-height: 24px;
}}
QComboBox:hover {{
    border: 1px solid {WIN_BLUE};
    background-color: {WIN_BLUE_MIST};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::drop-down:hover {{
    background-color: {WIN_BLUE};
}}
QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    selection-background-color: {WIN_BLUE};
    selection-color: #ffffff;
    border: 1px solid {WIN_BLUE};
}}

QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 6px;
}}
QCheckBox:hover {{
    color: {WIN_BLUE_HOVER};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER};
    border-radius: 2px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {WIN_BLUE};
    background: {WIN_BLUE_MIST};
}}
QCheckBox::indicator:checked {{
    background: {WIN_BLUE};
    border: 1px solid {WIN_BLUE_GLOW};
}}

QTableWidget {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    selection-background-color: {WIN_BLUE};
    selection-color: #ffffff;
}}
QTableWidget::item:hover {{
    background-color: {WIN_BLUE_MIST};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    padding: 4px;
    border: 1px solid {BORDER};
}}
QHeaderView::section:hover {{
    background-color: {WIN_BLUE_SOFT};
    border: 1px solid {WIN_BLUE};
    color: #ffffff;
}}

QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG_PANEL};
}}
QScrollArea {{
    border: none;
    background: {BG_APP};
}}
QScrollBar:vertical {{
    background: {BG_PANEL};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BG_ELEVATED};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {WIN_BLUE};
}}
QProgressBar {{
    border: 1px solid {BORDER};
    background: {BG_INPUT};
    text-align: center;
    color: {TEXT_PRIMARY};
}}
QProgressBar::chunk {{
    background-color: {WIN_BLUE};
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}
QLineEdit:focus, QComboBox:focus, QCheckBox:focus, QSpinBox:focus {{
    border: 2px solid {WIN_BLUE_GLOW};
    outline: none;
}}
"""

HIGH_CONTRAST_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #000000;
    color: #ffffff;
    font-family: "Segoe UI", sans-serif;
    font-size: 11pt;
}
QPushButton {
    background-color: #000000;
    color: #ffffff;
    border: 2px solid #ffffff;
    padding: 8px 14px;
    min-height: 28px;
}
QPushButton:hover, QPushButton:focus {
    background-color: #ffffff;
    color: #000000;
    border: 2px solid #ffff00;
}
QPushButton:checked {
    background-color: #0078D4;
    color: #ffffff;
    border: 2px solid #ffffff;
}
QLineEdit, QSpinBox, QComboBox, QTableWidget {
    background-color: #000000;
    color: #ffffff;
    border: 2px solid #ffffff;
}
QTabBar::tab:selected {
    background: #0078D4;
    color: #ffffff;
    border: 2px solid #ffffff;
}
QHeaderView::section {
    background-color: #000000;
    color: #ffffff;
    border: 2px solid #ffffff;
}
QLabel { color: #ffffff; }
"""


def high_contrast_requested() -> bool:
    if os.environ.get("AA_HIGH_CONTRAST", "").strip() == "1":
        return True
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("dwFlags", wintypes.DWORD),
                ("lpszDefaultScheme", wintypes.LPWSTR),
            ]

        hc = HIGHCONTRAST()
        hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        if ctypes.windll.user32.SystemParametersInfoW(0x0042, hc.cbSize, ctypes.byref(hc), 0):
            return bool(hc.dwFlags & 0x1)
    except (AttributeError, OSError, ValueError):
        pass
    return False


def apply_cockpit_theme(app_widget) -> None:
    """Apply global stylesheet to QApplication."""
    sheet = HIGH_CONTRAST_STYLESHEET if high_contrast_requested() else COCKPIT_STYLESHEET
    app_widget.setStyleSheet(sheet)
