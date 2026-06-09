"""P4 shadow champion framework — registries, shadow signals, promotion gates (no auto-promote)."""
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

from aa_challenger_eval import evaluate_promotion_gate, resolve_champion_variant
from aa_recovery import load_last_known_good
from aa_safe_io import atomic_write_json

CHAMPION_REGISTRY = "champion_registry.json"
CHALLENGER_REGISTRY = "challenger_registry.json"
SHADOW_SIGNALS_FILE = "shadow_signals.parquet"
SHADOW_OUTCOMES_FILE = "shadow_outcomes.parquet"
PROMOTION_STATUS_FILE = "promotion_status.json"
ROLLBACK_REGISTRY_FILE = "rollback_registry.json"

PROMOTION_GATES = (
    "INTEGRITY_GATE",
    "DATA_QUALITY_GATE",
    "FORECAST_QUALITY_GATE",
    "ECONOMIC_VALUE_GATE",
    "RISK_GATE",
    "COST_STRESS_GATE",
    "SHADOW_GATE",
    "ROLLBACK_READINESS_GATE",
)

SHADOW_SIGNAL_COLUMNS = (
    "shadow_id",
    "champion_variant_id",
    "challenger_variant_id",
    "signal_role",
    "rebalance_date",
    "signal_date",
    "ticker",
    "target_weight",
    "mu_hat",
    "selection_score",
    "recorded_at_utc",
)

