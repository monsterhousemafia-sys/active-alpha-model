"""Visible panel — what Auto (Ubuntu operator) is doing locally."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget

from analytics.operator_visibility import build_visibility_snapshot
from ui.invest_layout import body_label, set_banner
from ui.interactive_cockpit.cockpit_theme import BG_ELEVATED, BORDER, TEXT_PRIMARY


class AutoOperatorPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._title = body_label("Auto — Ubuntu Operator")
        set_banner(self._title, "info")
        lay.addWidget(self._title)

        self._headline = QLabel("Lädt …")
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet(
            f"background:{BG_ELEVATED}; color:{TEXT_PRIMARY}; padding:8px; border-radius:6px; border:1px solid {BORDER};"
        )
        lay.addWidget(self._headline)

        self._scope = QLabel("")
        self._scope.setWordWrap(True)
        self._scope.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:10pt;")
        lay.addWidget(self._scope)

        self._timers = QLabel("")
        self._timers.setWordWrap(True)
        lay.addWidget(self._timers)

        self._actions = QTextEdit()
        self._actions.setReadOnly(True)
        self._actions.setMinimumHeight(100)
        self._actions.setMaximumHeight(160)
        self._actions.setPlaceholderText("Operator-Aktionen erscheinen hier …")
        self._actions.setStyleSheet(f"border:1px solid {BORDER}; font-family:monospace; font-size:9pt;")
        lay.addWidget(self._actions)

        self._capabilities = QLabel("")
        self._capabilities.setWordWrap(True)
        self._capabilities.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:9pt; padding:4px;")
        lay.addWidget(self._capabilities)

        self._note = body_label("")
        self._note.setWordWrap(True)
        lay.addWidget(self._note)

    def refresh(self, root: Path, snap: Optional[Dict[str, Any]] = None) -> None:
        root = Path(root)
        vis = build_visibility_snapshot(root)
        cockpit_next = str(vis.get("cockpit_next_step_de") or "")
        circle_hl = str(vis.get("circle_headline_de") or "")
        chat_nxt = str(vis.get("chat_evolution_next_de") or "")
        headline = vis.get("headline_de", "")
        if chat_nxt:
            headline = f"KI: {chat_nxt}\n{headline}"
        elif circle_hl and circle_hl not in headline:
            headline = circle_hl
        if cockpit_next:
            headline = f"{cockpit_next}\n{headline}"
        self._headline.setText(
            f"{headline}\n{vis.get('h1_banner_de', vis.get('h1_status_de', ''))} · {vis.get('generated_at_local', '')}"
        )
        scope_lines = vis.get("scope_lines_de") or []
        self._scope.setText(" · ".join(scope_lines) if scope_lines else "Operator-Scope: —")

        timer_lines: list[str] = []
        for t in vis.get("scheduled_timers") or []:
            timer_lines.append(f"⏱ {t.get('label_de')}: {t.get('schedule_de')}")
        for line in vis.get("systemd_next_de") or []:
            timer_lines.append(line)
        self._timers.setText("\n".join(timer_lines) if timer_lines else "Keine Timer konfiguriert.")

        actions = vis.get("operator_actions_de") or []
        self._actions.setPlainText("\n".join(actions) if actions else "Noch keine Operator-Aktionen protokolliert.")
        self._actions.verticalScrollBar().setValue(self._actions.verticalScrollBar().maximum())

        can = vis.get("can_do_de") or []
        cannot = vis.get("cannot_do_de") or []
        cap_lines: list[str] = []
        if can:
            cap_lines.append("Kann: " + " · ".join(str(c) for c in can[:4]))
        if cannot:
            cap_lines.append("Nicht: " + " · ".join(str(c) for c in cannot[:2]))
        how = vis.get("how_to_see_de") or []
        if how:
            cap_lines.append("Siehe auch: " + str(how[0]))
        self._capabilities.setText("\n".join(cap_lines) if cap_lines else "")

        note = vis.get("surface_note_de") or ""
        if vis.get("evolution_platform_de"):
            note = f"{vis.get('evolution_platform_de')} · {note}"
        if snap:
            traffic = str(snap.get("traffic") or "—")
            note = f"{note} · Ampel: {traffic}"
        self._note.setText(note)
