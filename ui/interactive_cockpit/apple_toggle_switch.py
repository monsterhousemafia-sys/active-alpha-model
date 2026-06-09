"""Apple-style on/off slider toggle (green when on, white when off)."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, Property, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QSizePolicy, QWidget

IOS_GREEN = QColor("#34C759")
TRACK_OFF = QColor("#FFFFFF")
KNOB = QColor("#FFFFFF")
TRACK_BORDER = QColor("#D1D1D6")


class AppleToggleSwitch(QCheckBox):
    """Slide toggle — checked = ON (green track), unchecked = OFF (white track)."""

    toggled_by_user = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Review Mode Schalter")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(52, 32)
        self._knob_pos = 1.0 if self.isChecked() else 0.0
        self._anim = QPropertyAnimation(self, b"knobPosition", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggled)
        self.setStyleSheet("QCheckBox { spacing: 0; background: transparent; }")

    def get_knob_position(self) -> float:
        return self._knob_pos

    def set_knob_position(self, value: float) -> None:
        self._knob_pos = max(0.0, min(1.0, float(value)))
        self.update()

    knobPosition = Property(float, get_knob_position, set_knob_position)

    def _on_toggled(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setChecked(self, checked: bool) -> None:  # noqa: N802 — Qt API
        self._anim.stop()
        self._knob_pos = 1.0 if checked else 0.0
        super().setChecked(checked)
        self.update()

    def nextCheckState(self) -> None:
        super().nextCheckState()
        self.toggled_by_user.emit(self.isChecked())

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        track_h = 26
        track_y = (h - track_h) / 2
        track_rect = (4, track_y, w - 8, track_h)
        radius = track_h / 2

        if self.isChecked():
            painter.setBrush(IOS_GREEN)
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(TRACK_OFF)
            painter.setPen(QPen(TRACK_BORDER, 1))
        painter.drawRoundedRect(*track_rect, radius, radius)

        knob_d = track_h - 6
        travel = track_rect[2] - knob_d - 6
        knob_x = track_rect[0] + 3 + travel * self._knob_pos
        knob_y = track_y + 3
        painter.setBrush(KNOB)
        painter.setPen(QPen(QColor("#00000015"), 1))
        painter.drawEllipse(int(knob_x), int(knob_y), int(knob_d), int(knob_d))
        painter.end()

    def hitButton(self, pos) -> bool:  # noqa: N802
        return self.contentsRect().contains(pos)
