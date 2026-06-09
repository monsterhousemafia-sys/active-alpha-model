"""Handelsmodus — ein Schalter, eine Checkliste."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from execution.confirmed_live.trading_mode_policy import (
    apply_trading_mode,
    get_trading_mode,
    trading_readiness,
)
from ui.interactive_cockpit.apple_toggle_switch import AppleToggleSwitch
from ui.interactive_cockpit.button_roles import ROLE_DANGER, ROLE_LINK, ROLE_PRIMARY, set_button_role
from ui.interactive_cockpit.cockpit_theme import INFO_PANEL, SUCCESS_BANNER, WARNING_BANNER
from ui.interactive_cockpit.services.activity_audit_service import log_activity

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def add_trading_mode_panel(win: "InteractiveCockpitWindow", lay: QVBoxLayout, *, compact: bool = False) -> None:
    """Single toggle: off = manual, on = AI-assisted."""
    grp = QGroupBox("Handelsmodus")
    inner = QVBoxLayout(grp)

    from ui.invest_layout import body_label

    row = QHBoxLayout()
    lbl = body_label("KI-unterstütztes Trading")
    lbl.setMinimumHeight(40)
    row.addWidget(lbl, 1)
    switch = AppleToggleSwitch()
    switch.setAccessibleName("KI-unterstütztes Trading")
    switch.setAccessibleDescription("An = Rebalance/Orders an T212. Aus = App sendet nichts.")
    switch.toggled.connect(lambda on: _on_toggle(win, on))
    win._trading_mode_switch = switch
    row.addWidget(switch)
    row.addStretch()
    inner.addLayout(row)

    win._trading_mode_status = body_label("")
    inner.addWidget(win._trading_mode_status)

    if not compact:
        win._today_pick_label = body_label("")
        inner.addWidget(win._today_pick_label)

        win._today_pick_btn = QPushButton("Heute als Order öffnen")
        set_button_role(win._today_pick_btn, ROLE_PRIMARY)
        win._today_pick_btn.clicked.connect(lambda: _open_today_pick(win))
        inner.addWidget(win._today_pick_btn)

        win._trading_readiness_label = body_label("")
        inner.addWidget(win._trading_readiness_label)

        btn_row = QHBoxLayout()
        broker_btn = QPushButton("Broker")
        set_button_role(broker_btn, ROLE_LINK)
        broker_btn.clicked.connect(lambda: win._go_nav("t212"))
        sym_btn = QPushButton("Symbole")
        set_button_role(sym_btn, ROLE_LINK)
        sym_btn.clicked.connect(lambda: win._go_nav("live_setup"))
        order_btn = QPushButton("Orders")
        set_button_role(order_btn, ROLE_PRIMARY)
        order_btn.clicked.connect(lambda: win._go_nav("order_review"))
        btn_row.addWidget(broker_btn)
        btn_row.addWidget(sym_btn)
        btn_row.addWidget(order_btn)
        btn_row.addStretch()
        inner.addLayout(btn_row)

    lay.addWidget(grp)
    refresh_trading_mode_panel(win)


def add_trading_hub_to_overview(win: "InteractiveCockpitWindow", lay: QVBoxLayout) -> None:
    add_trading_mode_panel(win, lay, compact=False)


def add_trading_mode_status_only(win: "InteractiveCockpitWindow", lay: QVBoxLayout) -> None:
    """Read-only line + link (Risiko)."""
    row = QHBoxLayout()
    win._risk_mode_label = QLabel()
    win._risk_mode_label.setWordWrap(True)
    row.addWidget(win._risk_mode_label, stretch=1)
    go = QPushButton("Modus ändern")
    set_button_role(go, ROLE_LINK)
    go.clicked.connect(lambda: win._go_nav("overview"))
    row.addWidget(go)
    lay.addLayout(row)


def refresh_trading_mode_panel(win: "InteractiveCockpitWindow") -> None:
    if not hasattr(win, "_trading_mode_switch"):
        if hasattr(win, "_risk_mode_label"):
            mode = get_trading_mode(win.root)
            win._risk_mode_label.setText(
                f"Handelsmodus: {'KI-unterstützt' if mode == 'ai_assisted' else 'Manuell'}"
            )
        return

    mode = get_trading_mode(win.root)
    win._trading_mode_switch.blockSignals(True)
    win._trading_mode_switch.setChecked(mode == "ai_assisted")
    win._trading_mode_switch.blockSignals(False)

    from ui.invest_layout import set_banner

    if mode == "ai_assisted":
        win._trading_mode_status.setText("An — «Order ausführen» sendet direkt an T212.")
        set_banner(win._trading_mode_status, "ok")
    else:
        win._trading_mode_status.setText("Aus — die App sendet keine Orders.")
        set_banner(win._trading_mode_status, "info")

    if hasattr(win, "_today_pick_label"):
        from analytics.pilot_today_pick import load_today_pick

        pick = load_today_pick(win.root)
        sym = pick.get("symbol") or "—"
        eur = pick.get("target_eur")
        eur_txt = f"{eur:.0f} €" if isinstance(eur, (int, float)) else "—"
        win._today_pick_label.setText(
            f"<b>Heute ({pick.get('signal_date') or '—'})</b>: {sym} · ca. {eur_txt}\n"
            f"{pick.get('reason_de', '')}"
        )
        ready = get_trading_mode(win.root) == "ai_assisted"
        win._today_pick_btn.setEnabled(bool(pick.get("executable")) and ready)

    if hasattr(win, "_trading_readiness_label"):
        rd = trading_readiness(win.root)
        lines = [f"{'✓' if c['ok'] else '○'} {c['label']}" for c in rd.get("checks") or []]
        from ui.invest_layout import set_banner

        if rd.get("ready"):
            win._trading_readiness_label.setText("Bereit:\n" + "\n".join(lines))
            set_banner(win._trading_readiness_label, "ok")
        else:
            win._trading_readiness_label.setText("Offen:\n" + "\n".join(lines))
            set_banner(win._trading_readiness_label, "warn")

    if hasattr(win, "_risk_mode_label"):
        win._risk_mode_label.setText(
            f"Handelsmodus: {'KI-unterstützt' if mode == 'ai_assisted' else 'Manuell'}"
        )


def _on_toggle(win: "InteractiveCockpitWindow", ai_on: bool) -> None:
    target = "ai_assisted" if ai_on else "manual"
    if get_trading_mode(win.root) == target:
        return
    if ai_on:
        reply = QMessageBox.question(
            win,
            "KI-unterstützt",
            "Empfehlungen ja — Auto-Orders nein.\nJede Order nur nach Ihrem Klick.\n\nEinschalten?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            refresh_trading_mode_panel(win)
            return

    res = apply_trading_mode(win.root, target, changed_by="trading_mode_toggle")
    if not res.get("ok"):
        QMessageBox.warning(win, "Handelsmodus", str(res.get("message") or res.get("error") or res))
        refresh_trading_mode_panel(win)
        return

    log_activity(win.root, category="Sicherheit", action="Handelsmodus", result=target, status="ERFOLGREICH")
    refresh_trading_mode_panel(win)
    from ui.interactive_cockpit.order_workflow_ui import refresh_order_views

    refresh_order_views(win)
    win.refresh_state(full=False)


def _open_today_pick(win: "InteractiveCockpitWindow") -> None:
    from ui.interactive_cockpit.order_workflow_ui import open_today_pick_order

    open_today_pick_order(win)
