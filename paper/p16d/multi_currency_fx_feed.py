"""Read-only multi-currency FX feed — no static fallback on performance paths."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

PAPER_BASE = "EUR"
FX_PAIRS = {"USD": "EURUSD=X", "GBP": "GBPEUR=X"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _hash_record(record: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest()


def _fetch_pair(pair: str) -> tuple[Optional[float], str, str]:
    try:
        import yfinance as yf

        hist = yf.Ticker(pair).history(period="1d", interval="1m")
        if hist.empty:
            return None, "UNAVAILABLE", "empty_history"
        close = float(hist.iloc[-1]["Close"])
        if close <= 0:
            return None, "UNAVAILABLE", "non_positive"
        if pair == "EURUSD=X":
            return 1.0 / close, "READONLY_YFINANCE", ""
        if pair == "GBPEUR=X":
            return close, "READONLY_YFINANCE", ""
        return None, "UNAVAILABLE", "unknown_pair"
    except Exception as exc:
        return None, "UNAVAILABLE", str(exc)


def fetch_multi_currency_fx(root: Path) -> Dict[str, Any]:
    root = Path(root)
    ledger = root / "paper/p16d/fx_observation_ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    now = _utc_now()

    usd_rate, usd_src, usd_err = _fetch_pair(FX_PAIRS["USD"])
    gbp_rate, gbp_src, gbp_err = _fetch_pair(FX_PAIRS["GBP"])

    obs = {
        "paper_base_currency": PAPER_BASE,
        "usd_to_eur_rate": usd_rate,
        "gbp_to_eur_rate": gbp_rate,
        "fx_event_time_utc": now,
        "fx_ingestion_time_utc": now,
        "usd_fx_source": usd_src,
        "gbp_fx_source": gbp_src,
        "usd_fx_quality_gate": "PASS" if usd_rate else "FAIL",
        "gbp_fx_quality_gate": "PASS" if gbp_rate else "FAIL",
        "static_fallback_used": False,
        "usd_error": usd_err,
        "gbp_error": gbp_err,
    }
    obs["conversion_hash"] = _hash_record(obs)
    with (ledger / "fx_observations.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(obs) + "\n")
    return obs
