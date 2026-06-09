"""Read-only cost stress evidence engine (V2 / V2R)."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from aa_evidence_schema import LEGACY_V2_COST_STRESS_LABEL, resolve_locked_champion
from aa_reporting import calculate_metrics
from aa_safe_io import atomic_write_json

EVIDENCE_PATH = Path("control") / "evidence" / "cost_stress_status.json"

CHAMPION = LEGACY_V2_COST_STRESS_LABEL  # historical V2 label only; use resolve_locked_champion(root)
M1_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"
CHALLENGER = "MOM_63_TOP12"

SCENARIOS: Dict[str, Any] = {
    "BASELINE": {"extra_bps": 0, "kind": "incremental_bps"},
    "PLUS_10_BPS": {"extra_bps": 10, "kind": "incremental_bps"},
    "PLUS_25_BPS": {"extra_bps": 25, "kind": "incremental_bps"},
    "PLUS_50_BPS": {"extra_bps": 50, "kind": "incremental_bps"},
    "SLIPPAGE_TURNOVER_STRESS": {"multiplier": 2.0, "kind": "turnover_multiplier"},
}

APPROVED_STRESS_SCENARIO = "PLUS_25_BPS"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_daily_returns(path: Path, column: Optional[str] = None) -> Optional[pd.Series]:
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        if column and column in frame.columns:
            col = column
        elif "strategy_return" in frame.columns:
            col = "strategy_return"
        else:
            col = frame.columns[0]
        series = pd.to_numeric(frame[col], errors="coerce").dropna()
        series.index = pd.to_datetime(series.index)
        return series.sort_index()
    except Exception:
        return None


def _load_rebalance_turnover(decisions_path: Path) -> Optional[pd.Series]:
    if not decisions_path.is_file():
        return None
    try:
        frame = pd.read_csv(
            decisions_path,
            usecols=lambda c: c in {"rebalance_date", "turnover", "selected_canonical_turnover"},
        )
        turn_col = "turnover" if "turnover" in frame.columns else (
            "selected_canonical_turnover" if "selected_canonical_turnover" in frame.columns else None
        )
        if "rebalance_date" not in frame.columns or turn_col is None:
            return None
        rb = frame.drop_duplicates("rebalance_date").copy()
        rb["rebalance_date"] = pd.to_datetime(rb["rebalance_date"])
        turnover = pd.to_numeric(rb[turn_col], errors="coerce").dropna()
        return pd.Series(turnover.values, index=rb["rebalance_date"].values).sort_index()
    except Exception:
        return None


def _latest_validation_dir(root: Path, suffix: str) -> Optional[Path]:
    """Newest validation_runs/*_{suffix} with a returns artefact."""
    vroot = Path(root) / "validation_runs"
    if not vroot.is_dir():
        return None
    candidates = sorted(
        (p for p in vroot.iterdir() if p.is_dir() and p.name.endswith(f"_{suffix}")),
        key=lambda p: p.name,
        reverse=True,
    )
    for run in candidates:
        if any((run / name).is_file() for name in ("strategy_daily_returns.csv", "mom_blend_matched_controls_daily_returns.csv")):
            return run
    return candidates[0] if candidates else None


def verify_baseline_cost_treatment(root: Path, source: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    proof_path = source.get("baseline_cost_proof_path")
    if proof_path:
        path = root / str(proof_path)
        if path.is_file():
            suffix = path.suffix.lower()
            if suffix == ".csv":
                try:
                    frame = pd.read_csv(path, nrows=5)
                    cols = {str(c).lower() for c in frame.columns}
                    verified = bool(cols & {"tx_cost", "slippage_cost", "commission_cost", "execution_cost"})
                    return {
                        "verified": verified,
                        "source_path": str(proof_path),
                        "source_sha256": file_sha256(path),
                        "interpretation": "Execution cost ledger documents tx_cost / slippage fields"
                        if verified
                        else "CSV lacks execution cost columns",
                    }
                except Exception:
                    pass
            text = path.read_text(encoding="utf-8", errors="replace")
            has_cost = bool(re.search(r"cost_bps\s*:", text, re.I)) or "tx_cost" in text.lower()
            has_fee = "fee_model" in text.lower() or "trading212" in text.lower()
            verified = has_cost or has_fee
            return {
                "verified": verified,
                "source_path": str(proof_path),
                "source_sha256": file_sha256(path),
                "interpretation": "Baseline transaction costs documented in backtest report" if verified else "Report lacks cost fields",
            }
    return {
        "verified": False,
        "source_path": None,
        "source_sha256": None,
        "interpretation": "No readable baseline cost proof artifact",
    }


def resolve_variant_sources(root: Path) -> Dict[str, Dict[str, Any]]:
    root = Path(root)
    out: Dict[str, Dict[str, Any]] = {}
    champion_id = resolve_locked_champion(root)

    champ_ret = root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv"
    champ_dec = root / "model_output_sp500_pit_t212" / "backtest_decisions.csv"
    champ_report = root / "model_output_sp500_pit_t212" / "backtest_report.txt"
    if not champ_ret.is_file():
        fallback = _latest_validation_dir(root, champion_id) or _latest_validation_dir(root, "R3_w075_q065_noexit")
        if fallback is not None:
            if (fallback / "strategy_daily_returns.csv").is_file():
                champ_ret = fallback / "strategy_daily_returns.csv"
            if (fallback / "backtest_decisions.csv").is_file():
                champ_dec = fallback / "backtest_decisions.csv"
            if (fallback / "backtest_report.txt").is_file():
                champ_report = fallback / "backtest_report.txt"
    out[champion_id] = {
        "returns_path": str(champ_ret.relative_to(root)).replace("\\", "/"),
        "decisions_path": str(champ_dec.relative_to(root)).replace("\\", "/"),
        "returns_column": "strategy_return",
        "baseline_cost_proof_path": str(champ_report.relative_to(root)).replace("\\", "/") if champ_report.is_file() else None,
        "turnover_verified": True,
        "gate_eligible": True,
    }

    m1_dir = _latest_validation_dir(root, M1_VARIANT) or (root / "validation_runs" / "20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS")
    m1_ret = m1_dir / "mom_blend_matched_controls_daily_returns.csv"
    if not m1_ret.is_file():
        m1_ret = m1_dir / "strategy_daily_returns.csv"
    m1_report = m1_dir / "backtest_report.txt"
    out[M1_VARIANT] = {
        "returns_path": str(m1_ret.relative_to(root)).replace("\\", "/") if m1_ret.is_file() else "",
        "decisions_path": str((m1_dir / "backtest_decisions.csv").relative_to(root)).replace("\\", "/"),
        "returns_column": None,
        "baseline_cost_proof_path": str(m1_report.relative_to(root)).replace("\\", "/") if m1_report.is_file() else None,
        "turnover_verified": True,
        "gate_eligible": True,
    }

    naive_path = (
        root
        / "runs"
        / "20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce"
        / "naive_momentum_daily_returns.csv"
    )
    g1_base = root / "evidence" / "g1_independent_next_level" / "challenger" / CHALLENGER
    g1_legacy_turnover = g1_base / "turnover" / "rebalance_turnover.csv"
    ar_turnover = (
        root
        / "evidence"
        / "autonomous_research"
        / "MOM_63_TOP15_RECONSTRUCTED"
        / "turnover_ledgers"
        / "turnover_ledger.csv"
    )
    challenger_dec_path = g1_legacy_turnover if g1_legacy_turnover.is_file() else (
        ar_turnover if ar_turnover.is_file() else None
    )
    g1_ret = g1_base / "daily_returns.csv"
    ar_ret = root / "evidence" / "autonomous_research" / "MOM_63_TOP15_RECONSTRUCTED" / "daily_returns.csv"
    challenger_ret_path = g1_ret if g1_ret.is_file() else (ar_ret if ar_ret.is_file() else naive_path)
    challenger_cost_proof = g1_base / "costs" / "execution_costs.csv"
    if not challenger_cost_proof.is_file():
        challenger_cost_proof = root / "evidence" / "autonomous_research" / "MOM_63_TOP15_RECONSTRUCTED" / "execution_costs.csv"
    baseline_proof = challenger_cost_proof if challenger_cost_proof.is_file() else (
        m1_report if m1_report.is_file() else champ_report
    )
    out[CHALLENGER] = {
        "returns_path": str(challenger_ret_path.relative_to(root)).replace("\\", "/") if challenger_ret_path.is_file() else "",
        "returns_column": "strategy_return" if g1_ret.is_file() else "NAIVE_MOMENTUM_MOM_63_TOP12",
        "decisions_path": str(challenger_dec_path.relative_to(root)).replace("\\", "/") if challenger_dec_path else "",
        "baseline_cost_proof_path": str(baseline_proof.relative_to(root)).replace("\\", "/") if baseline_proof.is_file() else None,
        "turnover_verified": bool(challenger_dec_path and challenger_dec_path.is_file()),
        "gate_eligible": bool(challenger_dec_path and challenger_dec_path.is_file() and challenger_ret_path.is_file()),
        "turnover_proxy_variant": None if challenger_dec_path else champion_id,
    }
    return out


def apply_incremental_cost_stress(
    daily_returns: pd.Series,
    rebalance_turnover: pd.Series,
    *,
    extra_bps: float = 0.0,
    turnover_multiplier: float = 1.0,
) -> Tuple[pd.Series, Dict[str, Any]]:
    stressed = daily_returns.copy()
    if rebalance_turnover is None or rebalance_turnover.empty:
        return stressed, {"applied": False, "reason": "turnover_missing"}

    total_drag = 0.0
    applied_events = 0
    for rb_date, turn in rebalance_turnover.items():
        rb_ts = pd.Timestamp(rb_date)
        incremental = (float(extra_bps) / 10000.0) * float(turn)
        if turnover_multiplier != 1.0:
            incremental += ((float(turnover_multiplier) - 1.0) * float(turn) * 0.0002)
        match_idx = stressed.index[stressed.index >= rb_ts]
        if len(match_idx) == 0:
            continue
        target = match_idx[0]
        if target in stressed.index:
            stressed.loc[target] = stressed.loc[target] - incremental
            total_drag += incremental
            applied_events += 1

    return stressed, {
        "applied": applied_events > 0,
        "events": applied_events,
        "total_drag": total_drag,
        "extra_bps": extra_bps,
        "turnover_multiplier": turnover_multiplier,
    }


def _resolve_turnover_path(root: Path, variant_id: str, source: Dict[str, Any], *, allow_proxy: bool) -> Tuple[Optional[Path], bool]:
    dec_rel = str(source.get("decisions_path") or "")
    if dec_rel:
        return root / dec_rel, False
    if allow_proxy and source.get("turnover_proxy_variant"):
        proxy = resolve_variant_sources(root).get(str(source["turnover_proxy_variant"]), {})
        proxy_dec = str(proxy.get("decisions_path") or "")
        if proxy_dec:
            return root / proxy_dec, True
    return None, False


def evaluate_variant_scenario(
    root: Path,
    variant_id: str,
    source: Dict[str, Any],
    scenario_name: str,
    scenario: Dict[str, Any],
    *,
    allow_turnover_proxy: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {
        "variant_id": variant_id,
        "scenario": scenario_name,
        "evaluation_status": "NOT_EVALUABLE",
        "comparison_result": "NOT_APPLICABLE",
        "metrics": {},
        "source_files": {},
        "baseline_cost_treatment": verify_baseline_cost_treatment(root, source),
        "turnover_is_proxy": False,
        "gate_evidence_eligible": bool(source.get("gate_eligible")),
        "reason": "",
    }

    ret_path = root / str(source.get("returns_path") or "")
    if not ret_path.is_file():
        result["reason"] = "returns_file_missing"
        return result

    returns = _load_daily_returns(ret_path, source.get("returns_column"))
    if returns is None or returns.empty:
        result["reason"] = "returns_unparseable"
        return result

    result["source_files"]["returns"] = {
        "path": str(source.get("returns_path")),
        "sha256": file_sha256(ret_path),
    }

    if not result["baseline_cost_treatment"].get("verified"):
        result["reason"] = "baseline_cost_treatment_not_verified"
        return result

    dec_path, is_proxy = _resolve_turnover_path(root, variant_id, source, allow_proxy=allow_turnover_proxy)
    if dec_path is None or not dec_path.is_file():
        result["reason"] = "turnover_missing"
        return result

    result["turnover_is_proxy"] = is_proxy
    turnover = _load_rebalance_turnover(dec_path)
    if turnover is None or turnover.empty:
        result["reason"] = "turnover_unparseable"
        return result

    result["source_files"]["turnover_decisions"] = {
        "path": str(dec_path.relative_to(root)).replace("\\", "/"),
        "sha256": file_sha256(dec_path),
        "is_proxy": is_proxy,
        "label": "NOT_GATE_EVIDENCE" if is_proxy else "VERIFIED_VARIANT_TURNOVER",
    }

    if is_proxy:
        result["reason"] = "turnover_proxy_only"
        return result

    if scenario.get("kind") == "turnover_multiplier":
        stressed, detail = apply_incremental_cost_stress(
            returns, turnover, extra_bps=0.0, turnover_multiplier=float(scenario.get("multiplier", 2.0))
        )
    else:
        stressed, detail = apply_incremental_cost_stress(
            returns, turnover, extra_bps=float(scenario.get("extra_bps", 0.0))
        )

    if not detail.get("applied") and scenario_name != "BASELINE":
        result["reason"] = "stress_not_applied"
        return result

    metrics = calculate_metrics(stressed)
    result["metrics"] = metrics
    result["stress_detail"] = detail
    result["evaluation_status"] = "EVALUABLE"
    result["comparison_result"] = "NOT_APPLICABLE"
    return result


def evaluate_cost_stress_gate(
    gate_scenarios: Dict[str, List[Dict[str, Any]]],
    *,
    blockers: List[str],
    champion_id: str,
) -> Dict[str, Any]:
    approved = APPROVED_STRESS_SCENARIO
    rows = gate_scenarios.get(approved, [])
    champ = next(
        (r for r in rows if r.get("variant_id") == champion_id and r.get("evaluation_status") == "EVALUABLE"),
        None,
    )
    m1 = next((r for r in rows if r.get("variant_id") == M1_VARIANT and r.get("evaluation_status") == "EVALUABLE"), None)
    chal = next(
        (r for r in rows if r.get("variant_id") == CHALLENGER and r.get("evaluation_status") == "EVALUABLE" and r.get("gate_evidence_eligible")),
        None,
    )

    if blockers:
        return {
            "pass": False,
            "evaluation_status": "NOT_EVALUABLE",
            "detail": "; ".join(blockers),
            "approved_scenario": approved,
            "blockers": blockers,
        }

    if not champ or not m1 or not chal:
        missing = []
        if not chal:
            missing.append("CHALLENGER_TURNOVER_NOT_VERIFIED")
        if not champ or not m1:
            missing.append("CHAMPION_OR_M1_NOT_EVALUABLE")
        return {
            "pass": False,
            "evaluation_status": "NOT_EVALUABLE",
            "detail": "gate inputs incomplete",
            "approved_scenario": approved,
            "blockers": missing,
        }

    c_sh = float(champ.get("metrics", {}).get("sharpe_0rf", float("nan")))
    m_sh = float(m1.get("metrics", {}).get("sharpe_0rf", float("nan")))
    h_sh = float(chal.get("metrics", {}).get("sharpe_0rf", float("nan")))
    beats_champion = bool(pd.notna(h_sh) and pd.notna(c_sh) and h_sh > c_sh)
    beats_m1 = bool(pd.notna(h_sh) and pd.notna(m_sh) and h_sh > m_sh)
    gate_pass = beats_champion and beats_m1

    for row in rows:
        if row.get("variant_id") == CHALLENGER:
            row["comparison_result"] = "PASS" if gate_pass else "FAIL"
        elif row.get("evaluation_status") == "EVALUABLE":
            row["comparison_result"] = "NOT_APPLICABLE"

    return {
        "pass": gate_pass,
        "evaluation_status": "PASS" if gate_pass else "FAIL",
        "approved_scenario": approved,
        "detail": f"challenger_sharpe={h_sh:.6f} champion_sharpe={c_sh:.6f} m1_sharpe={m_sh:.6f}",
        "beats_champion": beats_champion,
        "beats_m1": beats_m1,
        "blockers": [],
    }


def build_cost_stress_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    sources = resolve_variant_sources(root)
    scenario_results: Dict[str, List[Dict[str, Any]]] = {}
    sensitivity: Dict[str, List[Dict[str, Any]]] = {}
    blockers: List[str] = []

    chal_src = sources.get(CHALLENGER, {})
    if not chal_src.get("turnover_verified"):
        blockers.append("CHALLENGER_TURNOVER_NOT_VERIFIED")

    for variant_id, source in sources.items():
        bct = verify_baseline_cost_treatment(root, source)
        if not bct.get("verified"):
            blockers.append(f"BASELINE_COST_TREATMENT_NOT_VERIFIED:{variant_id}")

    for scenario_name, scenario_def in SCENARIOS.items():
        scenario_results[scenario_name] = []
        for variant_id, source in sources.items():
            scenario_results[scenario_name].append(
                evaluate_variant_scenario(root, variant_id, source, scenario_name, scenario_def, allow_turnover_proxy=False)
            )
        if CHALLENGER in sources and not sources[CHALLENGER].get("turnover_verified"):
            sensitivity[scenario_name] = [
                evaluate_variant_scenario(
                    root, CHALLENGER, sources[CHALLENGER], scenario_name, scenario_def, allow_turnover_proxy=True
                )
            ]

    champion_id = resolve_locked_champion(root)
    gate = evaluate_cost_stress_gate(
        scenario_results,
        blockers=sorted(set(blockers)),
        champion_id=champion_id,
    )

    return {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_HISTORICAL_EVIDENCE",
        "baseline_cost_policy": {
            "incremental_stress_only": True,
            "note": "V2R requires verified baseline cost documentation per variant; no proxy turnover for gate pass.",
        },
        "variants": list(sources.keys()),
        "scenarios": scenario_results,
        "sensitivity_analysis": {
            "proxy_turnover_results": sensitivity,
            "label": "NOT_GATE_EVIDENCE",
        },
        "COST_STRESS_GATE": gate,
    }


def export_cost_stress_status(root: Path) -> Path:
    root = Path(root)
    path = root / EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_cost_stress_status(root))
    return path
