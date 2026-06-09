"""Dialog — saved EXE setup permissions (informational, does not apply flags yet)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from aa_exe_setup_questionnaire import load_exe_setup_permissions, setup_pending
from ui.interactive_cockpit.button_roles import ROLE_LINK, ROLE_PRIMARY, set_button_role

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def _multi_user_notice() -> str:
    return (
        "<b>Andere Personen / andere PCs</b><br>"
        "• Jeder Windows-Benutzer braucht eigene T212-Zugangsdaten (<code>setup_t212_credentials.bat</code>).<br>"
        "• DPAPI-Keys sind an den Windows-Login gebunden — nicht übertragbar.<br>"
        "• EXE + Ordner <code>live_pilot/</code> (Live-Trading-Daten) zusammen kopieren oder pro PC neu einrichten.<br>"
        "• Kein Code-Signing — Windows SmartScreen kann warnen."
    )


class ExeSetupAssistantDialog(QDialog):
    """Shows saved questionnaire answers and recommended order — read-only apply."""

    def __init__(self, parent: "InteractiveCockpitWindow") -> None:
        super().__init__(parent)
        self.root = parent.root
        self.setWindowTitle("Geplante App-Einrichtung")
        self.resize(760, 560)

        doc = load_exe_setup_permissions(self.root) or {}
        outer = QVBoxLayout(self)

        intro = QLabel(
            "<h2>Gespeicherte Einrichtungswünsche</h2>"
            "Diese Auswahl wurde für eine spätere vollständige Einrichtung gespeichert. "
            "<b>Es werden noch keine operativen Schalter geändert</b> (Safety fail-closed)."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        lay = QVBoxLayout(body)

        order: List[str] = list(doc.get("recommended_implementation_order") or [])
        if order:
            lay.addWidget(QLabel("<b>Empfohlene Reihenfolge (noch nicht ausgeführt):</b>"))
            for i, step in enumerate(order, 1):
                lay.addWidget(QLabel(f"{i}. {step.replace('_', ' ')}"))

        for item in doc.get("responses") or []:
            lay.addWidget(self._response_block(item))

        impl = doc.get("implementation_status") or {}
        if impl.get("blocking_note"):
            note = QLabel(str(impl["blocking_note"]))
            note.setWordWrap(True)
            note.setStyleSheet("color: #ffe0a0; padding: 8px;")
            lay.addWidget(note)

        mu = QLabel(_multi_user_notice())
        mu.setWordWrap(True)
        mu.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(mu)
        lay.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)

        t212 = QPushButton("Trading 212 Zugangsdaten einrichten")
        set_button_role(t212, ROLE_LINK)
        t212.clicked.connect(lambda: (self.accept(), parent._go_nav("t212")))
        outer.addWidget(t212)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            set_button_role(close_btn, ROLE_PRIMARY)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        outer.addWidget(buttons)

    def _response_block(self, item: Dict[str, Any]) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        title = QLabel(f"<b>{item.get('prompt_de', item.get('id', 'Frage'))}</b>")
        title.setWordWrap(True)
        v.addWidget(title)
        choice = QLabel(f"Ihre Wahl: {item.get('selected_option_label_de', '—')}")
        choice.setWordWrap(True)
        choice.setStyleSheet("color: #34C759; font-weight: bold;")
        v.addWidget(choice)
        reqs = item.get("future_setup_requirements") or []
        if reqs:
            v.addWidget(QLabel("Voraussetzungen:"))
            for r in reqs:
                rl = QLabel(f"• {r}")
                rl.setWordWrap(True)
                v.addWidget(rl)
        if item.get("governance_conflict"):
            gc = QLabel(f"⚠ {item['governance_conflict']}")
            gc.setWordWrap(True)
            gc.setStyleSheet("color: #ffccaa;")
            v.addWidget(gc)
        w.setStyleSheet("background: #1a2332; border: 1px solid #3d5166; border-radius: 6px; padding: 6px;")
        return w


def maybe_show_setup_assistant(win: "InteractiveCockpitWindow") -> None:
    if not setup_pending(win.root):
        return
    if not load_exe_setup_permissions(win.root):
        return
    dlg = ExeSetupAssistantDialog(win)
    dlg.exec()
