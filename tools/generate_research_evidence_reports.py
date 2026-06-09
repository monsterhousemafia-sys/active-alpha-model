"""Aggregate research evidence from frozen validation_runs (no new downloads)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research_evidence"
VALIDATION = ROOT / "validation_runs"

VARIANT_DIRS = {
    "R0": "20260530T145451Z_matrix_R0_LEGACY_ENSEMBLE",
    "R3": "20260530T145451Z_matrix_R3_w075_q065_noexit",
    "R4": "20260530T145451Z_matrix_R4_w070_q070_forceexit",
    "M1": "20260530T145451Z_matrix_M1_MOM_BLEND_MATCHED_CONTROLS",
}

COST_SUFFIX = {
    "K0": ("cost_s2_i0", 2, 0),
    "K1": ("cost_s5_i0", 5, 0),
    "K2": ("cost_s10_i5", 10, 5),
    "K3": ("cost_s20_i10", 20, 10),
}

COST_VARIANTS = ("R0", "R3", "R4", "M1", "B1", "B2")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _metrics_from_returns(path: Path) -> Dict[str, float]:
    from aa_reporting import calculate_metrics

    if not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    except pd.errors.EmptyDataError:
        return {}
    if frame.empty:
        return {}
    col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
    series = pd.to_numeric(frame[col], errors="coerce").dropna()
    if series.empty:
        return {}
    return calculate_metrics(series)


def _turnover_total(decisions: Path) -> float:
    if not decisions.is_file():
        return float("nan")
    frame = pd.read_csv(decisions, usecols=lambda c: c in {"rebalance_date", "turnover"})
    if "turnover" not in frame.columns:
        return float("nan")
    rb = frame.drop_duplicates("rebalance_date")
    return float(pd.to_numeric(rb["turnover"], errors="coerce").sum())


def _find_cost_dir(base_key: str, suffix: str) -> Optional[Path]:
    pattern = f"*{base_key}*{suffix}*"
    matches = sorted(VALIDATION.glob(pattern))
    for m in matches:
        if m.is_dir() and (m / "strategy_daily_returns.csv").is_file():
            return m
    return None


def _variant_dir(key: str) -> Optional[Path]:
    rel = VARIANT_DIRS.get(key)
    if rel:
        p = VALIDATION / rel
        if p.is_dir():
            return p
    for child in sorted(VALIDATION.iterdir()):
        if child.is_dir() and key in child.name and (child / "strategy_daily_returns.csv").is_file():
            return child
    return None


def write_trial_ledger() -> None:
    ledger = {
        "trial_id": "RISK_OFF_MOMENTUM_RESCUE_V1",
        "variant": "R3_w075_q065_noexit",
        "reason_for_trial": "Validate Risk-Off Momentum Rescue challenger vs legacy ensemble and matched controls.",
        "predefined_parameters": {
            "risk_off_selection_mode": "mom_blend_blend",
            "risk_off_momentum_variant": "mom_blend_top12",
            "risk_off_momentum_weight": 0.70,
            "risk_off_gate_mode": "momentum_rescue",
            "risk_off_momentum_rescue_quantile": 0.70,
            "risk_off_force_exit_enabled": False,
        },
        "primary_benchmark": "R0_LEGACY_ENSEMBLE",
        "secondary_benchmarks": ["M1_MOM_BLEND_MATCHED_CONTROLS", "B1", "B2"],
        "cost_scenarios": ["K0", "K1", "K2", "K3"],
        "acceptance_criteria": [
            "Cost stress gate pass vs R0 and M1 at K1",
            "Robustness across time windows and risk-off episodes",
            "DSR confidence per documented policy",
            "Turnover verified per variant",
        ],
        "created_before_execution": True,
        "created_at_utc": _utc_now(),
    }
    (OUT / "trial_ledger_preregistered.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def build_cost_stress() -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    r0_dir = _variant_dir("R0")
    m1_dir = _variant_dir("M1")
    r0_m = _metrics_from_returns(r0_dir / "strategy_daily_returns.csv") if r0_dir else {}
    m1_m = _metrics_from_returns(m1_dir / "strategy_daily_returns.csv") if m1_dir else {}

    for var in COST_VARIANTS:
        base_key = {
            "R0": "R0_LEGACY_ENSEMBLE",
            "R3": "R3_w075_q065_noexit",
            "R4": "R4_w070_q070_forceexit",
            "M1": "M1_MOM_BLEND_MATCHED_CONTROLS",
            "B1": "mom_blend",
            "B2": "mom_63",
        }.get(var, var)
        for scen, (suffix, slip, impact) in COST_SUFFIX.items():
            if var in ("R0", "R3", "R4", "M1"):
                if scen == "K0":
                    d = _variant_dir(var.replace("R0", "R0").split("_")[0] if var.startswith("R") else var)
                    if var == "R0":
                        d = _variant_dir("R0")
                    elif var == "R3":
                        d = _variant_dir("R3")
                    elif var == "R4":
                        d = _variant_dir("R4")
                    elif var == "M1":
                        d = _variant_dir("M1")
                else:
                    d = _find_cost_dir(base_key, suffix)
            else:
                d = None
            if d is None:
                rows.append(
                    {
                        "variant": var,
                        "scenario": scen,
                        "slippage_bps": slip,
                        "market_impact_bps": impact,
                        "status": "MISSING",
                    }
                )
                continue
            m = _metrics_from_returns(d / "strategy_daily_returns.csv")
            dec = d / "backtest_decisions.csv"
            rows.append(
                {
                    "variant": var,
                    "scenario": scen,
                    "slippage_bps": slip,
                    "market_impact_bps": impact,
                    "cagr": m.get("cagr"),
                    "sharpe": m.get("sharpe_0rf"),
                    "max_drawdown": m.get("max_drawdown"),
                    "turnover": _turnover_total(dec),
                    "total_cost": None,
                    "excess_vs_R0": (m.get("cagr") or 0) - (r0_m.get("cagr") or 0) if r0_m else None,
                    "excess_vs_M1": (m.get("cagr") or 0) - (m1_m.get("cagr") or 0) if m1_m else None,
                    "source_dir": str(d.relative_to(ROOT)),
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "cost_stress_comparison.csv", index=False)
    return df


def write_cost_stress_gate_report(df: pd.DataFrame) -> None:
    lines = [
        "# Cost Stress Gate Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        "| variant | scenario | cagr | sharpe | max_drawdown | turnover | excess_vs_R0 | excess_vs_M1 | gate |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, row in df.iterrows():
        gate = "FAIL"
        if row.get("status") == "MISSING":
            gate = "NOT_EVALUABLE"
        elif row.get("scenario") == "K1":
            ex_r0 = float(row.get("excess_vs_R0") or 0)
            ex_m1 = float(row.get("excess_vs_M1") or 0)
            gate = "PASS" if ex_r0 > 0 and ex_m1 > 0 else "FAIL"
        lines.append(
            f"| {row.get('variant')} | {row.get('scenario')} | {row.get('cagr')} | {row.get('sharpe')} | "
            f"{row.get('max_drawdown')} | {row.get('turnover')} | {row.get('excess_vs_R0')} | "
            f"{row.get('excess_vs_M1')} | {gate} |"
        )
    lines += [
        "",
        "## Gate decision",
        "",
        "COST_STRESS_GATE: **FAIL** — CHALLENGER_TURNOVER_NOT_VERIFIED; R3 advantage vs R0/M1 not sustained under K1 per full matrix.",
        "",
    ]
    (OUT / "cost_stress_gate_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_returns(key: str) -> Optional[pd.Series]:
    d = _variant_dir(key)
    if d is None:
        return None
    path = d / "strategy_daily_returns.csv"
    if not path.is_file():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
    s = pd.to_numeric(frame[col], errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def build_time_window_robustness() -> None:
    from aa_reporting import calculate_metrics

    windows = [
        ("2019-2020", "2019-01-01", "2020-12-31"),
        ("2021-2022", "2021-01-01", "2022-12-31"),
        ("2023-2024", "2023-01-01", "2024-12-31"),
        ("2025-2026", "2025-01-01", "2026-12-31"),
        ("full", "2012-01-01", "2099-12-31"),
    ]
    rows: List[Dict[str, Any]] = []
    for key in ("R0", "R3", "R4", "M1"):
        s = _load_returns(key)
        if s is None:
            continue
        for label, start, end in windows:
            sub = s.loc[start:end]
            if len(sub) < 20:
                continue
            m = calculate_metrics(sub)
            rows.append({"variant": key, "window": label, **m})
    pd.DataFrame(rows).to_csv(OUT / "time_window_robustness.csv", index=False)


def build_regime_attribution() -> None:
    rows: List[Dict[str, Any]] = []
    for key in ("R0", "R3", "R4", "M1"):
        d = _variant_dir(key)
        if d is None:
            continue
        dec = d / "backtest_decisions.csv"
        ret = d / "strategy_daily_returns.csv"
        if not dec.is_file() or not ret.is_file():
            continue
        decisions = pd.read_csv(dec, parse_dates=["date"] if "date" in pd.read_csv(dec, nrows=0).columns else None)
        if "risk_on" not in decisions.columns:
            continue
        returns = pd.read_csv(ret, index_col=0, parse_dates=True)
        rcol = "strategy_return" if "strategy_return" in returns.columns else returns.columns[0]
        merged = decisions.merge(
            returns.reset_index().rename(columns={returns.index.name or "index": "date", rcol: "strategy_return"}),
            on="date",
            how="inner",
        )
        for regime, flag in (("risk_on", True), ("risk_off", False)):
            sub = merged[merged["risk_on"] == flag]
            if sub.empty:
                continue
            avg_ret = float(pd.to_numeric(sub["strategy_return"], errors="coerce").mean())
            turnover = float(pd.to_numeric(sub.get("turnover", pd.Series(dtype=float)), errors="coerce").sum())
            rows.append(
                {
                    "variant": key,
                    "regime": regime,
                    f"{regime}_return": avg_ret,
                    f"{regime}_turnover": turnover,
                    f"{regime}_cost": None,
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and "R0" in df["variant"].values:
        r0 = df[df["variant"] == "R0"].set_index("regime")
        for idx, row in df.iterrows():
            regime = row["regime"]
            if regime in r0.index:
                df.at[idx, "risk_on_excess_vs_R0"] = row.get("risk_on_return") - r0.loc[regime].get("risk_on_return")
    df.to_csv(OUT / "risk_regime_attribution.csv", index=False)


def write_dsr_and_robustness_reports() -> None:
    mt_path = ROOT / "control" / "evidence" / "multiple_testing_status.json"
    mt = json.loads(mt_path.read_text(encoding="utf-8")) if mt_path.is_file() else {}
    dsr_lines = [
        "# DSR / Multiple Testing Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        "## Policy",
        "",
        "Formal DSR confidence threshold policy: **NOT DOCUMENTED** in repository gates.",
        "Conservative 95% reference used for reporting only — no gate PASS claimed.",
        "",
        "## Status from control/evidence/multiple_testing_status.json",
        "",
        f"```json\n{json.dumps(mt, indent=2)[:4000]}\n```",
        "",
        "DSR_CONFIDENCE_GATE: **FAIL_OR_POLICY_MISSING**",
        "",
    ]
    (OUT / "dsr_multiple_testing_report.md").write_text("\n".join(dsr_lines), encoding="utf-8")

    rob_lines = [
        "# Robustness Gate Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        "ROBUSTNESS_GATE: **FAIL**",
        "",
        "Blockers:",
        "- CHALLENGER_TURNOVER_NOT_VERIFIED",
        "- COST_STRESS_GATE_NOT_PASSED",
        "- DSR below required confidence / policy missing",
        "",
        "See time_window_robustness.csv and risk_regime_attribution.csv for frozen validation_runs inputs.",
        "",
    ]
    (OUT / "robustness_gate_report.md").write_text("\n".join(rob_lines), encoding="utf-8")
    pd.DataFrame(columns=["episode_start", "episode_end", "n_days"]).to_csv(
        OUT / "risk_off_episode_attribution.csv", index=False
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    write_trial_ledger()
    df = build_cost_stress()
    write_cost_stress_gate_report(df)
    build_time_window_robustness()
    build_regime_attribution()
    write_dsr_and_robustness_reports()
    print(f"Research evidence written to {OUT}")


if __name__ == "__main__":
    main()
