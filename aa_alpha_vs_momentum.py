"""Compare ensemble alpha against internal momentum baselines for tuning gates."""
from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from aa_reporting import _benchmark_row

MOMENTUM_BENCHMARK_NAMES: Tuple[str, ...] = (
    "NAIVE_MOMENTUM_MOM_BLEND_TOP12",
    "mom_blend_top12",
    "mom_blend_matched_controls",
    "NAIVE_MOMENTUM_MOM_BLEND_MATCHED_CONTROLS",
    "MTUM",
)


@dataclass(frozen=True)
class AlphaMomentumThresholds:
    min_cagr_diff: float = 0.03
    min_sharpe_diff: float = 0.08
    min_information_ratio: float = 0.20

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class AlphaMomentumComparison:
    momentum_benchmark: str
    source: str
    n_days: int
    strategy_cagr: float
    momentum_cagr: float
    cagr_diff: float
    strategy_sharpe: float
    momentum_sharpe: float
    sharpe_diff: float
    information_ratio: float
    tracking_error: float
    correlation: float
    beta_to_momentum: float
    beats_momentum: bool = False
    gate_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_report_sections(report_path: Path) -> Dict[str, Dict[str, float]]:
    """Parse backtest_report.txt without later sections overwriting strategy metrics."""
    out: Dict[str, Dict[str, float]] = {"strategy": {}, "benchmark": {}}
    if not report_path.is_file():
        return out
    section = ""
    for line in report_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped == "Strategy metrics":
            section = "strategy"
            continue
        if stripped == "Benchmark metrics":
            section = "benchmark"
            continue
        if stripped.startswith("---") or stripped.endswith("metrics"):
            continue
        if section not in out or ":" not in line:
            continue
        key, _, val = line.partition(":")
        k = key.strip().lower().replace(" ", "_")
        try:
            out[section][k] = float(val.strip().replace("%", ""))
        except ValueError:
            continue
    return out


def load_daily_returns(path: Path, preferred_col: Optional[str] = None) -> Optional[pd.Series]:
    if not path.is_file():
        return None
    try:
        frame = pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception:
        return None
    if frame.empty:
        return None
    if preferred_col and preferred_col in frame.columns:
        col = preferred_col
    elif "strategy_return" in frame.columns:
        col = "strategy_return"
    else:
        col = frame.columns[0]
    return pd.to_numeric(frame[col], errors="coerce").dropna()


