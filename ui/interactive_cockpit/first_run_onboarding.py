"""P17 first-run onboarding wizard — no terminal required."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aa_safe_io import atomic_write_json
from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_TERTIARY, set_button_role
from execution.confirmed_live.p17_review_mode_guard import review_mode_active

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def _flag_path(root: Path) -> Path:
    p = root / "control/p18_first_run_completed.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def first_run_required(root: Path) -> bool:
    return not _flag_path(root).is_file()


def mark_first_run_completed(root: Path) -> None:
    atomic_write_json(
        _flag_path(root),
        {"completed": True, "phase": "P18_WINDOWS_UX_ACCESSIBILITY"},
    )


class FirstRunOnboardingDialog(QDialog):
    """Five-step onboarding — review mode, no live execution."""

    def __init__(self, parent: "InteractiveCockpitWindow") -> None:
        super().__init__(parent)
        self.root = parent.root
        self.setWindowTitle("Willkommen — Marktanalyse (P18)")
        self.resize(720, 520)
        self.stack = QStackedWidget()
        self._risk_ack = QCheckBox("Ich habe die Risikohinweise gelesen und verstanden.")
        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

        self.stack.addWidget(
            self._page(
                "Schritt 1 — Willkommen",
                "Real Read-only · Paper · Planung · Confirm-Before-Submit (gesperrt) · Intraday Paper/Research\n\n"
                "REVIEWMODUS — KEINE LIVE-ORDERÜBERMITTLUNG.",
            )
        )
        self.stack.addWidget(self._page_with_widget(
            "Schritt 2 — Sicherheit",
            "Echtgeld kann verloren gehen. Der Echtgeldmodus ist derzeit nicht aktiv.\n"
            "Jede künftige Order muss einzeln bestätigt werden. Kill Switch jederzeit verfügbar.\n"
            "Kein Auto-Trading.",
            self._risk_ack,
        ))
        self.stack.addWidget(
            self._page(
                "Schritt 3 — Trading 212 Read-only",
                "Optional: API Key und API Secret nur lokal.\n"
                "Keine E-Mail, kein Weblogin, kein Kontopasswort.\n"
                "Setup kann übersprungen werden.",
            )
        )
        self.stack.addWidget(
            self._page(
                "Schritt 4 — Portfolio",
                "Realdaten nur nach Read-only-Verbindung.\n"
                "Paper und Planung sind klar getrennt.\n"
                "Managed Scope wird nicht automatisch aktiviert.",
            )
        )
        self.stack.addWidget(
            self._page(
                "Schritt 5 — Start",
                "Dashboard mit Systemstatus und Fehlerzuständen.\n"
                "Real Capital Deployed By Application: 0,00 EUR.\n"
                f"Review Mode: {'AKTIV' if review_mode_active() else 'INAKTIV'}",
            )
        )

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Zurück")
        self.next_btn = QPushButton("Weiter")
        self.skip_btn = QPushButton("Überspringen")
        set_button_role(self.back_btn, ROLE_TERTIARY)
        set_button_role(self.next_btn, ROLE_PRIMARY)
        set_button_role(self.skip_btn, ROLE_TERTIARY)
        self.back_btn.clicked.connect(self._back)
        self.next_btn.clicked.connect(self._next)
        self.skip_btn.clicked.connect(self._accept_skip)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        nav.addWidget(self.skip_btn)
        layout.addLayout(nav)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._update_nav()

    def _page(self, title: str, body: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._title_label(title))
        b = QLabel(body)
        b.setWordWrap(True)
        lay.addWidget(b)
        lay.addStretch()
        return w

    def _page_with_widget(self, title: str, body: str, extra: QWidget) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(self._title_label(title))
        b = QLabel(body)
        b.setWordWrap(True)
        lay.addWidget(b)
        lay.addWidget(extra)
        lay.addStretch()
        return w

    def _title_label(self, title: str) -> QLabel:
        t = QLabel(f"<h2>{title}</h2>")
        t.setTextFormat(Qt.TextFormat.RichText)
        return t

    def _update_nav(self) -> None:
        idx = self.stack.currentIndex()
        self.back_btn.setEnabled(idx > 0)
        self.next_btn.setText("Abschließen" if idx >= self.stack.count() - 1 else "Weiter")

    def _back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._update_nav()

    def _accept_skip(self) -> None:
        mark_first_run_completed(self.root)
        self.accept()

    def _next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 1 and not self._risk_ack.isChecked():
            self._risk_ack.setStyleSheet("color:#cc4444;font-weight:bold;")
            return
        self._risk_ack.setStyleSheet("")
        if idx >= self.stack.count() - 1:
            mark_first_run_completed(self.root)
            self.accept()
            return
        self.stack.setCurrentIndex(idx + 1)
        self._update_nav()


def maybe_show_first_run(win: "InteractiveCockpitWindow") -> None:
    if not first_run_required(win.root):
        return
    dlg = FirstRunOnboardingDialog(win)
    dlg.exec()
