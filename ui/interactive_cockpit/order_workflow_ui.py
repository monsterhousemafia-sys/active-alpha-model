"""P16H order workflow UI helpers — confirm-before-submit."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.interactive_cockpit.button_roles import ROLE_DANGER, ROLE_PRIMARY, ROLE_SECONDARY, ROLE_TERTIARY, set_button_role
from ui.interactive_cockpit.cockpit_theme import ERROR_BANNER, SUCCESS_BANNER, WARNING_BANNER
from execution.confirmed_live.confirmed_execution_mode_controller import (
    ACTIVATION_PHRASE,
    activate_by_user,
    load_mode,
    pause_by_user,
)
from execution.confirmed_live.global_kill_switch import activate as kill_on, deactivate as kill_off, load_state as kill_state
from execution.confirmed_live.managed_scope_service import create_baseline, load_baseline, load_managed_scope, set_managed_scope
from execution.confirmed_live.order_confirmation_token_service import confirmation_phrase, issue_token
from execution.confirmed_live.order_draft_service import create_draft, load_queue_summary, refresh_draft_status
from execution.confirmed_live.order_submission_service import submit_confirmed_order
from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION, PROFILE_MONITORING_READONLY
from integrations.trading212.t212_dual_profile_credential_store import set_profile_credentials, clear_profile
from integrations.trading212.t212_dual_profile_secure_store import save_profile_credentials
from ui.interactive_cockpit.services.activity_audit_service import log_activity

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def _t212_id_for_symbol(symbol: str) -> str:
    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE

    sym = str(symbol or "").upper().strip()
    meta = MAPPING_TABLE.get(sym) or {}
    return str(meta.get("provider_instrument_id") or f"{sym}_US_EQ")


def _ensure_symbol_in_scope(win: "InteractiveCockpitWindow", symbol: str) -> None:
    sym = str(symbol).upper().strip()
    sc = load_managed_scope(win.root)
    instruments = [str(x).upper() for x in (sc.get("managed_instruments") or [])]
    if sym not in instruments:
        instruments.append(sym)
        set_managed_scope(
            win.root,
            managed_instruments=instruments,
            authorized_capital_eur=float(sc.get("authorized_capital_eur") or 0),
        )


def open_today_pick_order(win: "InteractiveCockpitWindow") -> None:
    """Ein Klick: Limit-Order sofort an Trading 212 (API mit Order-Rechten)."""
    from analytics.pilot_today_pick import load_today_pick
    from execution.confirmed_live.order_confirmation_token_service import issue_token
    from execution.confirmed_live.trading_mode_policy import get_trading_mode, trading_readiness
    from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
    from execution.confirmed_live.trading_mode_policy import execution_credentials_ready

    if get_trading_mode(win.root) != "ai_assisted":
        QMessageBox.information(win, "Handelsmodus", "Bitte KI-unterstützt einschalten.")
        return
    if not execution_credentials_ready(win.root):
        QMessageBox.warning(win, "API", "Zuerst API mit Order-Rechten speichern (unten «Speichern»).")
        return
    rd = trading_readiness(win.root)
    if not rd.get("ready"):
        QMessageBox.warning(
            win,
            "Noch nicht bereit",
            "\n".join(c["label"] for c in rd.get("checks") or [] if not c["ok"]),
        )
        return

    pick = load_today_pick(win.root)
    plan = (getattr(win, "state", None) or {}).get("investment_plan") or {}
    primary = plan.get("primary_action") or {}
    if primary.get("symbol"):
        pick = {**pick, **primary}
    sym = str(pick.get("symbol") or "").upper()
    if not sym:
        QMessageBox.warning(win, "Signal", "Kein Handelssignal auf dem aktuellen Stand.")
        return

    _ensure_symbol_in_scope(win, sym)
    try:
        from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

        broker_live = sync_readonly_account(win.root, force=True)
        win.state["broker"] = {
            "cash_eur": broker_live.cash_eur,
            "cash_breakdown": broker_live.cash_breakdown or {},
            "status": broker_live.status,
            "last_sync_utc": broker_live.last_successful_sync_utc,
        }
    except Exception:
        pass
    broker = win.state.get("broker") or {}
    cash = broker.get("cash_eur")
    from execution.confirmed_live.managed_scope_service import baseline_exists, create_baseline

    if not baseline_exists(win.root):
        create_baseline(
            win.root,
            account_currency="EUR",
            available_cash=cash,
            positions=[],
        )
    notional = float(pick.get("target_eur") or primary.get("target_eur") or 42.0)
    plan = (getattr(win, "state", None) or {}).get("investment_plan") or plan
    if not plan.get("primary_action"):
        plan = {
            **plan,
            "primary_action": {"symbol": sym, "target_eur": notional},
            "signal_date": pick.get("signal_date"),
        }

    from analytics.pilot_live_trade_gate import (
        build_live_order_preflight,
        format_confirmation_dialog_text,
    )

    preflight = build_live_order_preflight(
        win.root,
        symbol=sym,
        target_notional_eur=notional,
        broker=broker,
        plan=plan,
        champion_guard=(getattr(win, "state", None) or {}).get("champion_guard"),
    )
    win.state["market_prices"] = preflight.get("quote_snapshot") or {}
    win.state["last_order_preflight"] = preflight
    if not preflight.get("ok"):
        QMessageBox.warning(
            win,
            "Live-Prüfung fehlgeschlagen",
            format_confirmation_dialog_text(preflight),
        )
        return

    limit = float(preflight.get("limit_price_eur") or 0)
    if limit <= 0:
        QMessageBox.warning(win, "Order", "Kein Limitpreis — Order abgebrochen.")
        return

    confirm = QMessageBox.question(
        win,
        "Order bestätigen",
        format_confirmation_dialog_text(preflight),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    if confirm != QMessageBox.StandardButton.Yes:
        return

    from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy
    from execution.confirmed_live.order_draft_service import prune_stale_order_drafts
    from execution.confirmed_live.order_sizing import plan_executable_buy_order

    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now
    from integrations.trading212.t212_order_readiness import (
        assess_deferred_enqueue_readiness,
        assess_order_readiness,
    )

    sess = us_equity_regular_session_open_now()
    if sess.get("open"):
        readiness = assess_order_readiness(
            win.root,
            free_cash_eur=float(cash) if cash is not None else None,
        )
    else:
        from execution.confirmed_live.us_equity_deferred_intents import load_policy

        if load_policy(win.root).get("enabled"):
            readiness = assess_deferred_enqueue_readiness(
                win.root,
                free_cash_eur=float(cash) if cash is not None else None,
            )
        else:
            readiness = assess_order_readiness(
                win.root,
                free_cash_eur=float(cash) if cash is not None else None,
            )
    if not readiness.ok:
        QMessageBox.warning(win, "Order nicht möglich", readiness.status_de)
        return

    prune_stale_order_drafts(win.root, max_age_minutes=10.0)
    if getattr(win, "_order_submit_in_progress", False):
        QMessageBox.information(
            win,
            "Order",
            "ℹ Order wird bereits gesendet — bitte warten.",
        )
        return
    win._order_submit_in_progress = True
    try:
        plan_preview = plan_executable_buy_order(
            target_notional_eur=notional,
            limit_price_eur=limit,
            free_cash_eur=float(cash) if cash is not None else None,
            root=win.root,
        )
        from integrations.trading212.t212_fee_economics import (
            is_notional_worth_trading,
            round_trip_summary_de,
        )

        exec_notional = float(plan_preview.get("executable_notional_eur") or notional)
        worth, fee_reason = is_notional_worth_trading(exec_notional, win.root, price_eur=limit)
        if not worth:
            QMessageBox.warning(
                win,
                "Order unwirtschaftlich",
                "Diese Order ist voraussichtlich zu klein — die Gebühren würden einen "
                "überproportionalen Anteil fressen.\n\n"
                f"{fee_reason}\n\n"
                f"{round_trip_summary_de(exec_notional, win.root)}",
            )
            return
        if plan_preview["quantity"] < 0.01:
            from integrations.trading212.t212_user_messages import humanize_t212_error
            from execution.confirmed_live.order_execution_receipt_pdf import (
                open_receipt_pdf,
                write_order_execution_receipt,
            )

            pre_result = {
                "ok": False,
                "stage": "sizing",
                "error": "INSUFFICIENT_FREE_CASH",
                "user_message_de": humanize_t212_error("insufficient funds"),
            }
            pdf_ok, pdf_path = write_order_execution_receipt(
                win.root,
                symbol=sym,
                t212_id=_t212_id_for_symbol(sym),
                target_notional_eur=notional,
                limit_price_eur=limit,
                free_cash_eur=float(cash) if cash is not None else None,
                plan_preview=plan_preview,
                result=pre_result,
                pick=pick,
                stage="preflight",
            )
            extra = f"\n\nProtokoll-PDF:\n{pdf_path}" if pdf_ok else ""
            if pdf_ok:
                open_receipt_pdf(pdf_path)
            QMessageBox.warning(
                win,
                "Order nicht möglich",
                humanize_t212_error("insufficient funds") + extra,
            )
            return

        currency = (load_baseline(win.root).get("account_currency") or "EUR") if load_baseline(win.root) else "EUR"
        if hasattr(win, "_order_btn"):
            win._order_btn.setEnabled(False)
            win._order_btn.setText("Order wird gesendet …")
        defer_plan = {
            "primary_action": {
                "symbol": sym,
                "target_eur": notional,
            },
            "signal_date": plan.get("signal_date"),
            "champion_id": plan.get("champion_id"),
            "allocations": plan.get("allocations") or [],
        }
        from execution.confirmed_live.us_equity_deferred_intents import try_enqueue_or_execute_now

        result = try_enqueue_or_execute_now(
            win.root,
            plan=plan,
            limit_price_eur=limit,
            free_cash_eur=float(cash) if cash is not None else None,
            quote_snapshot=preflight.get("quote_snapshot") or win.state.get("market_prices"),
            champion_guard=(getattr(win, "state", None) or {}).get("champion_guard"),
        )
        draft = result.get("draft") or {}
        log_activity(
            win.root,
            category="Submission",
            action="Order ausführen (1 Klick)",
            result=str(result.get("user_message_de") or result.get("status") or result.get("error")),
            status="ERFOLGREICH" if result.get("ok") else "FEHLGESCHLAGEN",
            instruments=[sym],
            user_action_required=not bool(result.get("ok")),
            details={
                "scaled_down": result.get("scaled_down"),
                "attempts": result.get("attempts"),
                "stage": result.get("stage"),
            },
        )
        from execution.confirmed_live.order_execution_receipt_pdf import (
            open_receipt_pdf,
            write_order_execution_receipt,
        )

        pdf_ok, pdf_path = write_order_execution_receipt(
            win.root,
            symbol=sym,
            t212_id=_t212_id_for_symbol(sym),
            target_notional_eur=notional,
            limit_price_eur=limit,
            free_cash_eur=float(cash) if cash is not None else None,
            plan_preview=plan_preview,
            result=result,
            pick=pick,
            stage="submission",
        )
        pdf_note = f"\n\nProtokoll-PDF:\n{pdf_path}" if pdf_ok else "\n\n(PDF-Protokoll konnte nicht erstellt werden.)"
        if pdf_ok:
            open_receipt_pdf(pdf_path)

        msg = str(result.get("user_message_de") or result.get("message_de") or "")
        if result.get("ok"):
            mode = str(result.get("mode") or "")
            if mode in ("deferred_batch", "deferred"):
                title = "US-Orders vorgemerkt"
            elif mode == "live_batch":
                title = "Orders gesendet (Batch)"
            else:
                title = "Order gesendet"
            QMessageBox.information(win, title, msg + pdf_note)
            prune_stale_order_drafts(win.root, max_age_minutes=0.5)
        else:
            QMessageBox.warning(win, "Order fehlgeschlagen", (msg or "Unbekannter Fehler") + pdf_note)
        refresh_order_views(win)
        if hasattr(win, "_refresh_all"):
            win._refresh_all()
    finally:
        win._order_submit_in_progress = False
        if hasattr(win, "_order_btn"):
            win._order_btn.setText("Order ausführen")


def build_order_review_view(win: "InteractiveCockpitWindow") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("<h2>Orders</h2><p>Entwurf prüfen und an T212 senden.</p>"))
    win._order_review_warn = QLabel()
    win._order_review_warn.setWordWrap(True)
    lay.addWidget(win._order_review_warn)
    from ui.interactive_cockpit.integrated_pilot_refresh import extend_order_review_preflight_line

    extend_order_review_preflight_line(win, lay)
    win._order_queue_label = QLabel()
    lay.addWidget(win._order_queue_label)
    win._order_review_table = QTableWidget(0, 6)
    win._order_review_table.setHorizontalHeaderLabels(["ID", "Instrument", "Seite", "Betrag", "Status", "Aktion"])
    lay.addWidget(win._order_review_table)
    btn_row = QHBoxLayout()
    create_btn = QPushButton("Entwurf anlegen (Test)")
    set_button_role(create_btn, ROLE_SECONDARY)
    create_btn.clicked.connect(lambda: _create_sample_draft(win))
    lay.addLayout(btn_row)
    btn_row.addWidget(create_btn)
    return w


def build_confirmed_orders_view(win: "InteractiveCockpitWindow") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("<h2>Bestätigte Live-Orders & Reconciliation</h2>"))
    win._confirmed_orders_body = QLabel()
    win._confirmed_orders_body.setWordWrap(True)
    lay.addWidget(win._confirmed_orders_body)
    return w


def build_live_setup_view(win: "InteractiveCockpitWindow") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("<h2>Portfolio</h2><p>Champion-Positionen für Live-Trading (volles T212-Guthaben).</p>"))

    win._pilot_trading_status = QLabel()
    win._pilot_trading_status.setWordWrap(True)
    lay.addWidget(win._pilot_trading_status)

    grp = QGroupBox("Erlaubte Aktien")
    form = QFormLayout(grp)
    win._managed_symbols = QLineEdit("INTC,WDC,STX")
    win._managed_capital = QLineEdit("0")
    form.addRow("Symbole (kommagetrennt)", win._managed_symbols)
    form.addRow("Budget EUR (0 = volles freies T212-Guthaben)", win._managed_capital)
    lay.addWidget(grp)
    win._baseline_label = QLabel()
    win._baseline_label.setWordWrap(True)
    lay.addWidget(win._baseline_label)
    save_scope = QPushButton("Speichern")
    set_button_role(save_scope, ROLE_PRIMARY)
    save_scope.clicked.connect(lambda: _save_baseline_scope(win))
    lay.addWidget(save_scope)
    return w


def extend_risk_view(win: "InteractiveCockpitWindow", layout: QVBoxLayout) -> None:
    lt_grp = QGroupBox("Live-Trading")
    lt_lay = QVBoxLayout(lt_grp)
    win._live_trading_risk = QCheckBox(
        "Ich bestätige Echtgeld-Orders über Trading 212 (Champion unverändert, keine Auto-Promotion)."
    )
    lt_lay.addWidget(win._live_trading_risk)
    lt_on = QPushButton("Live-Trading aktivieren")
    set_button_role(lt_on, ROLE_PRIMARY)
    lt_on.clicked.connect(lambda: _enable_live_trading(win))
    lt_off = QPushButton("Live-Trading deaktivieren")
    set_button_role(lt_off, ROLE_SECONDARY)
    lt_off.clicked.connect(lambda: _disable_live_trading(win))
    lt_lay.addWidget(lt_on)
    lt_lay.addWidget(lt_off)
    layout.addWidget(lt_grp)

    grp = QGroupBox("Notfall")
    lay = QVBoxLayout(grp)
    win._core_live_status = QLabel()
    win._core_live_status.setWordWrap(True)
    lay.addWidget(win._core_live_status)
    kill_btn = QPushButton("SOFORT STOPPEN — alle App-Orders sperren (Kill Switch)")
    set_button_role(kill_btn, ROLE_DANGER)
    kill_btn.clicked.connect(lambda: _kill_switch(win))
    lay.addWidget(kill_btn)
    layout.addWidget(grp)


def extend_t212_profiles(win: "InteractiveCockpitWindow", layout: QVBoxLayout) -> None:
    layout.addWidget(QLabel("<b>Lese-Key</b> — Konto anzeigen (oben im Formular)."))
    layout.addWidget(QLabel("<b>API mit Order-Rechten</b> — einmalig, Bestätigung später Ja/Nein:"))
    mon_grp = QGroupBox("Lese-Key (optional, zweiter Schlüssel)")
    mon_form = QFormLayout(mon_grp)
    win._mon_key = QLineEdit()
    win._mon_key.setEchoMode(QLineEdit.EchoMode.Password)
    win._mon_secret = QLineEdit()
    win._mon_secret.setEchoMode(QLineEdit.EchoMode.Password)
    mon_form.addRow("API Key", win._mon_key)
    mon_form.addRow("API Secret", win._mon_secret)
    layout.addWidget(mon_grp)
    mon_save = QPushButton("Monitoring-Profil speichern & testen")
    set_button_role(mon_save, ROLE_PRIMARY)
    mon_save.clicked.connect(lambda: _save_monitoring_profile(win))
    layout.addWidget(mon_save)

    exec_grp = QGroupBox("API mit Order-Rechten")
    exec_form = QFormLayout(exec_grp)
    win._exec_key = QLineEdit()
    win._exec_key.setEchoMode(QLineEdit.EchoMode.Password)
    win._exec_secret = QLineEdit()
    win._exec_secret.setEchoMode(QLineEdit.EchoMode.Password)
    exec_form.addRow("API Key", win._exec_key)
    exec_form.addRow("API Secret", win._exec_secret)
    layout.addWidget(exec_grp)
    exec_save = QPushButton("API speichern")
    set_button_role(exec_save, ROLE_SECONDARY)
    exec_save.clicked.connect(lambda: _save_execution_profile(win))
    layout.addWidget(exec_save)


def refresh_order_views(win: "InteractiveCockpitWindow") -> None:
    if hasattr(win, "_order_queue_label"):
        q = load_queue_summary(win.root)
        w, b = int(q.get("waiting_review") or 0), int(q.get("blocked") or 0)
        if w or b:
            win._order_queue_label.setText(
                f"Lokale Live-Trading-Entwürfe (nicht T212): {w} bereit · {b} blockiert — "
                f"«Order ausführen» sendet nur eine Limit-Order."
            )
        else:
            win._order_queue_label.setText("")
        win._fill_order_table(q.get("drafts") or [])
    if hasattr(win, "_confirmed_orders_body"):
        from pathlib import Path

        submitted = list((win.root / "live_pilot/confirmed_execution/submitted_orders").glob("*.json"))
        win._confirmed_orders_body.setText(f"Übermittelte Orders (reconciliert/read-only): {len(submitted)}")
    if hasattr(win, "_baseline_label"):
        bl = load_baseline(win.root)
        sc = load_managed_scope(win.root)
        win._baseline_label.setText(
            f"Gespeichert: {', '.join(sc.get('managed_instruments') or []) or '—'} "
            f"| {sc.get('authorized_capital_eur', '—')} EUR"
        )
    if hasattr(win, "_core_live_status"):
        _refresh_core_live_panel(win)
    if hasattr(win, "_pilot_trading_status"):
        _refresh_pilot_trading_status(win)
    if hasattr(win, "_order_review_warn"):
        _refresh_order_review_banner(win)


def _fill_table_helper(table: QTableWidget, rows: list) -> None:
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            table.setItem(r, c, QTableWidgetItem(str(val)))


def _create_sample_draft(win: "InteractiveCockpitWindow") -> None:
    draft = create_draft(
        win.root,
        instrument="OXY",
        side="BUY",
        max_notional_eur=50.0,
        limit_price=50.0,
        t212_id="OXY_US_EQ",
        quantity=1.0,
    )
    broker = win.state.get("broker") or {}
    cash = broker.get("cash_eur")
    currency = (load_baseline(win.root).get("account_currency") or "EUR") if load_baseline(win.root) else "EUR"
    refresh_draft_status(win.root, draft, readonly_cash=cash, account_currency=currency)
    log_activity(win.root, category="Orderentwurf", action="Entwurf erzeugt", result=draft.get("status"), instruments=[draft.get("instrument")])
    refresh_order_views(win)
    if draft.get("status") == "DRAFT_READY_FOR_REVIEW":
        _open_confirm_dialog(win, draft, cash, currency)


def _open_confirm_dialog(win: "InteractiveCockpitWindow", draft: Dict[str, Any], cash: Any, currency: str) -> None:
    from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed
    from integrations.trading212.t212_dual_profile_credential_store import execution_configured

    sym = draft.get("instrument", "?")
    side = draft.get("side", "BUY")
    limit = draft.get("limit_price", "—")
    eur = draft.get("max_notional_eur", "—")
    can_send = live_submission_allowed(win.root) and execution_configured()

    from ui.invest_layout import body_label, set_banner, uniform_button_row
    from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_SECONDARY, set_button_role

    dlg = QDialog(win)
    dlg.setWindowTitle("Ja oder Nein?")
    dlg.setMinimumWidth(520)
    lay = QVBoxLayout(dlg)
    lay.setSpacing(14)
    msg = body_label(
        f"Limit-Order an Trading 212 senden?\n\n"
        f"{side} {sym}\n"
        f"Limit {limit} · ca. {eur} €\n\n"
        f"Ja + Enter = senden\n"
        f"Nein oder Esc = abbrechen"
    )
    set_banner(msg, "info")
    lay.addWidget(msg)
    if not can_send:
        hint = body_label(
            "Live-Versand noch nicht möglich — Broker-Zugang «Order-Zugang» speichern."
        )
        set_banner(hint, "warn")
        lay.addWidget(hint)

    yes_btn = QPushButton("Ja — ausführen")
    no_btn = QPushButton("Nein")
    set_button_role(yes_btn, ROLE_PRIMARY)
    set_button_role(no_btn, ROLE_SECONDARY)
    yes_btn.setDefault(True)
    yes_btn.setAutoDefault(True)
    lay.addLayout(uniform_button_row(yes_btn, no_btn))

    token_preview = issue_token(win.root, draft, profile=PROFILE_CONFIRMED_EXECUTION)

    def _submit_yes() -> None:
        from analytics.prediction_operations import ensure_prediction_before_orders
        from execution.confirmed_live.gui_execution_confirmation import grant_execution_confirmation

        pred = ensure_prediction_before_orders(win.root, auto_run=True)
        if not pred.get("ok") and not pred.get("skipped"):
            QMessageBox.warning(win, "Predict fehlt", pred.get("message_de", "Signal nicht bereit."))
            return
        grant = grant_execution_confirmation(
            win.root,
            source="ORDER_WORKFLOW_DIALOG",
            scope="SINGLE_ORDER",
            max_submissions=1,
        )
        if not grant.get("ok"):
            QMessageBox.warning(win, "Order blockiert", grant.get("message_de", "Freigabe fehlgeschlagen."))
            return
        result = submit_confirmed_order(
            win.root,
            draft,
            one_time_token=token_preview["one_time_token"],
            readonly_cash=float(cash) if cash is not None else None,
            account_currency=currency,
            dry_run=not can_send,
        )
        log_activity(
            win.root,
            category="Submission",
            action="Order Ja",
            result=str(result.get("status", result.get("error"))),
        )
        if result.get("ok"):
            QMessageBox.information(
                win,
                "Order",
                "Gesendet an Trading 212."
                if can_send
                else "Entwurf bestätigt (Live-Versand noch nicht konfiguriert).",
            )
        else:
            QMessageBox.warning(win, "Order", str(result.get("error") or result))
        dlg.accept()
        refresh_order_views(win)
        if hasattr(win, "_refresh_all"):
            win._refresh_all()

    yes_btn.clicked.connect(_submit_yes)
    no_btn.clicked.connect(dlg.reject)
    dlg.exec()


def _save_baseline_scope(win: "InteractiveCockpitWindow") -> None:
    broker = win.state.get("broker") or {}
    positions = []
    syms = [s.strip().upper() for s in win._managed_symbols.text().split(",") if s.strip()]
    create_baseline(
        win.root,
        account_currency="EUR",
        available_cash=broker.get("cash_eur"),
        positions=positions,
    )
    set_managed_scope(win.root, managed_instruments=syms, authorized_capital_eur=float(win._managed_capital.text().replace(",", ".") or 0))
    log_activity(win.root, category="Konto", action="Baseline & Managed Scope gespeichert", result="OK")
    refresh_order_views(win)
    QMessageBox.information(win, "Gespeichert", "Symbole und Budget gespeichert.")


def _refresh_core_live_panel(win: "InteractiveCockpitWindow") -> None:
    from execution.confirmed_live.trading_mode_policy import get_trading_mode

    ks = kill_state(win.root)
    tm = get_trading_mode(win.root)
    win._core_live_status.setText(
        f"Handelsmodus: {'KI-unterstützt' if tm == 'ai_assisted' else 'Manuell'}\n"
        f"Kill Switch: {'AKTIV — alle Orders gesperrt' if ks.get('active') else 'INAKTIV'}"
    )


def _activation_dialog_text(res: Dict[str, Any]) -> str:
    return str(res.get("message") or res.get("error") or "Unbekannter Fehler")


def _activate_core_live(win: "InteractiveCockpitWindow") -> None:
    res = activate_by_user(win.root, phrase=win._core_live_phrase.text(), risk_ack=win._core_live_risk.isChecked())
    if not res.get("ok"):
        QMessageBox.warning(win, "Core-Live", _activation_dialog_text(res))
        _refresh_core_live_panel(win)
        return
    log_activity(win.root, category="Risiko", action="Core-Live aktiviert", result="ACTIVE")
    refresh_order_views(win)
    QMessageBox.information(
        win,
        "Core-Live aktiv",
        "Core-Live-Modus ist AKTIV (nur nach Einzelbestätigung).\n\n"
        "Nächster Schritt: Order Review → Entwurf → LIVE an T212 senden.",
    )


def _pause_core_live(win: "InteractiveCockpitWindow") -> None:
    pause_by_user(win.root)
    refresh_order_views(win)


def _kill_switch(win: "InteractiveCockpitWindow") -> None:
    ks = kill_state(win.root)
    if ks.get("active"):
        kill_off(win.root)
    else:
        kill_on(win.root)
    refresh_order_views(win)


def _save_monitoring_profile(win: "InteractiveCockpitWindow") -> None:
    set_profile_credentials(
        PROFILE_MONITORING_READONLY,
        api_key=win._mon_key.text(),
        api_secret=win._mon_secret.text(),
        mode="LIVE_READ_ONLY",
    )
    win._mon_key.clear()
    win._mon_secret.clear()
    log_activity(win.root, category="Verbindung", action="Monitoring-Profil gespeichert", result="OK")
    win.refresh_state(full=True)


def _save_execution_profile(win: "InteractiveCockpitWindow") -> None:
    from integrations.trading212.t212_execution_dpapi_store import save_execution_credentials

    key = win._exec_key.text().strip()
    secret = win._exec_secret.text().strip()
    if not key or not secret:
        QMessageBox.warning(win, "Execution-Profil", "API Key und Secret erforderlich (Order-Rechte in T212).")
        return
    set_profile_credentials(
        PROFILE_CONFIRMED_EXECUTION,
        api_key=key,
        api_secret=secret,
        mode="LIVE_READ_ONLY",
        persist_requested=True,
    )
    save_profile_credentials(PROFILE_CONFIRMED_EXECUTION, key, secret)
    ok_dp, dp_msg = save_execution_credentials(win.root, key, secret)
    win._exec_key.setText(key)
    win._exec_secret.setText(secret)
    log_activity(
        win.root,
        category="Verbindung",
        action="Execution-Profil gespeichert",
        result="OK" if ok_dp else dp_msg,
    )
    QMessageBox.information(
        win,
        "Gespeichert",
        "API gespeichert.\n"
        "Keine Auto-Orders — nur nach Ihrer Bestätigung unter Orders.",
    )


def _refresh_pilot_trading_status(win: "InteractiveCockpitWindow") -> None:
    from execution.confirmed_live.trading_mode_policy import trading_readiness

    rd = trading_readiness(win.root)
    lines = [f"{'✓' if c['ok'] else '○'} {c['label']}" for c in rd.get("checks") or []]
    win._pilot_trading_status.setText("\n".join(lines))


def _refresh_order_review_banner(win: "InteractiveCockpitWindow") -> None:
    from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed
    from execution.confirmed_live.trading_mode_policy import get_trading_mode, trading_readiness

    if get_trading_mode(win.root) == "ai_assisted" and live_submission_allowed(win.root):
        win._order_review_warn.setText("Bereit — Order bestätigen, dann LIVE an T212.")
        win._order_review_warn.setStyleSheet(SUCCESS_BANNER)
    elif get_trading_mode(win.root) == "ai_assisted":
        miss = [c["label"] for c in (trading_readiness(win.root).get("checks") or []) if not c["ok"]]
        win._order_review_warn.setText("Noch offen auf Start:\n• " + "\n• ".join(miss))
        win._order_review_warn.setStyleSheet(WARNING_BANNER)
    else:
        win._order_review_warn.setText("App sendet nichts — auf Start «KI-unterstützt» einschalten.")
        win._order_review_warn.setStyleSheet(ERROR_BANNER)


def _enable_live_trading(win: "InteractiveCockpitWindow") -> None:
    from execution.confirmed_live.live_trading_enablement import enable_live_trading

    risk_ok = True
    if hasattr(win, "_live_trading_risk"):
        risk_ok = win._live_trading_risk.isChecked()
    if not risk_ok:
        QMessageBox.warning(win, "Live-Trading", "Bitte Risikohinweis bestätigen.")
        return
    res = enable_live_trading(win.root, risk_ack=True, changed_by="user")
    if not res.get("ok"):
        QMessageBox.warning(win, "Live-Trading", str(res.get("error", res)))
        return
    log_activity(win.root, category="Risiko", action="Live-Trading aktiviert", result="OK")
    win.refresh_state(full=False)
    refresh_order_views(win)
    QMessageBox.information(
        win,
        "Aktiviert",
        "Live-Trading aktiv (Paper-Rhythmus: täglicher Mark, Rebalance alle 5 Lauf-Tage).\n"
        "1. T212 → API mit Order-Rechten\n"
        "2. Portfolio-Scope speichern\n"
        "3. «Order ausführen» oder Auto bei US-Eröffnung",
    )


def _disable_live_trading(win: "InteractiveCockpitWindow") -> None:
    from execution.confirmed_live.live_trading_enablement import disable_live_trading

    disable_live_trading(win.root, changed_by="user")
    win.refresh_state(full=False)
    refresh_order_views(win)
    QMessageBox.information(win, "Deaktiviert", "Live-Trading aus. Review Mode wieder AN.")


# Backward-compatible aliases
_enable_pilot_trading = _enable_live_trading
_disable_pilot_trading = _disable_live_trading


def bind_order_table_fill(win: "InteractiveCockpitWindow") -> None:
    def _fill(rows):
        win._order_review_table.setRowCount(len(rows))
        for r, draft in enumerate(rows):
            btn = QPushButton("Prüfen")
            set_button_role(btn, ROLE_SECONDARY)
            btn.clicked.connect(lambda checked, d=draft: _open_confirm_dialog(
                win, d, (win.state.get("broker") or {}).get("cash_eur"), "EUR"
            ))
            cols = [
                draft.get("draft_id", "")[:8],
                draft.get("instrument"),
                draft.get("side"),
                draft.get("max_notional_eur"),
                draft.get("status"),
            ]
            for c, val in enumerate(cols):
                win._order_review_table.setItem(r, c, QTableWidgetItem(str(val)))
            win._order_review_table.setCellWidget(r, 5, btn)

    win._fill_order_table = _fill
