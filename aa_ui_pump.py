"""Keep the Qt UI responsive while the main thread runs blocking work."""
from __future__ import annotations

import os


def plain_progress_quiet() -> bool:
    return os.environ.get("AA_PLAIN_PROGRESS_QUIET", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def pump_ui(*, force: bool = True) -> None:
    if plain_progress_quiet():
        return
    try:
        from aa_dashboard_qt_window import AppSession

        session = AppSession._instance
        if session is None:
            return
        if force:
            session.flush(force=True)
        else:
            session.mark_dirty()
            session._tick()
        session.window._animate_progress()
        session._process_events()
    except Exception:
        pass