def _pick_momentum_row(rows: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    indexed = {str(row.get("benchmark", "")).strip(): row for row in rows}
    for name in MOMENTUM_BENCHMARK_NAMES:
        if name in indexed:
            return indexed[name]
    for row in rows:
        source = str(row.get("source", "")).lower()
        benchmark = str(row.get("benchmark", "")).lower()
        if source == "internal_naive_momentum" or "mom_blend" in benchmark or benchmark == "mtum":
            return row
    return None


def load_benchmark_comparison_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(dict(row))
    return rows


def comparison_from_row(row: Dict[str, Any]) -> AlphaMomentumComparison:
    def f(key: str, default: float = 0.0) -> float:
        try:
            return float(row.get(key, default))
        except (TypeError, ValueError):
            return default

    return AlphaMomentumComparison(
        momentum_benchmark=str(row.get("benchmark", "")),
        source=str(row.get("source", "")),
        n_days=int(float(row.get("n_days", 0) or 0)),
        strategy_cagr=f("strategy_cagr"),
        momentum_cagr=f("benchmark_cagr"),
        cagr_diff=f("cagr_diff"),
        strategy_sharpe=f("strategy_sharpe_0rf"),
        momentum_sharpe=f("benchmark_sharpe_0rf"),
        sharpe_diff=f("sharpe_diff"),
        information_ratio=f("information_ratio"),
        tracking_error=f("tracking_error"),
        correlation=f("correlation"),
        beta_to_momentum=f("beta_to_benchmark"),
    )


def parse_backtest_report_momentum(out_dir: Path) -> Optional[AlphaMomentumComparison]:
    """Parse NAIVE/MTUM benchmark lines from backtest_report.txt."""
    report = Path(out_dir) / "backtest_report.txt"
    if not report.is_file():
        return None
    text = report.read_text(encoding="utf-8", errors="ignore")
    sections = parse_report_sections(report)
    strategy = sections.get("strategy", {})
    strategy_cagr = float(strategy.get("cagr", 0.0))
    strategy_sharpe = float(strategy.get("sharpe_0rf", 0.0))
    pattern = re.compile(
        r"^(?P<name>[A-Z0-9_]+):\s*CAGR diff=(?P<cagr_diff>[-0-9.eE+]+),\s*"
        r"IR=(?P<ir>[-0-9.eE+]+),\s*corr=(?P<corr>[-0-9.eE+]+),\s*beta=(?P<beta>[-0-9.eE+]+)\s*$",
        re.MULTILINE,
    )
    picked_name = ""
    picked = None
    for match in pattern.finditer(text):
        name = match.group("name")
        if name in MOMENTUM_BENCHMARK_NAMES or "MOM_BLEND" in name or name == "MTUM":
            picked_name = name
            picked = match
            if "MOM_BLEND" in name or name.startswith("NAIVE_MOMENTUM"):
                break
    if picked is None:
        return None
    cagr_diff = float(picked.group("cagr_diff"))
    information_ratio = float(picked.group("ir"))
    correlation = float(picked.group("corr"))
    beta_to_momentum = float(picked.group("beta"))
    momentum_cagr = strategy_cagr - cagr_diff
    momentum_sharpe = strategy_sharpe * (momentum_cagr / strategy_cagr) if strategy_cagr > 0 else 0.0
    sharpe_diff = strategy_sharpe - momentum_sharpe
    return AlphaMomentumComparison(
        momentum_benchmark=picked_name,
        source="backtest_report",
        n_days=int(strategy.get("n_days", 0)),
        strategy_cagr=strategy_cagr,
        momentum_cagr=momentum_cagr,
        cagr_diff=cagr_diff,
        strategy_sharpe=strategy_sharpe,
        momentum_sharpe=momentum_sharpe,
        sharpe_diff=sharpe_diff,
        information_ratio=information_ratio,
        tracking_error=0.0,
        correlation=correlation,
        beta_to_momentum=beta_to_momentum,
    )


def compare_return_series(strategy: pd.Series, momentum: pd.Series) -> Optional[AlphaMomentumComparison]:
    row = _benchmark_row(strategy, momentum, "mom_blend_top12", "computed")
    if row is None:
        return None
    return comparison_from_row(row)


def extract_alpha_vs_momentum(out_dir: Path) -> Optional[AlphaMomentumComparison]:
    out_dir = Path(out_dir)
    rows = load_benchmark_comparison_rows(out_dir / "benchmark_comparison.csv")
    picked = _pick_momentum_row(rows)
    if picked is not None:
        return comparison_from_row(picked)

    strategy = load_daily_returns(out_dir / "strategy_daily_returns.csv")
    if strategy is None or strategy.empty:
        return None

    naive_path = out_dir / "naive_momentum_daily_returns.csv"
    if naive_path.is_file():
        naive = pd.read_csv(naive_path, index_col=0, parse_dates=True)
        for name in MOMENTUM_BENCHMARK_NAMES:
            if name in naive.columns:
                mom = pd.to_numeric(naive[name], errors="coerce").dropna()
                cmp = compare_return_series(strategy, mom)
                if cmp is not None:
                    cmp.momentum_benchmark = name
                    cmp.source = "naive_momentum_daily_returns"
                    return cmp
        if not naive.empty:
            col = naive.columns[0]
            cmp = compare_return_series(strategy, pd.to_numeric(naive[col], errors="coerce").dropna())
            if cmp is not None:
                cmp.momentum_benchmark = str(col)
                cmp.source = "naive_momentum_daily_returns"
                return cmp

    matched = out_dir / "mom_blend_matched_controls_daily_returns.csv"
    mom = load_daily_returns(matched)
    if mom is not None and not mom.empty:
        cmp = compare_return_series(strategy, mom)
        if cmp is not None:
            cmp.momentum_benchmark = "mom_blend_matched_controls"
            cmp.source = "matched_controls_daily_returns"
            return cmp
    return parse_backtest_report_momentum(out_dir)


def alpha_beats_momentum_significantly(
    comparison: Optional[AlphaMomentumComparison],
    thresholds: Optional[AlphaMomentumThresholds] = None,
) -> Tuple[bool, str]:
    th = thresholds or AlphaMomentumThresholds()
    if comparison is None:
        return False, "momentum_comparison_missing"
    reasons: List[str] = []
    if comparison.cagr_diff < th.min_cagr_diff:
        reasons.append(f"cagr_diff={comparison.cagr_diff:.4f}<{th.min_cagr_diff:.4f}")
    if comparison.sharpe_diff < th.min_sharpe_diff:
        reasons.append(f"sharpe_diff={comparison.sharpe_diff:.4f}<{th.min_sharpe_diff:.4f}")
    if comparison.information_ratio < th.min_information_ratio:
        reasons.append(f"ir={comparison.information_ratio:.4f}<{th.min_information_ratio:.4f}")
    ok = not reasons
    comparison.beats_momentum = ok
    comparison.gate_reason = "PASS" if ok else "; ".join(reasons)
    return ok, comparison.gate_reason


def score_alpha_vs_momentum(comparison: Optional[AlphaMomentumComparison]) -> float:
    if comparison is None:
        return -999.0
    return (
        0.35 * comparison.information_ratio
        + 0.30 * comparison.sharpe_diff
        + 0.25 * comparison.cagr_diff
        + 0.10 * max(0.0, -comparison.strategy_sharpe * 0.0)
    )


def write_alpha_momentum_status(
    path: Path,
    *,
    comparisons: Sequence[AlphaMomentumComparison],
    thresholds: AlphaMomentumThresholds,
    best_name: str,
    round_index: int,
    target_met: bool,
    notes: str = "",
) -> None:
    payload = {
        "generated_at_utc": _utc_now(),
        "round_index": round_index,
        "target_met": target_met,
        "thresholds": thresholds.as_dict(),
        "best_variant": best_name,
        "notes": notes,
        "results": [c.as_dict() for c in comparisons],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
