"""Interactive Marktanalyse Investment Cockpit — P16G."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from integrations.trading212.t212_credentials_ui_controller import (
    apply_credentials_from_gui,
    credential_storage_summary,
    forget_all_credentials,
    populate_stored_credentials_in_gui,
    test_credentials_from_gui,
)
from integrations.trading212.t212_readonly_connection_service import sync_readonly_account
from ui.interactive_cockpit.services.activity_audit_service import log_activity
from ui.interactive_cockpit.services.cockpit_state_service import (
    load_draft_tickets,
    load_superseded_tickets,
    refresh_cockpit_state,
)
from ui.interactive_cockpit.services.scenario_planning_service import (
    calculate_scenario,
    create_scenario,
    delete_scenario,
    duplicate_scenario,
    load_scenarios,
    parse_amount_input,
    save_scenarios,
)
from ui.interactive_cockpit.cockpit_theme import (
    CARD_SUBTITLE,
    ERROR_BANNER,
    INFO_PANEL,
    MARKET_STATUS,
    SAFETY_BANNER,
    SUCCESS_BANNER,
    TICKET_WARN,
    WARNING_BANNER,
)
from ui.interactive_cockpit.button_roles import (
    ROLE_LINK,
    ROLE_NAV,
    ROLE_PRIMARY,
    ROLE_SECONDARY,
    ROLE_TERTIARY,
    apply_button_affordance,
    set_button_role,
)

FORBIDDEN_BUTTON_LABELS = ("kaufen", "verkaufen", "order senden", "jetzt handeln", "trade now", "rebalance ausführen")

_APP_INSTANCE_GUARD = None

NAV_ITEMS = (
    ("overview", "Start"),
    ("comparison", "Vergleich"),
    ("t212", "Broker"),
    ("live_setup", "Symbole"),
    ("planning", "Planung"),
    ("order_review", "Orders"),
    ("market", "Kurse"),
    ("risk", "Stopp"),
    ("investments", "Investments"),
    ("paper", "Paper"),
    ("proposals", "Warteschlange"),
    ("confirmed_orders", "Erledigte Orders"),
    ("tickets", "Tickets"),
    ("trigger", "Trigger"),
    ("intraday", "Intraday"),
    ("activity", "Aktivität"),
    ("audit", "Audit"),
    ("settings", "Mehr"),
)


def _eur(v: Any) -> str:
    if v is None or v == "NOT_AVAILABLE":
        return "—"
    try:
        return f"{float(v):,.2f} EUR"
    except (TypeError, ValueError):
        return str(v)


logger = logging.getLogger(__name__)


class InteractiveCockpitWindow(QMainWindow):
    """Main interactive desktop cockpit — read-only broker, no order submission."""

    def __init__(self, root: Path, parent=None) -> None:
        super().__init__(parent)
        self.root = Path(root)
        self.state: Dict[str, Any] = {}
        self._nav_index: Dict[str, int] = {}
        self.setWindowTitle("Marktanalyse — Investment Cockpit (P18 UX & Safety)")
        self.resize(1280, 840)
        self._build_ui()
        apply_button_affordance(self)
        from ui.interactive_cockpit.accessibility_helpers import install_keyboard_shortcuts

        install_keyboard_shortcuts(self)
        self._price_timer = QTimer(self)
        self._price_timer.timeout.connect(self._auto_refresh_market_prices)
        test_mode = os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1" or os.environ.get(
            "AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", ""
        ).strip() == "1"
        self.refresh_state(full=not test_mode)
        if not test_mode:
            QTimer.singleShot(800, self._start_live_price_auto_refresh)
        log_activity(self.root, category="System", action="Anwendung gestartet", result="GUI bereit", status="ERFOLGREICH")

    def _start_live_price_auto_refresh(self) -> None:
        if os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1":
            return
        if os.environ.get("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "").strip() == "1":
            return
        from market.live_quote_engine import auto_refresh_interval_seconds

        self._price_timer.start(auto_refresh_interval_seconds() * 1000)

    def _auto_refresh_market_prices(self) -> None:
        if os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1":
            return
        if os.environ.get("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "").strip() == "1":
            return
        self.refresh_state(full=False, force_market_prices=True)
        # Hourly path also attempts EOD once per day via learning cycle inside refresh_state

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)

        self.nav_list = QWidget()
        nav_layout = QVBoxLayout(self.nav_list)
        nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        from ui.interactive_cockpit.pilot_nav import build_pilot_nav

        self._nav_buttons = build_pilot_nav(self, nav_layout)
        nav_layout.addStretch()
        self.nav_list.setFixedWidth(220)
        layout.addWidget(self.nav_list)

        right = QVBoxLayout()
        self.safety_banner = QLabel()
        self.safety_banner.setWordWrap(True)
        self.safety_banner.setStyleSheet(SAFETY_BANNER)
        self.safety_banner.setAccessibleName("Sicherheitsbanner Echtgeld und Reviewmodus")
        self._update_safety_banner()
        right.addWidget(self.safety_banner)

        self.stack = QStackedWidget()
        for i, (key, _) in enumerate(NAV_ITEMS):
            self._nav_index[key] = i
            self.stack.addWidget(self._build_view(key))
        right.addWidget(self.stack)
        layout.addLayout(right, 1)
        self.setCentralWidget(central)
        self._go_nav("overview")

    def _update_safety_banner(self, *, dev: bool = False) -> None:
        from execution.confirmed_live.trading_mode_policy import get_trading_mode
        from ui.interactive_cockpit.dev_companion import dev_mode_active

        mode = get_trading_mode(self.root)
        if dev or dev_mode_active():
            self.safety_banner.setText(
                "DEV — run_live_trading_dev_fast.bat · "
                f"Modus: {'KI-unterstützt' if mode == 'ai_assisted' else 'Manuell (keine App-Orders)'}"
            )
        elif mode == "ai_assisted":
            self.safety_banner.setText(
                "KI-unterstützt — Orders nur nach Ihrer Bestätigung · Kein Auto-Trading · F5 = Aktualisieren"
            )
        else:
            self.safety_banner.setText(
                "Manuell — die App sendet keine Orders · F5 = Aktualisieren"
            )

    def _go_nav(self, key: str) -> None:
        idx = self._nav_index.get(key, 0)
        self.stack.setCurrentIndex(idx)
        from ui.interactive_cockpit.pilot_nav import PILOT_PRIMARY_NAV

        primary_keys = [k for k, _ in PILOT_PRIMARY_NAV]
        for btn in self._nav_buttons:
            btn.setChecked(False)
        if key in primary_keys:
            i = primary_keys.index(key)
            if 0 <= i < len(self._nav_buttons):
                self._nav_buttons[i].setChecked(True)
        if key == "comparison":
            from ui.interactive_cockpit.portfolio_comparison_view import refresh_portfolio_comparison

            refresh_portfolio_comparison(self, force_sync=False)

    def refresh_state(self, *, full: bool = False, force_market_prices: bool = False) -> None:
        from ui.interactive_cockpit.dev_companion import dev_mode_active

        if dev_mode_active():
            self._update_safety_banner(dev=True)
        else:
            self._update_safety_banner()
        try:
            self.state = refresh_cockpit_state(
                self.root, full_remediation=full, force_market_prices=force_market_prices or full
            )
        except Exception as exc:
            self.state = self.state or {}
            self.state["refresh_error"] = str(exc)[:200]
        if full or force_market_prices:
            from ui.interactive_cockpit.integrated_pilot_refresh import apply_integrated_pilot_refresh

            apply_integrated_pilot_refresh(self.root, self.state, force=True)
        self._refresh_all_views()
        from ui.interactive_cockpit.trading_mode_ui import refresh_trading_mode_panel

        refresh_trading_mode_panel(self)

    def _build_view(self, key: str) -> QWidget:
        builders = {
            "overview": self._view_overview,
            "t212": self._view_t212,
            "comparison": self._view_portfolio_comparison,
            "live_setup": self._view_live_setup,
            "investments": self._view_investments,
            "paper": self._view_paper,
            "planning": self._view_planning,
            "proposals": self._view_proposals,
            "order_review": self._view_order_review,
            "confirmed_orders": self._view_confirmed_orders,
            "tickets": self._view_tickets,
            "trigger": self._view_trigger,
            "intraday": self._view_intraday,
            "market": self._view_market,
            "activity": self._view_activity,
            "risk": self._view_risk,
            "audit": self._view_audit,
            "settings": self._view_settings,
        }
        return builders.get(key, self._placeholder)()

    def _scroll_wrap(self, inner: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        return scroll

    def _placeholder(self) -> QWidget:
        w = QWidget()
        QVBoxLayout(w).addWidget(QLabel("Ansicht wird geladen…"))
        return w

    def _card(self, title: str, value: str, subtitle: str = "") -> QFrame:
        f = QFrame()
        f.setFrameStyle(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(f)
        lay.addWidget(QLabel(f"<b>{title}</b>"))
        lay.addWidget(QLabel(value))
        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet(CARD_SUBTITLE)
            lay.addWidget(sub)
        return f

    def _view_overview(self) -> QWidget:
        w = QWidget()
        self._overview_layout = QVBoxLayout(w)
        hdr = QLabel("<h2>Start</h2>")
        self._overview_layout.addWidget(hdr)
        from ui.interactive_cockpit.trading_mode_ui import add_trading_hub_to_overview

        add_trading_hub_to_overview(self, self._overview_layout)
        from ui.interactive_cockpit.integrated_pilot_refresh import attach_live_prufstand_overview

        attach_live_prufstand_overview(self, self._overview_layout)
        self._overview_failure_host = QVBoxLayout()
        self._overview_layout.addLayout(self._overview_failure_host)
        self._overview_cards = QGridLayout()
        self._overview_layout.addLayout(self._overview_cards)
        btn_row = QHBoxLayout()
        refresh = QPushButton("Aktualisieren")
        set_button_role(refresh, ROLE_SECONDARY)
        refresh.clicked.connect(lambda: self.refresh_state(full=True))
        btn_row.addWidget(refresh)
        btn_row.addStretch()
        self._overview_layout.addLayout(btn_row)
        self._overview_activity = QLabel()
        self._overview_activity.setWordWrap(True)
        self._overview_layout.addWidget(self._overview_activity)
        self._overview_layout.addStretch()
        return self._scroll_wrap(w)

    def _view_t212(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Trading 212 Read-Only</h2>"))
        lay.addWidget(QLabel("Nur API-Key und API-Secret — kein Kontopasswort."))

        self._t212_status = QLabel()
        self._t212_status.setWordWrap(True)
        lay.addWidget(self._t212_status)

        wizard = QGroupBox("Verbindungs-Assistent")
        form = QFormLayout(wizard)
        self._conn_name = QLineEdit("Trading 212")
        self._conn_mode = QComboBox()
        self._conn_mode.addItems(["LIVE_READ_ONLY", "DEMO_READ_ONLY"])
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_secret = QLineEdit()
        self._api_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._show_secrets = QCheckBox("Anzeigen (nur lokal, nicht geloggt)")
        self._show_secrets.toggled.connect(self._toggle_secret_visibility)
        self._persist = QCheckBox("Sicher speichern (Windows-Datenschutz / Keyring)")
        self._persist.setChecked(True)
        self._persist.setToolTip(
            "Speichert API-Key und Secret verschlüsselt auf diesem PC — überlebt App-Neustart."
        )
        self._session_only = QCheckBox("Nur für diese Sitzung")
        self._session_only.setChecked(False)
        self._session_only.setToolTip("Nach Neustart müssen Sie die Zugangsdaten erneut eingeben.")
        self._persist.toggled.connect(lambda on: self._session_only.setChecked(False) if on else None)
        self._session_only.toggled.connect(lambda on: self._persist.setChecked(False) if on else None)
        form.addRow("Verbindungsname", self._conn_name)
        form.addRow("Modus", self._conn_mode)
        form.addRow("API Key", self._api_key)
        form.addRow("API Secret", self._api_secret)
        form.addRow("", self._show_secrets)
        form.addRow("", self._persist)
        form.addRow("", self._session_only)
        self._t212_fields_hint = QLabel(
            "Gespeicherte Zugangsdaten werden beim Start in die Felder geladen (maskiert). "
            "„Anzeigen“ blendet Key und Secret ein."
        )
        self._t212_fields_hint.setWordWrap(True)
        self._t212_fields_hint.setStyleSheet("color: #8a9bb0; font-size: 11px;")
        form.addRow("", self._t212_fields_hint)
        lay.addWidget(wizard)

        readonly_box = QGroupBox("Read-Only-Bestätigung (Pflicht)")
        readonly_lay = QVBoxLayout(readonly_box)
        self._readonly_confirm = QCheckBox(
            "Ich habe einen Read-only API-Key ohne Orderrechte erstellt "
            "(in der Trading-212-App: Einstellungen → API → nur Lesen / Read-only)."
        )
        self._readonly_confirm.setAccessibleName("Read-only API-Key Bestätigung")
        self._readonly_confirm.setStyleSheet("font-weight: bold; color: #cce5ff;")
        readonly_lay.addWidget(self._readonly_confirm)
        readonly_hint = QLabel(
            "Ohne diese Bestätigung sind „Verbindung testen“ und „Speichern & synchronisieren“ blockiert."
        )
        readonly_hint.setWordWrap(True)
        readonly_hint.setStyleSheet(WARNING_BANNER)
        readonly_lay.addWidget(readonly_hint)
        lay.addWidget(readonly_box)

        btns = QHBoxLayout()
        test_btn = QPushButton("Verbindung testen")
        set_button_role(test_btn, ROLE_SECONDARY)
        test_btn.clicked.connect(self._test_t212_connection)
        save_btn = QPushButton("Speichern & synchronisieren")
        set_button_role(save_btn, ROLE_PRIMARY)
        save_btn.clicked.connect(self._save_t212_connection)
        forget_btn = QPushButton("Credentials entfernen")
        set_button_role(forget_btn, ROLE_TERTIARY)
        forget_btn.clicked.connect(self._forget_t212)
        sync_btn = QPushButton("Aktualisieren")
        set_button_role(sync_btn, ROLE_SECONDARY)
        sync_btn.clicked.connect(self._sync_t212)
        btns.addWidget(test_btn)
        btns.addWidget(save_btn)
        btns.addWidget(sync_btn)
        btns.addWidget(forget_btn)
        lay.addLayout(btns)

        safety = QLabel(
            "TRADING 212 READ-ONLY | ORDERENDPUNKTE BLOCKIERT | SCHREIBMETHODEN BLOCKIERT\n"
            "ECHTE ORDERS NUR MANUELL DURCH DEN NUTZER"
        )
        safety.setStyleSheet(SUCCESS_BANNER)
        lay.addWidget(safety)
        self._t212_account = QLabel()
        self._t212_account.setWordWrap(True)
        lay.addWidget(self._t212_account)
        self._t212_fx_hint = QLabel()
        self._t212_fx_hint.setWordWrap(True)
        lay.addWidget(self._t212_fx_hint)
        self._t212_positions = QTableWidget(0, 4)
        self._t212_positions.setHorizontalHeaderLabels(["Symbol", "Menge", "Wert", "Status"])
        lay.addWidget(self._t212_positions)
        from ui.interactive_cockpit.order_workflow_ui import extend_t212_profiles

        extend_t212_profiles(self, lay)
        return self._scroll_wrap(w)

    def _view_portfolio_comparison(self) -> QWidget:
        from ui.interactive_cockpit.portfolio_comparison_view import (
            build_portfolio_comparison_view,
            refresh_portfolio_comparison,
        )

        w = build_portfolio_comparison_view(self)
        refresh_portfolio_comparison(self, force_sync=False)
        return self._scroll_wrap(w)

    def _view_live_setup(self) -> QWidget:
        from ui.interactive_cockpit.order_workflow_ui import build_live_setup_view

        return build_live_setup_view(self)

    def _view_order_review(self) -> QWidget:
        from ui.interactive_cockpit.order_workflow_ui import bind_order_table_fill, build_order_review_view

        w = build_order_review_view(self)
        bind_order_table_fill(self)
        return w

    def _view_confirmed_orders(self) -> QWidget:
        from ui.interactive_cockpit.order_workflow_ui import build_confirmed_orders_view

        return build_confirmed_orders_view(self)

    def _view_proposals(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Vorschläge & Bestätigungswarteschlange</h2>"))
        self._proposals_body = QLabel()
        self._proposals_body.setWordWrap(True)
        lay.addWidget(self._proposals_body)
        return self._scroll_wrap(w)

    def _view_investments(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Aktuelle Investments</h2>"))
        self._inv_real = QLabel()
        self._inv_real.setWordWrap(True)
        lay.addWidget(QLabel("<b>Realer Brokerbestand (Trading 212 Read-Only)</b>"))
        lay.addWidget(self._inv_real)
        self._inv_real_table = QTableWidget(0, 4)
        self._inv_real_table.setHorizontalHeaderLabels(["Symbol", "Menge", "Wert", "Status"])
        lay.addWidget(self._inv_real_table)
        self._inv_paper = QLabel()
        self._inv_paper.setWordWrap(True)
        lay.addWidget(QLabel("<b>Virtuelles Paper-Portfolio</b>"))
        lay.addWidget(self._inv_paper)
        self._inv_compare = QLabel()
        self._inv_compare.setWordWrap(True)
        lay.addWidget(QLabel("<b>Vergleich Real vs. Paper</b>"))
        lay.addWidget(self._inv_compare)
        return self._scroll_wrap(w)

    def _view_paper(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Paper / Simulation</h2>"))
        self._paper_body = QLabel()
        self._paper_body.setWordWrap(True)
        lay.addWidget(self._paper_body)
        warn = QLabel("SIMULATION — NICHT DAS REALE TRADING-212-KONTO")
        warn.setStyleSheet(WARNING_BANNER.replace("padding:8px", "padding:4px;font-weight:bold;"))
        lay.addWidget(warn)
        return self._scroll_wrap(w)

    def _view_planning(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Zukünftige Planungen</h2><p>Nur Planung — keine ausgeführte Order</p>"))
        self._plan_model = QLabel()
        self._plan_model.setWordWrap(True)
        lay.addWidget(QLabel("<b>Modellbasierte Planung</b>"))
        lay.addWidget(self._plan_model)

        grp = QGroupBox("Freier Szenarioplaner")
        form = QFormLayout(grp)
        self._sc_name = QLineEdit("Mein Szenario")
        self._sc_capital = QLineEdit("500.00")
        self._sc_reserve = QLineEdit("50.00")
        self._sc_symbol = QLineEdit("OXY")
        self._sc_amount = QLineEdit("100.00")
        form.addRow("Szenarioname", self._sc_name)
        form.addRow("Geplantes Kapital EUR", self._sc_capital)
        form.addRow("Cashreserve EUR", self._sc_reserve)
        form.addRow("Instrument", self._sc_symbol)
        form.addRow("Betrag EUR", self._sc_amount)
        lay.addWidget(grp)

        row = QHBoxLayout()
        calc = QPushButton("Berechnen")
        set_button_role(calc, ROLE_PRIMARY)
        calc.clicked.connect(self._calc_scenario)
        save = QPushButton("Szenario speichern")
        set_button_role(save, ROLE_SECONDARY)
        save.clicked.connect(self._save_scenario)
        dup = QPushButton("Duplizieren")
        set_button_role(dup, ROLE_SECONDARY)
        dup.clicked.connect(self._dup_scenario)
        reset = QPushButton("Zurücksetzen")
        set_button_role(reset, ROLE_TERTIARY)
        reset.clicked.connect(self._reset_scenario_fields)
        row.addWidget(calc)
        row.addWidget(save)
        row.addWidget(dup)
        row.addWidget(reset)
        lay.addLayout(row)
        self._plan_result = QLabel()
        self._plan_result.setWordWrap(True)
        lay.addWidget(self._plan_result)
        self._plan_table = QTableWidget(0, 5)
        self._plan_table.setHorizontalHeaderLabels(["Szenario", "Kapital", "Status", "Gesamt", "Aktion"])
        lay.addWidget(self._plan_table)
        self._current_scenario_id: Optional[str] = None
        return self._scroll_wrap(w)

    def _view_tickets(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Manuelle Ticketentwürfe</h2>"))
        warn = QLabel(
            "DIES IST KEINE AUSGEFÜHRTE ORDER. PRÜFEN SIE PREIS, RISIKO UND INSTRUMENT IM BROKER.\n"
            "DIE ORDER MUSS VON IHNEN SELBST MANUELL IN TRADING 212 EINGEGEBEN WERDEN."
        )
        warn.setStyleSheet(TICKET_WARN)
        warn.setWordWrap(True)
        lay.addWidget(warn)
        tabs = QTabWidget()
        self._ticket_invalid = QTableWidget(0, 4)
        self._ticket_invalid.setHorizontalHeaderLabels(["ID", "Instrument", "Status", "Betrag"])
        self._ticket_draft = QTableWidget(0, 5)
        self._ticket_draft.setHorizontalHeaderLabels(["ID", "Instrument", "Status", "Betrag", "Blocker"])
        tabs.addTab(self._ticket_invalid, "Ungültige historische Tickets")
        tabs.addTab(self._ticket_draft, "Entwürfe")
        lay.addWidget(tabs)
        return self._scroll_wrap(w)

    def _view_trigger(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Gewinntrigger & US-Session-Freischaltung</h2>"))
        self._trigger_body = QLabel()
        self._trigger_body.setWordWrap(True)
        lay.addWidget(self._trigger_body)
        self._trigger_bar = QProgressBar()
        self._trigger_bar.setMaximum(5000)
        lay.addWidget(self._trigger_bar)
        return self._scroll_wrap(w)

    def _view_intraday(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Intraday Paper / Research</h2>"))
        self._intraday_body = QLabel()
        self._intraday_body.setWordWrap(True)
        lay.addWidget(self._intraday_body)
        self._intraday_capital = QLineEdit("500.00")
        lay.addWidget(QLabel("Intraday Paper-Kapital (Planung, editierbar):"))
        lay.addWidget(self._intraday_capital)
        return self._scroll_wrap(w)

    def _view_market(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Markt- und FX-Daten (Live)</h2>"))
        self._market_status = QLabel()
        self._market_status.setWordWrap(True)
        self._market_status.setStyleSheet(MARKET_STATUS)
        lay.addWidget(self._market_status)
        lay.addWidget(QLabel("<b>Sektor-Referenz (read-only)</b>"))
        self._sector_reference_label = QLabel("Sektoren: —")
        self._sector_reference_label.setWordWrap(True)
        self._sector_reference_label.setStyleSheet(MARKET_STATUS)
        lay.addWidget(self._sector_reference_label)
        btn = QPushButton("Live-Preise jetzt aktualisieren")
        set_button_role(btn, ROLE_PRIMARY)
        btn.clicked.connect(lambda: self.refresh_state(full=False, force_market_prices=True))
        lay.addWidget(btn)
        self._market_table = QTableWidget(0, 7)
        self._market_table.setHorizontalHeaderLabels(
            ["Instrument", "Preis EUR", "Rohkurs", "Währung", "Marktzeit UTC", "Alter (s)", "Gate"]
        )
        lay.addWidget(self._market_table)
        from ui.interactive_cockpit.integrated_pilot_refresh import attach_pilot_reeval_market

        attach_pilot_reeval_market(self, lay)
        lay.addWidget(QLabel("<b>Portfolio-Abgleich Champion (Live-Preise, keine Order)</b>"))
        self._gap_table = QTableWidget(0, 6)
        self._gap_table.setHorizontalHeaderLabels(
            ["Symbol", "Ziel EUR", "Ist EUR", "Gap EUR", "Live EUR", "Stück (~)"]
        )
        lay.addWidget(self._gap_table)
        lay.addWidget(QLabel("<b>Lern-Archiv (Beobachtung — kein Auto-Training)</b>"))
        self._learning_status = QLabel()
        self._learning_status.setWordWrap(True)
        self._learning_status.setStyleSheet(MARKET_STATUS)
        lay.addWidget(self._learning_status)
        self._learning_table = QTableWidget(0, 2)
        self._learning_table.setHorizontalHeaderLabels(["Metrik", "Wert"])
        lay.addWidget(self._learning_table)
        return self._scroll_wrap(w)

    def _view_activity(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Aktivitäten & Entscheidungen</h2>"))
        self._activity_table = QTableWidget(0, 6)
        self._activity_table.setHorizontalHeaderLabels(["Zeit", "Kategorie", "Aktion", "Ergebnis", "Status", "Nutzer?"])
        lay.addWidget(self._activity_table)
        self._planned_label = QLabel()
        self._planned_label.setWordWrap(True)
        lay.addWidget(QLabel("<b>Geplante nächste Aktionen</b>"))
        lay.addWidget(self._planned_label)
        return self._scroll_wrap(w)

    def _view_risk(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Stopp</h2>"))
        from ui.interactive_cockpit.trading_mode_ui import add_trading_mode_status_only

        add_trading_mode_status_only(self, lay)
        self._risk_body = QLabel()
        self._risk_body.setWordWrap(True)
        lay.addWidget(self._risk_body)
        from ui.interactive_cockpit.order_workflow_ui import extend_risk_view

        extend_risk_view(self, lay)
        return self._scroll_wrap(w)

    def _view_audit(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Audit & Reports</h2>"))
        self._audit_body = QLabel()
        self._audit_body.setWordWrap(True)
        lay.addWidget(self._audit_body)
        export = QPushButton("Aktivitätenreport exportieren (ohne Secrets)")
        set_button_role(export, ROLE_SECONDARY)
        export.clicked.connect(self._export_activity)
        lay.addWidget(export)
        return self._scroll_wrap(w)

    def _view_settings(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("<h2>Mehr</h2>"))
        lay.addWidget(QLabel("Handelsmodus: Schalter auf <b>Start</b>."))

        setup_btn = QPushButton("Geplante Einrichtung anzeigen (gespeicherte Freigaben)")
        set_button_role(setup_btn, ROLE_LINK)
        setup_btn.clicked.connect(self._show_setup_assistant)
        lay.addWidget(setup_btn)

        vision_btn = QPushButton("Produkt-Vision (Roadmap) anzeigen")
        set_button_role(vision_btn, ROLE_LINK)
        vision_btn.clicked.connect(self._show_product_vision)
        lay.addWidget(vision_btn)

        lay.addWidget(QLabel("<b>Broker-Verbindungen → Trading 212 Read-Only</b>"))
        go = QPushButton("Trading 212 einrichten")
        set_button_role(go, ROLE_LINK)
        go.clicked.connect(lambda: self._go_nav("t212"))
        lay.addWidget(go)
        summary = credential_storage_summary(self.root)
        store_lbl = QLabel(
            f"Credential-Speicher: {summary.get('hint', '—')}\n"
            f"Keyring: {'ja' if summary.get('keyring_available') else 'nein'} | "
            f"Windows-Datenschutz (DPAPI): {'ja' if summary.get('dpapi_available') else 'nein'} | "
            f"Überlebt Neustart: {'ja' if summary.get('survives_restart') else 'nein'}"
        )
        store_lbl.setWordWrap(True)
        lay.addWidget(store_lbl)

        from ui.interactive_cockpit.dev_companion import dev_mode_active

        dev_grp = QGroupBox("Entwicklung mit Cursor (max. Effizienz)")
        dev_lay = QVBoxLayout(dev_grp)
        dev_hint = (
            "Schnellster Zyklus: <code>run_live_trading_dev_fast.bat</code>. "
            "Produktion: <code>run_live_trading_start.bat</code> (EXE nur mit --exe nach Build)."
        )
        if dev_mode_active():
            dev_hint = (
                "<b>DEV-MODUS aktiv</b> — Sie starten aus Python (kein PyInstaller-Rebuild nötig). "
                "Nach Code-Änderung: Fenster schließen und run_live_trading_dev_fast.bat erneut ausführen."
            )
        hint_lbl = QLabel(dev_hint)
        hint_lbl.setWordWrap(True)
        dev_lay.addWidget(hint_lbl)
        self._dev_build_label = QLabel()
        self._dev_build_label.setWordWrap(True)
        self._dev_build_label.setStyleSheet(INFO_PANEL)
        dev_lay.addWidget(self._dev_build_label)
        copy_btn = QPushButton("Kontext für Cursor kopieren")
        set_button_role(copy_btn, ROLE_PRIMARY)
        copy_btn.clicked.connect(self._copy_cursor_dev_context)
        dev_lay.addWidget(copy_btn)
        open_btn = QPushButton("Kontext-Datei im Explorer öffnen")
        set_button_role(open_btn, ROLE_SECONDARY)
        open_btn.clicked.connect(self._open_cursor_handoff_file)
        dev_lay.addWidget(open_btn)
        lay.addWidget(dev_grp)
        self._refresh_dev_build_label()

        lay.addStretch()
        return self._scroll_wrap(w)

    def _show_setup_assistant(self) -> None:
        from ui.interactive_cockpit.exe_setup_assistant_dialog import ExeSetupAssistantDialog

        ExeSetupAssistantDialog(self).exec()

    def _show_product_vision(self) -> None:
        from aa_product_vision import load_product_vision

        doc = load_product_vision(self.root) or {}
        pillars = doc.get("product_pillars") or []
        phases = doc.get("roadmap_phases") or []
        lines = [str(doc.get("north_star", "")), ""]
        lines.append("Säulen:")
        for p in pillars:
            lines.append(f"• {p.get('title_de', p.get('id'))}")
        lines.append("")
        lines.append("Roadmap:")
        for ph in phases:
            lines.append(f"• {ph.get('phase')}: {ph.get('label_de')}")
        lines.append("")
        lines.append(str(doc.get("governance_reminder", "")))
        QMessageBox.information(self, "Produkt-Vision", "\n".join(lines))

        log_activity(
            self.root,
            category="Sicherheit",
            action="Review Mode umgeschaltet",
            result="AN" if enabled else "AUS",
            status="ERFOLGREICH",
        )
        self.refresh_state(full=False)

    def _toggle_secret_visibility(self, show: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password
        self._api_key.setEchoMode(mode)
        self._api_secret.setEchoMode(mode)

    def _test_t212_connection(self) -> None:
        if not self._readonly_confirm.isChecked():
            self._readonly_confirm.setFocus()
            QMessageBox.warning(
                self,
                "Berechtigung",
                "Bitte zuerst die Checkbox „Read-only API-Key“ aktivieren — "
                "nur Keys ohne Orderrechte sind zulässig.",
            )
            return
        ok, msg = test_credentials_from_gui(
            self._api_key.text(),
            self._api_secret.text(),
            self._conn_mode.currentText(),
            root=self.root,
        )
        log_activity(self.root, category="Verbindung", action="T212 Verbindungstest", result=msg, status="ERFOLGREICH" if ok else "FEHLGESCHLAGEN")
        QMessageBox.information(self, "Verbindungstest", msg)

    def _save_t212_connection(self) -> None:
        if not self._readonly_confirm.isChecked():
            self._readonly_confirm.setFocus()
            QMessageBox.warning(
                self,
                "Berechtigung",
                "Bitte zuerst die Checkbox „Read-only API-Key“ aktivieren — "
                "nur Keys ohne Orderrechte sind zulässig.",
            )
            return
        res = apply_credentials_from_gui(
            api_key=self._api_key.text(),
            api_secret=self._api_secret.text(),
            mode=self._conn_mode.currentText(),
            connection_name=self._conn_name.text(),
            persist=self._persist.isChecked(),
            session_only=self._session_only.isChecked(),
            root=self.root,
        )
        populate_stored_credentials_in_gui(self.root, self._api_key, self._api_secret, only_if_empty=False)
        sync_readonly_account(self.root, force=True)
        log_activity(self.root, category="Verbindung", action="T212 Credentials gespeichert", result=res.get("stored", ""))
        self.refresh_state(full=True)
        QMessageBox.information(self, "Gespeichert", res.get("message", "OK"))

    def _forget_t212(self) -> None:
        forget_all_credentials(self.root)
        self._api_key.clear()
        self._api_secret.clear()
        log_activity(self.root, category="Verbindung", action="Credentials entfernt", result="OK")
        self.refresh_state(full=False)
        QMessageBox.information(self, "Entfernt", "Credentials aus Sitzung und Secure Store entfernt.")

    def _current_nav_key(self) -> str:
        idx = self.stack.currentIndex()
        for key, _ in NAV_ITEMS:
            if self._nav_index.get(key) == idx:
                return key
        return ""

    def _refresh_dev_build_label(self) -> None:
        if not hasattr(self, "_dev_build_label"):
            return
        from ui.interactive_cockpit.dev_companion import dev_mode_active, get_dev_runtime_info

        info = get_dev_runtime_info(self.root)
        sha = info.get("executable_sha256") or "—"
        short_sha = f"{sha[:12]}…" if len(sha) > 12 else sha
        mode = "Python Dev" if info.get("python_launch") else "EXE frozen"
        if dev_mode_active():
            mode = "DEV aktiv · " + mode
        self._dev_build_label.setText(
            f"Laufart: {mode}\n"
            f"Runtime-Root: {info.get('runtime_root')}\n"
            f"Marktanalyse.exe SHA-256: {short_sha}\n"
            f"Vollständiger Hash + Kontext: Button „Kontext für Cursor kopieren“"
        )

    def _copy_cursor_dev_context(self) -> None:
        from PySide6.QtGui import QGuiApplication
        from ui.interactive_cockpit.dev_companion import format_cursor_handoff, write_cursor_handoff_file

        text = format_cursor_handoff(
            self.root,
            nav_view=self._current_nav_key(),
            state=self.state,
        )
        path = write_cursor_handoff_file(self.root, text)
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(text)
        log_activity(
            self.root,
            category="Entwicklung",
            action="Cursor-Kontext exportiert",
            result=str(path.name),
        )
        QMessageBox.information(
            self,
            "Cursor-Kontext",
            f"Kontext in Zwischenablage kopiert.\n\nDatei:\n{path}\n\nIn Cursor einfügen (Strg+V).",
        )

    def _open_cursor_handoff_file(self) -> None:
        import os
        import subprocess
        import sys

        from ui.interactive_cockpit.dev_companion import format_cursor_handoff, write_cursor_handoff_file

        path = write_cursor_handoff_file(
            self.root,
            format_cursor_handoff(
                self.root,
                nav_view=self._current_nav_key(),
                state=self.state,
            ),
        )
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 — Windows Explorer
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
        QMessageBox.information(self, "Datei", f"Geöffnet:\n{path}")

    def _sync_t212(self) -> None:
        sync_readonly_account(self.root, force=True)
        log_activity(self.root, category="Synchronisation", action="T212 Read-Only Sync", result="Abgeschlossen")
        self.refresh_state(full=False)

    def _calc_scenario(self) -> None:
        cap, err = parse_amount_input(self._sc_capital.text())
        if err:
            QMessageBox.warning(self, "Eingabe", err)
            return
        res, err = parse_amount_input(self._sc_amount.text())
        if err:
            QMessageBox.warning(self, "Eingabe", err)
            return
        sym = self._sc_symbol.text().upper().strip()
        fresh = self.state.get("market_price_freshness") or {}
        prices = (self.state.get("market_prices") or {}).get("executable_prices_eur") or {}
        if not fresh.get("calculation_allowed"):
            QMessageBox.warning(
                self,
                "Live-Preise",
                fresh.get("reason") or "Marktpreise nicht aktuell. Bitte F5 drücken oder Live-Preise aktualisieren.",
            )
            self.refresh_state(full=False, force_market_prices=True)
            return
        scenario = {
            "name": self._sc_name.text(),
            "capital_eur": cap or 500,
            "reserve_eur": float(self._sc_reserve.text().replace(",", ".") or 50),
            "items": [{"symbol": sym, "amount_eur": res or 0}],
        }
        calc = calculate_scenario(scenario, live_prices=prices, price_freshness=fresh)
        detail = calc.get("live_price_detail") or {}
        sym_line = ""
        if sym in detail:
            d = detail[sym]
            sym_line = f"\nLive-Preis {sym}: {_eur(d.get('live_price_eur'))} → ca. {d.get('estimated_shares')} Stück"
        self._plan_result.setText(
            f"Status: {calc['planning_status']}\n"
            f"Gesamtinvestition: {_eur(calc['total_notional_eur'])}\n"
            f"Kosten (geschätzt): {_eur(calc['total_costs_eur'])}\n"
            f"Budgetgate: {calc['budget_gate']}\n"
            f"Live-Preis-Gate: {calc.get('live_price_gate', '—')}{sym_line}\n"
            f"NICHT AUSGEFÜHRT — NUR PLANUNG"
        )
        log_activity(self.root, category="Planung", action="Szenario berechnet", result=calc["planning_status"], amounts_eur=calc["total_notional_eur"])

    def _save_scenario(self) -> None:
        cap, _ = parse_amount_input(self._sc_capital.text())
        amt, _ = parse_amount_input(self._sc_amount.text())
        s = create_scenario(
            self.root,
            name=self._sc_name.text(),
            capital_eur=cap or 500,
            reserve_eur=float(self._sc_reserve.text().replace(",", ".") or 50),
            items=[{"symbol": self._sc_symbol.text().upper(), "amount_eur": amt or 0}],
        )
        self._current_scenario_id = s["id"]
        log_activity(self.root, category="Planung", action="Szenario gespeichert", result=s["name"])
        self.refresh_state(full=False)

    def _dup_scenario(self) -> None:
        if not self._current_scenario_id:
            scenarios = load_scenarios(self.root)
            if scenarios:
                self._current_scenario_id = scenarios[-1]["id"]
        if self._current_scenario_id:
            duplicate_scenario(self.root, self._current_scenario_id)
            self.refresh_state(full=False)

    def _reset_scenario_fields(self) -> None:
        self._sc_name.setText("Mein Szenario")
        self._sc_capital.setText("500.00")
        self._sc_reserve.setText("50.00")
        self._sc_symbol.clear()
        self._sc_amount.clear()
        self._plan_result.clear()

    def _export_activity(self) -> None:
        from ui.interactive_cockpit.services.activity_audit_service import load_recent_activities

        acts = load_recent_activities(self.root, 200)
        out = self.root / "live_pilot/activity/export_latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        import json

        out.write_text(json.dumps({"activities": acts}, indent=2), encoding="utf-8")
        QMessageBox.information(self, "Export", f"Exportiert nach:\n{out}")

    def _refresh_all_views(self) -> None:
        s = self.state
        while self._overview_failure_host.count():
            item = self._overview_failure_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        from ui.interactive_cockpit.failure_state_panel import build_failure_state_panel

        self._overview_failure_host.addWidget(build_failure_state_panel(s))
        from ui.interactive_cockpit.integrated_pilot_refresh import (
            render_last_order_preflight,
            render_live_prufstand,
            render_pilot_reeval_market,
            trade_gate_summary,
        )

        render_live_prufstand(self)
        render_pilot_reeval_market(self)
        render_last_order_preflight(self)

        cash = s.get("cash") or {}
        trigger = s.get("trigger") or {}
        profit = float(trigger.get("current_eligible_realized_net_profit_eur") or 0)
        paper = s.get("paper") or {}
        broker = s.get("broker") or {}
        real_money = s.get("real_money") or {}
        real_only = bool(real_money.get("real_money_only"))
        from ui.interactive_cockpit.cockpit_cash_display import (
            amount_with_usd,
            apply_fx_footer_label,
            apply_rich_cash_label,
            cash_display_html,
            cash_display_plain,
            load_fx,
        )

        fx_obs = load_fx(self.root)

        while self._overview_cards.count():
            item = self._overview_cards.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        trade_val, trade_sub, _trade_sev = trade_gate_summary(s)
        cards = [
            ("P18", "UX & FEHLERZUSTÄNDE", "Windows-Serienreife Basis"),
            ("Handeln heute?", trade_val, trade_sub),
            (
                "Handelsmodus",
                "KI-unterstützt" if __import__("execution.confirmed_live.trading_mode_policy", fromlist=["get_trading_mode"]).get_trading_mode(self.root) == "ai_assisted" else "Manuell",
                "Kein Auto-Trading",
            ),
            ("Live-Preise", (s.get("market_price_freshness") or {}).get("status", "—"), (s.get("market_price_freshness") or {}).get("reason", "—")[:80]),
            (
                "Lern-Archiv",
                "AKTIV" if (s.get("learning_readiness") or {}).get("learning_collection_active") else "—",
                f"EOD: {(s.get('learning_readiness') or {}).get('last_eod_date', '—')} | Intraday: {(s.get('learning_readiness') or {}).get('intraday_observations', 0)}",
            ),
            ("T212", broker.get("status", "NICHT KONFIGURIERT"), "Read-Only Broker"),
            (
                "Verfügbar (T212)",
                amount_with_usd(
                    real_money.get("cash_eur")
                    if real_only
                    else (broker.get("cash_eur") or cash.get("readonly_observed_real_broker_available_cash_eur")),
                    fx_obs,
                ),
                "Offiziell verbucht · USD Spot" if real_only else "Nur bei Verbindung · USD Spot",
            ),
            (
                "Investiert (T212)",
                _eur(real_money.get("invested_eur") if real_only else cash.get("readonly_reconciled_real_invested_eur")),
                f"Gesamt: {_eur(real_money.get('total_value_eur'))}" if real_only else "Read-only Sync",
            ),
            ("Deployed", "0,00 EUR", "Real Capital By App"),
            ("Trigger", _eur(trigger.get("current_eligible_realized_net_profit_eur", 0)), f"Ziel 50 EUR — {trigger.get('trigger_status', '')}"),
        ]
        for i, (t, v, sub) in enumerate(cards):
            self._overview_cards.addWidget(self._card(t, v, sub), i // 2, i % 2)

        if hasattr(self, "_overview_progress"):
            self._overview_progress.setMaximum(5000)
            self._overview_progress.setValue(min(int(profit * 100), 5000))

        acts = s.get("activities") or []
        lines = [f"• {a.get('action')} — {a.get('result')} ({a.get('status')})" for a in acts[:5]]
        err = s.get("refresh_error")
        if err:
            lines.insert(0, f"⚠ Aktualisierung eingeschränkt: {err}")
        self._overview_activity.setText("\n".join(lines) if lines else "Keine Aktivitäten — System bereit.")

        store = credential_storage_summary(self.root)
        if hasattr(self, "_api_key"):
            populate_stored_credentials_in_gui(self.root, self._api_key, self._api_secret)
        cred_line = ""
        if broker.get("credentials_configured") or store.get("survives_restart"):
            key_len = len(self._api_key.text()) if hasattr(self, "_api_key") else 0
            cred_line = (
                f"Zugangsdaten: {'in Feldern geladen' if key_len else 'gespeichert (Sync aktiv)'}\n"
            )
        self._t212_status.setText(
            f"Status: {broker.get('status')}\n"
            f"Umgebung: {broker.get('environment', '—')}\n"
            f"{cred_line}"
            f"Letzter Sync: {broker.get('last_successful_sync_utc', '—')}\n"
            f"Fehler: {broker.get('last_error') or '—'}\n"
            f"Speicher: {store.get('hint', '—')}"
        )
        cash_html, cash_footer, _fx = cash_display_html(
            self.root, broker, real_money=real_money if real_only else None
        )
        t212_extra = f"<br>Positionen: {broker.get('positions_count', 0)}"
        if real_only:
            t212_extra = (
                f"<br>Investiert (T212): {amount_with_usd(real_money.get('invested_eur'), _fx)}"
                f"<br>Realisierte P/L: {amount_with_usd(real_money.get('realized_pnl_eur'), _fx)}"
                f"<br>Unrealisierte P/L: {amount_with_usd(real_money.get('unrealized_pnl_eur'), _fx)}"
                + t212_extra
            )
        apply_rich_cash_label(self._t212_account, cash_html + t212_extra)
        if hasattr(self, "_t212_fx_hint"):
            apply_fx_footer_label(self._t212_fx_hint, cash_footer, fx_ok=bool(_fx.get("ok")))

        from integrations.trading212.t212_position_display import position_table_rows

        pos_rows = position_table_rows(broker.get("positions"))
        if not pos_rows and broker.get("credentials_configured"):
            pos_file = self.root / "live_pilot/manual_execution/readonly_real_positions/positions_snapshot.json"
            if pos_file.is_file():
                try:
                    import json

                    pos_rows = position_table_rows(json.loads(pos_file.read_text(encoding="utf-8")).get("positions"))
                except (json.JSONDecodeError, OSError) as exc:
                    logger.warning("positions snapshot fallback unreadable: %s", pos_file, exc_info=True)
        self._fill_table(self._t212_positions, pos_rows)
        if hasattr(self, "_inv_real_table"):
            self._fill_table(self._inv_real_table, pos_rows)

        if not broker.get("credentials_configured"):
            self._inv_real.setText(
                "REALDATEN NICHT VERFÜGBAR — TRADING-212-READ-ONLY-VERBINDUNG EINRICHTEN\n"
                "Keine erfundenen Kontowerte."
            )
            self._inv_paper.setText("Paper deaktiviert bis T212 verbunden ist.")
            self._inv_compare.setText("Vergleich nicht verfügbar — keine Realdaten.")
        elif real_only:
            rm = real_money
            cash_plain, plain_footer, _fx2 = cash_display_plain(
                self.root, broker, real_money=rm
            )
            self._inv_real.setText(
                f"{cash_plain}\n"
                f"Investiert laut T212: {amount_with_usd(rm.get('invested_eur'), _fx2)}\n"
                f"Realisierte P/L (T212): {amount_with_usd(rm.get('realized_pnl_eur'), _fx2)}\n"
                f"Unrealisierte P/L (T212): {amount_with_usd(rm.get('unrealized_pnl_eur'), _fx2)}\n"
                f"Letzte Sync: {broker.get('last_successful_sync_utc', '—')}\n"
                f"{plain_footer}\n"
                f"Quelle: Trading-212-Read-only — offiziell verbucht"
            )
            self._inv_paper.setText(
                "Virtuelles Paper-Cash ist im Live-Trading deaktiviert.\n"
                "Es zählen nur von Trading 212 verbuchte Salden."
            )
            self._inv_compare.setText(
                f"Live-Trading: NUR ECHTGELD (T212)\n"
                f"Cash {amount_with_usd(rm.get('cash_eur'), _fx2)} + "
                f"Investiert {amount_with_usd(rm.get('invested_eur'), _fx2)} "
                f"= {amount_with_usd(rm.get('total_value_eur'), _fx2)}"
            )
        else:
            cash_plain, plain_footer, _fx3 = cash_display_plain(self.root, broker)
            self._inv_real.setText(
                f"{cash_plain}\n"
                f"Investiert (reconciliert): "
                f"{amount_with_usd(cash.get('readonly_reconciled_real_invested_eur', 0), _fx3)}\n"
                f"Letzte Sync: {broker.get('last_successful_sync_utc', '—')}\n"
                f"{plain_footer}"
            )
            self._inv_paper.setText(
                f"Virtuelles Cash: {_eur(paper.get('virtual_paper_cash_eur'))}\n"
                f"Virtuelle P/L: {_eur(paper.get('virtual_paper_net_pnl_eur'))}\n"
                f"SIMULATION — NICHT REAL"
            )
            self._inv_compare.setText("Vergleich verfügbar sobald reale Brokerdaten verbunden sind.")

        self._paper_body.setText(
            "PAPER / SIMULATION — IM PILOT DEAKTIVIERT\n\n"
            "Nur Trading-212-Buchungen (Cash, Positionen, P/L aus Read-only-Sync).\n"
            "Virtuelles Paper-Portfolio wird nicht für Planung oder Budget verwendet."
            if real_only
            else self._inv_paper.text()
        )

        if real_only and hasattr(self, "_sc_capital") and real_money.get("total_value_eur"):
            self._sc_capital.setPlaceholderText(f"T212 Kontowert: {real_money.get('total_value_eur')} EUR")

        batch = (s.get("remediation") or {}).get("forward_batch") or {}
        prices = batch.get("executable_prices_eur") or {}
        mp = s.get("market_prices") or {}
        fresh = s.get("market_price_freshness") or {}
        quotes = mp.get("quotes_by_symbol") or {}
        if prices:
            age = fresh.get("age_seconds")
            plan_hdr = (
                "Live-Preise + Gap-Plan (Ist = T212 Positionen, Soll = Allokationsziel):\n"
                if real_only
                else "Live-Preise (P16C-Champion-Allokation, nicht ausgeführt):\n"
            )
            self._plan_model.setText(
                plan_hdr
                + f"Frische: {fresh.get('status', '—')} ({age if age is not None else '—'}s)\n"
                + "\n".join(f"• {sym}: {_eur(px)}" for sym, px in list(prices.items())[:12])
            )
        else:
            self._plan_model.setText(
                "KEINE AKTUELLEN LIVE-PREISE — INTERNET PRÜFEN UND „AKTUALISIEREN“ (F5)\n"
                "Berechnungen sind ohne frische Marktdaten gesperrt."
            )

        gap_rows = s.get("pilot_gap_plan") or []
        if gap_rows and hasattr(self, "_gap_table"):
            self._fill_table(
                self._gap_table,
                [
                    [
                        g.get("symbol"),
                        _eur(g.get("target_eur")),
                        _eur(g.get("current_eur")),
                        _eur(g.get("gap_eur")),
                        _eur(g.get("live_price_eur")),
                        g.get("estimated_shares_if_buy_gap"),
                    ]
                    for g in gap_rows
                ],
            )

        self._fill_table(self._plan_table, [
            [sc.get("name"), _eur(sc.get("capital_eur")), "PLANUNG", _eur(sum(float(i.get("amount_eur") or 0) for i in sc.get("items") or [])), "—"]
            for sc in s.get("scenarios") or []
        ])

        invalid = load_superseded_tickets(self.root)
        drafts = load_draft_tickets(self.root)
        self._fill_table(self._ticket_invalid, [[t.get("ticket_id", "?"), t.get("instrument"), t.get("status"), _eur(t.get("maximum_manual_order_notional_eur"))] for t in invalid])
        self._fill_table(self._ticket_draft, [[t.get("ticket_id", "?")[:8], t.get("instrument"), t.get("status"), _eur(t.get("maximum_manual_order_notional_eur")), ", ".join(t.get("blockers") or [])] for t in drafts])

        dist = float(trigger.get("distance_to_trigger_eur") or 50)
        self._trigger_body.setText(
            f"Ziel: 50,00 EUR realisierter Netto-Handelsgewinn (read-only reconciliiert)\n"
            f"Aktuell anrechenbar: {_eur(profit)}\n"
            f"Verbleibend: {_eur(dist)}\n"
            f"Status: {trigger.get('trigger_status')}\n\n"
            f"Ausgeschlossen: Paper-P/L, unrealisierte P/L, Einzahlungen, Dividenden"
        )
        self._trigger_bar.setValue(min(int(profit * 100), 5000))

        unlocked = trigger.get("id0_intraday_paper_branch_unlocked")
        if unlocked:
            self._intraday_body.setText("FREIGESCHALTET — NUR PAPER / RESEARCH\nStrategy Class: SEPARATE_RESEARCH_CANDIDATE_NOT_CHAMPION\nReal Money: 0 EUR")
        else:
            self._intraday_body.setText(
                "GESPERRT — 50,00 EUR read-only reconcilierter realisierter Netto-Handelsgewinn erforderlich\n"
                f"Aktueller Fortschritt: {_eur(profit)} / 50,00 EUR\n"
                "Freischaltung aktiviert ausschließlich Paper-/Research-Modus."
            )

        if hasattr(self, "_market_status"):
            self._market_status.setText(
                f"Status: {fresh.get('status', '—')} | Alter: {fresh.get('age_seconds', '—')}s "
                f"(max {fresh.get('max_age_seconds', 120)}s) | Symbole: {fresh.get('executable_symbol_count', 0)}\n"
                f"{fresh.get('reason', '')}\n"
                f"Provider: {mp.get('provider', '—')} | FX-Gate: {mp.get('fx_runtime_gate', '—')} | "
                f"DQ-Gate: {mp.get('data_quality_gate', '—')}"
            )
        if hasattr(self, "_sector_reference_label"):
            sector_st = s.get("sector_status") or {}
            status_file = sector_st.get("status_file") or {}
            file_status = str(status_file.get("status") or "—")
            updated = str(status_file.get("updated_at_utc") or "")[:19]
            detail = f"Status-Datei: {file_status}"
            if updated:
                detail += f" · aktualisiert {updated}"
            if sector_st.get("reference_path"):
                detail += f" · {sector_st.get('reference_path')}"
            self._sector_reference_label.setText(f"{sector_st.get('summary_de', 'Sektoren: —')}\n{detail}")
            traffic = str(sector_st.get("traffic") or "GELB")
            sector_style = {
                "GRUEN": SUCCESS_BANNER,
                "GELB": WARNING_BANNER,
                "ROT": ERROR_BANNER,
            }.get(traffic, MARKET_STATUS)
            self._sector_reference_label.setStyleSheet(sector_style)
        market_rows = []
        for sym, px in sorted(prices.items()):
            q = quotes.get(sym) or {}
            market_rows.append(
                [
                    sym,
                    _eur(px),
                    q.get("raw_price", "—"),
                    q.get("quote_currency", "—"),
                    str(q.get("market_event_time_utc", "—"))[:19],
                    fresh.get("age_seconds", "—"),
                    q.get("data_quality_gate", batch.get("data_quality_gate", "—")),
                ]
            )
        self._fill_table(self._market_table, market_rows)

        lr = s.get("learning_readiness") or {}
        if hasattr(self, "_learning_status"):
            self._learning_status.setText(
                f"Beobachtung aktiv: {'JA' if lr.get('learning_collection_active') else 'NEIN'} | "
                f"Auto-Training: BLOCKIERT | Champion: {lr.get('champion_locked', 'R3_w075_q065_noexit')}\n"
                f"Intraday: {lr.get('intraday_observations', 0)} | EOD-Closes: {lr.get('eod_close_observations', 0)} | "
                f"Broker-Tages: {lr.get('broker_daily_snapshots', 0)}\n"
                f"Letzter EOD: {lr.get('last_eod_date', '—')} | Offline-Forschung bereit: "
                f"{'JA' if lr.get('ready_for_offline_research') else 'NEIN (Daten sammeln…)'}\n"
                f"{lr.get('next_offline_step', '')}"
            )
            rows = [
                ("Intraday-Beobachtungen", lr.get("intraday_observations", 0)),
                ("EOD-Tagesabschlüsse", lr.get("eod_close_observations", 0)),
                ("Broker-Tages-Snapshots", lr.get("broker_daily_snapshots", 0)),
                ("Letztes Intraday UTC", lr.get("last_intraday_utc", "—")),
                ("Letzter EOD-Tag", lr.get("last_eod_date", "—")),
                ("Auto-Training", "BLOCKIERT (Governance)"),
            ]
            self._fill_table(self._learning_table, rows)

        self._fill_table(
            self._activity_table,
            [
                [
                    a.get("timestamp_utc", "")[:19],
                    a.get("category"),
                    a.get("action"),
                    a.get("result"),
                    a.get("status"),
                    "JA" if a.get("user_action_required") else "NEIN",
                ]
                for a in s.get("activities") or []
            ],
        )
        planned = s.get("planned_actions") or []
        self._planned_label.setText("\n".join(f"• {p.get('title')}: {p.get('status')} — {p.get('real_money_impact', 'NEIN')}" for p in planned) or "—")

        tickets = s.get("tickets") or {}
        self._risk_body.setText(
            f"Champion: {s.get('active_champion')}\n"
            f"Live-Trading: volles T212-Guthaben (Paper-Workflow, kein Kapital-Cap)\n"
            f"Verfügbares Ticketbudget: {amount_with_usd(cash.get('available_real_manual_ticket_budget_eur'), fx_obs)}\n"
            f"Draft Tickets: {tickets.get('draft_tickets', 0)} | Ready: {tickets.get('ready_for_user_manual_review', 0)}\n\n"
            "BROKERORDER DURCH ANWENDUNG: DEAKTIVIERT\nAUTOMATISCHES ECHTGELDROUTING: DEAKTIVIERT"
        )

        self._audit_body.setText(
            f"Phase: P16H Confirmed Order Workflow\n"
            f"Build: Marktanalyse.exe (Projektroot)\n"
            f"Trigger: Managed Scope 50 EUR\n"
            f"P16E invalid tickets superseded: {s.get('gui', {}).get('p16e_invalid_tickets_superseded', 0)}"
        )

        self._refresh_dev_build_label()

        from ui.interactive_cockpit.order_workflow_ui import refresh_order_views

        refresh_order_views(self)
        if hasattr(self, "_proposals_body"):
            q = __import__("execution.confirmed_live.order_draft_service", fromlist=["load_queue_summary"]).load_queue_summary(self.root)
            self._proposals_body.setText(
                f"Bereit zur Prüfung: {q.get('waiting_review', 0)} | Blockiert: {q.get('blocked', 0)}\n"
                "Keine Sammelbestätigung. Kein Auto-Submit."
            )

    def _fill_table(self, table: QTableWidget, rows: List[List[Any]]) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val)))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def verify_no_order_buttons(self) -> bool:
        for btn in self.findChildren(QPushButton):
            text = (btn.text() or "").lower()
            if any(k in text for k in FORBIDDEN_BUTTON_LABELS):
                return False
        return True


def launch_interactive_cockpit(root: Path) -> int:
    global _APP_INSTANCE_GUARD
    if (
        os.environ.get("AA_LEGACY_FULL_COCKPIT", "").strip() != "1"
        and os.environ.get("AA_MINIMAL_INVEST_APP", "").strip() != "1"
        and os.environ.get("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "").strip() != "1"
        and os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() != "1"
    ):
        from aa_live_trading_launch import launch_default_live_trading_ui

        return launch_default_live_trading_ui(Path(root))

    os.environ.setdefault("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    os.environ.setdefault("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    os.environ.setdefault("AA_P18_UX_BUILD", "1")
    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout

    root = ensure_marktanalyse_runtime_layout(Path(root))
    os.environ["AA_PROJECT_ROOT"] = str(root)
    from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials
    from integrations.trading212.t212_env_file_loader import load_trading212_env_file

    load_trading212_env_file(root)
    bootstrap_trading212_credentials(root)
    from execution.confirmed_live.p17_review_mode_preferences import apply_saved_review_mode_to_environment

    apply_saved_review_mode_to_environment(root)
    from execution.confirmed_live.trading_mode_policy import apply_saved_trading_mode

    apply_saved_trading_mode(root)
    from execution.confirmed_live.trading_mode_policy import trading_readiness
    from ui.interactive_cockpit.pilot_setup_wizard import mark_pilot_setup_completed, pilot_setup_required

    if pilot_setup_required(root) and trading_readiness(root).get("ready"):
        mark_pilot_setup_completed(root)
    full_function_test = os.environ.get("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "").strip() == "1"
    smoke = os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1"
    if not full_function_test and not smoke:
        try:
            from aa_config_env import load_aa_env
            from aa_live_daily_sync import ensure_between_trading_day_daily_refresh

            ensure_between_trading_day_daily_refresh(root, load_aa_env(root), log_print=False)
        except Exception:
            pass
    from execution.confirmed_live.recovery_state_machine import record_startup

    record_startup(root, build_id="P18")
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.interactive_cockpit.accessibility_helpers import apply_accessibility_baseline

    apply_accessibility_baseline(app)
    smoke = not full_function_test and os.environ.get("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "").strip() == "1"
    if not smoke and not full_function_test:
        from aa_single_instance import acquire_single_instance

        _APP_INSTANCE_GUARD = acquire_single_instance(root, window_title="Marktanalyse")
        if _APP_INSTANCE_GUARD is None:
            QMessageBox.information(
                None,
                "Marktanalyse",
                "Marktanalyse läuft bereits.\nDas bestehende Fenster wurde in den Vordergrund geholt.",
            )
            return 0
    win = InteractiveCockpitWindow(root)
    from ui.interactive_cockpit.accessibility_helpers import apply_window_accessibility, tag_interactive_widgets

    apply_window_accessibility(win)
    tag_interactive_widgets(win)
    win.show()
    from ui.interactive_cockpit.pilot_setup_wizard import maybe_show_pilot_setup

    QTimer.singleShot(400, lambda: maybe_show_pilot_setup(win) if not full_function_test else None)
    if not full_function_test and not smoke:

        def _maybe_setup_assistant() -> None:
            from ui.interactive_cockpit.exe_setup_assistant_dialog import maybe_show_setup_assistant
            from ui.interactive_cockpit.first_run_onboarding import first_run_required

            if first_run_required(win.root):
                return
            maybe_show_setup_assistant(win)

        QTimer.singleShot(800, _maybe_setup_assistant)
    if smoke:

        def _finish() -> None:
            ok = win.verify_no_order_buttons()
            from execution.confirmed_live.p17_review_mode_guard import review_mode_active

            evidence = {
                "result": "PASS_SELF_EXIT" if ok else "FAIL_ORDER_BUTTONS",
                "interactive_cockpit": True,
                "nav_views": len(NAV_ITEMS),
                "order_buttons_present": not ok,
                "p17_review_mode": review_mode_active(),
            }
            out = root / "evidence" / "p18_interactive_gui_smoke_test_result.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            import json

            out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            app.exit(0 if ok else 1)

        QTimer.singleShot(1500, _finish)
    elif full_function_test:

        def _full_matrix() -> None:
            from ui.interactive_cockpit.exe_function_test_harness import (
                run_full_function_matrix,
                write_matrix_evidence,
            )

            report = run_full_function_matrix(win)
            write_matrix_evidence(root, report)
            app.exit(0 if report.get("overall") == "PASS" else 1)

        QTimer.singleShot(2000, _full_matrix)
    return app.exec()
