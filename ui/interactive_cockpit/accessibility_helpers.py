"""Accessibility helpers — keyboard focus, contrast, mode badges."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QTabBar, QTableWidget, QWidget

from ui.interactive_cockpit.button_roles import apply_button_affordance
from ui.interactive_cockpit.cockpit_theme import MODE_BADGE_STYLES, apply_cockpit_theme

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def mode_badge(text: str, mode: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(MODE_BADGE_STYLES.get(mode, MODE_BADGE_STYLES["PLANNING"]))
    lbl.setWordWrap(True)
    lbl.setAccessibleName(text)
    return lbl


def install_keyboard_shortcuts(win: "InteractiveCockpitWindow") -> None:
    keys = [
        ("Ctrl+1", "overview"),
        ("Ctrl+2", "t212"),
        ("Ctrl+3", "investments"),
        ("Ctrl+4", "paper"),
        ("Ctrl+5", "planning"),
        ("Ctrl+6", "order_review"),
        ("Ctrl+7", "risk"),
        ("Ctrl+8", "activity"),
        ("Ctrl+9", "settings"),
    ]
    for seq, nav_key in keys:
        sc = QShortcut(QKeySequence(seq), win)
        sc.activated.connect(lambda k=nav_key: win._go_nav(k))
    refresh = QShortcut(QKeySequence("F5"), win)
    refresh.activated.connect(lambda: win.refresh_state(full=True))


def tag_interactive_widgets(root: QWidget) -> None:
    """Ensure clickable controls expose readable accessible names."""
    for btn in root.findChildren(QPushButton):
        if not btn.accessibleName():
            label = btn.text().strip() or btn.toolTip().strip()
            if label:
                btn.setAccessibleName(label)
    for combo in root.findChildren(QComboBox):
        if not combo.accessibleName() and combo.objectName():
            combo.setAccessibleName(combo.objectName().replace("_", " "))
    for field in root.findChildren(QLineEdit):
        if not field.accessibleName() and field.placeholderText():
            field.setAccessibleName(field.placeholderText())
    for table in root.findChildren(QTableWidget):
        if not table.accessibleName():
            table.setAccessibleName("Datentabelle")
    for tab_bar in root.findChildren(QTabBar):
        if not tab_bar.accessibleName():
            tab_bar.setAccessibleName("Registerkarten")
    for chk in root.findChildren(QCheckBox):
        if not chk.accessibleName() and chk.text():
            chk.setAccessibleName(chk.text())


def apply_accessibility_baseline(app_widget: QWidget) -> None:
    apply_cockpit_theme(app_widget)


def apply_window_accessibility(window: QWidget) -> None:
    apply_button_affordance(window)
    tag_interactive_widgets(window)
