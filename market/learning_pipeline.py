"""Live observation + EOD learning pipeline — collect only, never auto-train or promote."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json
from paper.p16d.instrument_identity import EXECUTABLE_FILL, INSTRUMENT_DEFS

logger = logging.getLogger(__name__)

LEARNING_ROOT_REL = Path("market_data/live_learning")
INTRADAY_LEDGER = "intraday_quotes.jsonl"
EOD_LEDGER = "eod_closes.jsonl"
BROKER_DAILY_LEDGER = "broker_daily_snapshots.jsonl"
BROKER_EVENT_LEDGER = "broker_event_snapshots.jsonl"
MANIFEST_FILE = "learning_manifest.json"
POLICY_FILE = Path("control/learning_collection_policy.json")

# Efficiency: at most one intraday row per symbol per N seconds unless price moves materially
INTRADAY_MIN_INTERVAL_S = 300
INTRADAY_MIN_PRICE_MOVE_PCT = 0.001
MIN_EOD_SYMBOLS_FOR_OK = 4


def _empty_manifest() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "intraday_rows": 0,
        "eod_rows": 0,
        "broker_daily_rows": 0,
        "broker_event_rows": 0,
        "last_intraday_utc": None,
        "last_eod_date": None,
        "last_broker_daily_date": None,
        "last_broker_event_utc": None,
        "last_broker_positions_count": None,
        "last_intraday_by_symbol": {},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def learning_root(root: Path) -> Path:
    p = Path(root) / LEARNING_ROOT_REL
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ledger_path(root: Path, name: str) -> Path:
    return learning_root(root) / name


def _load_manifest(root: Path) -> Dict[str, Any]:
    path = learning_root(root) / MANIFEST_FILE
    if not path.is_file():
        return _empty_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_manifest()
        base = _empty_manifest()
        base.update(data)
        return base
    except (json.JSONDecodeError, OSError):
        logger.warning("learning manifest corrupt or unreadable — resetting counters", exc_info=True)
        return _empty_manifest()


def _save_manifest(root: Path, manifest: Dict[str, Any]) -> None:
    manifest["updated_at_utc"] = _utc_now()
    atomic_write_json(learning_root(root) / MANIFEST_FILE, manifest)


def ensure_learning_policy(root: Path) -> Dict[str, Any]:
    """Write fail-closed policy: observe yes, train/promote no."""
    root = Path(root)
    path = root / POLICY_FILE
    policy = {
        "schema_version": 1,
        "observation_collection_enabled": True,
        "intraday_quote_capture_enabled": True,
        "eod_close_capture_enabled": True,
        "broker_daily_snapshot_enabled": True,
        "offline_feature_materialization_enabled": False,
        "auto_model_training_enabled": False,
        "auto_champion_update_enabled": False,
        "auto_execute_real_money_enabled": False,
        "active_champion_locked": "R3_w075_q065_noexit",
        "purpose": "Forward observation ledger for approved offline research — no live learning loop.",
        "updated_at_utc": _utc_now(),
    }
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, policy)
    return policy


def _append_jsonl(path: Path, record: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _provider_symbols() -> Dict[str, str]:
    return {sym: INSTRUMENT_DEFS[sym]["provider_symbol"] for sym in EXECUTABLE_FILL if sym in INSTRUMENT_DEFS}


def append_intraday_from_snapshot(root: Path, snapshot: Dict[str, Any]) -> int:
    """Append deduplicated intraday quotes from live quote snapshot. Returns rows written."""
    if os.environ.get("AA_LEARNING_CAPTURE", "1").strip() == "0":
        return 0
    root = Path(root)
    manifest = _load_manifest(root)
    last_by_sym: Dict[str, Any] = dict(manifest.get("last_intraday_by_symbol") or {})
    prices = snapshot.get("executable_prices_eur") or {}
    quotes = snapshot.get("quotes_by_symbol") or {}
    now_ts = snapshot.get("generated_at_utc") or _utc_now()
    written = 0

    for sym in sorted(EXECUTABLE_FILL):
        px = prices.get(sym)
        if px is None:
            continue
        try:
            px_f = float(px)
        except (TypeError, ValueError):
            continue
        prev = last_by_sym.get(sym) or {}
        prev_ts = prev.get("recorded_at_utc")
        prev_px = prev.get("price_eur")
        skip = False
        if prev_ts and prev_px is not None:
            try:
                prev_dt = datetime.fromisoformat(str(prev_ts).replace("Z", "+00:00"))
                now_dt = datetime.fromisoformat(str(now_ts).replace("Z", "+00:00"))
                age_s = (now_dt - prev_dt.astimezone(timezone.utc)).total_seconds()
                move = abs(px_f - float(prev_px)) / max(float(prev_px), 1e-9)
                if age_s < INTRADAY_MIN_INTERVAL_S and move < INTRADAY_MIN_PRICE_MOVE_PCT:
                    skip = True
            except (TypeError, ValueError):
                pass
        if skip:
            continue

        q = quotes.get(sym) or {}
        record = {
            "recorded_at_utc": now_ts,
            "observation_type": "INTRADAY_QUOTE_EUR",
            "symbol": sym,
            "price_eur": round(px_f, 6),
            "raw_price": q.get("raw_price"),
            "quote_currency": q.get("quote_currency"),
            "market_event_time_utc": q.get("market_event_time_utc"),
            "provider": snapshot.get("provider", "READONLY_YFINANCE"),
            "freshness_status": (snapshot.get("freshness") or {}).get("status"),
            "learning_use": "FEATURE_MATERIALIZATION_OFFLINE_ONLY",
            "model_update": False,
        }
        _append_jsonl(_ledger_path(root, INTRADAY_LEDGER), record)
        last_by_sym[sym] = {"recorded_at_utc": now_ts, "price_eur": px_f}
        written += 1

    if written:
        manifest["intraday_rows"] = int(manifest.get("intraday_rows", 0)) + written
        manifest["last_intraday_utc"] = now_ts
        manifest["last_intraday_by_symbol"] = last_by_sym
        _save_manifest(root, manifest)
    return written


def ensure_today_eod_closes(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Fetch daily OHLCV closes once per UTC calendar day (batch, efficient)."""
    if os.environ.get("AA_LEARNING_CAPTURE", "1").strip() == "0":
        return {"skipped": True, "reason": "AA_LEARNING_CAPTURE=0"}
    root = Path(root)
    ensure_learning_policy(root)
    manifest = _load_manifest(root)
    today = _today_utc()
    if not force and manifest.get("last_eod_date") == today:
        return {"skipped": True, "reason": "already_captured_today", "date": today}

    sym_to_yf = _provider_symbols()
    tickers = list(dict.fromkeys(sym_to_yf.values()))
    result: Dict[str, Any] = {"date": today, "symbols": {}, "errors": []}

    try:
        import yfinance as yf

        raw = yf.download(tickers, period="10d", interval="1d", progress=False, auto_adjust=True, threads=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}

    yf_to_sym = {v: k for k, v in sym_to_yf.items()}
    captured = 0

    for yf_ticker in tickers:
        sym = yf_to_sym.get(yf_ticker, yf_ticker)
        try:
            if len(tickers) == 1:
                close_s = raw["Close"] if "Close" in raw.columns else raw
            else:
                close_s = raw["Close"][yf_ticker] if yf_ticker in raw["Close"].columns else None
            if close_s is None:
                result["errors"].append(f"{sym}:no_close")
                continue
            close_s = close_s.dropna()
            if close_s.empty:
                result["errors"].append(f"{sym}:empty")
                continue
            last_idx = close_s.index[-1]
            close_val = float(close_s.iloc[-1])
            bar_date = str(last_idx.date()) if hasattr(last_idx, "date") else today
            record = {
                "recorded_at_utc": _utc_now(),
                "observation_type": "EOD_CLOSE",
                "symbol": sym,
                "provider_symbol": yf_ticker,
                "bar_date": bar_date,
                "close": close_val,
                "currency": INSTRUMENT_DEFS.get(sym, {}).get("quote_currency", "USD"),
                "provider": "READONLY_YFINANCE",
                "learning_use": "OUTCOME_LABEL_OFFLINE_ONLY",
                "model_update": False,
            }
            record["record_hash"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
            _append_jsonl(_ledger_path(root, EOD_LEDGER), record)
            result["symbols"][sym] = {"bar_date": bar_date, "close": close_val}
            captured += 1
        except Exception as exc:
            result["errors"].append(f"{sym}:{str(exc)[:40]}")

    result["ok"] = captured >= MIN_EOD_SYMBOLS_FOR_OK
    result["captured"] = captured
    if captured:
        manifest["eod_rows"] = int(manifest.get("eod_rows", 0)) + captured
        manifest["last_eod_date"] = today
        manifest["last_eod_capture_utc"] = _utc_now()
        _save_manifest(root, manifest)
    return result


def append_broker_daily_snapshot(
    root: Path,
    *,
    broker: Dict[str, Any],
    cash: Dict[str, Any],
    positions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """One broker state snapshot per day when credentials configured."""
    if os.environ.get("AA_LEARNING_CAPTURE", "1").strip() == "0":
        return {"skipped": True}
    if not broker.get("credentials_configured"):
        return {"skipped": True, "reason": "broker_not_configured"}
    root = Path(root)
    manifest = _load_manifest(root)
    today = _today_utc()
    if manifest.get("last_broker_daily_date") == today:
        return {"skipped": True, "reason": "already_captured_today"}

    pos = positions if positions is not None else broker.get("positions") or []
    record = {
        "recorded_at_utc": _utc_now(),
        "observation_type": "BROKER_DAILY_SNAPSHOT",
        "snapshot_date": today,
        "cash_eur": broker.get("cash_eur"),
        "positions_count": broker.get("positions_count", len(pos)),
        "positions_summary": [
            {
                "ticker": p.get("ticker"),
                "quantity": p.get("quantity"),
                "currentValue": p.get("currentValue"),
            }
            for p in pos[:50]
        ],
        "reconciled_invested_eur": cash.get("readonly_reconciled_real_invested_eur"),
        "learning_use": "PORTFOLIO_OUTCOME_RECONCILIATION_OFFLINE",
        "model_update": False,
    }
    _append_jsonl(_ledger_path(root, BROKER_DAILY_LEDGER), record)
    manifest["broker_daily_rows"] = int(manifest.get("broker_daily_rows", 0)) + 1
    manifest["last_broker_daily_date"] = today
    _save_manifest(root, manifest)
    return {"ok": True, "date": today}


def append_broker_event_snapshot(
    root: Path,
    *,
    broker: Dict[str, Any],
    event: str,
    previous_positions_count: int = 0,
    cash: Optional[Dict[str, Any]] = None,
    positions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Broker-Zustandswechsel (z. B. Liquidation) — mehrfach pro Tag erlaubt."""
    if os.environ.get("AA_LEARNING_CAPTURE", "1").strip() == "0":
        return {"skipped": True}
    if not broker.get("credentials_configured"):
        return {"skipped": True, "reason": "broker_not_configured"}
    root = Path(root)
    manifest = _load_manifest(root)
    pos = positions if positions is not None else broker.get("positions") or []
    cur_n = int(broker.get("positions_count", len(pos)))
    record = {
        "recorded_at_utc": _utc_now(),
        "observation_type": "BROKER_EVENT_SNAPSHOT",
        "event": str(event or "position_change"),
        "positions_count": cur_n,
        "previous_positions_count": int(previous_positions_count),
        "cash_eur": broker.get("cash_eur"),
        "positions_summary": [
            {
                "ticker": p.get("ticker"),
                "quantity": p.get("quantity"),
                "currentValue": p.get("currentValue"),
            }
            for p in pos[:50]
        ],
        "sync_utc": broker.get("last_successful_sync_utc"),
        "learning_use": "T212_OUTCOME_RECONCILIATION",
        "model_update": False,
    }
    _append_jsonl(_ledger_path(root, BROKER_EVENT_LEDGER), record)
    manifest["broker_event_rows"] = int(manifest.get("broker_event_rows", 0)) + 1
    manifest["last_broker_event_utc"] = _utc_now()
    manifest["last_broker_positions_count"] = cur_n
    _save_manifest(root, manifest)
    return {"ok": True, "event": event, "positions_count": cur_n}


def run_learning_capture_cycle(
    root: Path,
    *,
    live_snapshot: Optional[Dict[str, Any]] = None,
    broker: Optional[Dict[str, Any]] = None,
    cash: Optional[Dict[str, Any]] = None,
    force_eod: bool = False,
) -> Dict[str, Any]:
    """Single efficient cycle: intraday from snapshot + daily EOD + broker snapshot."""
    root = Path(root)
    policy = ensure_learning_policy(root)
    out: Dict[str, Any] = {"policy": policy, "intraday_appended": 0}

    if live_snapshot and live_snapshot.get("executable_prices_eur"):
        out["intraday_appended"] = append_intraday_from_snapshot(root, live_snapshot)

    out["eod"] = ensure_today_eod_closes(root, force=force_eod)

    if broker:
        out["broker_daily"] = append_broker_daily_snapshot(root, broker=broker, cash=cash or {}, positions=broker.get("positions"))

    readiness = learning_readiness_report(root)
    capture_errors: List[str] = []
    eod = out.get("eod") or {}
    if eod.get("skipped"):
        pass
    elif eod.get("ok") is False:
        capture_errors.append(str(eod.get("error") or eod.get("errors") or "EOD capture failed")[:200])
    broker_daily = out.get("broker_daily") or {}
    if broker_daily.get("ok") is False:
        capture_errors.append(str(broker_daily.get("reason") or "broker daily snapshot failed")[:200])
    readiness["capture_errors"] = capture_errors
    readiness["learning_healthy"] = len(capture_errors) == 0
    if capture_errors:
        readiness["error"] = "; ".join(capture_errors)
    out["readiness"] = readiness
    return out


def learning_readiness_report(root: Path) -> Dict[str, Any]:
    """Status for cockpit — proves forward learning data is accumulating."""
    root = Path(root)
    manifest = _load_manifest(root)
    policy_path = root / POLICY_FILE
    policy = {}
    if policy_path.is_file():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("learning policy unreadable — using defaults", exc_info=True)

    intraday_n = int(manifest.get("intraday_rows", 0))
    eod_n = int(manifest.get("eod_rows", 0))
    broker_n = int(manifest.get("broker_daily_rows", 0))

    ready = intraday_n >= 1 and eod_n >= len(EXECUTABLE_FILL)
    learning_active = policy.get("observation_collection_enabled", True) and not policy.get("auto_model_training_enabled", False)

    return {
        "learning_collection_active": learning_active,
        "ready_for_offline_research": ready,
        "intraday_observations": intraday_n,
        "eod_close_observations": eod_n,
        "broker_daily_snapshots": broker_n,
        "broker_event_snapshots": int(manifest.get("broker_event_rows", 0)),
        "last_broker_positions_count": manifest.get("last_broker_positions_count"),
        "last_intraday_utc": manifest.get("last_intraday_utc"),
        "last_eod_date": manifest.get("last_eod_date"),
        "last_broker_daily_date": manifest.get("last_broker_daily_date"),
        "auto_training_blocked": True,
        "champion_locked": policy.get(
            "governance_champion_locked",
            policy.get("active_champion_locked", "R0_LEGACY_ENSEMBLE"),
        ),
        "next_offline_step": "Approved research phase: materialize features from ledgers → validate challenger offline",
        "ledger_paths": {
            "intraday": str(LEARNING_ROOT_REL / INTRADAY_LEDGER),
            "eod": str(LEARNING_ROOT_REL / EOD_LEDGER),
            "broker_daily": str(LEARNING_ROOT_REL / BROKER_DAILY_LEDGER),
            "broker_events": str(LEARNING_ROOT_REL / BROKER_EVENT_LEDGER),
        },
    }


def count_ledger_lines(root: Path, name: str) -> int:
    path = _ledger_path(root, name)
    if not path.is_file():
        return 0
    return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
