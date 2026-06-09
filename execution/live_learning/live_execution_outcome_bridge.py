"""Bridge T212 live fills → prediction_ledger (observe-only, no auto-train)."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_prediction_outcomes import (
    LEDGER_COLUMNS,
    _atomic_write_parquet,
    ledger_path,
    load_ledger,
    write_outcomes_parquet,
    write_prediction_feedback_summary,
)
from aa_safe_io import atomic_write_json

SOURCE_LIVE = "LIVE_T212"
INDEX_REL = Path("live_pilot/confirmed_execution/live_execution_outcome_index.json")
EVIDENCE_REL = Path("evidence/live_execution_outcome_sync_latest.json")
SUBMITTED_REL = Path("live_pilot/confirmed_execution/submitted_orders")
OUT_DIR_NAME = "model_output_sp500_pit_t212"
PORTFOLIO_REL = Path(OUT_DIR_NAME) / "latest_target_portfolio.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def make_live_prediction_id(*, draft_id: str) -> str:
    raw = f"LIVE_T212|{draft_id}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _out_dir(root: Path) -> Path:
    return Path(root) / OUT_DIR_NAME


def _load_index(root: Path) -> Dict[str, Any]:
    path = Path(root) / INDEX_REL
    if not path.is_file():
        return {"schema_version": 1, "entries": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "entries": {}}
    if not isinstance(doc, dict):
        return {"schema_version": 1, "entries": {}}
    doc.setdefault("entries", {})
    return doc


def _save_index(root: Path, doc: Dict[str, Any]) -> None:
    doc["updated_at_utc"] = _utc_now()
    atomic_write_json(Path(root) / INDEX_REL, doc)


def _portfolio_row(root: Path, ticker: str) -> Dict[str, Any]:
    path = Path(root) / PORTFOLIO_REL
    if not path.is_file():
        return {}
    try:
        df = pd.read_csv(path)
        sym = str(ticker).upper()
        row = df[df["ticker"].astype(str).str.upper() == sym]
        if row.empty:
            return {}
        rec = row.iloc[0].to_dict()
        return {k: rec.get(k) for k in ("signal_date", "mu_hat", "alpha_lcb", "target_weight", "rank_score", "selection_score", "risk_on")}
    except Exception:
        return {}


def _resolve_horizon(root: Path) -> int:
    try:
        from analytics.prediction_operations import profile_variant_key

        prof = profile_variant_key(root)
        if "DAILY" in prof.upper() or "H1" in prof.upper():
            return 1
    except Exception:
        pass
    return 1


def _parse_date(value: str | None) -> Optional[date]:
    if not value:
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _filled_from_payload(response: Dict[str, Any], draft: Dict[str, Any]) -> Tuple[bool, float, float]:
    """Return (filled, filled_qty, entry_price_eur)."""
    resp = response or {}
    try:
        filled_qty = abs(float(resp.get("filledQuantity") or resp.get("filled_quantity") or 0))
    except (TypeError, ValueError):
        filled_qty = 0.0
    status = str(resp.get("status") or "").upper()
    if filled_qty > 0 or status in ("FILLED", "EXECUTED"):
        price = float(resp.get("averagePrice") or resp.get("limitPrice") or draft.get("limit_price") or 0)
        if price <= 0:
            price = float(draft.get("limit_price") or 0)
        return True, filled_qty, price
    return False, 0.0, 0.0


def _load_submitted_records(root: Path) -> List[Dict[str, Any]]:
    folder = Path(root) / SUBMITTED_REL
    if not folder.is_dir():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(doc, dict):
            continue
        draft = doc.get("draft") or {}
        draft_id = str(draft.get("draft_id") or path.stem)
        rows.append(
            {
                "path": str(path),
                "draft_id": draft_id,
                "draft": draft,
                "body": doc.get("body") or {},
                "response": doc.get("response") or {},
                "submitted_at_utc": doc.get("submitted_at_utc"),
            }
        )
    return rows


def _history_orders_by_id(root: Path) -> Dict[str, Dict[str, Any]]:
    hist_path = Path(root) / "live_pilot/manual_execution/readonly_real_trade_history/latest.json"
    if not hist_path.is_file():
        return {}
    try:
        doc = json.loads(hist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for item in doc.get("trades") or []:
        if not isinstance(item, dict):
            continue
        order = item.get("order") if isinstance(item.get("order"), dict) else item
        oid = str(order.get("id") or order.get("orderId") or "")
        if oid:
            merged = dict(order)
            fill = item.get("fill")
            if isinstance(fill, dict):
                merged["fill"] = fill
                if fill.get("price") and not merged.get("averagePrice"):
                    merged["averagePrice"] = fill.get("price")
            out[oid] = merged
    return out


def _merge_fill_from_history(record: Dict[str, Any], history: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    resp = dict(record.get("response") or {})
    oid = str(resp.get("id") or "")
    if oid and oid in history:
        hist = history[oid]
        resp.update({k: v for k, v in hist.items() if v is not None})
        record = {**record, "response": resp}
    return record


def _close_price(out_dir: Path, ticker: str, on: date) -> Optional[float]:
    panel_path = out_dir / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return None
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "close"])
        sym = str(ticker).upper()
        sub = panel[(panel["ticker"].astype(str).str.upper() == sym)]
        if sub.empty:
            return None
        sub = sub.copy()
        sub["date"] = pd.to_datetime(sub["date"], errors="coerce").dt.date
        sub = sub[sub["date"] <= on].sort_values("date")
        if sub.empty:
            return None
        return float(sub.iloc[-1]["close"])
    except Exception:
        return None


def _forward_return(out_dir: Path, ticker: str, entry: date, horizon: int, *, side: str) -> Optional[float]:
    if horizon < 1:
        horizon = 1
    px0 = _close_price(out_dir, ticker, entry)
    if px0 is None or px0 <= 0:
        return None
    exit_day = entry + timedelta(days=max(horizon, 1))
    px1 = _close_price(out_dir, ticker, exit_day)
    if px1 is None:
        return None
    ret = (px1 - px0) / px0
    if str(side).upper() == "SELL":
        ret = -ret
    return float(ret)


def _ledger_row_from_submission(
    root: Path,
    *,
    draft: Dict[str, Any],
    submitted_at_utc: str | None,
    filled_qty: float,
    entry_price: float,
    variant_id: str,
    horizon: int,
) -> Dict[str, Any]:
    sym = str(draft.get("instrument") or "").upper()
    draft_id = str(draft.get("draft_id") or "")
    pid = make_live_prediction_id(draft_id=draft_id)
    pf = _portfolio_row(root, sym)
    signal_day = _parse_date(str(pf.get("signal_date") or "")) or _parse_date(str(submitted_at_utc or "")[:10])
    trade_day = _parse_date(str(submitted_at_utc or "")[:10]) or signal_day or date.today()
    mu = pf.get("mu_hat")
    if pd.isna(mu) or mu is None:
        mu = pf.get("alpha_lcb")
    try:
        mu_f = float(mu) if mu is not None and not pd.isna(mu) else 0.0
    except (TypeError, ValueError):
        mu_f = 0.0
    alpha_lcb = pf.get("alpha_lcb")
    try:
        alpha_f = float(alpha_lcb) if alpha_lcb is not None and not pd.isna(alpha_lcb) else np.nan
    except (TypeError, ValueError):
        alpha_f = np.nan
    tw = float(pf.get("target_weight") or 0.0) if pf.get("target_weight") is not None else 0.0
    rb = pd.Timestamp(trade_day)
    hold_end = rb + pd.Timedelta(days=max(1, horizon))
    now = _utc_now()
    return {
        "prediction_id": pid,
        "signal_id": pid,
        "model_label": variant_id,
        "variant_id": variant_id,
        "source_run_id": SOURCE_LIVE,
        "rebalance_date": rb,
        "feature_date": pd.Timestamp(signal_day) if signal_day else rb,
        "signal_date": pd.Timestamp(signal_day) if signal_day else rb,
        "intended_trade_date": rb,
        "holding_period_start": rb,
        "holding_period_end": hold_end,
        "ticker": sym,
        "horizon": int(horizon),
        "rebalance_every": 1,
        "mu_hat": mu_f,
        "alpha_lcb": alpha_f,
        "rank_score": float(pf.get("rank_score") or 0) if pf.get("rank_score") is not None else np.nan,
        "selection_score": float(pf.get("selection_score") or 0) if pf.get("selection_score") is not None else np.nan,
        "target_weight": tw,
        "cash_weight": np.nan,
        "target_exposure": np.nan,
        "risk_on": bool(pf.get("risk_on", True)),
        "selection_mode": "live_execution",
        "gate_mode": str(draft.get("source") or "LIVE_T212"),
        "data_quality_status": "LIVE_FILL",
        "signal_validity_status": "VALID",
        "status": "pending",
        "realized_target": np.nan,
        "prediction_error": np.nan,
        "signed_hit": np.nan,
        "recorded_at_utc": now,
        "matured_at_utc": "",
    }


def append_live_executions_from_submitted(root: Path) -> int:
    """Append filled live orders to prediction_ledger. Returns rows added."""
    root = Path(root)
    out_dir = _out_dir(root)
    index = _load_index(root)
    entries: Dict[str, Any] = dict(index.get("entries") or {})
    history = _history_orders_by_id(root)
    variant_id = "unknown"
    try:
        from analytics.prediction_operations import resolve_operational_signal_id

        variant_id = resolve_operational_signal_id(root)
    except Exception:
        pass
    horizon = _resolve_horizon(root)
    ledger = load_ledger(out_dir)
    existing = set(ledger["prediction_id"].astype(str).tolist()) if not ledger.empty else set()
    new_rows: List[Dict[str, Any]] = []

    for rec in _load_submitted_records(root):
        draft_id = rec["draft_id"]
        if draft_id in entries:
            continue
        rec = _merge_fill_from_history(rec, history)
        filled, filled_qty, entry_price = _filled_from_payload(rec["response"], rec["draft"])
        if not filled:
            continue
        pid = make_live_prediction_id(draft_id=draft_id)
        if pid in existing:
            entries[draft_id] = {"prediction_id": pid, "skipped": "already_in_ledger"}
            continue
        row = _ledger_row_from_submission(
            root,
            draft=rec["draft"],
            submitted_at_utc=rec.get("submitted_at_utc"),
            filled_qty=filled_qty,
            entry_price=entry_price,
            variant_id=variant_id,
            horizon=horizon,
        )
        new_rows.append(row)
        entries[draft_id] = {
            "prediction_id": pid,
            "ticker": row["ticker"],
            "filled_qty": filled_qty,
            "entry_price": entry_price,
            "recorded_at_utc": _utc_now(),
        }

    if not new_rows:
        index["entries"] = entries
        _save_index(root, index)
        return 0

    frame = pd.DataFrame(new_rows)
    for col in LEDGER_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    merged = pd.concat([ledger, frame[list(LEDGER_COLUMNS)]], ignore_index=True)
    _atomic_write_parquet(ledger_path(out_dir), merged)
    write_prediction_feedback_summary(out_dir)
    index["entries"] = entries
    _save_index(root, index)
    return len(new_rows)


def mature_live_execution_outcomes(root: Path) -> int:
    """Mature pending LIVE_T212 rows when horizon elapsed and prices available."""
    root = Path(root)
    out_dir = _out_dir(root)
    ledger = load_ledger(out_dir)
    if ledger.empty:
        return 0
    pending = (ledger["status"] == "pending") & (ledger["source_run_id"].astype(str) == SOURCE_LIVE)
    if not pending.any():
        return 0
    today = date.today()
    updated = 0
    now = _utc_now()
    for idx in ledger.index[pending]:
        end = ledger.at[idx, "holding_period_end"]
        try:
            end_day = pd.Timestamp(end).date()
        except Exception:
            continue
        if end_day > today:
            continue
        sym = str(ledger.at[idx, "ticker"])
        side = "BUY"
        try:
            entry_day = pd.Timestamp(ledger.at[idx, "rebalance_date"]).date()
        except Exception:
            continue
        horizon = int(ledger.at[idx, "horizon"] or 1)
        realized = _forward_return(out_dir, sym, entry_day, horizon, side=side)
        if realized is None:
            continue
        mu = float(ledger.at[idx, "mu_hat"])
        ledger.at[idx, "realized_target"] = realized
        ledger.at[idx, "prediction_error"] = mu - realized
        if realized != 0 and mu != 0:
            ledger.at[idx, "signed_hit"] = bool(np.sign(mu) == np.sign(realized))
        ledger.at[idx, "status"] = "mature"
        ledger.at[idx, "matured_at_utc"] = now
        updated += 1

    if updated:
        _atomic_write_parquet(ledger_path(out_dir), ledger)
        write_outcomes_parquet(out_dir)
        write_prediction_feedback_summary(out_dir)
    return updated


def sync_live_execution_outcomes(root: Path, *, refresh_history: bool = True) -> Dict[str, Any]:
    """Full sync: optional T212 history pull → append fills → mature outcomes."""
    root = Path(root)
    history_result: Dict[str, Any] = {"skipped": True}
    if refresh_history:
        try:
            from integrations.trading212.t212_readonly_trade_history_sync import sync_live_readonly_trade_history

            history_result = sync_live_readonly_trade_history(root)
        except Exception as exc:
            history_result = {"ok": False, "error": str(exc)[:200]}

    added = append_live_executions_from_submitted(root)
    matured = mature_live_execution_outcomes(root)
    out_dir = _out_dir(root)
    from aa_prediction_outcomes import ledger_status_counts

    counts = ledger_status_counts(out_dir)
    live_n = 0
    ledger = load_ledger(out_dir)
    if not ledger.empty:
        live_n = int((ledger["source_run_id"].astype(str) == SOURCE_LIVE).sum())

    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": True,
        "added_from_submitted": added,
        "matured_live": matured,
        "live_rows_total": live_n,
        "ledger_counts": counts,
        "history_sync": history_result,
        "message_de": (
            f"Live-Fills -> Ledger: +{added} neu, {matured} reif, {live_n} LIVE_T212 gesamt."
        ),
    }
    out = Path(root) / EVIDENCE_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, report)
    return report
