"""Live-Trading dashboard — three Paper steps, no legacy pilot UI."""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from PySide6.QtCore import Qt, QTimer

from ui.live_trading_dashboard.bg_bridge import DashboardBgBridge
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from analytics.active_alpha_identity import product_name, status_line_de, unified_intro_de, window_title
from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_SECONDARY, set_button_role
from ui.invest_layout import (
    SPACING,
    body_label,
    configure_table,
    full_width_primary_button,
    make_scroll_host,
    make_section,
    metric_label,
    set_banner,
    uniform_button_row,
)
from ui.live_trading_dashboard import service as dash
from ui.live_trading_dashboard.activity_log import (
    load_dashboard_lines,
    log_dashboard_activity,
    planned_auto_actions_de,
    summarize_refresh,
)
from ui.live_trading_dashboard.auto_operator_panel import AutoOperatorPanel
from ui.live_trading_dashboard.visual_ops_panel import VisualOpsPanel


class LiveTradingDashboardWindow(QMainWindow):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self._snap: Dict[str, Any] = {}
        self.state: Dict[str, Any] = {}
        self._busy = False
        self._refreshing = False
        self._pending_action: Optional[Dict[str, Any]] = None
        self._warn_dialog_codes: set[str] = set()
        self._bg = DashboardBgBridge()
        self._bg.action_finished.connect(self._on_action_finished)
        self._bg.refresh_finished.connect(self._on_refresh_finished)
        self._busy_watchdog = QTimer(self)
        self._busy_watchdog.setSingleShot(True)
        self._busy_watchdog.timeout.connect(self._reset_busy_state)
        self._eod_timer = QTimer(self)
        self._eod_timer.setInterval(15 * 60 * 1000)
        self._eod_timer.timeout.connect(self._on_eod_timer)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_timer)
        self.setWindowTitle(window_title(self.root))
        self.setMinimumSize(760, 780)
        self.resize(820, 900)

        scroll, lay = make_scroll_host()
        self.setCentralWidget(scroll)

        ops_box, ops_lay = make_section(f"{product_name(self.root)} — Live-Cockpit")
        self._unified_intro = body_label(unified_intro_de(self.root))
        self._unified_intro.setWordWrap(True)
        ops_lay.addWidget(self._unified_intro)
        self._visual_ops = VisualOpsPanel()
        ops_lay.addWidget(self._visual_ops)
        lay.addWidget(ops_box)

        self._status_banner = metric_label("Bereit — Schaltflächen unten bedienen.")
        lay.addWidget(self._status_banner)
        self._warnings_banner = metric_label("")
        self._warnings_banner.setWordWrap(True)
        lay.addWidget(self._warnings_banner)
        self._warnings_detail = body_label("")
        self._warnings_detail.setWordWrap(True)
        lay.addWidget(self._warnings_detail)
        self._action_line = body_label("")
        lay.addWidget(self._action_line)

        activity_box, activity_lay = make_section(f"Was {product_name(self.root)} gerade tut")
        self._auto_operator = AutoOperatorPanel()
        activity_lay.addWidget(self._auto_operator)
        activity_lay.addWidget(
            body_label(
                "Protokoll unten: jede Auto-Aktion (Cursor, Timer, H1, Lernen). "
                "Desktop-Benachrichtigung bei Operator-Schritten B–D. "
                "Orders nur nach Ihrer Bestätigung hier im Dashboard."
            )
        )
        self._activity_next = body_label("Nächste Auto-Schritte werden geladen …")
        self._activity_next.setWordWrap(True)
        activity_lay.addWidget(self._activity_next)
        self._activity_log = QTextEdit()
        self._activity_log.setReadOnly(True)
        self._activity_log.setMinimumHeight(140)
        self._activity_log.setMaximumHeight(220)
        self._activity_log.setPlaceholderText("Aktivitäten erscheinen hier …")
        activity_lay.addWidget(self._activity_log)
        lay.addWidget(activity_box)

        port_box, port_lay = make_section("Champion-Portfolio — Orders (gesamt)")
        port_lay.addWidget(
            body_label(
                "Kauft/verkauft das vollständige Champion-Portfolio (alle Symbole mit Ziel-Gewicht), "
                "nicht nur eine Einzelaktie. Verkäufe zuerst, dann Käufe — wie Paper-Rebalance. "
                "KI-unterstützt AN; API mit Order-Rechten unten speichern."
            )
        )
        self._portfolio_metric = metric_label("Portfolio-Orders werden berechnet …")
        port_lay.addWidget(self._portfolio_metric)
        self._portfolio_detail = body_label("")
        port_lay.addWidget(self._portfolio_detail)
        order_type_row = QHBoxLayout()
        order_type_row.addWidget(body_label("Order-Typ an T212:"))
        self._order_type_combo = QComboBox()
        self._order_type_combo.addItem("Limit-Order (Standard)", "limit")
        self._order_type_combo.addItem("Market-Order (US-Session)", "market")
        self._order_type_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._order_type_combo.currentIndexChanged.connect(self._on_order_type_changed)
        order_type_row.addWidget(self._order_type_combo, stretch=1)
        port_lay.addLayout(order_type_row)
        self._btn_portfolio_orders = full_width_primary_button(
            "Champion-Portfolio an T212 senden (alle geplanten Orders)"
        )
        set_button_role(self._btn_portfolio_orders, ROLE_PRIMARY)
        self._btn_portfolio_orders.clicked.connect(self._on_execute_portfolio)
        port_lay.addWidget(self._btn_portfolio_orders)
        lay.addWidget(port_box)

        steps_box, steps_lay = make_section("Schritte (wie Paper-Trading)")
        steps_lay.addWidget(
            body_label(
                "① Täglicher Markt = T212-Sync + Sektor-Refresh + Zähler (kein ML). "
                "③ Signal = Profil daily_alpha_h1 (EOD ab 22:15 CET, Button erzwingt sofort). "
                "② Rebalance = Signal + Orders. Budget = freies T212-Guthaben (variabel)."
            )
        )
        self._sector_status_label = body_label("Sektoren: —")
        steps_lay.addWidget(self._sector_status_label)
        self._btn_mark = full_width_primary_button("① Täglicher Markt (T212-Sync + Sektor)")
        set_button_role(self._btn_mark, ROLE_PRIMARY)
        self._btn_mark.clicked.connect(self._on_daily_mark)
        steps_lay.addWidget(self._btn_mark)

        self._btn_rebalance = full_width_primary_button("② Rebalance — Signal + Orders an T212")
        set_button_role(self._btn_rebalance, ROLE_PRIMARY)
        self._btn_rebalance.clicked.connect(self._on_rebalance)
        steps_lay.addWidget(self._btn_rebalance)

        self._btn_signal = QPushButton("③ Signal aktualisieren (Profil daily_alpha_h1 / EOD)")
        set_button_role(self._btn_signal, ROLE_SECONDARY)
        self._btn_signal.setMinimumHeight(46)
        self._btn_signal.clicked.connect(self._on_signal)
        steps_lay.addWidget(self._btn_signal)

        self._btn_force = QPushButton("Rebalance erzwingen (ohne Fälligkeit)")
        set_button_role(self._btn_force, ROLE_SECONDARY)
        self._btn_force.clicked.connect(self._on_force_rebalance)
        self._btn_refresh = QPushButton("Aktualisieren")
        set_button_role(self._btn_refresh, ROLE_SECONDARY)
        self._btn_refresh.clicked.connect(lambda: self._refresh_ui(force=True))
        self._btn_reset_gate = QPushButton("T212-Kaufblock zurücksetzen")
        set_button_role(self._btn_reset_gate, ROLE_SECONDARY)
        self._btn_reset_gate.clicked.connect(self._on_reset_buy_gate)
        steps_lay.addLayout(
            uniform_button_row(self._btn_force, self._btn_refresh, self._btn_reset_gate)
        )
        lay.addWidget(steps_box)

        learn_box, learn_lay = make_section("KI-Lernen (öffentliche Evidenz)")
        learn_lay.addWidget(
            body_label(
                "Lernt aus Kursen, EOD-Closes und Order-Ergebnissen — messbar (IC, Hit-Rate), "
                "ohne verstecktes Autotrading. Täglich: python3 tools/ai_kernel.py learn"
            )
        )
        self._learning_metric = metric_label("Lernqualität: —")
        learn_lay.addWidget(self._learning_metric)
        self._learning_detail = body_label("")
        self._learning_detail.setWordWrap(True)
        learn_lay.addWidget(self._learning_detail)
        lay.addWidget(learn_box)

        ready_box, ready_lay = make_section("Go-Live")
        self._ready_label = metric_label("Prüfe …")
        ready_lay.addWidget(self._ready_label)
        self._ready_detail = body_label("")
        ready_lay.addWidget(self._ready_detail)
        from ui.interactive_cockpit.trading_mode_ui import add_trading_mode_panel

        add_trading_mode_panel(self, ready_lay, compact=True)
        lay.addWidget(ready_box)

        sched_box, sched_lay = make_section("Rebalance-Plan")
        self._schedule_label = body_label("—")
        sched_lay.addWidget(self._schedule_label)
        lay.addWidget(sched_box)

        konto_box, konto_lay = make_section("Trading 212 — Konto")
        self._cash_label = metric_label("Guthaben: —")
        konto_lay.addWidget(self._cash_label)
        self._positions_label = body_label("")
        konto_lay.addWidget(self._positions_label)
        self._btn_connect = QPushButton("Verbindung zu T212 laden")
        set_button_role(self._btn_connect, ROLE_SECONDARY)
        self._btn_connect.clicked.connect(self._on_connect_t212)
        konto_lay.addWidget(self._btn_connect)
        lay.addWidget(konto_box)

        model_box, model_lay = make_section("Champion-Portfolio")
        self._model_summary = body_label("")
        model_lay.addWidget(self._model_summary)
        self._portfolio_table = QTableWidget(0, 6)
        self._portfolio_table.setHorizontalHeaderLabels(
            ["Symbol", "Gewicht %", "Ziel €", "Ist €", "Gap €", "Empfehlung"]
        )
        configure_table(self._portfolio_table)
        model_lay.addWidget(self._portfolio_table)
        lay.addWidget(model_box)

        queue_box, queue_lay = make_section("US-Orders (Warteschlange)")
        self._queue_label = body_label("")
        queue_lay.addWidget(self._queue_label)
        self._auto_open_cb = QCheckBox(
            "Auto bei US-Eröffnung (deaktiviert — echtes Geld nur nach EXE-Bestätigung)"
        )
        self._auto_open_cb.setEnabled(False)
        self._auto_open_cb.setChecked(False)
        self._auto_open_cb.setToolTip(
            "Live-Orders an Trading 212 erfordern immer die finale Bestätigung im Dialog "
            "«Champion-Portfolio an T212 senden»."
        )
        queue_lay.addWidget(self._auto_open_cb)
        lay.addWidget(queue_box)

        from ui.broker_setup_panel import BrokerSetupPanel

        self._broker_panel = BrokerSetupPanel(self, self.root)
        lay.addWidget(self._broker_panel.widget)

        self._setup_banner = body_label("")
        lay.addWidget(self._setup_banner)

        lay.addStretch()
        self._ensure_controls_operable()
        self._show_exe_setup_hint()
        self._load_cached_ui_fast()
        self._log_ui_activity(
            product_name(self.root),
            "Dashboard bereit",
            status_line_de(self.root, surface="marktanalyse_app"),
            source="AUTO",
        )
        self._reload_activity_panel()
        if os.environ.get("AA_GUI_PREVIEW", "").strip() != "1":
            QTimer.singleShot(400, lambda: self._refresh_ui(force=True, source="AUTO_START"))
            self._eod_timer.start()
            self._schedule_auto_refresh()

    def _log_ui_activity(
        self,
        category: str,
        action: str,
        result: str,
        *,
        status: str = "ERFOLGREICH",
        source: str = "AUTO",
        details: dict | None = None,
    ) -> None:
        try:
            log_dashboard_activity(
                self.root,
                category=category,
                action=action,
                result=result,
                status=status,
                source=source,
                details=details,
            )
        except Exception:
            pass
        self._reload_activity_panel()

    def _reload_activity_panel(self, snap: dict | None = None) -> None:
        try:
            lines = load_dashboard_lines(self.root, limit=30)
        except Exception:
            lines = []
        if hasattr(self, "_auto_operator"):
            try:
                self._auto_operator.refresh(self.root, snap=snap or getattr(self, "_snap", None))
            except Exception:
                pass
        if hasattr(self, "_activity_log"):
            self._activity_log.setPlainText("\n".join(lines) if lines else "Noch keine Aktivitäten.")
            self._activity_log.verticalScrollBar().setValue(self._activity_log.verticalScrollBar().maximum())

    def _schedule_auto_refresh(self) -> None:
        try:
            from analytics.pilot_day_trading_policy import effective_full_refresh_ms

            ms = max(60_000, int(effective_full_refresh_ms(self.root)))
        except Exception:
            ms = 5 * 60 * 1000
        self._auto_refresh_timer.setInterval(ms)
        if not self._auto_refresh_timer.isActive():
            self._auto_refresh_timer.start()

    def _on_auto_refresh_timer(self) -> None:
        if self._busy or self._refreshing:
            self._log_ui_activity(
                "Auto-Refresh",
                "Übersprungen",
                "Vorheriger Lauf noch aktiv",
                status="INFO",
            )
            return
        self._log_ui_activity("Auto-Refresh", "Geplant", "Konto und Kurse im Hintergrund")
        self._refresh_ui(force=False, source="AUTO_TIMER")

    def _on_eod_timer(self) -> None:
        if self._busy or self._refreshing:
            return

        def work() -> None:
            label = "EOD-Check: nicht fällig"
            status = "INFO"
            try:
                from analytics.prediction_operations import eod_switch_due, maybe_run_eod_prediction_switch

                if not eod_switch_due(self.root):
                    self._bg.refresh_finished.emit({"eod_check_only": True, "eod_log": label, "eod_status": "INFO"})
                    return
                label = "EOD-Signal-Umstellung"
                sw = maybe_run_eod_prediction_switch(self.root, force=False)
                if sw.get("ok") and not sw.get("skipped"):
                    label = f"EOD-Signal aktualisiert ({sw.get('profile_used') or 'daily_alpha_h1'})"
                    status = "ERFOLGREICH"
                try:
                    from analytics.evolution_stage_runner import run_evolution_cycle

                    evo = run_evolution_cycle(self.root, apply_improvements=True)
                    st = (evo.get("stage") or {}).get("stage_label_de") or "Evolution"
                    label = f"{label} · {st}"
                except Exception:
                    pass
            except Exception as exc:
                label = f"EOD-Fehler: {str(exc)[:120]}"
                status = "FEHLGESCHLAGEN"
            self._bg.refresh_finished.emit({"eod_only": True, "eod_log": label, "eod_status": status})

        threading.Thread(target=work, daemon=True).start()

    def _on_eod_logged(self, payload: Dict[str, Any]) -> None:
        if payload.get("eod_log"):
            self._log_ui_activity(
                "Evolution",
                "EOD",
                str(payload.get("eod_log")),
                status=str(payload.get("eod_status") or "INFO"),
            )

    def _action_widgets(self) -> tuple[QPushButton, ...]:
        return (
            self._btn_mark,
            self._btn_rebalance,
            self._btn_signal,
            self._btn_force,
            self._btn_refresh,
            self._btn_reset_gate,
            self._btn_connect,
            self._btn_portfolio_orders,
        )

    def _ensure_controls_operable(self) -> None:
        """Buttons and inputs stay clickable even while data loads in the background."""
        for w in self._action_widgets():
            w.setEnabled(True)
        if hasattr(self, "_trading_mode_switch"):
            self._trading_mode_switch.setEnabled(True)
        self._auto_open_cb.setEnabled(False)
        if hasattr(self, "_order_type_combo"):
            self._order_type_combo.setEnabled(True)
        for field in self._broker_panel._key, self._broker_panel._secret:
            field.setEnabled(True)
            field.setReadOnly(False)
            field.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _show_exe_setup_hint(self) -> None:
        from aa_frozen import is_frozen_exe

        if not is_frozen_exe():
            self._setup_banner.setText("")
            return
        from aa_exe_direct_startup import direct_exe_ready_message, direct_exe_requirements

        msg = direct_exe_ready_message(direct_exe_requirements(self.root))
        if msg:
            set_banner(self._setup_banner, "warn")
            self._setup_banner.setText(msg)
        else:
            self._setup_banner.setText(
                "EXE-Modus: Signal/Rebalance nutzen .venv im Projektordner (neben Marktanalyse.exe)."
            )
            set_banner(self._setup_banner, "info")

    def _load_cached_ui_fast(self) -> None:
        """Main-thread: show last known cash/pick before background refresh (EXE fix)."""
        try:
            from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status
            cached = load_cached_broker_status(self.root)
            broker: Dict[str, Any] = {}
            if cached and cached.cash_eur is not None:
                broker = {
                    "cash_eur": float(cached.cash_eur),
                    "credentials_configured": True,
                    "cached": True,
                }
                self._apply_broker_labels(broker)
                self.state["broker"] = broker
        except Exception:
            pass

    def _reset_busy_state(self) -> None:
        self._busy = False
        self._refreshing = False
        self._ensure_controls_operable()
        self._status_banner.setText("Zeitüberschreitung — erneut versuchen oder «Verbindung zu T212 laden».")

    def _set_action_busy(self, busy: bool, hint: str = "") -> None:
        self._busy = busy
        if busy:
            self._busy_watchdog.start(300_000)
        else:
            self._busy_watchdog.stop()
        if hint:
            self._status_banner.setText(hint)

    def _run_bg(self, label: str, fn: Callable[[], Dict[str, Any]], *, on_ok_refresh: bool = True) -> None:
        if self._busy:
            QMessageBox.information(self, label, "Bitte warten — vorheriger Schritt läuft noch.")
            return
        self._pending_action = {"label": label, "on_ok_refresh": on_ok_refresh}
        self._set_action_busy(True, f"{label} … läuft")
        self._log_ui_activity(label, "Gestartet", "läuft im Hintergrund", source="USER", status="LAUFEND")
        self._ensure_controls_operable()

        def work() -> None:
            try:
                result = fn()
            except Exception as exc:
                result = {"ok": False, "message_de": str(exc)[:400]}
            self._bg.action_finished.emit({"label": label, "result": result, "on_ok_refresh": on_ok_refresh})

        threading.Thread(target=work, daemon=True).start()

    def _on_action_finished(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._reset_busy_state()
            return
        label = str(payload.get("label") or "Aktion")
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        on_ok_refresh = bool(payload.get("on_ok_refresh"))
        self._set_action_busy(False)
        self._ensure_controls_operable()
        exec_block = result.get("execution") if isinstance(result.get("execution"), dict) else {}
        enqueue_only = bool(result.get("enqueue_only") or exec_block.get("enqueue_only"))
        sent_t212 = result.get("sent_to_t212")
        if sent_t212 is None:
            sent_t212 = exec_block.get("sent_to_t212")
        ok = bool(
            result.get("ok")
            or result.get("sync_ok")
            or result.get("recorded")
            or (result.get("daily_mark") or {}).get("recorded")
            or result.get("portfolio_csv_exists")
        )
        if enqueue_only or (sent_t212 is False and int(exec_block.get("enqueued") or exec_block.get("enqueued_count") or 0) > 0):
            ok = False
        msg = (
            result.get("message_de")
            or result.get("summary_de")
            or exec_block.get("message_de")
            or (result.get("rebalance") or {}).get("message_de")
            or ("OK" if ok else "Fehlgeschlagen")
        )
        self._status_banner.setText(str(msg)[:220])
        self._log_ui_activity(
            label,
            "Abgeschlossen",
            str(msg)[:180],
            source="USER",
            status="ERFOLGREICH" if ok else "FEHLGESCHLAGEN",
        )
        if enqueue_only or (not ok and not result.get("recorded")):
            detail = (result.get("stderr_tail") or result.get("stdout_tail") or "")[:800]
            QMessageBox.warning(
                self,
                label,
                f"{msg}\n\n{detail}" if detail else str(msg)[:1200],
            )
        if on_ok_refresh:
            self._refresh_ui(force=True)
        if label == "Champion-Portfolio" and ok and not enqueue_only:
            self._run_post_order_learning_async()

    def _run_post_order_learning_async(self) -> None:
        def work() -> None:
            try:
                from analytics.post_order_learning import run_post_order_learning

                run_post_order_learning(self.root)
            except Exception:
                pass

        threading.Thread(target=work, name="post-order-learn", daemon=True).start()

    def _on_daily_mark(self) -> None:
        self._run_bg("Täglicher Markt", lambda: dash.action_daily_mark(self.root))

    def _ensure_predict_ready(self, *, auto_run: bool = True) -> bool:
        from analytics.prediction_operations import ensure_prediction_before_orders

        pred = ensure_prediction_before_orders(self.root, auto_run=auto_run)
        if pred.get("ok") or pred.get("skipped"):
            if pred.get("auto_run") and pred.get("predict_ok"):
                self._refresh_ui(force=True)
            return True
        QMessageBox.warning(
            self,
            "Predict fehlt",
            pred.get("message_de", "Signal (predict) nicht bereit — keine Orders möglich.")
            + "\n\n"
            + " · ".join(str(b) for b in (pred.get("blockers") or [])[:4]),
        )
        return False

    def _grant_live_wave_confirmation(self, *, source: str, max_orders: int = 40) -> bool:
        from execution.confirmed_live.gui_execution_confirmation import grant_execution_confirmation

        grant = grant_execution_confirmation(
            self.root,
            source=source,
            scope="LIVE_WAVE",
            max_submissions=max(5, int(max_orders) + 3),
        )
        if grant.get("ok"):
            return True
        QMessageBox.warning(
            self,
            "Order blockiert",
            str(grant.get("message_de") or grant.get("error") or "Freigabe fehlgeschlagen"),
        )
        return False

    def _confirm_live_orders(self, *, title: str, intro: str) -> bool:
        if not self._ensure_predict_ready(auto_run=True):
            return False
        pfo = self._snap.get("portfolio_orders") or {}
        if not pfo.get("has_orders"):
            QMessageBox.information(
                self,
                title,
                pfo.get("summary_de")
                or "Keine Portfolio-Deltas — Tabelle prüfen oder ③ Signal aktualisieren.",
            )
            return False
        lines = "\n".join(pfo.get("lines_de") or [])
        msg = (
            f"{intro}\n\n{pfo.get('summary_de', '')}\n\n"
            f"Geplante Orders:\n{lines}\n\n"
            "Echtes Geld bei Trading 212 — finale Bestätigung erforderlich.\n"
            "Jetzt ausführen?"
        )
        ans = QMessageBox.question(
            self,
            title,
            msg[:3500],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return False
        pfo = self._snap.get("portfolio_orders") or {}
        if not self._grant_live_wave_confirmation(
            source=title,
            max_orders=int(pfo.get("order_count") or 40),
        ):
            return False
        return True

    def _on_rebalance(self) -> None:
        st = self._snap.get("rebalance_status") or {}
        if not st.get("is_due"):
            ans = QMessageBox.question(
                self,
                "Rebalance",
                "Zähler noch nicht voll — trotzdem Rebalance starten?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        if not self._confirm_live_orders(
            title="Rebalance bestätigen",
            intro="Signal + Orders an Trading 212.",
        ):
            return
        self._run_bg(
            "Rebalance",
            lambda: dash.action_rebalance(self.root, force=True),
        )

    def _on_force_rebalance(self) -> None:
        if not self._confirm_live_orders(
            title="Rebalance erzwingen",
            intro="Rebalance ohne Fälligkeit — Orders an Trading 212.",
        ):
            return
        self._run_bg("Rebalance erzwingen", lambda: dash.action_rebalance(self.root, force=True))

    def _on_signal(self) -> None:
        from aa_frozen import is_frozen_exe

        from aa_paths import venv_python_ok

        if is_frozen_exe() and not venv_python_ok(self.root):
            QMessageBox.warning(
                self,
                "Signal (ML)",
                "Für ML-Training wird .venv im Projektordner benötigt.\n"
                "Windows: setup_active_alpha_env.bat · Linux: tools/setup_linux_native.sh",
            )
            return
        QMessageBox.information(
            self,
            "Signal (ML)",
            "Startet Yahoo-Historie + ML-Training über .venv (kann mehrere Minuten dauern).\n"
            "Fortschritt erscheint nach Abschluss im Status.",
        )
        self._run_bg("Signal (ML)", lambda: dash.action_signal_update(self.root))

    def _on_reset_buy_gate(self) -> None:
        self._run_bg("T212-Kaufblock", lambda: dash.action_reset_t212_buy_gate(self.root))

    def _on_connect_t212(self) -> None:
        self._run_bg("T212-Verbindung", lambda: dash.action_sync_broker(self.root))

    def _on_execute_portfolio(self) -> None:
        if not self._ensure_predict_ready(auto_run=True):
            return
        from execution.confirmed_live.trading_mode_policy import (
            execution_credentials_ready,
            get_trading_mode,
            trading_readiness,
        )

        if get_trading_mode(self.root) != "ai_assisted":
            QMessageBox.information(
                self,
                "Champion-Portfolio",
                "Bitte «KI-unterstützt» einschalten.",
            )
            return
        if not execution_credentials_ready(self.root):
            QMessageBox.warning(
                self,
                "Champion-Portfolio",
                "Zuerst API mit Order-Rechten speichern (unten).",
            )
            return
        rd = trading_readiness(self.root)
        if not rd.get("ready"):
            QMessageBox.warning(
                self,
                "Champion-Portfolio",
                "\n".join(c["label"] for c in rd.get("checks") or [] if not c.get("ok")),
            )
            return

        pfo = self._snap.get("portfolio_orders") or {}
        qc = self._snap.get("quote_coverage") or pfo.get("quote_coverage") or {}
        if int(pfo.get("n_buys") or 0) > 0 and not qc.get("ok"):
            QMessageBox.warning(
                self,
                "Champion-Portfolio",
                qc.get("message_de")
                or "Live-Kurse unvollständig — bitte «Aktualisieren» und erneut prüfen.",
            )
            return
        if not pfo.get("has_orders"):
            QMessageBox.information(
                self,
                "Champion-Portfolio",
                pfo.get("summary_de")
                or "Keine Portfolio-Deltas — Tabelle prüfen oder ③ Signal aktualisieren.",
            )
            return

        lines = "\n".join(pfo.get("lines_de") or [])
        qc_line = ""
        if int(pfo.get("n_buys") or 0) > 0:
            qc_line = f"Live-Kurse: {pfo.get('quote_coverage_label_de') or qc.get('quote_coverage_label_de', '—')}\n\n"
        msg = (
            f"{pfo.get('summary_de', '')}\n\n"
            f"{qc_line}"
            f"Geplante Orders:\n{lines}\n\n"
            "Verkäufe werden vor Käufen ausgeführt.\n"
            f"Order-Typ: {self._order_type_combo.currentText()}.\n"
            "Außerhalb US-Handelszeit: Vormerkung für Eröffnung.\n\n"
            "Echtes Geld — finale Bestätigung erforderlich.\n"
            "Jetzt Champion-Portfolio an T212 senden?"
        )
        ans = QMessageBox.question(
            self,
            "Champion-Portfolio bestätigen",
            msg[:3500],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        if not self._grant_live_wave_confirmation(
            source="LIVE_DASHBOARD_PORTFOLIO",
            max_orders=int(pfo.get("order_count") or 40),
        ):
            return
        self._run_bg(
            "Champion-Portfolio",
            lambda: dash.action_execute_champion_portfolio(self.root, run_signal_first=False),
        )

    def _on_order_type_changed(self, _index: int) -> None:
        data = self._order_type_combo.currentData()
        if data is None:
            return
        try:
            dash.set_order_execution_type(self.root, str(data))
        except Exception as exc:
            QMessageBox.warning(self, "Order-Typ", str(exc)[:300])

    def _on_auto_open_toggled(self, _state: int) -> None:
        armed = self._auto_open_cb.isChecked()
        try:
            from execution.confirmed_live.us_equity_deferred_intents import set_user_armed_auto_open

            set_user_armed_auto_open(self.root, armed=armed)
        except Exception as exc:
            QMessageBox.warning(self, "Auto-Eröffnung", str(exc)[:300])
        self._refresh_ui(force=False)

    def _refresh_ui(self, *, force: bool, source: str = "USER") -> None:
        if self._refreshing and not force:
            return
        self._refreshing = True
        self._last_refresh_source = source
        hint = "Aktualisiere Konto und Modell …"
        if source.startswith("AUTO"):
            hint = "Auto-Refresh: Konto, Kurse, Modell …"
        self._status_banner.setText(hint)
        if source.startswith("AUTO"):
            self._log_ui_activity("Auto-Refresh", "Läuft", hint, source="AUTO", status="LAUFEND")
        if hasattr(self, "_visual_ops"):
            self._visual_ops.set_pulse(hint, kind="warn")
        self._ensure_controls_operable()

        def work() -> None:
            try:
                from execution.confirmed_live.live_trading_enablement import is_live_trading_enabled

                if not is_live_trading_enabled(self.root):
                    dash.action_enable_live(self.root)
                snap = dash.refresh_snapshot(self.root, force_quotes=force, force_sync=force)
                snap["_refresh_source"] = source
            except Exception as exc:
                snap = {
                    "error": str(exc)[:300],
                    "traffic": "ROT",
                    "today_action_de": str(exc)[:200],
                    "_refresh_source": source,
                }
            self._bg.refresh_finished.emit(snap)

        threading.Thread(target=work, daemon=True).start()

    def _on_refresh_finished(self, snap: object) -> None:
        self._refreshing = False
        if isinstance(snap, dict) and snap.get("eod_check_only"):
            self._on_eod_logged(snap)
            return
        if isinstance(snap, dict) and snap.get("eod_only"):
            self._on_eod_logged(snap)
            self._refresh_ui(force=True, source="AUTO_EOD")
            return
        if isinstance(snap, dict):
            self._apply_snapshot(snap)
            if hasattr(self, "_visual_ops"):
                self._visual_ops.set_pulse(
                    str(snap.get("today_action_de") or "Aktualisierung fertig")[:120],
                    kind={"GRUEN": "ok", "GELB": "warn", "ROT": "err"}.get(
                        str(snap.get("traffic") or "GELB"), "info"
                    ),
                )
        self._ensure_controls_operable()

    def _apply_snapshot(self, snap: Dict[str, Any]) -> None:
        self._snap = snap
        from ui.interactive_cockpit.trading_mode_ui import refresh_trading_mode_panel

        refresh_trading_mode_panel(self)

        broker = snap.get("broker") or {}
        plan = snap.get("plan") or {}
        guard = snap.get("guard") or {}
        self.state["broker"] = broker
        self.state["investment_plan"] = plan
        self.state["champion_guard"] = guard

        pfo = snap.get("portfolio_orders") or {}
        qc = snap.get("quote_coverage") or pfo.get("quote_coverage") or {}
        qc_label = str(pfo.get("quote_coverage_label_de") or qc.get("quote_coverage_label_de") or "—")
        qc_ok = bool(pfo.get("quote_coverage_ok", qc.get("ok")))
        n_buys = int(pfo.get("n_buys") or 0)
        n_alloc = len((plan.get("allocations") or []))
        sig_date = str(plan.get("signal_date") or pfo.get("signal_date") or "—")
        if pfo.get("has_orders"):
            if n_buys > 0 and qc_ok:
                set_banner(self._portfolio_metric, "ok")
            elif n_buys > 0:
                set_banner(self._portfolio_metric, "err")
            else:
                set_banner(self._portfolio_metric, "ok")
            title = str(pfo.get("summary_de") or "Portfolio-Orders bereit")
            if n_buys > 0:
                title = f"{title} · Live-Kurse: {qc_label}"
            self._portfolio_metric.setText(title)
            detail_lines = [f"Signal-Datum: {sig_date}", f"Modell-Positionen: {n_alloc}"]
            if n_buys > 0:
                detail_lines.append(
                    f"Kurs-Abdeckung (geplante Käufe): {qc_label}"
                    + ("" if qc_ok else f" — {qc.get('message_de', '')[:200]}")
                )
            detail_lines.extend(pfo.get("lines_de") or [])
            self._portfolio_detail.setText("\n".join(detail_lines)[:1200])
        else:
            set_banner(self._portfolio_metric, "warn")
            self._portfolio_metric.setText(
                f"Portfolio ({n_alloc} Symbole) — keine neuen Orders (Ziel ≈ Ist)"
            )
            self._portfolio_detail.setText(
                f"Signal-Datum: {sig_date} · Bei Bedarf ③ Signal, dann «Aktualisieren»."
            )

        from execution.confirmed_live.trading_mode_policy import get_trading_mode, trading_readiness

        rd = trading_readiness(self.root)
        pred_gate = snap.get("prediction_gate") or {}
        pred_ok = bool(pred_gate.get("ok") or pred_gate.get("skipped"))
        portfolio_ready = (
            get_trading_mode(self.root) == "ai_assisted"
            and rd.get("ready")
            and pred_ok
            and bool(pfo.get("has_orders"))
            and broker.get("cash_eur") is not None
            and not broker.get("error")
            and (qc_ok or n_buys == 0)
        )
        self._btn_portfolio_orders.setEnabled(portfolio_ready)
        if not portfolio_ready and pfo.get("has_orders"):
            hints = []
            if not pred_ok:
                hints.append(
                    str(pred_gate.get("message_de") or "Predict fehlt — ③ Signal oder EOD-Task 22:15")
                )
            if n_buys > 0 and not qc_ok:
                hints.append(f"Live-Kurse unvollständig ({qc_label}) — «Aktualisieren»")
            if get_trading_mode(self.root) != "ai_assisted":
                hints.append("KI-unterstützt einschalten")
            if not rd.get("ready"):
                hints.append("API speichern")
            if broker.get("error") or broker.get("cash_eur") is None:
                hints.append("«Verbindung zu T212 laden»")
            self._portfolio_detail.setText(
                (self._portfolio_detail.text() + "\n\nGesperrt: " + ", ".join(hints)).strip()[:1200]
            )

        if snap.get("error") and broker.get("cash_eur") is None:
            self._status_banner.setText("Hinweis beim Laden")
            set_banner(self._status_banner, "warn")
            self._action_line.setText(str(snap.get("error")))
            self._apply_broker_labels(broker)
            return

        readiness = snap.get("trading_readiness") or {}
        if readiness.get("ready") and readiness.get("orders_allowed"):
            set_banner(self._ready_label, "ok")
            self._ready_label.setText("Bereit — Orders an T212 möglich")
        elif readiness.get("ready"):
            set_banner(self._ready_label, "warn")
            self._ready_label.setText("Fast bereit — Review-Mode oder Modus blockiert Orders")
        else:
            set_banner(self._ready_label, "err")
            self._ready_label.setText("Nicht bereit für Live-Orders")
        checks = readiness.get("checks") or []
        extra = []
        if not snap.get("venv_ok"):
            extra.append(".venv fehlt (Signal in EXE braucht Projekt-.venv)")
        if not snap.get("model_script_ok"):
            extra.append("active_alpha_model.py fehlt neben EXE")
        if readiness.get("review_mode_active"):
            extra.append("Review-Mode blockiert — KI-Schalter oben prüfen")
        self._ready_detail.setText(
            " · ".join(
                [f"{c.get('label')}: {'OK' if c.get('ok') else '—'}" for c in checks]
                + extra
            )[:500]
        )

        traffic = str(snap.get("traffic") or "GELB")
        banner_map = {"GRUEN": "ok", "GELB": "warn", "ROT": "err"}
        set_banner(self._status_banner, banner_map.get(traffic, "warn"))
        status = snap.get("rebalance_status") or {}
        self._status_banner.setText(str(status.get("summary_de") or snap.get("today_action_de") or "—"))
        self._apply_day_warnings(snap)
        self._apply_learning_panel(snap)
        self._apply_trading_day_cockpit(snap)
        self._action_line.setText(str(snap.get("today_action_de") or ""))

        rec = status.get("recorded_trading_days_since_rebalance", 0)
        every = status.get("rebalance_every_trading_days", 1)
        rem = status.get("days_remaining", 0)
        self._schedule_label.setText(
            f"Markt-Tage seit letztem Rebalance: {rec} / {every} · "
            f"noch {rem} bis fällig · Empfehlung: {status.get('recommendation', '—')}"
        )
        sector_st = snap.get("sector_status") or {}
        self._sector_status_label.setText(str(sector_st.get("summary_de") or "Sektoren: —"))
        set_banner(self._sector_status_label, {"GRUEN": "ok", "GELB": "warn", "ROT": "err"}.get(
            str(sector_st.get("traffic") or "GELB"), "warn"
        ))

        self._apply_broker_labels(broker, plan)
        self._positions_label.setText(f"Positionen: {snap.get('n_positions', 0)}")

        pred = snap.get("prediction_meta") or plan.get("prediction_meta") or {}
        eod = snap.get("eod_switch") or {}
        eod_hint = ""
        if pred.get("eod_due_now"):
            eod_hint = f" · EOD-Umstellung fällig (ab {pred.get('eod_local_time_cet', '22:15')} CET)"
        elif eod.get("ok") and not eod.get("skipped"):
            eod_hint = " · EOD-Signal aktualisiert"
        self._model_summary.setText(
            (str(plan.get("summary_de") or plan.get("methodology_de") or "")[:400]
            or f"Symbole: {len(plan.get('allocations') or [])}")
            + eod_hint
        )

        rows = dash.portfolio_table_rows(snap)
        self._portfolio_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            self._portfolio_table.setItem(r, 0, QTableWidgetItem(row["symbol"]))
            self._portfolio_table.setItem(r, 1, QTableWidgetItem(f"{row['weight_pct']:.2f}"))
            self._portfolio_table.setItem(r, 2, QTableWidgetItem(f"{row['target_eur']:.2f}"))
            self._portfolio_table.setItem(r, 3, QTableWidgetItem(f"{row['current_eur']:.2f}"))
            self._portfolio_table.setItem(r, 4, QTableWidgetItem(f"{row['gap_eur']:+.2f}"))
            self._portfolio_table.setItem(r, 5, QTableWidgetItem(row["action_de"]))

        lt_pol = snap.get("policy") or {}
        exec_type = str(lt_pol.get("order_execution_type") or "limit").lower()
        self._order_type_combo.blockSignals(True)
        idx = self._order_type_combo.findData("market" if exec_type == "market" else "limit")
        if idx >= 0:
            self._order_type_combo.setCurrentIndex(idx)
        self._order_type_combo.blockSignals(False)

        deferred = snap.get("deferred") or {}
        self._queue_label.setText(str(deferred.get("status_de") or "Keine Warteschlange"))
        pol = deferred.get("policy") or {}
        self._auto_open_cb.blockSignals(True)
        self._auto_open_cb.setChecked(bool(pol.get("user_armed")))
        self._auto_open_cb.blockSignals(False)

        guard = snap.get("guard") or {}
        if not guard.get("signals_ok"):
            set_banner(self._model_summary, "warn")
        if not snap.get("live_enabled"):
            self._action_line.setText(
                self._action_line.text() + " · Live-Trading wird beim ersten Schritt aktiviert."
            )

        status = snap.get("rebalance_status") or {}
        if status.get("is_due"):
            self._schedule_label.setText(
                self._schedule_label.text()
                + "\n\nRebalance FÄLLIG: ② Rebalance nach GUI-Bestätigung (KI-Modus)."
            )

        src = str(snap.get("_refresh_source") or getattr(self, "_last_refresh_source", "USER"))
        summary = summarize_refresh(snap)
        st = "ERFOLGREICH" if not snap.get("error") else "FEHLGESCHLAGEN"
        cat = "Auto-Refresh" if src.startswith("AUTO") else "Dashboard"
        self._log_ui_activity(cat, "Aktualisierung fertig", summary, source=src.split("_")[0], status=st)
        try:
            self._activity_next.setText("\n".join(planned_auto_actions_de(self.root, snap))[:600])
        except Exception:
            pass
        self._schedule_auto_refresh()
        if hasattr(self, "_visual_ops"):
            self._visual_ops.update_from_snap(self.root, snap)
        self._reload_activity_panel(snap)

    def _apply_trading_day_cockpit(self, snap: Dict[str, Any]) -> None:
        try:
            from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

            doc = load_trading_day_cockpit_doc(self.root)
            if not doc:
                return
            lines = doc.get("cockpit_lines_de") or []
            next_step = str(doc.get("next_step_de") or "")
            circle = doc.get("circle_score") or {}
            title = "Tages-Cockpit"
            if circle.get("headline_de"):
                title = f"Kreis · {circle['headline_de']}"
            if lines and hasattr(self, "_activity_next"):
                self._activity_next.setText(
                    (f"{title}\n" + "\n".join(lines) + (f"\n\n→ {next_step}" if next_step else ""))[:700]
                )
            h1_banner = (doc.get("h1") or {}).get("banner_de")
            if h1_banner and hasattr(self, "_warnings_banner"):
                current = self._warnings_banner.text()
                if h1_banner not in current:
                    self._warnings_banner.setText(f"{h1_banner}\n{current}"[:500])
        except Exception:
            pass

    def _apply_learning_panel(self, snap: Dict[str, Any]) -> None:
        pl = snap.get("public_learning") or {}
        if not pl:
            self._learning_metric.setText("Lernreport fehlt — einmal «python3 tools/ai_kernel.py learn»")
            set_banner(self._learning_metric, "warn")
            self._learning_detail.setText("")
            return
        score = pl.get("score")
        grade = pl.get("grade") or "—"
        banner = "ok" if isinstance(score, (int, float)) and score >= 70 else "warn" if score else "warn"
        set_banner(self._learning_metric, banner)
        stage = pl.get("stage_de") or "Sportwagen"
        next_st = pl.get("next_stage_id") or "—"
        self._learning_metric.setText(
            f"Evolution: {stage} → {next_st} · Lernqualität {score if score is not None else '—'}/100 (Note {grade})"
        )
        ic = pl.get("ic_pearson")
        hit = pl.get("signed_hit_rate")
        live = pl.get("live_mature", 0)
        applied = int(pl.get("auto_applied_count") or 0)
        lines = [
            pl.get("headline_de") or "",
            f"IC {ic:.4f} · Hit {hit:.1%}" if ic is not None and hit is not None else "",
            f"Live reif: {live} · Auto-Tuning heute: {applied} · Lernen: {'ja' if pl.get('learning_detected') else 'nein'}",
        ]
        gaps = pl.get("stage_gaps_de") or []
        if gaps:
            lines.append("Nächste Stufe: " + "; ".join(str(g) for g in gaps[:3]))
        for step in pl.get("next_steps_de") or []:
            lines.append(f"→ {step}")
        self._learning_detail.setText("\n".join(x for x in lines if x)[:1200])

    def _apply_day_warnings(self, snap: Dict[str, Any]) -> None:
        report = snap.get("day_warnings") or {}
        critical = [w for w in (report.get("warnings") or []) if w.get("severity") == "critical"]
        warns = [w for w in (report.get("warnings") or []) if w.get("severity") == "warn"]
        if not report.get("count"):
            self._warnings_banner.setText("")
            self._warnings_detail.setText("")
            return
        sev = str(report.get("severity") or "warn")
        set_banner(self._warnings_banner, {"critical": "err", "warn": "warn", "ok": "ok"}.get(sev, "warn"))
        self._warnings_banner.setText(str(report.get("headline_de") or ""))
        lines = []
        for w in (critical + warns)[:6]:
            act = str(w.get("action_de") or "").strip()
            lines.append(f"• {w.get('title_de')}: {w.get('detail_de')}"[:220])
            if act:
                lines.append(f"  → {act}"[:200])
        self._warnings_detail.setText("\n".join(lines)[:1200])
        if critical and os.environ.get("AA_GUI_PREVIEW", "").strip() != "1":
            codes = {str(w.get("code") or "") for w in critical}
            new_codes = codes - self._warn_dialog_codes
            if new_codes:
                self._warn_dialog_codes |= codes
                body = "\n\n".join(
                    f"{w.get('title_de')}\n{w.get('detail_de')}\n→ {w.get('action_de', '')}".strip()
                    for w in critical[:4]
                )
                QMessageBox.warning(
                    self,
                    "Vor dem Handelstag — kritische Punkte",
                    (
                        "Diese Blocker haben den letzten schlechten Tag verursacht. "
                        "Bitte vor US-Eröffnung beheben:\n\n"
                        + body
                    )[:3500],
                )

    def _apply_broker_labels(self, broker: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> None:
        if broker.get("error") and broker.get("cash_eur") is None:
            self._cash_label.setText(f"Konto: {broker.get('error')}")
            set_banner(self._cash_label, "err")
            return
        cash = broker.get("cash_eur")
        if cash is None:
            self._cash_label.setText("Guthaben unbekannt — «Verbindung zu T212 laden»")
            set_banner(self._cash_label, "warn")
            return
        suffix = ""
        if broker.get("cached"):
            suffix = " (letzter Stand)"
        if broker.get("warning"):
            suffix = f" — {broker.get('warning')}"[:120]
        investable = (plan or {}).get("investable_eur")
        if investable is not None and float(investable) > 0:
            self._cash_label.setText(
                f"Verfügbar (T212): {float(cash):,.2f} € · investierbar: {float(investable):,.2f} €{suffix}"
            )
        else:
            self._cash_label.setText(f"Verfügbar (T212): {float(cash):,.2f} €{suffix}")
        set_banner(self._cash_label, "warn" if broker.get("warning") else "ok")


def launch_live_trading_dashboard(root: Path) -> int:
    from PySide6.QtWidgets import QApplication

    from ui.invest_layout import apply_invest_typography

    app = QApplication.instance() or QApplication(sys.argv)
    apply_invest_typography(app)
    win = LiveTradingDashboardWindow(root)
    win.show()
    return app.exec()
