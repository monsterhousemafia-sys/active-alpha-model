"""Spendable EUR for order sizing — availableToTrade minus pending buy holds."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def planning_cash_from_breakdown(broker: Mapping[str, Any] | None) -> Optional[float]:
    """Prefer explicit available_to_trade from T212 cash breakdown."""
    if not broker:
        return None
    bd = broker.get("cash_breakdown")
    if isinstance(bd, dict):
        for key in ("planning_cash_eur", "available_to_trade_eur"):
            val = bd.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
    cash = broker.get("cash_eur")
    if cash is not None:
        try:
            return float(cash)
        except (TypeError, ValueError):
            return None
    return None


def estimate_pending_buy_hold_eur(root: Path) -> float:
    """Sum notional of open BUY orders from T212 (reduces wave sizing)."""
    try:
        from integrations.trading212.t212_pending_orders import pending_buy_reservation_eur

        return float(pending_buy_reservation_eur(root))
    except Exception:
        return 0.0


def resolve_planning_cash_eur(
    cash_eur: float | None,
    *,
    broker: Mapping[str, Any] | None = None,
    root: Path | None = None,
    subtract_pending_orders: bool = True,
) -> float | None:
    """
    Cash usable for new buy sizing.
    Uses availableToTrade only; optionally subtracts pending API buy reservations.
    """
    base = planning_cash_from_breakdown(broker) if broker else None
    if base is None and cash_eur is not None:
        try:
            base = float(cash_eur)
        except (TypeError, ValueError):
            base = None
    if base is None:
        return None
    hold = estimate_pending_buy_hold_eur(root) if (subtract_pending_orders and root is not None) else 0.0
    return max(0.0, round(float(base) - float(hold), 2))
