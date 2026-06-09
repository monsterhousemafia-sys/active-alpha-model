"""Real-money authority — only Trading 212 booked balances for Live-Trading UI."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def real_money_authority_active(broker: Optional[Dict[str, Any]]) -> bool:
    b = broker or {}
    return bool(b.get("credentials_configured")) and str(b.get("status", "")).startswith(
        ("LIVE_READONLY", "DEMO_READONLY", "CONNECTED_READONLY")
    )


def _position_market_value_eur(pos: Dict[str, Any]) -> float:
    wi = pos.get("walletImpact")
    if isinstance(wi, dict) and wi.get("currentValue") is not None:
        try:
            return float(wi["currentValue"])
        except (TypeError, ValueError):
            pass
    for key in ("currentValue", "marketValue", "value"):
        if pos.get(key) is not None:
            try:
                return float(pos[key])
            except (TypeError, ValueError):
                pass
    qty = pos.get("quantity")
    price = pos.get("currentPrice")
    try:
        if qty is not None and price is not None:
            return float(qty) * float(price)
    except (TypeError, ValueError):
        pass
    return 0.0


def t212_booked_totals(broker: Dict[str, Any]) -> Dict[str, Any]:
    """Extract officially synced T212 account figures (EUR where available)."""
    summary = broker.get("account_summary") if isinstance(broker.get("account_summary"), dict) else {}
    cash_block = summary.get("cash") if isinstance(summary.get("cash"), dict) else {}
    inv_block = summary.get("investments") if isinstance(summary.get("investments"), dict) else {}

    cash = broker.get("cash_eur")
    if cash is None and cash_block.get("availableToTrade") is not None:
        try:
            cash = float(cash_block["availableToTrade"])
        except (TypeError, ValueError):
            cash = None

    positions: List[Any] = broker.get("positions") or []
    invested = 0.0
    for pos in positions:
        if isinstance(pos, dict):
            invested += _position_market_value_eur(pos)

    total_value = summary.get("totalValue")
    try:
        total_value = float(total_value) if total_value is not None else None
    except (TypeError, ValueError):
        total_value = None
    if total_value is None and cash is not None:
        total_value = round(float(cash) + invested, 4)

    realized_pnl = inv_block.get("realizedProfitLoss")
    unrealized_pnl = inv_block.get("unrealizedProfitLoss")
    try:
        realized_pnl = float(realized_pnl) if realized_pnl is not None else None
    except (TypeError, ValueError):
        realized_pnl = None
    try:
        unrealized_pnl = float(unrealized_pnl) if unrealized_pnl is not None else None
    except (TypeError, ValueError):
        unrealized_pnl = None

    return {
        "authority": "trading212_readonly_sync",
        "cash_eur": cash,
        "invested_eur": round(invested, 4),
        "total_value_eur": total_value,
        "realized_pnl_eur": realized_pnl,
        "unrealized_pnl_eur": unrealized_pnl,
        "positions_count": int(broker.get("positions_count") or len(positions)),
        "last_sync_utc": broker.get("last_successful_sync_utc"),
        "currency": summary.get("currency") or "EUR",
    }


def apply_real_money_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Attach real-money block; hide virtual paper from Live-Trading-facing state."""
    broker = state.get("broker") or {}
    if real_money_authority_active(broker):
        booked = t212_booked_totals(broker)
        state["real_money"] = {**booked, "real_money_only": True}
        state["paper"] = {
            "display_suppressed": True,
            "reason": "Nur Trading-212-Buchungen — kein virtuelles Paper-Cash im Live-Trading.",
        }
        cash = dict(state.get("cash") or {})
        if booked.get("cash_eur") is not None:
            cash["readonly_observed_real_broker_available_cash_eur"] = booked["cash_eur"]
            cash["readonly_broker_cash_verified"] = True
        if booked.get("invested_eur") is not None:
            cash["readonly_reconciled_real_invested_eur"] = booked["invested_eur"]
        cash["real_money_only"] = True
        state["cash"] = cash
    else:
        state["real_money"] = {"real_money_only": False, "authority": None}
    return state
