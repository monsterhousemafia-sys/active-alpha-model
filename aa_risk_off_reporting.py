"""Risk-off research comparison and episode attribution reports."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_reporting import calculate_metrics, newey_west_tstat


def _load_daily_returns(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return pd.Series(dtype=float)
    col = df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_decisions(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, parse_dates=["rebalance_date"], low_memory=False)


def _parse_report_metrics(path: Path) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not path.exists():
        return out
    section = ""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line in {"Strategy metrics", "Benchmark metrics", "Portfolio diagnostics"}:
            section = line
            continue
        if ":" not in line or line.startswith("-"):
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        prefix = "strategy_" if section == "Strategy metrics" and k not in {"information_ratio", "tracking_error", "excess_cagr_approx"} else ""
        key = prefix + k
        try:
            out[key] = float(v)
        except Exception:
            out[key] = v
    return out


def _rebalance_regime_map(decisions: pd.DataFrame) -> pd.Series:
    if decisions.empty or "rebalance_date" not in decisions.columns:
        return pd.Series(dtype=bool)
    rb = decisions.drop_duplicates(subset=["rebalance_date"], keep="first").copy()
    rb["rebalance_date"] = pd.to_datetime(rb["rebalance_date"])
    rb = rb.sort_values("rebalance_date")
    if "risk_on" not in rb.columns:
        return pd.Series(dtype=bool)
    risk_on = rb.set_index("rebalance_date")["risk_on"].astype(bool)
    return risk_on


def _daily_regime_mask(daily_index: pd.DatetimeIndex, regime_map: pd.Series) -> pd.Series:
    if daily_index.empty or regime_map.empty:
        return pd.Series(False, index=daily_index)
    rb_dates = pd.DatetimeIndex(regime_map.index.sort_values())
    out = pd.Series(index=daily_index, dtype=object)
    for dt in daily_index:
        prior = rb_dates[rb_dates <= dt]
        if len(prior) == 0:
            out.loc[dt] = bool(regime_map.iloc[0])
        else:
            out.loc[dt] = bool(regime_map.loc[prior[-1]])
    return out.fillna(False).astype(bool)


def _regime_annualized_return(daily: pd.Series, mask: pd.Series) -> float:
    if daily.empty:
        return float("nan")
    sub = daily.reindex(mask.index).loc[mask.fillna(False)]
    if len(sub) < 5:
        return float("nan")
    m = calculate_metrics(sub)
    return float(m.get("cagr", np.nan))


def _resolve_daily_returns_path(variant: str, out_dir: Path) -> Path:
    """Pick the correct daily-returns file (naive baselines live beside ensemble outputs)."""
    out_dir = Path(out_dir)
    slug_map = {
        "NAIVE_MOM_BLEND_TOP12": "naive_mom_blend_daily_returns.csv",
        "NAIVE_MOM_63_TOP12": "naive_mom_63_daily_returns.csv",
        "M1_MOM_BLEND_MATCHED_CONTROLS": "mom_blend_matched_controls_daily_returns.csv",
    }
    alt_name = slug_map.get(variant)
    if alt_name:
        alt_path = out_dir / alt_name
        if alt_path.exists():
            return alt_path
    return out_dir / "strategy_daily_returns.csv"


def _variant_summary(
    variant: str,
    out_dir: Path,
    *,
    legacy_returns: Optional[pd.Series] = None,
    matched_returns: Optional[pd.Series] = None,
) -> Dict[str, Any]:
    out_dir = Path(out_dir)
    daily_path = _resolve_daily_returns_path(variant, out_dir)
    daily = _load_daily_returns(daily_path)
    decisions = _load_decisions(out_dir / "backtest_decisions.csv")
    report = _parse_report_metrics(out_dir / "backtest_report.txt")
    metrics = calculate_metrics(daily) if not daily.empty else {}
    row: Dict[str, Any] = {
        "variant": variant,
        "out_dir": str(out_dir),
        "total_return": metrics.get("total_return", np.nan),
        "cagr": metrics.get("cagr", report.get("strategy_cagr", np.nan)),
        "annual_vol": metrics.get("annual_vol", np.nan),
        "sharpe_0rf": metrics.get("sharpe_0rf", np.nan),
        "max_drawdown": metrics.get("max_drawdown", np.nan),
    }
    if not decisions.empty:
        rb = decisions.drop_duplicates(subset=["rebalance_date"], keep="first")
        row["avg_turnover"] = float(pd.to_numeric(rb.get("turnover", 0.0), errors="coerce").mean())
        row["approx_annual_turnover"] = float(row["avg_turnover"]) * (252.0 / max(float(getattr(rb, "rebalance_every", 5) or 5), 1))
        row["total_tx_cost"] = float(pd.to_numeric(rb.get("tx_cost", 0.0), errors="coerce").sum())
        row["avg_exposure"] = float(pd.to_numeric(rb.get("portfolio_exposure", 0.0), errors="coerce").mean())
        row["avg_beta"] = float(pd.to_numeric(rb.get("portfolio_beta", 0.0), errors="coerce").mean())
        row["constraint_violations"] = float(pd.to_numeric(rb.get("constraint_violations", 0.0), errors="coerce").sum())
    else:
        row.update({"avg_turnover": np.nan, "approx_annual_turnover": np.nan, "total_tx_cost": np.nan, "avg_exposure": np.nan, "avg_beta": np.nan, "constraint_violations": np.nan})
    regime_map = _rebalance_regime_map(decisions)
    if not daily.empty and not regime_map.empty:
        mask = _daily_regime_mask(daily.index, regime_map)
        row["risk_on_return"] = _regime_annualized_return(daily, mask)
        row["risk_off_return"] = _regime_annualized_return(daily, ~mask)
    else:
        row["risk_on_return"] = np.nan
        row["risk_off_return"] = np.nan
    if legacy_returns is not None and not daily.empty:
        common = daily.index.intersection(legacy_returns.index)
        ex = daily.reindex(common) - legacy_returns.reindex(common)
        row["information_ratio_vs_legacy"] = calculate_metrics(daily.reindex(common), legacy_returns.reindex(common)).get("information_ratio", np.nan)
        row["annualized_excess_vs_legacy"] = float(ex.mean() * 252.0) if len(ex) else np.nan
        row["nw_t_excess_vs_legacy"] = newey_west_tstat(ex) if len(ex) > 10 else np.nan
        row["risk_on_excess_vs_legacy"] = _regime_annualized_return(ex, _daily_regime_mask(common, regime_map)) if len(common) else np.nan
        row["risk_off_excess_vs_legacy"] = _regime_annualized_return(ex, ~_daily_regime_mask(common, regime_map)) if len(common) else np.nan
    else:
        row.update({"information_ratio_vs_legacy": np.nan, "annualized_excess_vs_legacy": np.nan, "nw_t_excess_vs_legacy": np.nan, "risk_on_excess_vs_legacy": np.nan, "risk_off_excess_vs_legacy": np.nan})
    if matched_returns is not None and not daily.empty:
        common = daily.index.intersection(matched_returns.index)
        ex = daily.reindex(common) - matched_returns.reindex(common)
        row["information_ratio_vs_matched_momentum"] = calculate_metrics(daily.reindex(common), matched_returns.reindex(common)).get("information_ratio", np.nan)
        row["annualized_excess_vs_matched_momentum"] = float(ex.mean() * 252.0) if len(ex) else np.nan
        row["nw_t_excess_vs_matched_momentum"] = newey_west_tstat(ex) if len(ex) > 10 else np.nan
    else:
        row.update({"information_ratio_vs_matched_momentum": np.nan, "annualized_excess_vs_matched_momentum": np.nan, "nw_t_excess_vs_matched_momentum": np.nan})
    return row


def write_risk_off_variant_comparison(
    out_dir: Path,
    variant_dirs: Dict[str, Path],
    *,
    legacy_key: str = "R0_LEGACY_ENSEMBLE",
    matched_key: str = "M1_MOM_BLEND_MATCHED_CONTROLS",
) -> Path:
    out_dir = Path(out_dir)
    legacy_returns = _load_daily_returns(variant_dirs.get(legacy_key, Path()) / "strategy_daily_returns.csv")
    matched_dir = variant_dirs.get(matched_key, Path())
    matched_returns = _load_daily_returns(matched_dir / "strategy_daily_returns.csv")
    if matched_returns.empty:
        matched_returns = _load_daily_returns(matched_dir / "mom_blend_matched_controls_daily_returns.csv")
    rows = [
        _variant_summary(name, path, legacy_returns=legacy_returns, matched_returns=matched_returns)
        for name, path in variant_dirs.items()
    ]
    df = pd.DataFrame(rows)
    path = out_dir / "risk_off_variant_comparison.csv"
    df.to_csv(path, index=False)
    return path


def _risk_off_episodes(regime_map: pd.Series) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    if regime_map.empty:
        return []
    rb = regime_map.sort_index()
    episodes: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    in_ep = False
    start: Optional[pd.Timestamp] = None
    for dt, risk_on in rb.items():
        if not bool(risk_on):
            if not in_ep:
                start = pd.Timestamp(dt)
                in_ep = True
        elif in_ep and start is not None:
            episodes.append((start, pd.Timestamp(dt)))
            in_ep = False
            start = None
    if in_ep and start is not None:
        episodes.append((start, pd.Timestamp(rb.index[-1])))
    return episodes


def _episode_slice(daily: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    if daily.empty:
        return daily
    idx = daily.index
    mask = (idx >= start) & (idx <= end)
    return daily.loc[mask]


def write_risk_off_episode_attribution(
    out_dir: Path,
    variant_dirs: Dict[str, Path],
    *,
    legacy_key: str = "R0_LEGACY_ENSEMBLE",
    candidate_key: str = "R3_RISK_OFF_MOMENTUM_RESCUE",
    matched_key: str = "M1_MOM_BLEND_MATCHED_CONTROLS",
) -> Path:
    out_dir = Path(out_dir)
    legacy = _load_daily_returns(variant_dirs.get(legacy_key, Path()) / "strategy_daily_returns.csv")
    candidate = _load_daily_returns(variant_dirs.get(candidate_key, Path()) / "strategy_daily_returns.csv")
    matched_dir = variant_dirs.get(matched_key, Path())
    matched = _load_daily_returns(matched_dir / "strategy_daily_returns.csv")
    if matched.empty:
        matched = _load_daily_returns(matched_dir / "mom_blend_matched_controls_daily_returns.csv")
    legacy_dec = _load_decisions(variant_dirs.get(legacy_key, Path()) / "backtest_decisions.csv")
    candidate_dec = _load_decisions(variant_dirs.get(candidate_key, Path()) / "backtest_decisions.csv")
    regime_map = _rebalance_regime_map(legacy_dec if not legacy_dec.empty else candidate_dec)
    rows: List[Dict[str, Any]] = []
    for i, (start, end) in enumerate(_risk_off_episodes(regime_map), start=1):
        leg = _episode_slice(legacy, start, end)
        cand = _episode_slice(candidate, start, end)
        mat = _episode_slice(matched, start, end)
        leg_ret = float((1.0 + leg).prod() - 1.0) if len(leg) else np.nan
        cand_ret = float((1.0 + cand).prod() - 1.0) if len(cand) else np.nan
        mat_ret = float((1.0 + mat).prod() - 1.0) if len(mat) else np.nan
        rb_c = candidate_dec.copy()
        if not rb_c.empty:
            rb_c["rebalance_date"] = pd.to_datetime(rb_c["rebalance_date"])
            ep_rb = rb_c[(rb_c["rebalance_date"] >= start) & (rb_c["rebalance_date"] <= end)].drop_duplicates("rebalance_date")
        else:
            ep_rb = pd.DataFrame()
        rows.append({
            "episode_id": i,
            "episode_start": start.date().isoformat(),
            "episode_end": end.date().isoformat(),
            "n_days": int(max(len(leg), len(cand), len(mat))),
            "legacy_return": leg_ret,
            "candidate_return": cand_ret,
            "mom_blend_matched_return": mat_ret,
            "candidate_excess_vs_legacy": cand_ret - leg_ret if np.isfinite(cand_ret) and np.isfinite(leg_ret) else np.nan,
            "candidate_excess_vs_matched_momentum": cand_ret - mat_ret if np.isfinite(cand_ret) and np.isfinite(mat_ret) else np.nan,
            "avg_exposure": float(pd.to_numeric(ep_rb.get("portfolio_exposure", 0.0), errors="coerce").mean()) if not ep_rb.empty else np.nan,
            "avg_beta": float(pd.to_numeric(ep_rb.get("portfolio_beta", 0.0), errors="coerce").mean()) if not ep_rb.empty else np.nan,
            "avg_n_eligible_candidates": float(pd.to_numeric(ep_rb.get("n_eligible_candidates", 0.0), errors="coerce").mean()) if not ep_rb.empty else np.nan,
            "avg_forced_exit_weight": float(pd.to_numeric(ep_rb.get("forced_exit_weight_after_controls", 0.0), errors="coerce").mean()) if not ep_rb.empty else np.nan,
            "turnover": float(pd.to_numeric(ep_rb.get("turnover", 0.0), errors="coerce").sum()) if not ep_rb.empty else np.nan,
            "tx_cost": float(pd.to_numeric(ep_rb.get("tx_cost", 0.0), errors="coerce").sum()) if not ep_rb.empty else np.nan,
        })
    df = pd.DataFrame(rows)
    if not df.empty and "candidate_excess_vs_matched_momentum" in df.columns:
        df = df.sort_values("candidate_excess_vs_matched_momentum")
    path = out_dir / "risk_off_episode_attribution.csv"
    df.to_csv(path, index=False)
    return path


def write_risk_off_research_reports(
    research_root: Path,
    variant_dirs: Dict[str, Path],
) -> List[Path]:
    research_root = Path(research_root)
    research_root.mkdir(parents=True, exist_ok=True)
    written = [
        write_risk_off_variant_comparison(research_root, variant_dirs),
        write_risk_off_episode_attribution(research_root, variant_dirs),
    ]
    return written
