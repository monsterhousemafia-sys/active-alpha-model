"""Multiple-testing adjustment evidence (V2 / V2R)."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_cost_stress import CHALLENGER, M1_VARIANT, _load_daily_returns, file_sha256, resolve_variant_sources
from aa_evidence_schema import resolve_locked_champion
from aa_safe_io import atomic_write_json

EVIDENCE_PATH = Path("control") / "evidence" / "multiple_testing_status.json"
DSR_REQUIRED_PROBABILITY = 0.95


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normal_cdf(x: float) -> float:
    try:
        from scipy.stats import norm

        return float(norm.cdf(x))
    except Exception:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _inverse_normal_cdf(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    try:
        from scipy.stats import norm

        return float(norm.ppf(p))
    except Exception:
        t = math.sqrt(-2.0 * math.log(1.0 - (p if p >= 0.5 else 1.0 - p)))
        c0, c1, c2 = 2.515517, 0.802853, 0.010328
        d1, d2, d3 = 1.432788, 0.189269, 0.001308
        sign = -1.0 if p < 0.5 else 1.0
        return sign * (t - (c0 + c1 * t + c2 * t * t) / (1.0 + d1 * t + d2 * t * t + d3 * t * t * t))


def derive_trial_count(root: Path) -> Tuple[Optional[int], List[Dict[str, str]], str, str]:
    root = Path(root)
    sources: List[Dict[str, str]] = []
    ids: List[str] = []

    report_path = root / "control" / "challenger_report.json"
    if report_path.is_file():
        report = _read_json(report_path)
        sources.append({"path": "control/challenger_report.json", "sha256": file_sha256(report_path)})
        for entry in report.get("entries") or []:
            vid = entry.get("variant_id")
            if vid:
                ids.append(str(vid))

    naive_rel = (
        "runs/20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce/naive_momentum_daily_returns.csv"
    )
    naive_path = root / naive_rel.replace("/", "\\") if False else root / naive_rel
    if naive_path.is_file():
        sources.append({"path": naive_rel, "sha256": file_sha256(naive_path)})
        try:
            frame = pd.read_csv(naive_path, nrows=0)
            for col in frame.columns:
                if str(col).startswith("NAIVE_MOMENTUM_"):
                    ids.append(str(col))
        except Exception:
            pass

    unique = sorted(set(ids))
    if not unique:
        return None, sources, "no auditable variant ids found", "Variants assumed non-independent (matrix + naive overlap possible)"

    derivation = f"unique variant ids from challenger_report entries ({len(report.get('entries') or []) if report_path.is_file() else 0}) + naive momentum columns"
    return len(unique), sources, derivation, "Variants treated as non-independent unless externally validated"


def deflated_sharpe_ratio(
    daily_returns: pd.Series,
    n_trials: int,
    *,
    skew: Optional[float] = None,
    kurtosis: Optional[float] = None,
) -> Dict[str, Any]:
    r = daily_returns.dropna().astype(float)
    n_obs = len(r)
    if n_obs < 30 or n_trials < 1:
        return {"status": "NOT_EVALUABLE", "reason": "invalid inputs"}

    periodic_sharpe = float(r.mean() / r.std()) if r.std() > 0 else float("nan")
    if not np.isfinite(periodic_sharpe):
        return {"status": "NOT_EVALUABLE", "reason": "non-finite periodic sharpe"}

    skew_val = float(skew if skew is not None else r.skew())
    kurt_val = float(kurtosis if kurtosis is not None else r.kurtosis() + 3.0)
    sr_std = math.sqrt(
        (1.0 - skew_val * periodic_sharpe + ((kurt_val - 1.0) / 4.0) * (periodic_sharpe**2))
        / max(n_obs - 1, 1)
    )
    if sr_std <= 0:
        return {"status": "NOT_EVALUABLE", "reason": "non-positive sharpe std"}

    euler = 0.5772156649
    expected_max = (1.0 - euler) * _inverse_normal_cdf(1.0 - 1.0 / n_trials) + euler * _inverse_normal_cdf(
        1.0 - 1.0 / (n_trials * math.e)
    )
    expected_max_sr = expected_max * sr_std
    test_statistic = (periodic_sharpe - expected_max_sr) / sr_std
    dsr_probability = _normal_cdf(test_statistic)
    annualized_sharpe = periodic_sharpe * math.sqrt(252)

    status = "PASS" if dsr_probability >= DSR_REQUIRED_PROBABILITY else "FAIL"
    if dsr_probability < DSR_REQUIRED_PROBABILITY:
        blocker = "DSR_BELOW_REQUIRED_CONFIDENCE"
    else:
        blocker = None

    return {
        "status": status,
        "periodic_sharpe": periodic_sharpe,
        "annualized_sharpe_display_only": annualized_sharpe,
        "observations_T": n_obs,
        "observation_frequency": "daily",
        "test_statistic": float(test_statistic),
        "dsr_probability": float(dsr_probability),
        "dsr_required_probability": DSR_REQUIRED_PROBABILITY,
        "expected_max_sharpe": float(expected_max_sr),
        "sharpe_std": float(sr_std),
        "blocker": blocker,
    }


def build_multiple_testing_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    n_trials, trial_sources, derivation, independence = derive_trial_count(root)
    challenger_src = resolve_variant_sources(root).get(CHALLENGER, {})
    path = root / str(challenger_src.get("returns_path") or "")
    returns = _load_daily_returns(path, challenger_src.get("returns_column"))

    if n_trials is None:
        return {
            "schema_version": 2,
            "generated_at_utc": _utc_now(),
            "tested_variant_count": None,
            "trial_count_source_files": trial_sources,
            "trial_count_derivation": derivation,
            "independence_assumption": independence,
            "MULTIPLE_TESTING_EVIDENCE": {
                "pass": False,
                "status": "NOT_EVALUABLE",
                "blocker": "TESTED_VARIANT_COUNT_NOT_VERIFIED",
            },
            "PBO_STATUS": "NOT_EVALUABLE",
            "PBO_BLOCKER": "INSUFFICIENT_CANDIDATE_MATRIX_FOR_PBO",
        }

    if returns is None or returns.empty:
        return {
            "schema_version": 2,
            "generated_at_utc": _utc_now(),
            "tested_variant_count": n_trials,
            "MULTIPLE_TESTING_EVIDENCE": {"pass": False, "status": "NOT_EVALUABLE", "detail": "challenger returns missing"},
            "PBO_STATUS": "NOT_EVALUABLE",
            "PBO_BLOCKER": "INSUFFICIENT_CANDIDATE_MATRIX_FOR_PBO",
        }

    dsr = deflated_sharpe_ratio(returns, n_trials)
    mt_pass = dsr.get("status") == "PASS"

    return {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_HISTORICAL_EVIDENCE",
        "tested_variant_count": n_trials,
        "trial_count_source_files": trial_sources,
        "trial_count_source_hashes": {s["path"]: s["sha256"] for s in trial_sources},
        "trial_count_derivation": derivation,
        "independence_assumption": independence,
        "challenger_variant_id": CHALLENGER,
        "champion_variant_id": resolve_locked_champion(root),
        "m1_variant_id": M1_VARIANT,
        "return_series_path": str(challenger_src.get("returns_path")),
        "return_series_sha256": file_sha256(path) if path.is_file() else "",
        "observations": int(len(returns.dropna())),
        "deflated_sharpe": dsr,
        "MULTIPLE_TESTING_EVIDENCE": {
            "pass": mt_pass,
            "status": dsr.get("status", "NOT_EVALUABLE"),
            "detail": f"dsr_probability={dsr.get('dsr_probability')} trials={n_trials}",
            "blocker": dsr.get("blocker"),
        },
        "PBO_STATUS": "NOT_EVALUABLE",
        "PBO_BLOCKER": "INSUFFICIENT_CANDIDATE_MATRIX_FOR_PBO",
    }


def export_multiple_testing_status(root: Path) -> Path:
    root = Path(root)
    path = root / EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_multiple_testing_status(root))
    return path
