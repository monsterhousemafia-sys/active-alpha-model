"""Shared T212 cash + USD display for interactive cockpit views."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from integrations.trading212.t212_cash_display import (
    eur_amount_with_usd_suffix,
    fetch_display_fx,
    format_cash_display_html,
    format_cash_display_plain,
)
from ui.interactive_cockpit.cockpit_theme import INFO_PANEL, WARNING_BANNER


def broker_cash_breakdown(
    broker: Dict[str, Any],
    *,
    real_money: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    bd = dict(broker.get("cash_breakdown") or {})
    if real_money and real_money.get("total_value_eur") is not None:
        bd.setdefault("total_account_value_eur", real_money.get("total_value_eur"))
    return bd


def load_fx(root: Path) -> Dict[str, Any]:
    return fetch_display_fx(Path(root))


def cash_display_html(
    root: Path,
    broker: Dict[str, Any],
    *,
    real_money: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    fx = load_fx(root)
    html, footer = format_cash_display_html(
        cash_eur=broker.get("cash_eur"),
        cash_breakdown=broker_cash_breakdown(broker, real_money=real_money),
        fx=fx,
    )
    return html, footer, fx


def cash_display_plain(
    root: Path,
    broker: Dict[str, Any],
    *,
    real_money: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    fx = load_fx(root)
    body, footer = format_cash_display_plain(
        cash_eur=broker.get("cash_eur"),
        cash_breakdown=broker_cash_breakdown(broker, real_money=real_money),
        fx=fx,
    )
    return body, footer, fx


def apply_rich_cash_label(lbl: QLabel, html: str) -> None:
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setText(html)


def apply_fx_footer_label(lbl: QLabel, footer: str, *, fx_ok: bool) -> None:
    lbl.setText(footer)
    lbl.setStyleSheet(WARNING_BANNER if not fx_ok else INFO_PANEL)
    lbl.setWordWrap(True)


def amount_with_usd(
    eur: Any,
    fx: Dict[str, Any],
) -> str:
    rate = fx.get("usd_to_eur_rate") if fx.get("ok") else None
    return eur_amount_with_usd_suffix(eur, usd_to_eur_rate=rate)
