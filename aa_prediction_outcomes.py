"""Prediction outcome ledger — record mu_hat vs realized forward alpha (Phase 2).

No champion changes, no auto-promotion. Append-only ledger from backtest decisions.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_safe_io import atomic_write_json, atomic_write_text

LEDGER_FILE = "prediction_ledger.parquet"
OUTCOMES_FILE = "prediction_outcomes.parquet"
FEEDBACK_SUMMARY_FILE = "prediction_feedback_summary.json"
LEDGER_META_FILE = "prediction_ledger_meta.json"
FEEDBACK_REPORT_FILE = "feedback_report.txt"

IMMUTABLE_LEDGER_COLS = frozenset(
    {
        "prediction_id",
        "signal_id",
        "variant_id",
        "model_label",
        "source_run_id",
        "rebalance_date",
        "feature_date",
        "signal_date",
        "intended_trade_date",
        "ticker",
        "horizon",
        "mu_hat",
        "alpha_lcb",
        "rank_score",
        "selection_score",
        "target_weight",
        "cash_weight",
        "target_exposure",
        "risk_on",
        "selection_mode",
        "gate_mode",
        "recorded_at_utc",
    }
)

OUTCOMES_COLUMNS = (
    "signal_id",
    "prediction_id",
    "variant_id",
    "rebalance_date",
    "ticker",
    "outcome_status",
    "realized_asset_return",
    "realized_target",
    "prediction_error",
    "portfolio_contribution",
    "signed_hit",
    "matured_at_utc",
)

LEDGER_COLUMNS = (
    "prediction_id",
    "signal_id",
    "model_label",
    "variant_id",
    "source_run_id",
    "rebalance_date",
    "feature_date",
    "signal_date",
    "intended_trade_date",
    "holding_period_start",
    "holding_period_end",
    "ticker",
    "horizon",
    "rebalance_every",
    "mu_hat",
    "alpha_lcb",
    "rank_score",
    "selection_score",
    "target_weight",
    "cash_weight",
    "target_exposure",
    "risk_on",
    "selection_mode",
    "gate_mode",
    "data_quality_status",
    "signal_validity_status",
    "status",
    "realized_target",
    "prediction_error",
    "signed_hit",
    "recorded_at_utc",
    "matured_at_utc",
)

DECISION_USE_COLS = (
    "rebalance_date",
    "date",
    "ticker",
    "mu_hat",
    "alpha_lcb",
    "rank_score",
    "selection_score",
    "target_weight",
    "target",
    "risk_on",
    "selection_mode",
    "gate_mode",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ledger_path(out_dir: Path) -> Path:
    return Path(out_dir) / LEDGER_FILE


def outcomes_path(out_dir: Path) -> Path:
    return Path(out_dir) / OUTCOMES_FILE


def feedback_summary_path(out_dir: Path) -> Path:
    return Path(out_dir) / FEEDBACK_SUMMARY_FILE


def ledger_meta_path(out_dir: Path) -> Path:
    return Path(out_dir) / LEDGER_META_FILE


def feedback_report_path(out_dir: Path) -> Path:
    return Path(out_dir) / FEEDBACK_REPORT_FILE


def make_prediction_id(*, variant_id: str, rebalance_date: str, ticker: str) -> str:
    raw = f"{variant_id}|{rebalance_date}|{ticker}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _atomic_write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        frame.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
    return path


def load_ledger(out_dir: Path) -> pd.DataFrame:
    path = ledger_path(out_dir)
    if not path.is_file():
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    for col in LEDGER_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    if "signal_id" in frame.columns and frame["signal_id"].isna().all() and "prediction_id" in frame.columns:
        frame["signal_id"] = frame["prediction_id"]
    return frame[list(LEDGER_COLUMNS)]


def load_outcomes(out_dir: Path) -> pd.DataFrame:
    path = outcomes_path(out_dir)
    if not path.is_file():
        return pd.DataFrame(columns=list(OUTCOMES_COLUMNS))
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame(columns=list(OUTCOMES_COLUMNS))
    for col in OUTCOMES_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame[list(OUTCOMES_COLUMNS)]


def _normalize_decisions(decisions: pd.DataFrame) -> pd.DataFrame:
    if decisions.empty:
        return decisions
    frame = decisions.copy()
    if "rebalance_date" not in frame.columns:
        raise ValueError("backtest_decisions.csv missing rebalance_date")
    frame["rebalance_date"] = pd.to_datetime(frame["rebalance_date"], errors="coerce")
    if "date" in frame.columns:
        frame["feature_date"] = pd.to_datetime(frame["date"], errors="coerce")
    else:
        frame["feature_date"] = frame["rebalance_date"]
    frame["ticker"] = frame["ticker"].astype(str)
    for col in ("mu_hat", "alpha_lcb", "rank_score", "selection_score", "target_weight", "target"):
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "risk_on" in frame.columns:
        frame["risk_on"] = frame["risk_on"].fillna(False).astype(bool)
    else:
        frame["risk_on"] = False
    for col in ("selection_mode", "gate_mode"):
        if col not in frame.columns:
            frame[col] = ""
        frame[col] = frame[col].fillna("").astype(str)
    return frame


def _rows_from_decisions(
    decisions: pd.DataFrame,
    *,
    variant_id: str,
    source_run_id: str,
    horizon: int,
    rebalance_every: int = 5,
    existing_ids: set,
) -> pd.DataFrame:
    frame = _normalize_decisions(decisions)
    frame = frame[frame["mu_hat"].notna() & frame["rebalance_date"].notna() & frame["ticker"].ne("")]
    if frame.empty:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))

    now = _utc_now()
    rows: List[Dict[str, Any]] = []
    for rec in frame.to_dict(orient="records"):
        rb = pd.Timestamp(rec["rebalance_date"])
        tk = str(rec["ticker"])
        pid = make_prediction_id(
            variant_id=variant_id,
            rebalance_date=rb.strftime("%Y-%m-%d"),
            ticker=tk,
        )
        if pid in existing_ids:
            continue
        realized = rec.get("target")
        mature = pd.notna(realized)
        mu = float(rec["mu_hat"])
        realized_f = float(realized) if mature else np.nan
        err = mu - realized_f if mature else np.nan
        hit = bool(np.sign(mu) == np.sign(realized_f)) if mature and realized_f != 0 and mu != 0 else np.nan
        feat = pd.Timestamp(rec.get("feature_date", rb))
        hold_end = rb + pd.Timedelta(days=max(1, int(horizon)))
        target_exposure = float(rec["target_exposure"]) if pd.notna(rec.get("target_exposure")) else np.nan
        if pd.isna(target_exposure) and pd.notna(rec.get("portfolio_exposure")):
            target_exposure = float(rec["portfolio_exposure"])
        cash_weight = float(rec["cash_weight"]) if pd.notna(rec.get("cash_weight")) else (
            max(0.0, 1.0 - target_exposure) if pd.notna(target_exposure) else np.nan
        )
        rows.append(
            {
                "prediction_id": pid,
                "signal_id": pid,
                "model_label": variant_id or "unknown",
                "variant_id": variant_id,
                "source_run_id": source_run_id,
                "rebalance_date": rb,
                "feature_date": feat,
                "signal_date": feat,
                "intended_trade_date": rb,
                "holding_period_start": rb,
                "holding_period_end": hold_end,
                "ticker": tk,
                "horizon": int(horizon),
                "rebalance_every": int(rebalance_every),
                "mu_hat": mu,
                "alpha_lcb": float(rec["alpha_lcb"]) if pd.notna(rec.get("alpha_lcb")) else np.nan,
                "rank_score": float(rec["rank_score"]) if pd.notna(rec.get("rank_score")) else np.nan,
                "selection_score": float(rec["selection_score"]) if pd.notna(rec.get("selection_score")) else np.nan,
                "target_weight": float(rec["target_weight"]) if pd.notna(rec.get("target_weight")) else 0.0,
                "cash_weight": cash_weight,
                "target_exposure": target_exposure,
                "risk_on": bool(rec.get("risk_on", False)),
                "selection_mode": str(rec.get("selection_mode", "") or ""),
                "gate_mode": str(rec.get("gate_mode", "") or ""),
                "data_quality_status": "OK",
                "signal_validity_status": "VALID",
                "status": "mature" if mature else "pending",
                "realized_target": realized_f,
                "prediction_error": err,
                "signed_hit": hit,
                "recorded_at_utc": now,
                "matured_at_utc": now if mature else "",
            }
        )
    if not rows:
        return pd.DataFrame(columns=list(LEDGER_COLUMNS))
    return pd.DataFrame(rows)


def append_predictions_from_decisions(
    out_dir: Path,
    *,
    decisions_path: Optional[Path] = None,
    variant_id: str = "",
    source_run_id: str = "",
    horizon: int = 10,
    rebalance_every: int = 5,
) -> int:
    """Append new prediction rows from backtest_decisions.csv. Returns count added."""
    out_dir = Path(out_dir)
    path = Path(decisions_path or (out_dir / "backtest_decisions.csv"))
    if not path.is_file():
        return 0
    usecols = [c for c in DECISION_USE_COLS if c in pd.read_csv(path, nrows=0).columns]
    if "rebalance_date" not in usecols or "ticker" not in usecols or "mu_hat" not in usecols:
        return 0
    decisions = pd.read_csv(path, usecols=usecols)
    ledger = load_ledger(out_dir)
    existing_ids = set(ledger["prediction_id"].astype(str).tolist()) if not ledger.empty else set()
    new_rows = _rows_from_decisions(
        decisions,
        variant_id=variant_id or "unknown",
        source_run_id=source_run_id,
        horizon=horizon,
        rebalance_every=rebalance_every,
        existing_ids=existing_ids,
    )
    if new_rows.empty:
        return 0
    merged = pd.concat([ledger, new_rows], ignore_index=True)
    _atomic_write_parquet(ledger_path(out_dir), merged)
    _write_ledger_meta(out_dir, variant_id=variant_id, added=int(len(new_rows)))
    write_outcomes_parquet(out_dir)
    return int(len(new_rows))


def _write_ledger_meta(out_dir: Path, *, variant_id: str = "", added: int = 0) -> None:
    ledger = load_ledger(out_dir)
    mature = ledger[ledger["status"] == "mature"] if not ledger.empty else ledger
    payload = {
        "updated_at_utc": _utc_now(),
        "variant_id": variant_id,
        "total_predictions": int(len(ledger)),
        "mature_predictions": int(len(mature)),
        "pending_predictions": int(len(ledger) - len(mature)) if not ledger.empty else 0,
        "last_append_count": int(added),
    }
    atomic_write_json(ledger_meta_path(out_dir), payload)
    write_prediction_feedback_summary(out_dir, extra=payload)


def write_prediction_feedback_summary(out_dir: Path, *, extra: Optional[Dict[str, Any]] = None) -> Path:
    out_dir = Path(out_dir)
    ledger = load_ledger(out_dir)
    metrics = compute_feedback_metrics(ledger)
    meta = extra or {}
    if not meta:
        meta_path = ledger_meta_path(out_dir)
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
    payload = {
        "updated_at_utc": _utc_now(),
        "stored_predictions": int(metrics.get("n_total", 0)),
        "mature_outcomes": int(metrics.get("n_mature", 0)),
        "pending_predictions": int(metrics.get("n_pending", 0)),
        "last_feedback_update_utc": _utc_now(),
        "metrics": metrics,
        "variant_id": str(meta.get("variant_id", "") or ""),
    }
    return atomic_write_json(feedback_summary_path(out_dir), payload)


def write_outcomes_parquet(out_dir: Path) -> Path:
    """Export mature outcomes to separate append-only outcomes file."""
    out_dir = Path(out_dir)
    ledger = load_ledger(out_dir)
    if ledger.empty:
        frame = pd.DataFrame(columns=list(OUTCOMES_COLUMNS))
        return _atomic_write_parquet(outcomes_path(out_dir), frame)
    mature = ledger[ledger["status"] == "mature"].copy()
    rows: List[Dict[str, Any]] = []
    for rec in mature.to_dict(orient="records"):
        realized = rec.get("realized_target")
        weight = float(rec.get("target_weight") or 0.0)
        contrib = float(realized) * weight if pd.notna(realized) else np.nan
        rows.append(
            {
                "signal_id": rec.get("signal_id", rec.get("prediction_id")),
                "prediction_id": rec.get("prediction_id"),
                "variant_id": rec.get("variant_id"),
                "rebalance_date": rec.get("rebalance_date"),
                "ticker": rec.get("ticker"),
                "outcome_status": "MATURE",
                "realized_asset_return": realized,
                "realized_target": realized,
                "prediction_error": rec.get("prediction_error"),
                "portfolio_contribution": contrib,
                "signed_hit": rec.get("signed_hit"),
                "matured_at_utc": rec.get("matured_at_utc"),
            }
        )
    frame = pd.DataFrame(rows)
    existing = load_outcomes(out_dir)
    if not existing.empty and not frame.empty:
        existing_ids = set(existing["prediction_id"].astype(str))
        frame = frame[~frame["prediction_id"].astype(str).isin(existing_ids)]
        if not frame.empty:
            frame = pd.concat([existing, frame], ignore_index=True)
        else:
            frame = existing
    elif existing.empty:
        pass
    else:
        frame = existing
    return _atomic_write_parquet(outcomes_path(out_dir), frame)


def ledger_status_counts(out_dir: Path) -> Dict[str, Any]:
    path = feedback_summary_path(out_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "stored_predictions": int(data.get("stored_predictions", 0)),
                "mature_outcomes": int(data.get("mature_outcomes", 0)),
                "pending_predictions": int(data.get("pending_predictions", 0)),
                "last_feedback_update_utc": str(data.get("last_feedback_update_utc", "") or ""),
            }
        except Exception:
            pass
    metrics = compute_feedback_metrics(load_ledger(out_dir))
    return {
        "stored_predictions": int(metrics.get("n_total", 0)),
        "mature_outcomes": int(metrics.get("n_mature", 0)),
        "pending_predictions": int(metrics.get("n_pending", 0)),
        "last_feedback_update_utc": "",
    }


def mature_pending_from_decisions(out_dir: Path, *, decisions_path: Optional[Path] = None) -> int:
    """Fill realized_target for pending rows when decisions file has target values."""
    out_dir = Path(out_dir)
    ledger = load_ledger(out_dir)
    if ledger.empty:
        return 0
    pending = ledger["status"] == "pending"
    if not pending.any():
        return 0

    path = Path(decisions_path or (out_dir / "backtest_decisions.csv"))
    if not path.is_file():
        return 0
    decisions = _normalize_decisions(pd.read_csv(path, usecols=lambda c: c in set(DECISION_USE_COLS)))
    if decisions.empty or "target" not in decisions.columns:
        return 0

    lookup: Dict[Tuple[str, str], float] = {}
    for rec in decisions.to_dict(orient="records"):
        if pd.isna(rec.get("target")):
            continue
        rb = pd.Timestamp(rec["rebalance_date"]).strftime("%Y-%m-%d")
        lookup[(rb, str(rec["ticker"]))] = float(rec["target"])

    now = _utc_now()
    updated = 0
    for idx in ledger.index[pending]:
        rb = pd.Timestamp(ledger.at[idx, "rebalance_date"]).strftime("%Y-%m-%d")
        tk = str(ledger.at[idx, "ticker"])
        realized = lookup.get((rb, tk))
        if realized is None:
            continue
        original_mu = float(ledger.at[idx, "mu_hat"])
        mu = original_mu
        ledger.at[idx, "realized_target"] = realized
        ledger.at[idx, "prediction_error"] = mu - realized
        if realized != 0 and mu != 0:
            ledger.at[idx, "signed_hit"] = bool(np.sign(mu) == np.sign(realized))
        ledger.at[idx, "status"] = "mature"
        ledger.at[idx, "matured_at_utc"] = now
        if float(ledger.at[idx, "mu_hat"]) != original_mu:
            raise RuntimeError("immutable prediction field mu_hat would be modified")
        updated += 1

    if updated:
        _atomic_write_parquet(ledger_path(out_dir), ledger)
        _write_ledger_meta(out_dir)
        write_outcomes_parquet(out_dir)
    return updated


def compute_feedback_metrics(ledger: pd.DataFrame) -> Dict[str, Any]:
    if ledger.empty:
        return {"n_total": 0, "n_mature": 0, "n_pending": 0}
    mature = ledger[ledger["status"] == "mature"].copy()
    pending = ledger[ledger["status"] == "pending"]
    out: Dict[str, Any] = {
        "n_total": int(len(ledger)),
        "n_mature": int(len(mature)),
        "n_pending": int(len(pending)),
    }
    if mature.empty:
        return out

    err = pd.to_numeric(mature["prediction_error"], errors="coerce").dropna()
    mu = pd.to_numeric(mature["mu_hat"], errors="coerce")
    realized = pd.to_numeric(mature["realized_target"], errors="coerce")
    valid = mu.notna() & realized.notna()
    if valid.any():
        out["ic_pearson"] = float(mu[valid].corr(realized[valid]))
        out["ic_spearman"] = float(mu[valid].corr(realized[valid], method="spearman"))
    if not err.empty:
        out["mae"] = float(err.abs().mean())
        out["rmse"] = float(np.sqrt((err ** 2).mean()))
    hits = mature["signed_hit"]
    hit_valid = hits.notna()
    if hit_valid.any():
        out["signed_hit_rate"] = float(hits[hit_valid].astype(float).mean())

    selected = mature[pd.to_numeric(mature["target_weight"], errors="coerce").fillna(0.0) > 0]
    out["n_mature_selected"] = int(len(selected))
    if not selected.empty:
        sel_err = pd.to_numeric(selected["prediction_error"], errors="coerce").dropna()
        if not sel_err.empty:
            out["selected_mae"] = float(sel_err.abs().mean())
        sel_hits = selected["signed_hit"]
        sel_hit_valid = sel_hits.notna()
        if sel_hit_valid.any():
            out["selected_signed_hit_rate"] = float(sel_hits[sel_hit_valid].astype(float).mean())

    by_rb = (
        mature.groupby(mature["rebalance_date"].dt.strftime("%Y-%m-%d"))["prediction_error"]
        .apply(lambda s: float(pd.to_numeric(s, errors="coerce").dropna().mean()) if s.notna().any() else np.nan)
        .dropna()
    )
    if not by_rb.empty:
        out["mean_error_by_rebalance"] = float(by_rb.mean())
        out["n_rebalance_periods"] = int(len(by_rb))
    return out


def write_feedback_report(out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    ledger = load_ledger(out_dir)
    metrics = compute_feedback_metrics(ledger)
    lines = [
        "Prediction Outcome Feedback Report",
        f"Generated: {_utc_now()}",
        "",
        f"Total predictions: {metrics.get('n_total', 0)}",
        f"Mature: {metrics.get('n_mature', 0)}",
        f"Pending: {metrics.get('n_pending', 0)}",
        "",
    ]
    if metrics.get("n_mature", 0) > 0:
        lines.extend(
            [
                "Mature cohort metrics",
                f"  IC (Pearson):  {metrics.get('ic_pearson', float('nan')):.4f}" if "ic_pearson" in metrics else "",
                f"  IC (Spearman): {metrics.get('ic_spearman', float('nan')):.4f}" if "ic_spearman" in metrics else "",
                f"  MAE:           {metrics.get('mae', float('nan')):.6f}" if "mae" in metrics else "",
                f"  RMSE:          {metrics.get('rmse', float('nan')):.6f}" if "rmse" in metrics else "",
                f"  Signed hit rate: {metrics.get('signed_hit_rate', float('nan')):.2%}" if "signed_hit_rate" in metrics else "",
                "",
                f"Selected positions (weight>0): {metrics.get('n_mature_selected', 0)}",
            ]
        )
        if "selected_mae" in metrics:
            lines.append(f"  Selected MAE: {metrics['selected_mae']:.6f}")
        if "selected_signed_hit_rate" in metrics:
            lines.append(f"  Selected hit rate: {metrics['selected_signed_hit_rate']:.2%}")
        if "n_rebalance_periods" in metrics:
            lines.append(f"  Rebalance periods with mature outcomes: {metrics['n_rebalance_periods']}")
    else:
        lines.append("No mature predictions yet — run feedback_update after horizon elapses.")
    lines = [ln for ln in lines if ln is not None]
    text = "\n".join(lines) + "\n"
    return atomic_write_text(feedback_report_path(out_dir), text)


def update_prediction_outcomes(
    out_dir: Path,
    *,
    variant_id: str = "",
    source_run_id: str = "",
    horizon: int = 10,
    decisions_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append new predictions, mature pending rows, write feedback report."""
    out_dir = Path(out_dir)
    added = append_predictions_from_decisions(
        out_dir,
        decisions_path=decisions_path,
        variant_id=variant_id,
        source_run_id=source_run_id,
        horizon=horizon,
    )
    matured = mature_pending_from_decisions(out_dir, decisions_path=decisions_path)
    report_path = write_feedback_report(out_dir)
    write_outcomes_parquet(out_dir)
    write_prediction_feedback_summary(out_dir)
    metrics = compute_feedback_metrics(load_ledger(out_dir))
    return {
        "added": added,
        "matured": matured,
        "report_path": str(report_path),
        "metrics": metrics,
    }


def sync_outcome_ledger_from_out_dir(
    out_dir: Path,
    *,
    run_id: str = "",
    variant_id: str = "",
    horizon: int = 10,
) -> Dict[str, Any]:
    """Called after validated publish — idempotent ledger sync."""
    return update_prediction_outcomes(
        out_dir,
        variant_id=variant_id,
        source_run_id=run_id,
        horizon=horizon,
    )


def ledger_status_label(out_dir: Path) -> str:
    path = ledger_path(out_dir)
    if not path.is_file():
        return "EMPTY"
    ledger = load_ledger(out_dir)
    if ledger.empty:
        return "EMPTY"
    if (ledger["status"] == "mature").any():
        return "ACTIVE"
    return "PENDING"
