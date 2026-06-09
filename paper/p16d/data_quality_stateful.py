"""Full stateful data quality with stale, duplicate, timestamp validation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

STALE_MAX_AGE_S = 86400
OUTLIER_THRESHOLD = 0.25


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _hash_obj(obj: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def load_dq_state(root: Path) -> Dict[str, Any]:
    path = root / "paper/p16d/data_quality_state.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    p16c = root / "paper/p16c/data_quality_state.json"
    if p16c.is_file():
        state = json.loads(p16c.read_text(encoding="utf-8"))
        state["inherited_from_p16c"] = True
        state["baseline_batch_count"] = int(state.get("batch_count", 1))
        return state
    return {
        "batch_count": 0,
        "post_baseline_batch_count": 0,
        "last_valid_price": {},
        "last_valid_observation_hash": {},
        "last_batch_fingerprint": None,
        "baseline_classified": False,
    }


def save_dq_state(root: Path, state: Dict[str, Any]) -> None:
    atomic_write_json(root / "paper/p16d/data_quality_state.json", state)


def assess_observation(
    *,
    symbol: str,
    raw_price: Optional[float],
    quote_currency: str,
    event_time_utc: str,
    ingestion_time_utc: str,
    dq_state: Dict[str, Any],
    fx_available: bool,
    identity_action: str,
    batch_fingerprint: str,
) -> Dict[str, Any]:
    post_baseline = int(dq_state.get("post_baseline_batch_count", 0))
    is_baseline = post_baseline == 0 and not dq_state.get("p16d_hardening_complete")

    result: Dict[str, Any] = {
        "symbol": symbol,
        "event_time_utc": event_time_utc,
        "ingestion_time_utc": ingestion_time_utc,
        "timestamp_order_valid": _parse(event_time_utc) <= _parse(ingestion_time_utc),
    }

    if raw_price is None or raw_price <= 0:
        result.update({"gate": "FAIL_RUNTIME_PAUSED", "virtual_fill_permitted": False, "mtm_permitted": False})
        return result

    age_s = (_parse(ingestion_time_utc) - _parse(event_time_utc)).total_seconds()
    stale = age_s > STALE_MAX_AGE_S
    prev_hash = dq_state.get("last_valid_observation_hash", {}).get(symbol)
    norm = {"symbol": symbol, "raw_price": raw_price, "quote_currency": quote_currency}
    norm_hash = _hash_obj(norm)
    duplicate_obs = prev_hash == norm_hash

    prev_price = dq_state.get("last_valid_price", {}).get(symbol)
    if is_baseline:
        outlier = "INITIAL_CORRECTED_BASELINE_BATCH_NOT_INDEPENDENT_PERFORMANCE_EVENT"
    elif prev_price and prev_price > 0:
        move = abs(raw_price - prev_price) / prev_price
        outlier = "OUTLIER" if move > OUTLIER_THRESHOLD else "OK"
    else:
        outlier = "NO_PRIOR_BASELINE"

    if not result["timestamp_order_valid"] or stale:
        gate = "FAIL_RUNTIME_PAUSED"
    elif duplicate_obs and dq_state.get("last_batch_fingerprint") == batch_fingerprint:
        gate = "PASS_FOR_OBSERVATION_NOT_PERFORMANCE"
    elif outlier == "OUTLIER":
        gate = "PARTIAL_AFFECTED_INSTRUMENTS_PAUSED"
    elif not fx_available and quote_currency.upper() != "EUR":
        gate = "PARTIAL_AFFECTED_INSTRUMENTS_PAUSED"
    elif identity_action.startswith("OBSERVATION") or identity_action.startswith("EXCLUDED"):
        gate = "PASS_FOR_OBSERVATION_NOT_PERFORMANCE"
    elif identity_action == "VIRTUAL_FILL_VALID" and fx_available:
        gate = "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE"
    elif fx_available:
        gate = "PASS_FOR_MTM_NOT_TRADE"
    else:
        gate = "PARTIAL_AFFECTED_INSTRUMENTS_PAUSED"

    result.update(
        {
            "gate": gate,
            "stale": stale,
            "duplicate_observation": duplicate_obs,
            "outlier_status": outlier,
            "raw_payload_hash": _hash_obj({"raw": raw_price}),
            "normalized_observation_hash": norm_hash,
            "virtual_fill_permitted": gate == "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE",
            "mtm_permitted": gate.startswith("PASS"),
            "performance_valid": gate == "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE" and not is_baseline,
        }
    )
    return result
