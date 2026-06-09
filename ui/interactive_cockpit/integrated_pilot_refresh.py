"""Linked Live-Trading refresh merged into Marktanalyse cockpit state."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ui.interactive_cockpit.cockpit_theme import ERROR_BANNER, SUCCESS_BANNER, WARNING_BANNER

if TYPE_CHECKING:
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow


def apply_integrated_pilot_refresh(
    root,
    state: Dict[str, Any],
    *,
    force: bool = True,
    auto_enqueue: bool = False,
) -> Optional[str]:
    """Run Live-Trading refresh chain; merge into state. Returns error text or None (fail-soft)."""
    from pathlib import Path

    from aa_runtime_guards import truncate_error

    root = Path(root)
    try:
        from analytics.pilot_integrated_refresh import run_integrated_refresh
        from market.live_quote_engine import merge_snapshot_into_state

        result = run_integrated_refresh(root, force=force, auto_enqueue=auto_enqueue)
        patch = result.as_state_patch()
        state.update(patch)
        mp = patch.get("market_prices")
        if isinstance(mp, dict) and mp:
            merge_snapshot_into_state(state, mp)
        state["pilot_integrated_refresh_ok"] = True
        state.pop("pilot_integrated_refresh_error", None)
        return None
    except Exception as exc:
        err = truncate_error(exc)
        state["pilot_integrated_refresh_ok"] = False
        state["pilot_integrated_refresh_error"] = err
        prev = state.get("refresh_error")
        state["refresh_error"] = f"{prev}; Live-Refresh: {err}" if prev else f"Live-Refresh: {err}"
        return err


def trade_gate_summary(state: Dict[str, Any]) -> tuple[str, str, str]:
    """Handeln heute? — (value, subtitle, severity ok|warn|fail)."""
    doc = state.get("refresh_status") or {}
    for row in doc.get("rows") or []:
        if row.get("key") == "trade_gate":
            st = str(row.get("status") or "FAIL")
            val = str(row.get("value_de") or "—")
            det = str(row.get("detail_de") or doc.get("summary_de") or "")[:120]
            sev = "ok" if st == "OK" else ("warn" if st == "WARN" else "fail")
            return val, det, sev
    err = state.get("pilot_integrated_refresh_error")
    if err:
        return "Nein", f"Live-Refresh fehlgeschlagen: {err[:100]}", "fail"
    if not doc:
        return "—", "Vollständig aktualisieren (F5)", "warn"
    return "—", str(doc.get("summary_de") or "Refresh ausstehend"), "warn"


def attach_live_prufstand_overview(win: "InteractiveCockpitWindow", layout: QVBoxLayout) -> None:
    grp = QGroupBox("Live-Prüfstand (verknüpfter Refresh)")
    lay = QVBoxLayout(grp)
    win._trade_today_banner = QLabel()
    win._trade_today_banner.setWordWrap(True)
    lay.addWidget(win._trade_today_banner)
    win._refresh_headline = QLabel()
    win._refresh_headline.setWordWrap(True)
    lay.addWidget(win._refresh_headline)
    win._refresh_checks = QTableWidget(0, 4)
    win._refresh_checks.setHorizontalHeaderLabels(["Prüfung", "Stand", "Status", "Details"])
    win._refresh_checks.setAlternatingRowColors(True)
    lay.addWidget(win._refresh_checks)
    win._pilot_plan_line = QLabel()
    win._pilot_plan_line.setWordWrap(True)
    lay.addWidget(win._pilot_plan_line)
    layout.addWidget(grp)


def render_live_prufstand(win: "InteractiveCockpitWindow") -> None:
    if not hasattr(win, "_refresh_checks"):
        return
    state = win.state or {}
    val, sub, sev = trade_gate_summary(state)
    if sev == "ok":
        win._trade_today_banner.setStyleSheet(SUCCESS_BANNER)
        win._trade_today_banner.setText(f"<b>Handeln heute?</b> {val} — {sub}")
    elif sev == "warn":
        win._trade_today_banner.setStyleSheet(WARNING_BANNER)
        win._trade_today_banner.setText(f"<b>Handeln heute?</b> {val} — {sub}")
    else:
        win._trade_today_banner.setStyleSheet(ERROR_BANNER)
        win._trade_today_banner.setText(f"<b>Handeln heute?</b> {val} — {sub}")

    doc = state.get("refresh_status") or {}
    rows = list(doc.get("rows") or [])
    win._refresh_checks.setRowCount(len(rows))
    for r, row in enumerate(rows):
        win._refresh_checks.setItem(r, 0, QTableWidgetItem(str(row.get("label_de", ""))))
        win._refresh_checks.setItem(r, 1, QTableWidgetItem(str(row.get("value_de", ""))))
        win._refresh_checks.setItem(r, 2, QTableWidgetItem(str(row.get("status") or "—")))
        win._refresh_checks.setItem(r, 3, QTableWidgetItem(str(row.get("detail_de", ""))[:120]))
    ts = str(doc.get("generated_at_utc") or "")[:19].replace("T", " ")
    summary = str(doc.get("summary_de") or "—")
    win._refresh_headline.setText(f"Letzter verknüpfter Refresh: {ts} UTC — {summary}")
    if doc.get("all_ok"):
        win._refresh_headline.setStyleSheet(SUCCESS_BANNER)
    elif any(x.get("status") == "FAIL" for x in rows):
        win._refresh_headline.setStyleSheet(ERROR_BANNER)
    else:
        win._refresh_headline.setStyleSheet(WARNING_BANNER)

    guard = state.get("champion_guard") or {}
    plan = state.get("investment_plan") or {}
    primary = plan.get("primary_action") or {}
    cr = state.get("cost_risk") or plan.get("cost_risk") or {}
    sym = str(primary.get("symbol") or "—")
    lines = [
        f"Champion: {guard.get('status_de', '—')[:80]}",
        f"Primär-Pick: {sym} · Ziel {float(primary.get('target_eur') or 0):.2f} €",
    ]
    if cr:
        lines.append(
            f"Gebühren: Basis ~{cr.get('base_round_trip_eur', 0):.2f} € · "
            f"Stress ~{cr.get('stress_round_trip_eur', 0):.2f} € · "
            f"{'Handel OK' if cr.get('trade_allowed') else 'Blockiert'}"
        )
    win._pilot_plan_line.setText("\n".join(lines))


def attach_pilot_reeval_market(win: "InteractiveCockpitWindow", layout: QVBoxLayout) -> None:
    layout.addWidget(QLabel("<b>Portfolio-Abgleich (Modell + Gebühren + Live)</b>"))
    win._pilot_reeval_summary = QLabel()
    win._pilot_reeval_summary.setWordWrap(True)
    layout.addWidget(win._pilot_reeval_summary)
    win._pilot_reeval_table = QTableWidget(0, 8)
    win._pilot_reeval_table.setHorizontalHeaderLabels(
        [
            "Symbol",
            "Ist €",
            "Soll €",
            "Gap €",
            "Empfehlung",
            "Gebühren",
            "Modell",
            "Live €",
        ]
    )
    layout.addWidget(win._pilot_reeval_table)


def render_pilot_reeval_market(win: "InteractiveCockpitWindow") -> None:
    if not hasattr(win, "_pilot_reeval_table"):
        return
    report = (win.state or {}).get("portfolio_reevaluation") or {}
    win._pilot_reeval_summary.setText(str(report.get("summary_de") or "—"))
    rows = list(report.get("recommended_actions") or report.get("rows") or [])[:12]
    win._pilot_reeval_table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        win._pilot_reeval_table.setItem(r, 0, QTableWidgetItem(str(row.get("symbol", ""))))
        win._pilot_reeval_table.setItem(r, 1, QTableWidgetItem(f"{row.get('current_eur', 0):.2f}"))
        win._pilot_reeval_table.setItem(r, 2, QTableWidgetItem(f"{row.get('target_eur', 0):.2f}"))
        win._pilot_reeval_table.setItem(r, 3, QTableWidgetItem(f"{float(row.get('gap_eur') or 0):+.2f}"))
        win._pilot_reeval_table.setItem(r, 4, QTableWidgetItem(str(row.get("action_de", ""))))
        win._pilot_reeval_table.setItem(r, 5, QTableWidgetItem(str(row.get("fee_note_de") or "—")))
        win._pilot_reeval_table.setItem(r, 6, QTableWidgetItem(str(row.get("pick_rationale_de") or "—")))
        lp = row.get("live_price_eur")
        win._pilot_reeval_table.setItem(
            r, 7, QTableWidgetItem(f"{float(lp):.2f}" if lp is not None else "—")
        )


def render_last_order_preflight(win: "InteractiveCockpitWindow") -> None:
    if not hasattr(win, "_last_preflight_label"):
        return
    pf = (win.state or {}).get("last_order_preflight") or {}
    if not pf:
        win._last_preflight_label.setText("Letzte Live-Order-Prüfung: noch keine in dieser Sitzung.")
        win._last_preflight_label.setStyleSheet("")
        return
    ok = bool(pf.get("ok"))
    sym = pf.get("symbol", "—")
    blocks = pf.get("blocks") or []
    if ok:
        win._last_preflight_label.setStyleSheet(SUCCESS_BANNER)
        win._last_preflight_label.setText(
            f"Letzte Live-Order-Prüfung: OK für {sym} · Limit {pf.get('limit_price_eur', '—')} €"
        )
    else:
        win._last_preflight_label.setStyleSheet(ERROR_BANNER)
        reason = blocks[0].get("message_de", "Blockiert") if blocks else "Blockiert"
        win._last_preflight_label.setText(f"Letzte Live-Order-Prüfung: BLOCKIERT ({sym}) — {reason[:120]}")


def extend_order_review_preflight_line(win: "InteractiveCockpitWindow", layout: QVBoxLayout) -> None:
    win._last_preflight_label = QLabel()
    win._last_preflight_label.setWordWrap(True)
    layout.insertWidget(2, win._last_preflight_label)
