"""Cache coherence rules: calendar freshness + TTL + downstream invalidation."""
from __future__ import annotations

from datetime import date
from typing import Dict, Mapping, Optional

from aa_data_freshness import is_market_data_current, is_signal_current, last_expected_market_date


def price_cache_operational(
    latest: Optional[date],
    *,
    meta_fresh: bool,
    reference: Optional[date] = None,
) -> bool:
    """Price cache is usable when the calendar date is current and TTL meta is valid."""
    ref = reference or last_expected_market_date()
    if latest is None:
        return False
    return bool(is_market_data_current(latest, reference=ref) and meta_fresh)


def apply_price_refresh_env(env: Mapping[str, str], *, prices_refreshed: bool) -> Dict[str, str]:
    """After a price-panel refresh, invalidate dependent caches for this run."""
    out = dict(env)
    if prices_refreshed:
        out["AA_SKIP_DOWNLOAD_IF_CACHED"] = "1"
        out["AA_FORCE_REBUILD_FEATURES"] = "1"
        out["AA_FORCE_REBUILD_PREDICTIONS"] = "1"
    return out


def apply_stale_price_env(env: Mapping[str, str], *, price_current: bool) -> Dict[str, str]:
    out = dict(env)
    if not price_current:
        out["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"
    return out
