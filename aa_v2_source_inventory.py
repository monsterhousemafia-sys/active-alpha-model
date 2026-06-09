"""V2 read-only source inventory."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from aa_cost_stress import CHALLENGER, M1_VARIANT, resolve_variant_sources, _load_daily_returns, _load_rebalance_turnover
from aa_evidence_schema import resolve_locked_champion
from aa_safe_io import atomic_write_json

INVENTORY_PATH = Path("control") / "evidence" / "v2_source_inventory.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_v2_source_inventory(root: Path) -> Dict[str, Any]:
    root = Path(root)
    sources = resolve_variant_sources(root)
    variants: List[Dict[str, Any]] = []
    calendars: List[pd.DatetimeIndex] = []

    for variant_id, src in sources.items():
        ret_path = root / str(src.get("returns_path") or "")
        dec_path = root / str(src.get("decisions_path") or "")
        returns = _load_daily_returns(ret_path, src.get("returns_column"))
        turnover = _load_rebalance_turnover(dec_path) if dec_path.is_file() else None
        entry: Dict[str, Any] = {
            "variant_id": variant_id,
            "returns_path": src.get("returns_path"),
            "returns_sha256": file_sha256(ret_path),
            "decisions_path": src.get("decisions_path") or None,
            "decisions_sha256": file_sha256(dec_path) if dec_path.is_file() else "",
            "returns_column": src.get("returns_column"),
            "baseline_costs_in_returns": src.get("baseline_costs_in_returns"),
            "observations": int(len(returns)) if returns is not None else 0,
            "calendar_start": str(returns.index.min().date()) if returns is not None and len(returns) else None,
            "calendar_end": str(returns.index.max().date()) if returns is not None and len(returns) else None,
            "mean_rebalance_turnover": float(turnover.mean()) if turnover is not None and len(turnover) else None,
            "available": returns is not None and len(returns) >= 200,
        }
        if returns is not None and len(returns):
            calendars.append(returns.index)
        variants.append(entry)

    aligned = True
    common_len = 0
    if len(calendars) >= 2:
        common = calendars[0]
        for idx in calendars[1:]:
            common = common.intersection(idx)
        common_len = len(common)
        aligned = common_len >= 200

    config_path = root / "promotion_gate_config.yaml"
    challenger_report = root / "control" / "challenger_report.json"

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "champion": resolve_locked_champion(root),
        "m1_control": M1_VARIANT,
        "challenger": CHALLENGER,
        "variants": variants,
        "aligned_calendar_observations": common_len,
        "aligned_calendar_ok": aligned,
        "cost_assumptions": {
            "config_path": "promotion_gate_config.yaml",
            "config_sha256": file_sha256(config_path),
            "cost_stress_scenarios_configured": ["baseline", "plus_25bps"],
            "baseline_costs_in_champion_returns": True,
            "fee_model": "trading212_us+fx_0bps+slippage_2bps",
        },
        "candidate_matrix": {
            "challenger_report_path": "control/challenger_report.json",
            "challenger_report_sha256": file_sha256(challenger_report),
            "variants_compared": 7,
            "pbo_inputs_available": False,
        },
        "source_files": [
            {"path": "model_output_sp500_pit_t212/strategy_daily_returns.csv", "role": "champion_returns"},
            {"path": "model_output_sp500_pit_t212/backtest_decisions.csv", "role": "champion_turnover"},
            {
                "path": "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/mom_blend_matched_controls_daily_returns.csv",
                "role": "m1_returns",
            },
            {
                "path": "runs/20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce/naive_momentum_daily_returns.csv",
                "role": "challenger_naive_mom_63_returns",
            },
        ],
    }


def export_v2_source_inventory(root: Path) -> Path:
    root = Path(root)
    path = root / INVENTORY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_v2_source_inventory(root))
    return path
