"""Pro-rata cash wave planner — scale BUY notionals before sequential T212 submission."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Mapping, Optional

DEFAULT_MIN_ORDER_EUR = 5.0


def _side(row: Mapping[str, Any]) -> str:
    return str(row.get("side") or "BUY").upper()


def _buy_notional(row: Mapping[str, Any]) -> float:
    for key in ("scaled_notional_eur", "notional_eur", "target_eur", "gap_eur"):
        val = row.get(key)
        if val is not None:
            try:
                return max(0.0, float(val))
            except (TypeError, ValueError):
                pass
    return 0.0


def plan_rebalance_wave(
    orders: List[Dict[str, Any]],
    planning_cash_eur: float | None,
    *,
    min_order_eur: float = DEFAULT_MIN_ORDER_EUR,
) -> Dict[str, Any]:
    """
    Scale BUY orders so sum(notional) <= planning_cash_eur.

    Sells are unchanged. Orders below min_order_eur after scaling are dropped.
    Each surviving BUY gets original_notional_eur, scaled_notional_eur, notional_eur (execution).
    """
    min_eur = max(0.0, float(min_order_eur))
    cash = max(0.0, float(planning_cash_eur or 0))

    sells: List[Dict[str, Any]] = []
    buys: List[Dict[str, Any]] = []
    for row in orders or []:
        item = deepcopy(row) if isinstance(row, dict) else {}
        if _side(item) == "SELL":
            sells.append(item)
        else:
            buys.append(item)

    raw_total = round(sum(_buy_notional(b) for b in buys), 2)
    if raw_total <= 0 or cash <= 0:
        factor = 0.0 if raw_total > 0 and cash <= 0 else 1.0
    else:
        factor = min(1.0, cash / raw_total)

    scaled_buys: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for row in buys:
        orig = round(_buy_notional(row), 2)
        scaled = round(orig * factor, 2)
        out = deepcopy(row)
        out["original_notional_eur"] = orig
        out["wave_scale_factor"] = round(factor, 6)
        if scaled < min_eur:
            dropped.append({"symbol": out.get("symbol"), "original_notional_eur": orig, "scaled_notional_eur": scaled})
            continue
        out["scaled_notional_eur"] = scaled
        out["notional_eur"] = scaled
        if out.get("target_eur") is not None:
            out["target_eur"] = scaled
        scaled_buys.append(out)

    scaled_total = round(sum(_buy_notional(b) for b in scaled_buys), 2)
    return {
        "orders": sells + scaled_buys,
        "scale_factor": round(factor, 6),
        "planning_cash_eur": round(cash, 2),
        "total_buy_notional_raw": raw_total,
        "total_buy_notional_scaled": scaled_total,
        "buy_count_raw": len(buys),
        "buy_count_scaled": len(scaled_buys),
        "dropped_below_min": dropped,
        "min_order_eur": min_eur,
    }


def plan_allocation_wave(
    allocations: List[Dict[str, Any]],
    planning_cash_eur: float | None,
    *,
    min_order_eur: float = DEFAULT_MIN_ORDER_EUR,
) -> Dict[str, Any]:
    """Scale champion batch allocations (target_eur) to planning cash."""
    orders = [
        {
            "symbol": str(r.get("symbol") or "").upper(),
            "side": "BUY",
            "notional_eur": float(r.get("target_eur") or 0),
            "target_eur": float(r.get("target_eur") or 0),
        }
        for r in allocations or []
        if str(r.get("symbol") or "").strip()
    ]
    wave = plan_rebalance_wave(orders, planning_cash_eur, min_order_eur=min_order_eur)
    by_sym = {str(o.get("symbol") or "").upper(): o for o in wave["orders"] if _side(o) == "BUY"}
    scaled_rows: List[Dict[str, Any]] = []
    for row in allocations or []:
        sym = str(row.get("symbol") or "").upper()
        if sym in by_sym:
            merged = deepcopy(row)
            src = by_sym[sym]
            merged["target_eur"] = src.get("scaled_notional_eur", src.get("notional_eur"))
            merged["original_target_eur"] = src.get("original_notional_eur")
            merged["wave_scale_factor"] = src.get("wave_scale_factor")
            scaled_rows.append(merged)
    wave["allocations"] = scaled_rows
    return wave


def wave_summary_de(wave: Mapping[str, Any]) -> str:
    factor = float(wave.get("scale_factor") or 1.0)
    cash = wave.get("planning_cash_eur")
    raw = wave.get("total_buy_notional_raw")
    scaled = wave.get("total_buy_notional_scaled")
    dropped = wave.get("dropped_below_min") or []
    parts = [
        f"Wellen-Cash {cash} €",
        f"Käufe {raw} € → {scaled} € (Faktor {factor:.2%})",
    ]
    if dropped:
        parts.append(f"{len(dropped)} unter Mindest-Order gestrichen")
    return " · ".join(parts)
