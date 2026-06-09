"""Parse Trading 212 cash — only availableToTrade is spendable/plannable."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class T212CashBreakdown:
    """Mirrors T212 account summary cash fields (EUR primary account)."""

    available_to_trade_eur: Optional[float]
    reserved_for_orders_eur: Optional[float]
    in_pies_eur: Optional[float]
    total_account_value_eur: Optional[float]
    invested_current_value_eur: Optional[float]
    currency: str
    source: str

    @property
    def planning_cash_eur(self) -> Optional[float]:
        """Cash that may be used for new orders and model allocation."""
        return self.available_to_trade_eur

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["planning_cash_eur"] = self.planning_cash_eur
        return d


def _as_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def parse_cash_breakdown(
    cash_payload: Any = None,
    *,
    account_summary: Any = None,
) -> T212CashBreakdown:
    """
    Extract T212 cash metrics. Planning uses only ``availableToTrade``.

    Never uses ``totalValue``, generic ``cash``, or ``total`` as spendable funds.
    """
    currency = "EUR"
    available: Optional[float] = None
    reserved: Optional[float] = None
    in_pies: Optional[float] = None
    total_value: Optional[float] = None
    invested: Optional[float] = None
    source = "UNAVAILABLE"

    if isinstance(account_summary, dict):
        currency = str(account_summary.get("currency") or currency)
        total_value = _as_float(account_summary.get("totalValue"))
        inv = account_summary.get("investments")
        if isinstance(inv, dict):
            invested = _as_float(inv.get("currentValue"))
        nested = account_summary.get("cash")
        if isinstance(nested, dict):
            available = _as_float(nested.get("availableToTrade"))
            reserved = _as_float(nested.get("reservedForOrders"))
            in_pies = _as_float(nested.get("inPies"))
            if available is not None:
                source = "account_summary.cash.availableToTrade"

    if available is None and isinstance(cash_payload, dict):
        for key in ("availableToTrade", "free", "available"):
            val = _as_float(cash_payload.get(key))
            if val is not None:
                available = val
                source = f"account_cash.{key}"
                break
        if reserved is None:
            reserved = _as_float(cash_payload.get("reservedForOrders"))
        if in_pies is None:
            in_pies = _as_float(cash_payload.get("inPies"))

    return T212CashBreakdown(
        available_to_trade_eur=available,
        reserved_for_orders_eur=reserved,
        in_pies_eur=in_pies,
        total_account_value_eur=total_value,
        invested_current_value_eur=invested,
        currency=currency,
        source=source,
    )


def extract_free_cash_eur(
    cash_payload: Any = None,
    *,
    account_summary: Any = None,
) -> Optional[float]:
    """Spendable cash for orders/plan — equals T212 availableToTrade."""
    return parse_cash_breakdown(cash_payload, account_summary=account_summary).planning_cash_eur


def verify_cash_eur_matches_summary(
    cash_eur: Optional[float],
    account_summary: Any,
    *,
    tolerance: float = 0.02,
) -> Dict[str, Any]:
    """Check stored cash_eur equals availableToTrade from summary."""
    breakdown = parse_cash_breakdown(account_summary=account_summary)
    expected = breakdown.available_to_trade_eur
    ok = (
        cash_eur is not None
        and expected is not None
        and abs(float(cash_eur) - float(expected)) <= tolerance
    )
    return {
        "ok": ok,
        "cash_eur": cash_eur,
        "available_to_trade_eur": expected,
        "source": breakdown.source,
        "total_account_value_eur": breakdown.total_account_value_eur,
        "reserved_for_orders_eur": breakdown.reserved_for_orders_eur,
        "in_pies_eur": breakdown.in_pies_eur,
    }
