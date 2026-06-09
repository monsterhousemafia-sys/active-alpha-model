"""Read-only robustness evidence (V2 / V2R)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from aa_cost_stress import CHALLENGER, M1_VARIANT, _load_daily_returns, file_sha256, resolve_variant_sources
from aa_evidence_schema import resolve_locked_champion
from aa_reporting import calculate_metrics
from aa_safe_io import atomic_write_json

EVIDENCE_PATH = Path("control") / "evidence" / "robustness_status.json"


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


def _variant_returns(root: Path, variant_id: str) -> Optional[pd.Series]:
    source = resolve_variant_sources(root).get(variant_id, {})
    path = root / str(source.get("returns_path") or "")
    return _load_daily_returns(path, source.get("returns_column"))


def _subperiod_screen(returns: pd.Series) -> Dict[str, Any]:
    if returns is None or len(returns) < 40:
        return {"pass": False, "status": "NOT_EVALUABLE", "reason": "insufficient_observations"}
    mid = len(returns) // 2
    first = returns.iloc[:mid]
    second = returns.iloc[mid:]
    m1 = calculate_metrics(first)
    m2 = calculate_metrics(second)
    stable = (
        pd.notna(m1.get("sharpe_0rf"))
        and pd.notna(m2.get("sharpe_0rf"))
        and min(m1["sharpe_0rf"], m2["sharpe_0rf"]) > 0
        and abs(m1["sharpe_0rf"] - m2["sharpe_0rf"]) < 1.5
    )
    return {
        "pass": bool(stable),
        "status": "PASS" if stable else "FAIL",
        "first_half": m1,
        "second_half": m2,
        "sharpe_delta": float(m2.get("sharpe_0rf", 0) - m1.get("sharpe_0rf", 0)),
    }


def build_robustness_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cost = _read_json(root / "control" / "evidence" / "cost_stress_status.json")
    mt = _read_json(root / "control" / "evidence" / "multiple_testing_status.json")

    cost_gate = cost.get("COST_STRESS_GATE") or {}
    mt_ev = mt.get("MULTIPLE_TESTING_EVIDENCE") or {}
    cost_ok = cost_gate.get("pass") is True and cost_gate.get("evaluation_status") == "PASS"
    mt_ok = mt_ev.get("pass") is True and mt_ev.get("status") == "PASS"

    champion_id = resolve_locked_champion(root)
    variants = [champion_id, M1_VARIANT, CHALLENGER]
    aligned: Dict[str, pd.Series] = {}
    source_hashes: Dict[str, str] = {}

    for vid in variants:
        src = resolve_variant_sources(root).get(vid, {})
        rel = str(src.get("returns_path") or "")
        path = root / rel
        series = _variant_returns(root, vid)
        if series is not None and not series.empty:
            aligned[vid] = series
            source_hashes[vid] = file_sha256(path)

    blockers: List[str] = []
    if len(aligned) < 3:
        blockers.append("ROBUSTNESS_INPUT_SERIES_INCOMPLETE")

    sub_screen_pass = False
    comparisons: Dict[str, Any] = {}
    if len(aligned) >= 3:
        common_idx = aligned[champion_id].index
        for vid in (M1_VARIANT, CHALLENGER):
            common_idx = common_idx.intersection(aligned[vid].index)
        if len(common_idx) >= 200:
            for vid in variants:
                series = aligned[vid].reindex(common_idx).dropna()
                comparisons[vid] = {
                    "full_sample": calculate_metrics(series),
                    "subperiod_screen": _subperiod_screen(series),
                    "source_sha256": source_hashes.get(vid, ""),
                }
            sub_screen_pass = all(
                bool(comparisons[v]["subperiod_screen"].get("pass")) for v in variants
            )
        else:
            blockers.append("ROBUSTNESS_CALENDAR_TOO_SHORT")

    if not cost_ok:
        blockers.append("COST_STRESS_GATE_NOT_PASSED")
    if not mt_ok:
        blockers.append("MULTIPLE_TESTING_NOT_PASSED")

    robust_pass = bool(sub_screen_pass and cost_ok and mt_ok and not blockers[:1])
    if sub_screen_pass and (not cost_ok or not mt_ok):
        status = "PARTIAL_ONLY"
        robust_pass = False
    elif robust_pass:
        status = "PASS"
    elif not comparisons:
        status = "NOT_EVALUABLE"
    else:
        status = "FAIL"

    return {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_HISTORICAL_EVIDENCE",
        "SUBPERIOD_STABILITY_SCREEN": {"pass": bool(sub_screen_pass)},
        "aligned_observations": int(
            comparisons.get(champion_id, {}).get("full_sample", {}).get("n_days", 0) or 0
        ),
        "variants": comparisons,
        "source_hashes": source_hashes,
        "ROBUSTNESS_EVIDENCE": {
            "pass": robust_pass,
            "status": status,
            "detail": f"subperiod_screen={sub_screen_pass} cost_ok={cost_ok} mt_ok={mt_ok}",
            "blockers": sorted(set(blockers)),
        },
        "blockers": sorted(set(blockers)),
    }


def export_robustness_status(root: Path) -> Path:
    root = Path(root)
    path = root / EVIDENCE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_robustness_status(root))
    return path