SHADOW_OUTCOME_COLUMNS = (
    "shadow_id",
    "challenger_variant_id",
    "outcome_status",
    "realized_return",
    "prediction_error",
    "matured_at_utc",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


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


def make_shadow_id(*, challenger: str, rebalance_date: str, ticker: str) -> str:
    raw = f"shadow|{challenger}|{rebalance_date}|{ticker}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def load_shadow_signals(out_dir: Path) -> pd.DataFrame:
    path = Path(out_dir) / SHADOW_SIGNALS_FILE
    if not path.is_file():
        return pd.DataFrame(columns=list(SHADOW_SIGNAL_COLUMNS))
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame(columns=list(SHADOW_SIGNAL_COLUMNS))
    for col in SHADOW_SIGNAL_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame[list(SHADOW_SIGNAL_COLUMNS)]


def load_shadow_outcomes(out_dir: Path) -> pd.DataFrame:
    path = Path(out_dir) / SHADOW_OUTCOMES_FILE
    if not path.is_file():
        return pd.DataFrame(columns=list(SHADOW_OUTCOME_COLUMNS))
    try:
        frame = pd.read_parquet(path)
    except Exception:
        return pd.DataFrame(columns=list(SHADOW_OUTCOME_COLUMNS))
    for col in SHADOW_OUTCOME_COLUMNS:
        if col not in frame.columns:
            frame[col] = np.nan
    return frame[list(SHADOW_OUTCOME_COLUMNS)]


def _resolve_shadow_challenger(root: Path, out_dir: Path) -> Tuple[str, Optional[Path]]:
    """Pick shadow challenger with decision artifacts (prefer best research candidate)."""
    research = _read_json(out_dir / "background_research_status.json")
    if not research:
        research = _read_json(root / "control" / "background_research_status.json")
    best_id = str((research.get("best_research_candidate") or {}).get("variant_id", "") or "")
    entries = {str(e.get("variant_id")): e for e in research.get("entries") or []}

    def _dir_for(vid: str) -> Optional[Path]:
        entry = entries.get(vid) or {}
        rd = str(entry.get("run_dir") or entry.get("reference_source") or "")
        if rd:
            p = Path(rd)
            if (p / "backtest_decisions.csv").is_file():
                return p
        return None

    if best_id:
        p = _dir_for(best_id)
        if p is not None:
            return best_id, p
    for entry in research.get("entries") or []:
        if entry.get("is_research_candidate") and entry.get("integrity_pass"):
            vid = str(entry.get("variant_id", ""))
            p = _dir_for(vid)
            if p is not None:
                return vid, p
    return "", None


def build_champion_registry(out_dir: Path) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    pointer = _read_json(out_dir / "latest_validated_run.json")
    return {
        "updated_at_utc": _utc_now(),
        "variant_id": str(pointer.get("variant_id", resolve_champion_variant(out_dir))),
        "run_id": str(pointer.get("run_id", "") or ""),
        "run_dir": str(pointer.get("run_dir", "") or ""),
        "integrity_status": str(pointer.get("integrity_status", pointer.get("status", "NOT_VALIDATED"))),
        "active": True,
        "role": "CHAMPION",
        "auto_promotion": "DISABLED",
    }


def build_challenger_registry(root: Path, out_dir: Path, *, shadow_challenger_id: str) -> Dict[str, Any]:
    root = Path(root)
    base = _read_json(root / CHALLENGER_REGISTRY)
    research = _read_json(out_dir / "background_research_status.json")
    shadow_entries: List[Dict[str, Any]] = []
    for entry in research.get("entries") or []:
        if not entry.get("is_research_candidate"):
            continue
        shadow_entries.append(
            {
                "id": entry.get("variant_id"),
                "role": "shadow",
                "status": "active" if entry.get("variant_id") == shadow_challenger_id else "standby",
                "enabled": True,
                "promoted": False,
                "integrity_pass": bool(entry.get("integrity_pass")),
            }
        )
    planned = list(base.get("challengers") or [])
    return {
        "updated_at_utc": _utc_now(),
        "auto_promotion": "DISABLED",
        "shadow_challenger_id": shadow_challenger_id or "",
        "challengers": shadow_entries + planned,
    }


def append_shadow_signals(
    out_dir: Path,
    *,
    champion_variant: str,
    challenger_variant: str,
    decisions_path: Path,
) -> int:
    out_dir = Path(out_dir)
    if not decisions_path.is_file():
        return 0
    usecols = [c for c in ("rebalance_date", "date", "ticker", "target_weight", "mu_hat", "selection_score", "target") if c in pd.read_csv(decisions_path, nrows=0).columns]
    decisions = pd.read_csv(decisions_path, usecols=usecols)
    if decisions.empty or "rebalance_date" not in decisions.columns:
        return 0
    decisions["rebalance_date"] = pd.to_datetime(decisions["rebalance_date"], errors="coerce")
    if "date" in decisions.columns:
        decisions["signal_date"] = pd.to_datetime(decisions["date"], errors="coerce")
    else:
        decisions["signal_date"] = decisions["rebalance_date"]
    decisions["target_weight"] = pd.to_numeric(decisions.get("target_weight"), errors="coerce").fillna(0.0)
    decisions = decisions[decisions["target_weight"] > 0].copy()
    if decisions.empty:
        return 0

    existing = load_shadow_signals(out_dir)
    existing_ids = set(existing["shadow_id"].astype(str).tolist()) if not existing.empty else set()
    now = _utc_now()
    rows: List[Dict[str, Any]] = []
    for rec in decisions.to_dict(orient="records"):
        rb = pd.Timestamp(rec["rebalance_date"])
        tk = str(rec["ticker"])
        sid = make_shadow_id(challenger=challenger_variant, rebalance_date=rb.strftime("%Y-%m-%d"), ticker=tk)
        if sid in existing_ids:
            continue
        rows.append(
            {
                "shadow_id": sid,
                "champion_variant_id": champion_variant,
                "challenger_variant_id": challenger_variant,
                "signal_role": "SHADOW",
                "rebalance_date": rb,
                "signal_date": pd.Timestamp(rec.get("signal_date", rb)),
                "ticker": tk,
                "target_weight": float(rec["target_weight"]),
                "mu_hat": float(rec["mu_hat"]) if pd.notna(rec.get("mu_hat")) else np.nan,
                "selection_score": float(rec["selection_score"]) if pd.notna(rec.get("selection_score")) else np.nan,
                "recorded_at_utc": now,
            }
        )
    if not rows:
        return 0
    merged = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    _atomic_write_parquet(out_dir / SHADOW_SIGNALS_FILE, merged)
    return len(rows)


def sync_shadow_outcomes(out_dir: Path, *, decisions_path: Path) -> int:
    out_dir = Path(out_dir)
    signals = load_shadow_signals(out_dir)
    if signals.empty or not decisions_path.is_file():
        return 0
    decisions = pd.read_csv(decisions_path, usecols=lambda c: c in {"rebalance_date", "ticker", "target", "mu_hat"})
    if decisions.empty or "target" not in decisions.columns:
        return 0
    decisions["rebalance_date"] = pd.to_datetime(decisions["rebalance_date"], errors="coerce")
    lookup: Dict[Tuple[str, str], float] = {}
    for rec in decisions.to_dict(orient="records"):
        if pd.isna(rec.get("target")):
            continue
        rb = pd.Timestamp(rec["rebalance_date"]).strftime("%Y-%m-%d")
        lookup[(rb, str(rec["ticker"]))] = float(rec["target"])

    outcomes = load_shadow_outcomes(out_dir)
    existing_ids = set(outcomes["shadow_id"].astype(str).tolist()) if not outcomes.empty else set()
    now = _utc_now()
    added = 0
    new_rows: List[Dict[str, Any]] = []
    for rec in signals.to_dict(orient="records"):
        sid = str(rec["shadow_id"])
        if sid in existing_ids:
            continue
        rb = pd.Timestamp(rec["rebalance_date"]).strftime("%Y-%m-%d")
        tk = str(rec["ticker"])
        realized = lookup.get((rb, tk))
        if realized is None:
            continue
        mu = rec.get("mu_hat")
        err = float(mu) - realized if pd.notna(mu) else np.nan
        new_rows.append(
            {
                "shadow_id": sid,
                "challenger_variant_id": rec.get("challenger_variant_id"),
                "outcome_status": "MATURE",
                "realized_return": realized,
                "prediction_error": err,
                "matured_at_utc": now,
            }
        )
        added += 1
    if new_rows:
        merged = pd.concat([outcomes, pd.DataFrame(new_rows)], ignore_index=True)
        _atomic_write_parquet(out_dir / SHADOW_OUTCOMES_FILE, merged)
    return added


def evaluate_promotion_gates(root: Path, out_dir: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = Path(out_dir)
    champion = build_champion_registry(out_dir)
    lkg = load_last_known_good(root / "control")
    feedback = _read_json(out_dir / "prediction_feedback_summary.json")
    shadow_n = int(len(load_shadow_signals(out_dir)))
    mature_shadow = int(len(load_shadow_outcomes(out_dir)))
    champion_integrity = str(champion.get("integrity_status", "")).upper() == "PASS"
    gates = {
        "INTEGRITY_GATE": {"pass": champion_integrity, "detail": champion.get("integrity_status", "")},
        "DATA_QUALITY_GATE": {"pass": (out_dir / "data_quality_report.csv").is_file(), "detail": "data_quality_report.csv"},
        "FORECAST_QUALITY_GATE": {
            "pass": int(feedback.get("mature_outcomes", 0) or 0) > 0,
            "detail": f"mature_outcomes={feedback.get('mature_outcomes', 0)}",
        },
        "ECONOMIC_VALUE_GATE": {"pass": False, "detail": "auto promotion disabled in P4"},
        "RISK_GATE": {"pass": champion_integrity, "detail": "champion validated"},
        "COST_STRESS_GATE": {"pass": None, "detail": "not evaluated in P4"},
        "SHADOW_GATE": {"pass": shadow_n > 0, "detail": f"shadow_signals={shadow_n}"},
        "ROLLBACK_READINESS_GATE": {
            "pass": bool(lkg.get("validated_run_id")),
            "detail": str(lkg.get("validated_run_id", "") or ""),
        },
    }
    all_required = all(
        gates[g]["pass"] is True for g in PROMOTION_GATES if gates[g]["pass"] is not None
    )
    gate_eval = evaluate_promotion_gate(
        champion={"integrity_pass": champion_integrity, "metrics": {"sharpe_0rf": 0.0}, "n_days": 300},
        m1=None,
    )
    return {
        "updated_at_utc": _utc_now(),
        "auto_promotion_enabled": False,
        "auto_execute_real_money": False,
        "overall_status": "BLOCKED",
        "all_gates_pass": all_required,
        "gates": gates,
        "blocked_reasons": list(gate_eval.get("blocked_reasons") or ["auto_promotion_disabled"]),
        "shadow_signal_count": shadow_n,
        "mature_shadow_comparisons": mature_shadow,
    }


def build_rollback_registry(root: Path) -> Dict[str, Any]:
    root = Path(root)
    lkg = load_last_known_good(root / "control")
    return {
        "updated_at_utc": _utc_now(),
        "rollback_available": bool(lkg.get("validated_run_id")),
        "target_run_id": str(lkg.get("validated_run_id", lkg.get("run_id", "")) or ""),
        "target_variant_id": str(lkg.get("validated_variant_id", lkg.get("variant_id", "")) or ""),
        "artifact_hashes": dict(lkg.get("artifact_hashes") or {}),
        "out_dir": str(lkg.get("out_dir", "") or ""),
    }


def shadow_status_summary(out_dir: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    root = root or out_dir.parent
    champion = _read_json(out_dir / CHAMPION_REGISTRY) or build_champion_registry(out_dir)
    challenger = _read_json(out_dir / CHALLENGER_REGISTRY) or _read_json(root / CHALLENGER_REGISTRY)
    promotion = _read_json(out_dir / PROMOTION_STATUS_FILE)
    rollback = _read_json(out_dir / ROLLBACK_REGISTRY_FILE) or build_rollback_registry(root)
    return {
        "active_champion_variant": str(champion.get("variant_id", "")),
        "shadow_challenger_variant": str(challenger.get("shadow_challenger_id", "")),
        "shadow_signal_count": int(promotion.get("shadow_signal_count", len(load_shadow_signals(out_dir))) or 0),
        "mature_shadow_comparisons": int(promotion.get("mature_shadow_comparisons", len(load_shadow_outcomes(out_dir))) or 0),
        "promotion_status": str(promotion.get("overall_status", "BLOCKED")),
        "rollback_available": bool(rollback.get("rollback_available")),
    }


def run_shadow_champion_sync(root: Path, out_dir: Path) -> Dict[str, Any]:
    """Sync P4 registries and shadow artifacts without changing the active champion."""
    root = Path(root)
    out_dir = Path(out_dir)
    champion_variant = resolve_champion_variant(out_dir)
    shadow_id, shadow_dir = _resolve_shadow_challenger(root, out_dir)

    champion_reg = build_champion_registry(out_dir)
    atomic_write_json(out_dir / CHAMPION_REGISTRY, champion_reg)
    atomic_write_json(root / "control" / CHAMPION_REGISTRY, champion_reg)

    challenger_reg = build_challenger_registry(root, out_dir, shadow_challenger_id=shadow_id)
    atomic_write_json(out_dir / CHALLENGER_REGISTRY, challenger_reg)
    atomic_write_json(root / CHALLENGER_REGISTRY, challenger_reg)

    added_signals = 0
    added_outcomes = 0
    if shadow_id and shadow_dir is not None:
        decisions = shadow_dir / "backtest_decisions.csv"
        added_signals = append_shadow_signals(
            out_dir,
            champion_variant=champion_variant,
            challenger_variant=shadow_id,
            decisions_path=decisions,
        )
        added_outcomes = sync_shadow_outcomes(out_dir, decisions_path=decisions)

    promotion = evaluate_promotion_gates(root, out_dir)
    atomic_write_json(out_dir / PROMOTION_STATUS_FILE, promotion)
    atomic_write_json(root / "control" / PROMOTION_STATUS_FILE, promotion)

    rollback = build_rollback_registry(root)
    atomic_write_json(out_dir / ROLLBACK_REGISTRY_FILE, rollback)
    atomic_write_json(root / "control" / ROLLBACK_REGISTRY_FILE, rollback)

    return {
        "status": "OK",
        "champion_variant": champion_variant,
        "shadow_challenger": shadow_id,
        "shadow_signals_added": added_signals,
        "shadow_outcomes_added": added_outcomes,
        "promotion_status": promotion.get("overall_status"),
        "rollback_available": rollback.get("rollback_available"),
    }
