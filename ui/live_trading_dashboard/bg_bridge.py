"""Thread-safe Qt bridge — worker threads must not touch widgets directly."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class DashboardBgBridge(QObject):
    """Emit from background threads; slots run on the GUI thread."""

    action_finished = Signal(object)
    refresh_finished = Signal(object)
