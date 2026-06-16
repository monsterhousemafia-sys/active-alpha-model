"""Post-baseline forward batch with multi-currency and full DQ."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json
from paper.p16d.data_quality_stateful import assess_observation, load_dq_state, save_dq_state
from paper.p16d.fx_runtime_guard import FX_PASS, classify_fx_observation, fx_available_for_currency
from paper.p16d.instrument_identity import EXECUTABLE_FILL, INSTRUMENT_DEFS
from paper.p16d.multi_currency_fx_feed import fetch_multi_currency_fx
from paper.p16d.quote_unit_normalization import normalize_quote_price
from research.p12a.providers.yfinance_readonly import ReadOnlyYFinanceProvider


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _convert_to_eur(normalized: float, quote_currency: str, fx_obs: Dict[str, Any]) -> float:
    qc = quote_currency.upper()
    if qc == "EUR":
        return normalized
    if qc == "USD":
        return normalized * float(fx_obs["usd_to_eur_rate"])
    if qc == "GBP":
        return normalized * float(fx_obs["gbp_to_eur_rate"])
    raise ValueError(f"UNSUPPORTED:{qc}")


def collect_post_baseline_batch(root: Path, identity: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    base = root / "paper/p16d"
    for sub in ("raw_market_observations", "normalized_market_observations", "market_data_quality_ledger", "incident_ledger"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    fx_obs = fetch_multi_currency_fx(root)
    fx_class = classify_fx_observation(fx_obs)
    fx_ok = fx_class["fx_runtime_gate"] == FX_PASS

    dq_state = load_dq_state(root)
    dq_state["p16d_hardening_complete"] = True
    now = _utc_now()
    batch_fp = hashlib.sha256(now.encode()).hexdigest()[:16]

    provider = ReadOnlyYFinanceProvider()
    entries = identity.get("primary", {}).get("entries") or []
    sym_to_provider = {e["user_reference_symbol"]: e["provider_symbol"] for e in entries}
    sym_to_action = {e["user_reference_symbol"]: e.get("allowed_action", "") for e in entries}
    sym_to_qc = {e["user_reference_symbol"]: e["quote_currency"] for e in entries}

    tickers = [sym_to_provider.get(s, s) for s in INSTRUMENT_DEFS]
    provider_map = {v: k for k, v in sym_to_provider.items()}
    df = provider.fetch_quotes(tickers)

    prices_eur: Dict[str, float] = {}
    conversions: List[Dict[str, Any]] = []
    gate_pass = 0
    incidents = 0

    for rec in df.to_dict(orient="records") if not df.empty else []:
        yf = rec.get("ticker", "")
        sym = provider_map.get(yf, str(yf).upper())
        raw = rec.get("last") or rec.get("bid")
        meta_def = INSTRUMENT_DEFS.get(sym, {})
        qc = sym_to_qc.get(sym, "USD")
        action = sym_to_action.get(sym, "")

        if raw is None or str(raw) == "nan":
            incidents += 1
            continue

        raw_f = float(raw)
        norm_price, norm_meta = normalize_quote_price(
            raw_price=raw_f,
            exchange=meta_def.get("exchange", ""),
            quote_currency=qc,
            instrument_type=meta_def.get("instrument_type", "EQUITY"),
        )
        fx_avail = fx_available_for_currency(fx_obs, norm_meta["quote_currency"])

        event_time = rec.get("market_event_time_utc") or rec.get("timestamp") or now
        ingest_time = _utc_now()
        dq = assess_observation(
            symbol=sym,
            raw_price=raw_f,
            quote_currency=norm_meta["quote_currency"],
            event_time_utc=event_time,
            ingestion_time_utc=ingest_time,
            dq_state=dq_state,
            fx_available=fx_avail,
            identity_action=action,
            batch_fingerprint=batch_fp,
        )

        conv: Dict[str, Any] = {
            "user_reference_symbol": sym,
            "provider_symbol": sym_to_provider.get(sym, sym),
            "portfolio_scope": "PROVISIONAL_EXECUTABLE" if sym in EXECUTABLE_FILL else "REFERENCE_OBSERVATION",
            **norm_meta,
            "required_fx_pair": f"{norm_meta['quote_currency']}EUR",
            "fx_rate_used": fx_obs.get("usd_to_eur_rate") if norm_meta["quote_currency"] == "USD" else fx_obs.get("gbp_to_eur_rate"),
            "fx_source": fx_obs.get("usd_fx_source") if norm_meta["quote_currency"] == "USD" else fx_obs.get("gbp_fx_source"),
            "fx_event_time_utc": fx_obs.get("fx_event_time_utc"),
            "fx_quality_gate": fx_obs.get("usd_fx_quality_gate") if norm_meta["quote_currency"] == "USD" else fx_obs.get("gbp_fx_quality_gate"),
            "allowed_action": action,
            "data_quality_gate": dq["gate"],
            "performance_valid": dq.get("performance_valid", False),
            "conversion_valid": False,
            "valuation_timestamp_utc": event_time,
            "market_event_time_utc": event_time,
        }

        if dq["mtm_permitted"] and fx_avail:
            try:
                conv["converted_price_eur"] = _convert_to_eur(norm_price, norm_meta["quote_currency"], fx_obs)
                conv["conversion_valid"] = True
                prices_eur[sym] = conv["converted_price_eur"]
                if sym in EXECUTABLE_FILL:
                    gate_pass += 1
                dq_state.setdefault("last_valid_price", {})[sym] = raw_f
                dq_state.setdefault("last_valid_observation_hash", {})[sym] = dq["normalized_observation_hash"]
            except (ValueError, KeyError, TypeError):
                incidents += 1
                with (base / "incident_ledger" / "incidents.jsonl").open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"symbol": sym, "reason": "fx_conversion_failed"}) + "\n")

        conversions.append(conv)
        with (base / "market_data_quality_ledger" / "quality.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"symbol": sym, **dq}) + "\n")

    dq_state["post_baseline_batch_count"] = int(dq_state.get("post_baseline_batch_count", 0)) + 1
    dq_state["last_batch_fingerprint"] = batch_fp
    save_dq_state(root, dq_state)

    exec_prices = {k: v for k, v in prices_eur.items() if k in EXECUTABLE_FILL}
    dq_gate = "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE" if gate_pass >= 4 and fx_ok else "PARTIAL_AFFECTED_INSTRUMENTS_PAUSED"

    manifest = {
        "generated_at_utc": now,
        "provider": provider.provider_name(),
        "portfolio_scope": "PROVISIONAL_EXECUTABLE",
        "valid_instrument_observations": len(prices_eur),
        "executable_prices_eur": exec_prices,
        "prices_eur": exec_prices,
        "instrument_conversions": conversions,
        "data_quality_gate": dq_gate,
        "fx_runtime_gate": fx_class["fx_runtime_gate"],
        "batch_number": dq_state["post_baseline_batch_count"],
        "stateful_outlier_gate_active": dq_state["post_baseline_batch_count"] > 1,
        "incident_count": incidents,
    }
    atomic_write_json(base / "forward_batch_manifest.json", manifest)
    return manifest
