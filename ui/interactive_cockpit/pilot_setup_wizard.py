"""First-run Live-Trading setup — mode, broker hint, symbols."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aa_safe_io import atomic_write_json
from execution.confirmed_live.managed_scope_service import create_baseline, set_managed_scope
from execution.confirmed_live.trading_mode_policy import apply_trading_mode
from ui.interactive_cockpit.apple_toggle_switch import AppleToggleSwitch
from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_TERTIARY, set_button_role

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def _flag_path(root: Path) -> Path:
    p = root / "control/live_trading_setup_completed.json"
    if not p.is_file():
        legacy = root / "control/pilot_setup_completed.json"
        if legacy.is_file():
            return legacy
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def live_trading_setup_required(root: Path) -> bool:
    return not _flag_path(root).is_file()


def mark_live_trading_setup_completed(root: Path) -> None:
    atomic_write_json(
        root / "control/live_trading_setup_completed.json",
        {"completed": True, "version": 1, "product": "live_trading"},
    )


pilot_setup_required = live_trading_setup_required
mark_pilot_setup_completed = mark_live_trading_setup_completed


class LiveTradingSetupWizard(QDialog):
    def __init__(self, parent: "InteractiveCockpitWindow") -> None:
        super().__init__(parent)
        self.win = parent
        self.root = parent.root
        self.setWindowTitle("Einrichtung — 2 Minuten")
        self.resize(560, 420)
        self.stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self.stack)

        self._ai_switch = AppleToggleSwitch()
        self._ai_switch.setChecked(True)
        self._symbols = QLineEdit("INTC,WDC,STX")
        self._risk = QCheckBox("Ich verstehe: keine Auto-Orders, nur meine Bestätigung.")

        self.stack.addWidget(self._page(
            "Willkommen",
            "Zwei Modi: Manuell (App sendet nichts) oder KI-unterstützt (Sie bestätigen jede Order).",
        ))
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.addWidget(QLabel("<h3>Handelsmodus</h3>"))
        l2.addWidget(QLabel("KI-unterstütztes Trading"))
        l2.addWidget(self._ai_switch)
        l2.addWidget(self._risk)
        l2.addStretch()
        self.stack.addWidget(p2)
        self.stack.addWidget(self._page(
            "Broker",
            "Als Nächstes: Broker — Lese-Key und API mit Order-Rechten (einmalig).\n"
            "Dieser Assistent speichert nur Ihre Symbole.",
        ))
        p4 = QWidget()
        l4 = QVBoxLayout(p4)
        l4.addWidget(QLabel("<h3>Erlaubte Aktien</h3>"))
        l4.addWidget(QLabel("Kommagetrennt — Champion-Portfolio für Live-Trading:"))
        l4.addWidget(self._symbols)
        l4.addStretch()
        self.stack.addWidget(p4)

        nav = QHBoxLayout()
        self.back_btn = QPushButton("Zurück")
        self.next_btn = QPushButton("Weiter")
        set_button_role(self.back_btn, ROLE_TERTIARY)
        set_button_role(self.next_btn, ROLE_PRIMARY)
        self.back_btn.clicked.connect(self._back)
        self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.back_btn)
        nav.addWidget(self.next_btn)
        layout.addLayout(nav)

    def _page(self, title: str, body: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel(f"<h2>{title}</h2>"))
        b = QLabel(body)
        b.setWordWrap(True)
        lay.addWidget(b)
        lay.addStretch()
        return w

    def _back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))

    def _next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 1:
            if not self._risk.isChecked():
                self._risk.setStyleSheet("color:#c44;font-weight:bold;")
                return
            self._risk.setStyleSheet("")
            mode = "ai_assisted" if self._ai_switch.isChecked() else "manual"
            apply_trading_mode(self.root, mode, changed_by="live_trading_setup_wizard")
        if idx >= self.stack.count() - 1:
            syms = [s.strip().upper() for s in self._symbols.text().split(",") if s.strip()]
            broker = self.win.state.get("broker") or {}
            create_baseline(
                self.root,
                account_currency="EUR",
                available_cash=broker.get("cash_eur"),
                positions=[],
            )
            set_managed_scope(self.root, managed_instruments=syms, authorized_capital_eur=0.0)
            mark_live_trading_setup_completed(self.root)
            from ui.interactive_cockpit.first_run_onboarding import mark_first_run_completed

            mark_first_run_completed(self.root)
            self.accept()
            return
        self.stack.setCurrentIndex(idx + 1)


PilotSetupWizard = LiveTradingSetupWizard


def maybe_show_live_trading_setup(win: "InteractiveCockpitWindow") -> None:
    if not live_trading_setup_required(win.root):
        return
    LiveTradingSetupWizard(win).exec()


maybe_show_pilot_setup = maybe_show_live_trading_setup
