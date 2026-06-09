"""Policy-backed limit vs market execution for confirmed live orders."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def resolve_order_execution_style(root: Path) -> str:
    """Return ``limit`` or ``market`` from live-trading policy."""
    from analytics.live_trading_operations import load_policy

    raw = str(load_policy(root).get("order_execution_type") or "limit").strip().lower()
    if raw in ("market", "market_order", "mkt"):
        return "market"
    return "limit"


def set_order_execution_style(root: Path, style: str) -> Dict[str, Any]:
    """Persist order execution type in unified pilot policy."""
    from analytics.pilot_day_trading_policy import load_unified_policy, save_unified_policy

    root = Path(root)
    normalized = (
        "market"
        if str(style).strip().lower() in ("market", "market_order", "mkt")
        else "limit"
    )
    pol = load_unified_policy(root)
    for key in ("live_trading", "walkforward_mirror"):
        sec = dict(pol.get(key) or {})
        sec["order_execution_type"] = normalized
        pol[key] = sec
    save_unified_policy(root, pol)
    return {"ok": True, "order_execution_type": normalized}


def execution_style_label_de(style: str) -> str:
    return "Market-Order" if str(style).lower() == "market" else "Limit-Order"
