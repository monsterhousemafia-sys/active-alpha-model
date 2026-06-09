"""Reusable failure-state panel for dashboard views."""
from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ui.interactive_cockpit.accessibility_helpers import mode_badge
from ui.interactive_cockpit.cockpit_theme import SEVERITY_STYLES, TEXT_MUTED


def build_failure_state_panel(state: Dict[str, Any]) -> QWidget:
    from ui.interactive_cockpit.services.failure_state_service import classify_system_state

    fs = classify_system_state(state)
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("<h3>Systemstatus & Fehlerzustände</h3>"))
    row = QWidget()
    row_l = QVBoxLayout(row)
    row_l.addWidget(mode_badge("REAL READ-ONLY", "REAL_READONLY"))
    row_l.addWidget(mode_badge("PAPER SIMULATION", "PAPER"))
    row_l.addWidget(mode_badge("PLANUNG — KEINE ORDER", "PLANNING"))
    row_l.addWidget(mode_badge("CONFIRMED LIVE — REVIEW GESPERRT", "LIVE_LOCKED"))
    row_l.addWidget(mode_badge("INTRADAY RESEARCH — PAPER ONLY", "INTRADAY_PAPER"))
    fresh = (state.get("market_price_freshness") or {}).get("status", "")
    if fresh:
        row_l.addWidget(mode_badge(f"LIVE-PREISE: {fresh}", "FRESH" if fresh == "FRESH" else "STALE"))
    lay.addWidget(row)

    overall = fs.get("overall", "OK")
    hdr = QLabel(f"Gesamtstatus: {overall}")
    hdr.setStyleSheet(SEVERITY_STYLES.get(overall if overall in SEVERITY_STYLES else "INFO", SEVERITY_STYLES["INFO"]))
    lay.addWidget(hdr)

    issues: List[Dict[str, str]] = fs.get("issues") or []
    if not issues:
        ok = QLabel("Keine aktiven Fehlerzustände.")
        ok.setWordWrap(True)
        lay.addWidget(ok)
    else:
        for issue in issues:
            lay.addWidget(_issue_frame(issue))

    empty = fs.get("empty_state_message", "")
    if empty:
        e = QLabel(empty)
        e.setWordWrap(True)
        e.setStyleSheet(f"color:{TEXT_MUTED};font-style:italic;padding:4px;")
        lay.addWidget(QLabel("<b>Leerzustand / Hinweis</b>"))
        lay.addWidget(e)
    return w


def _issue_frame(issue: Dict[str, str]) -> QFrame:
    f = QFrame()
    sev = issue.get("severity", "INFO")
    f.setStyleSheet(SEVERITY_STYLES.get(sev, SEVERITY_STYLES["INFO"]))
    lay = QVBoxLayout(f)
    lay.addWidget(QLabel(f"<b>{issue.get('title', '')}</b>"))
    lay.addWidget(QLabel(issue.get("user_action", "")))
    rec = QLabel(f"Recovery: {issue.get('recovery', '')}")
    rec.setWordWrap(True)
    lay.addWidget(rec)
    return f
