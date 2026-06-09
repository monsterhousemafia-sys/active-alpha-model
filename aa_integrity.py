"""Backtest calendar integrity validation and error export."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

import numpy as np
import pandas as pd

from aa_safe_io import atomic_write_json, atomic_write_text


@dataclass
class IntegrityResult:
    status: str  # PASS | INVALID
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    expected_rebalance_periods: int = 0
    simulated_rebalance_periods: int = 0
    expected_trading_days: int = 0
    actual_trading_days: int = 0
    duplicate_return_days: int = 0
    missing_periods: List[str] = field(default_factory=list)
    run_id: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS" and not self.errors


def _period_key(rb: pd.Timestamp, next_rb: pd.Timestamp) -> str:
    return f"{pd.Timestamp(rb).date()}->{pd.Timestamp(next_rb).date()}"


def expected_rebalance_periods(rebalance_dates: Sequence[pd.Timestamp]) -> List[tuple[pd.Timestamp, pd.Timestamp]]:
    rbs = [pd.Timestamp(d) for d in rebalance_dates]
    if len(rbs) < 2:
        return []
    return [(rbs[i], rbs[i + 1]) for i in range(len(rbs) - 1)]


def validate_backtest_calendar_integrity(
    *,
    rebalance_dates: Sequence[pd.Timestamp],
    strategy_returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    returns_calendar: Optional[pd.DatetimeIndex] = None,
    simulated_rebalance_dates: Optional[Sequence[pd.Timestamp]] = None,
    run_id: str = "",
    tol: float = 1e-12,
) -> IntegrityResult:
    """Validate that walk-forward simulation covers every rebalance hold period once."""
    errors: List[str] = []
    warnings: List[str] = []
    periods = expected_rebalance_periods(rebalance_dates)
    expected_n = len(periods)

    strat = pd.Series(strategy_returns, dtype=float).dropna()
    strat.index = pd.to_datetime(strat.index)
    strat = strat.sort_index()
    if strat.empty:
        errors.append("strategy_daily_returns is empty")
        return IntegrityResult(
            status="INVALID",
            errors=errors,
            expected_rebalance_periods=expected_n,
            run_id=run_id,
        )

    dup_mask = strat.index.duplicated(keep=False)
    dup_count = int(dup_mask.sum())
    if dup_count:
        errors.append(f"duplicate strategy return days: {dup_count}")

    sim_set: Set[pd.Timestamp] = set()
    if simulated_rebalance_dates is not None:
        sim_set = {pd.Timestamp(d) for d in simulated_rebalance_dates}

    missing_periods: List[str] = []
    covered_periods = 0
    for rb, next_rb in periods:
        rb_ts = pd.Timestamp(rb)
        next_ts = pd.Timestamp(next_rb)
        if sim_set and rb_ts not in sim_set:
            missing_periods.append(_period_key(rb_ts, next_ts))
            continue
        # Hold period: trading days strictly after rb up to and including next_rb boundary
        if returns_calendar is not None:
            cal = pd.DatetimeIndex(returns_calendar)
            mask = (cal > rb_ts) & (cal <= next_ts)
            period_days = cal[mask]
        else:
            mask = (strat.index > rb_ts) & (strat.index <= next_ts)
            period_days = strat.index[mask]
        if len(period_days) == 0:
            missing_periods.append(_period_key(rb_ts, next_ts))
        else:
            covered_periods += 1

    if missing_periods:
        errors.append(
            f"missing hold periods ({len(missing_periods)}/{expected_n}): "
            + ", ".join(missing_periods[:5])
            + (" …" if len(missing_periods) > 5 else "")
        )

    if simulated_rebalance_dates is not None and sim_set:
        if len(sim_set) < expected_n:
            errors.append(
                f"simulated rebalance count {len(sim_set)} < expected {expected_n}"
            )

    if returns_calendar is not None and not strat.empty:
        cal = pd.DatetimeIndex(returns_calendar)
        first_rb = pd.Timestamp(rebalance_dates[0]) if rebalance_dates else strat.index.min()
        last_rb = pd.Timestamp(rebalance_dates[-1]) if rebalance_dates else strat.index.max()
        expected_days = cal[(cal > first_rb) & (cal <= last_rb)]
        expected_n_days = len(expected_days)
        if dup_count:
            actual_in_range = strat.loc[strat.index.isin(expected_days)]
        else:
            actual_in_range = strat.reindex(expected_days).dropna()
        if len(actual_in_range) < expected_n_days:
            gap = expected_n_days - len(actual_in_range)
            if gap > max(1, int(0.01 * expected_n_days)):
                errors.append(
                    f"strategy returns missing {gap} of {expected_n_days} expected trading days "
                    f"in [{first_rb.date()}, {last_rb.date()}]"
                )
    else:
        expected_n_days = len(strat)

    if benchmark_returns is not None and not strat.empty:
        bench = pd.Series(benchmark_returns, dtype=float)
        bench.index = pd.to_datetime(bench.index)
        common = strat.index.intersection(bench.index)
        if len(common) < len(strat) * 0.99:
            errors.append(
                f"benchmark/strategy calendar mismatch: common={len(common)} strategy={len(strat)}"
            )
        elif not common.equals(strat.index):
            warnings.append("benchmark and strategy indices differ but overlap >= 99%")

    status = "PASS" if not errors else "INVALID"
    return IntegrityResult(
        status=status,
        errors=errors,
        warnings=warnings,
        expected_rebalance_periods=expected_n,
        simulated_rebalance_periods=covered_periods if not sim_set else len(sim_set),
        expected_trading_days=expected_n_days if returns_calendar is not None else len(strat),
        actual_trading_days=len(strat),
        duplicate_return_days=dup_count,
        missing_periods=missing_periods,
        run_id=run_id,
    )


def validate_matched_controls_calendar_integrity(
    *,
    strategy_returns: pd.Series,
    matched_returns: pd.Series,
    run_id: str = "",
    min_overlap_ratio: float = 0.99,
) -> IntegrityResult:
    """Ensure M1 matched-controls baseline shares the strategy return calendar."""
    errors: List[str] = []
    warnings: List[str] = []
    strat = pd.Series(strategy_returns, dtype=float).dropna()
    strat.index = pd.to_datetime(strat.index)
    matched = pd.Series(matched_returns, dtype=float).dropna()
    matched.index = pd.to_datetime(matched.index)
    if strat.empty:
        errors.append("strategy_daily_returns is empty")
    if matched.empty:
        errors.append("matched_controls daily returns is empty")
    if errors:
        return IntegrityResult(status="INVALID", errors=errors, run_id=run_id)
    common = strat.index.intersection(matched.index)
    if len(common) < len(strat) * min_overlap_ratio:
        errors.append(
            f"matched-controls/strategy calendar mismatch: common={len(common)} strategy={len(strat)}"
        )
    elif not common.equals(strat.index):
        warnings.append("matched-controls and strategy indices differ but overlap >= threshold")
    status = "PASS" if not errors else "INVALID"
    return IntegrityResult(
        status=status,
        errors=errors,
        warnings=warnings,
        expected_trading_days=len(strat),
        actual_trading_days=len(matched),
        run_id=run_id,
    )


def validate_backtest_integrity(
    *,
    rebalance_dates: Sequence[pd.Timestamp],
    strategy_returns: pd.Series,
    benchmark_returns: Optional[pd.Series] = None,
    returns_calendar: Optional[pd.DatetimeIndex] = None,
    simulated_rebalance_dates: Optional[Sequence[pd.Timestamp]] = None,
    run_id: str = "",
    tol: float = 1e-12,
) -> IntegrityResult:
    """Central backtest integrity gate (alias for calendar validation)."""
    return validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        returns_calendar=returns_calendar,
        simulated_rebalance_dates=simulated_rebalance_dates,
        run_id=run_id,
        tol=tol,
    )


def integrity_status_payload(
    result: IntegrityResult,
    *,
    matched_controls_calendar_complete: Optional[bool] = None,
) -> Dict[str, Any]:
    """Compact status document for EXE and automation hooks."""
    rebalance_complete = (
        result.expected_rebalance_periods > 0
        and result.simulated_rebalance_periods >= result.expected_rebalance_periods
        and not any("missing hold" in e.lower() or "rebalance count" in e.lower() for e in result.errors)
    )
    returns_complete = (
        result.duplicate_return_days == 0
        and not any("missing" in e.lower() and "trading days" in e.lower() for e in result.errors)
        and not any("duplicate" in e.lower() for e in result.errors)
    )
    calendar_complete = rebalance_complete and returns_complete and not any(
        "mismatch" in e.lower() for e in result.errors
    )
    status = "PASS" if result.passed else "FAIL"
    return {
        "status": status,
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "calendar_complete": calendar_complete,
        "rebalance_complete": rebalance_complete,
        "returns_complete": returns_complete,
        "matched_controls_calendar_complete": matched_controls_calendar_complete,
        "errors": list(result.errors),
    }


def backfill_integrity_status_json(out_dir: Path) -> Optional[Path]:
    """Write integrity_status.json from integrity_report.json if missing (non-destructive)."""
    out_dir = Path(out_dir)
    status_path = out_dir / "integrity_status.json"
    if status_path.is_file():
        return status_path
    report_path = out_dir / "integrity_report.json"
    if not report_path.is_file():
        return None
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    result = IntegrityResult(
        status=str(raw.get("status", "INVALID")),
        errors=list(raw.get("errors") or []),
        warnings=list(raw.get("warnings") or []),
        expected_rebalance_periods=int(raw.get("expected_rebalance_periods", 0) or 0),
        simulated_rebalance_periods=int(raw.get("simulated_rebalance_periods", 0) or 0),
        expected_trading_days=int(raw.get("expected_trading_days", 0) or 0),
        actual_trading_days=int(raw.get("actual_trading_days", 0) or 0),
        duplicate_return_days=int(raw.get("duplicate_return_days", 0) or 0),
        run_id=str(raw.get("run_id", "") or ""),
    )
    return write_integrity_status_json(out_dir, result)


def write_integrity_status_json(out_dir: Path, result: IntegrityResult) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(out_dir / "integrity_status.json", integrity_status_payload(result))


def validate_prediction_cache_coverage(
    cache: Dict[pd.Timestamp, Dict[str, Any]],
    rebalance_dates: Sequence[pd.Timestamp],
) -> IntegrityResult:
    """Ensure prediction cache covers every rebalance date (ok or resolvable forward)."""
    required = [pd.Timestamp(d) for d in rebalance_dates[:-1]]
    errors: List[str] = []
    missing: List[str] = []
    for rb in required:
        entry = cache.get(rb)
        if entry is None:
            missing.append(str(rb.date()))
            continue
        status = str(entry.get("status", ""))
        if status not in {"ok", "forwarded_ml_retrain"}:
            errors.append(f"rebalance {rb.date()} cache status={status!r}")
    if missing:
        errors.append(f"prediction cache missing rebalances: {', '.join(missing[:8])}" + (" …" if len(missing) > 8 else ""))
    return IntegrityResult(
        status="PASS" if not errors else "INVALID",
        errors=errors,
        expected_rebalance_periods=len(required),
        simulated_rebalance_periods=len(required) - len(missing),
        missing_periods=missing,
    )


def write_integrity_reports(out_dir: Path, result: IntegrityResult) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    atomic_write_json(out_dir / "integrity_report.json", payload)
    lines = [
        f"Integrity status: {result.status}",
        f"Run ID: {result.run_id or 'n/a'}",
        f"Expected rebalance periods: {result.expected_rebalance_periods}",
        f"Simulated rebalance periods: {result.simulated_rebalance_periods}",
        f"Strategy trading days: {result.actual_trading_days}",
    ]
    if result.errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(f"  - {e}" for e in result.errors)
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"  - {w}" for w in result.warnings)
    (out_dir / "integrity_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_integrity_status_json(out_dir, result)
    if not result.passed:
        err_payload = {"status": "INVALID", "errors": result.errors, "run_id": result.run_id}
        atomic_write_json(out_dir / "integrity_errors.json", err_payload)
        atomic_write_text(out_dir / "integrity_errors.txt", "\n".join(result.errors) + "\n")
