"""Unified pilot day-trading policy — single source for reeval, deferred, playbook."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

UNIFIED_REL = Path("control/pilot_day_trading.json")
_LEGACY = {
    "reevaluation": Path("control/pilot_portfolio_reevaluation.json"),
    "deferred": Path("control/us_equity_deferred_execution.json"),
    "playbook": Path("control/us_day_trading.json"),
}


def _default_unified() -> Dict[str, Any]:
    from analytics.pilot_portfolio_reevaluation import default_policy as reeval_defaults
    from analytics.live_trading_operations import default_policy as live_trading_defaults
    from execution.confirmed_live.us_day_trading_coordinator import default_policy as playbook_defaults
    from execution.confirmed_live.us_equity_deferred_intents import default_policy as deferred_defaults

    return {
        "schema_version": 1,
        "enabled": True,
        "live_trading": live_trading_defaults(),
        "walkforward_mirror": live_trading_defaults(),
        "refresh": {
            "quote_refresh_seconds_open": 60,
            "quote_refresh_seconds_preopen": 180,
            "quote_refresh_seconds_closed": 120,
            "full_refresh_minutes_open": 5,
            "full_refresh_minutes_open_early": 3,
            "full_refresh_minutes_closed": 30,
            "quote_fetch_timeout_open_s": 45,
            "quote_fetch_timeout_closed_s": 25,
        },
        "reevaluation": reeval_defaults(),
        "deferred": deferred_defaults(),
        "playbook": playbook_defaults(),
        "reliability": {
            "require_t212_live_in_plan": True,
            "require_pipeline_synced_for_execute": True,
            "min_buy_allocation_rows": 1,
            "max_single_buy_pct": 0.12,
            "fail_closed_missing_broker": True,
            "fail_closed_stale_plan": True,
        },
        "costs": {
            "schema_version": 1,
            "enabled": True,
            "us_equity_fx_fee_pct": 0.0015,
            "us_equity_reservation_buffer": 1.15,
            "show_fx_fee_in_playbook": True,
            "fx_bps": 15.0,
            "slippage_bps": 5.0,
            "min_trade_cost_multiple": 3.0,
            "min_trade_eur_floor": 12.0,
            "include_sell_regulatory_fees": True,
            "stress_fx_bps_add": 25.0,
            "stress_slippage_bps_add": 10.0,
            "require_stress_pass_for_trade": True,
        },
    }


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _load_legacy_sections(root: Path) -> Dict[str, Any]:
    root = Path(root)
    sections: Dict[str, Any] = {}
    for name, rel in _LEGACY.items():
        path = root / rel
        if path.is_file():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(doc, dict):
                    sections[name] = doc
            except (json.JSONDecodeError, OSError):
                pass
    return sections


def load_unified_policy(root: Path) -> Dict[str, Any]:
    root = Path(root)
    base = _default_unified()
    path = root / UNIFIED_REL
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return _deep_merge(base, doc)
        except (json.JSONDecodeError, OSError):
            pass
    legacy = _load_legacy_sections(root)
    if legacy:
        merged = _deep_merge(base, {"reevaluation": legacy.get("reevaluation", {}), "deferred": legacy.get("deferred", {}), "playbook": legacy.get("playbook", {})})
        if legacy.get("reevaluation"):
            merged["refresh"] = _deep_merge(
                merged.get("refresh") or {},
                {
                    "full_refresh_minutes_closed": legacy["reevaluation"].get("interval_minutes", 30),
                    "full_refresh_minutes_open": legacy["reevaluation"].get("interval_minutes_us_open", 5),
                },
            )
        return merged
    return base


def policy_section(root: Path, section: str) -> Dict[str, Any]:
    pol = load_unified_policy(root)
    defaults = _default_unified().get(section) or {}
    sec = pol.get(section) or {}
    if not isinstance(sec, dict):
        return dict(defaults)
    return _deep_merge(defaults if isinstance(defaults, dict) else {}, sec)


def save_unified_policy(root: Path, policy: Dict[str, Any]) -> Path:
    path = Path(root) / UNIFIED_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, policy)


def migrate_legacy_policies_to_unified(root: Path) -> Path:
    """One-time style merge of legacy JSON files into pilot_day_trading.json."""
    root = Path(root)
    path = root / UNIFIED_REL
    if path.is_file():
        return path
    pol = load_unified_policy(root)
    return save_unified_policy(root, pol)


def refresh_timing(root: Path) -> Dict[str, Any]:
    return policy_section(root, "refresh")


def effective_quote_refresh_seconds(root: Path) -> int:
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    ref = refresh_timing(root)
    sess = us_equity_regular_session_open_now()
    if sess.get("open"):
        detail = _session_detail_phase(sess)
        if detail == "OPEN_EARLY":
            return int(ref.get("quote_refresh_seconds_open") or 60)
        return int(ref.get("quote_refresh_seconds_open") or 60)
    if sess.get("phase") == "PREOPEN":
        return int(ref.get("quote_refresh_seconds_preopen") or 180)
    return int(ref.get("quote_refresh_seconds_closed") or 120)


def effective_full_refresh_ms(root: Path) -> int:
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    ref = refresh_timing(root)
    sess = us_equity_regular_session_open_now()
    if sess.get("open"):
        detail = _session_detail_phase(sess)
        if detail == "OPEN_EARLY":
            return int(ref.get("full_refresh_minutes_open_early") or 3) * 60 * 1000
        return int(ref.get("full_refresh_minutes_open") or 5) * 60 * 1000
    return int(ref.get("full_refresh_minutes_closed") or 30) * 60 * 1000


def _session_detail_phase(sess: Dict[str, Any]) -> str:
    from datetime import time
    from zoneinfo import ZoneInfo

    if not sess.get("open"):
        return str(sess.get("phase") or "CLOSED")
    ny = ZoneInfo("America/New_York")
    from datetime import datetime, timezone

    now_ny = datetime.now(timezone.utc).astimezone(ny)
    t = now_ny.time()
    start = time(9, 30)
    end = time(16, 0)
    open_m = start.hour * 60 + start.minute
    now_m = t.hour * 60 + t.minute
    close_m = end.hour * 60 + end.minute
    if now_m - open_m <= 45:
        return "OPEN_EARLY"
    if close_m - now_m <= 30:
        return "OPEN_LATE"
    return "OPEN_MID"
