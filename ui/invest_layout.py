"""Uniform layout and typography for the minimal Invest UI."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.interactive_cockpit.cockpit_theme import (
    BG_ELEVATED,
    BG_PANEL,
    BORDER,
    ERROR_BANNER,
    INFO_PANEL,
    SUCCESS_BANNER,
    TEXT_PRIMARY,
    WARNING_BANNER,
)

SPACING = 14
ROW_HEIGHT = 40
BUTTON_HEIGHT = 46
TABLE_ROW_HEIGHT = 36
FONT_PT = 11
TITLE_PT = 12
METRIC_PT = 14

CARD_STYLE = (
    f"background:{BG_PANEL}; color:{TEXT_PRIMARY}; "
    f"padding:12px; border:1px solid {BORDER}; border-radius:6px;"
)
METRIC_STYLE = (
    f"background:{BG_ELEVATED}; color:{TEXT_PRIMARY}; "
    f"font-size:{METRIC_PT}pt; font-weight:600; padding:14px; "
    f"border:1px solid {BORDER}; border-radius:6px;"
)

INVEST_EXTRA_STYLESHEET = f"""
QLabel {{
    font-size: {FONT_PT}pt;
}}
QGroupBox {{
    font-size: {TITLE_PT}pt;
    font-weight: 600;
    padding-top: 18px;
    margin-top: 4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
}}
QPushButton {{
    min-height: {BUTTON_HEIGHT}px;
    font-size: {FONT_PT}pt;
}}
QLineEdit, QComboBox {{
    min-height: {ROW_HEIGHT}px;
    font-size: {FONT_PT}pt;
    padding: 6px 10px;
}}
QCheckBox {{
    font-size: {FONT_PT}pt;
    min-height: {ROW_HEIGHT}px;
}}
QTableWidget {{
    font-size: {FONT_PT}pt;
}}
QHeaderView::section {{
    font-size: {FONT_PT}pt;
    padding: 10px 8px;
    min-height: {TABLE_ROW_HEIGHT}px;
}}
QTableWidget::item {{
    padding: 10px 8px;
}}
"""


def apply_invest_typography(app) -> None:
    from ui.interactive_cockpit.cockpit_theme import apply_cockpit_theme

    apply_cockpit_theme(app)
    app.setStyleSheet(app.styleSheet() + INVEST_EXTRA_STYLESHEET)


def make_scroll_host() -> tuple[QScrollArea, QVBoxLayout]:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setSpacing(SPACING)
    lay.setContentsMargins(16, 16, 16, 16)
    scroll.setWidget(host)
    return scroll, lay


def make_section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    inner = QVBoxLayout(box)
    inner.setSpacing(SPACING)
    inner.setContentsMargins(12, 20, 12, 12)
    return box, inner


def _mark_display_only(lbl: QLabel) -> QLabel:
    """Status/text panels must not steal clicks from buttons below."""
    lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    lbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return lbl


def body_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(CARD_STYLE)
    lbl.setMinimumHeight(ROW_HEIGHT + 8)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return _mark_display_only(lbl)


def metric_label(text: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(METRIC_STYLE)
    lbl.setMinimumHeight(56)
    lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return _mark_display_only(lbl)


def status_label(text: str = "") -> QLabel:
    lbl = body_label(text)
    return lbl


def set_banner(lbl: QLabel, kind: str) -> None:
    styles = {
        "ok": SUCCESS_BANNER,
        "warn": WARNING_BANNER,
        "err": ERROR_BANNER,
        "info": INFO_PANEL,
    }
    lbl.setStyleSheet(styles.get(kind, INFO_PANEL) + f" font-size:{FONT_PT}pt; padding:12px;")


def uniform_button_row(*buttons: QPushButton) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(SPACING)
    for btn in buttons:
        btn.setMinimumHeight(BUTTON_HEIGHT)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row.addWidget(btn, 1)
    return row


def configure_form(form: QFormLayout) -> None:
    form.setSpacing(SPACING)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)


def configure_table(table: QTableWidget) -> None:
    table.setMinimumHeight(180)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(TABLE_ROW_HEIGHT + 8)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.setShowGrid(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)


def full_width_primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setMinimumHeight(BUTTON_HEIGHT + 4)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    f = btn.font()
    f.setPointSize(TITLE_PT)
    f.setWeight(QFont.Weight.DemiBold)
    btn.setFont(f)
    return btn
