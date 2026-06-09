"""Data quality gate for formal model comparisons (PIT universe limitations)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List

import pandas as pd


@dataclass
class DataQualityResult:
    status: str  # PASS | DATA_QUALITY_WARN
    warnings: List[str] = field(default_factory=list)
    missing_beta_by_ticker: int = 0
    extreme_return_rows: int = 0
    missing_adv_rows: int = 0
    missing_vol_rows: int = 0
    missing_target_rows: int = 0
    membership_false_rows: int = 0

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def run_data_quality_gate(features: pd.DataFrame) -> DataQualityResult:
    warnings: List[str] = []
    if features is None or features.empty:
        return DataQualityResult(status="DATA_QUALITY_WARN", warnings=["empty feature table"])

    missing_beta = 0
    if "beta_252" in features.columns:
        missing_beta = int(pd.to_numeric(features["beta_252"], errors="coerce").isna().sum())
        if missing_beta:
            warnings.append(f"missing beta_252 values: {missing_beta}")

    extreme = 0
    if "ret_1" in features.columns:
        r = pd.to_numeric(features["ret_1"], errors="coerce")
        extreme = int((r.abs() > 0.50).sum())
        if extreme:
            warnings.append(f"extreme daily returns (|r|>50%): {extreme}")

    missing_adv = int(pd.to_numeric(features.get("adv_20", pd.Series(dtype=float)), errors="coerce").isna().sum()) if "adv_20" in features.columns else 0
    missing_vol = int(pd.to_numeric(features.get("vol_20", pd.Series(dtype=float)), errors="coerce").isna().sum()) if "vol_20" in features.columns else 0
    missing_target = int(pd.to_numeric(features.get("target", pd.Series(dtype=float)), errors="coerce").isna().sum()) if "target" in features.columns else 0
    membership_false = 0
    if "membership_allowed" in features.columns:
        membership_false = int((~features["membership_allowed"].fillna(False).astype(bool)).sum())

    if missing_adv:
        warnings.append(f"missing adv_20: {missing_adv}")
    if missing_vol:
        warnings.append(f"missing vol_20: {missing_vol}")
    if missing_target:
        warnings.append(f"missing target: {missing_target}")

    warnings.append(
        "DIY point-in-time universe: reduces survivorship bias but is not delisting- "
        "or corporate-action-complete."
    )
    warnings.append(
        "Live capital allocation must not rely on this historical dataset alone."
    )

    status = "PASS" if not any("missing" in w or "extreme" in w for w in warnings[:-2]) else "DATA_QUALITY_WARN"
    return DataQualityResult(
        status=status,
        warnings=warnings,
        missing_beta_by_ticker=missing_beta,
        extreme_return_rows=extreme,
        missing_adv_rows=missing_adv,
        missing_vol_rows=missing_vol,
        missing_target_rows=missing_target,
        membership_false_rows=membership_false,
    )


def write_data_quality_gate(out_dir: Path, result: DataQualityResult, features: pd.DataFrame) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "data_quality_gate.json"
    summary_path.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")

    if features is not None and not features.empty and "ret_1" in features.columns:
        r = pd.to_numeric(features["ret_1"], errors="coerce")
        extreme_df = features.loc[r.abs() > 0.50, ["date", "ticker", "ret_1"]].copy() if {"date", "ticker"}.issubset(features.columns) else pd.DataFrame()
        if not extreme_df.empty:
            extreme_df.to_csv(out_dir / "data_quality_extreme_returns.csv", index=False)

    if features is not None and "beta_252" in features.columns and {"date", "ticker"}.issubset(features.columns):
        miss = features.loc[pd.to_numeric(features["beta_252"], errors="coerce").isna(), ["date", "ticker", "beta_252"]]
        if not miss.empty:
            miss.head(5000).to_csv(out_dir / "data_quality_missing_beta.csv", index=False)

    return summary_path
