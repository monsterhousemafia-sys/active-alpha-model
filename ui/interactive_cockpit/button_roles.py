"""Windows 11-style button roles — visible affordance before click, latent after."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QWidget

ROLE_PRIMARY = "primaryButton"
ROLE_SECONDARY = "secondaryButton"
ROLE_TERTIARY = "tertiaryButton"
ROLE_NAV = "navButton"
ROLE_LINK = "linkButton"
ROLE_DANGER = "dangerButton"

_KNOWN_ROLES = frozenset(
    {ROLE_PRIMARY, ROLE_SECONDARY, ROLE_TERTIARY, ROLE_NAV, ROLE_LINK, ROLE_DANGER}
)


def set_button_role(btn: QPushButton, role: str) -> None:
    btn.setObjectName(role)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if role == ROLE_NAV:
        btn.setCheckable(True)


def apply_button_affordance(root: QWidget) -> None:
    """Untagged push buttons become secondary (visible outline) — never invisible actions."""
    for btn in root.findChildren(QPushButton):
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if (btn.objectName() or "") in _KNOWN_ROLES:
            continue
        btn.setObjectName(ROLE_SECONDARY)
