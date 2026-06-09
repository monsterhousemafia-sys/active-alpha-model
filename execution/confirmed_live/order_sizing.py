"""Conservative limit-order sizing from free cash (T212 reservation-aware)."""
from __future__ import annotations

from pathlib import Path

from execution.confirmed_live.confirmed_execution_mode_controller import CORE_LIVE_MIN_RESERVE_EUR

from integrations.trading212.t212_limit_order_constraints import (
    T212_MAX_CASH_UTILIZATION,
    US_EQUITY_RESERVATION_BUFFER,
)

# T212 may reserve quantity × limitPrice (+ FX buffer for US equities).
T212_RESERVATION_BUFFER = US_EQUITY_RESERVATION_BUFFER
MIN_BUY_QUANTITY = 0.01
MAX_AUTO_SCALE_ATTEMPTS = 3
# Market fills can slip above reference limit used for sizing (T212 docs).
MARKET_ORDER_SLIPPAGE_BUFFER = 1.0


def is_rate_limit_error(message: str | None) -> bool:
    from integrations.trading212.t212_sync_throttle import is_rate_limit_error as _rl

    return _rl(str(message or ""))


def is_insufficient_funds_error(message: str | None) -> bool:
    from integrations.trading212.t212_order_error_parser import parse_t212_order_error

    return parse_t212_order_error(str(message or "")).category == "insufficient"


def is_min_quantity_error(message: str | None) -> bool:
    from integrations.trading212.t212_order_error_parser import is_min_quantity_error as _min

    return _min(str(message or ""))


def size_buy_quantity(
    *,
    target_notional_eur: float,
    limit_price_eur: float,
    free_cash_eur: float | None,
    min_reserve_eur: float = CORE_LIVE_MIN_RESERVE_EUR,
    reservation_buffer: float = T212_RESERVATION_BUFFER,
    root: Path | None = None,
    execution_style: str = "limit",
) -> tuple[float, str | None]:
    """
    Return (quantity, warning). Quantity is capped by affordable notional (2 dp).
    """
    if limit_price_eur <= 0:
        return 0.0, "INVALID_LIMIT_PRICE"
    slip = MARKET_ORDER_SLIPPAGE_BUFFER if str(execution_style).lower() == "market" else 1.0
    target_qty = round((target_notional_eur / limit_price_eur) / slip, 2)

    if free_cash_eur is None:
        qty = max(MIN_BUY_QUANTITY, target_qty)
        return qty, "CASH_NOT_VERIFIED_SIZING_UNCAPPED"

    spendable = max(0.0, float(free_cash_eur) - float(min_reserve_eur)) * T212_MAX_CASH_UTILIZATION
    if root is not None:
        from integrations.trading212.t212_us_cost_model import (
            effective_cost_per_share,
            load_t212_cost_policy,
        )

        cost_per_share = effective_cost_per_share(
            limit_price_eur, load_t212_cost_policy(Path(root))
        )
    else:
        cost_per_share = limit_price_eur * float(reservation_buffer) * slip
    if cost_per_share <= 0:
        return 0.0, "INVALID_LIMIT_PRICE"
    max_qty = round(spendable / cost_per_share, 2)
    qty = min(target_qty, max_qty)
    qty = max(0.0, qty)
    warning = None
    if qty < target_qty - 1e-6:
        warning = "ORDER_SIZE_REDUCED_TO_AVAILABLE_CASH"
    if qty < MIN_BUY_QUANTITY:
        return 0.0, "INSUFFICIENT_FREE_CASH"
    if qty * cost_per_share > spendable + 0.02:
        return 0.0, "INSUFFICIENT_FREE_CASH"
    return qty, warning


def plan_executable_buy_order(
    *,
    target_notional_eur: float,
    limit_price_eur: float,
    free_cash_eur: float | None,
    root: Path | None = None,
    execution_style: str = "limit",
) -> dict:
    """Plan quantity/notional scaled to what T212 can likely accept."""
    limit = round(float(limit_price_eur), 2)
    target = round(float(target_notional_eur), 2)
    target_qty = round(target / limit, 2) if limit > 0 else 0.0
    qty, warn = size_buy_quantity(
        target_notional_eur=target,
        limit_price_eur=limit,
        free_cash_eur=free_cash_eur,
        root=root,
        execution_style=execution_style,
    )
    executable = round(qty * limit, 2)
    from integrations.trading212.t212_us_cost_model import (
        estimate_buy_cost_breakdown,
        load_t212_cost_policy,
    )

    cost_policy = load_t212_cost_policy(Path(root) if root else None)
    costs = estimate_buy_cost_breakdown(
        notional_eur=executable if executable > 0 else target,
        limit_price_eur=limit,
        quantity=qty,
        policy=cost_policy,
    )
    return {
        "quantity": qty,
        "limit_price_eur": limit,
        "target_notional_eur": target,
        "target_quantity": target_qty,
        "executable_notional_eur": executable,
        "scaled_down": bool(warn) or (target_qty > 0 and qty < target_qty - 1e-6),
        "warning": warn,
        "t212_cost_estimate": costs,
    }


def shrink_quantity_for_retry(quantity: float, *, attempt: int) -> float:
    """Reduce size after broker rejected insufficient funds (from last attempted qty)."""
    q = float(quantity)
    if attempt <= 0:
        return round(max(MIN_BUY_QUANTITY, q), 4)
    factor = 0.75 ** attempt
    return round(max(MIN_BUY_QUANTITY, q * factor), 4)
