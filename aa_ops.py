"""Central operations orchestrator for Marktanalyse (preflight, refresh, analyze, results)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from aa_data_freshness import DailyDataReport, assess_daily_data
from aa_preflight import PreflightReport, run_launcher_preflight
from aa_system_status import SystemStatus, combined_health, health_from_parts, write_system_status

LogFn = Callable[[str], None]


@dataclass
class RunPlan:
    mode: str
    reasons: List[str] = field(default_factory=list)

    @property
    def show_results_only(self) -> bool:
        return self.mode == "results"

    @property
    def needs_signal_refresh(self) -> bool:
        return self.mode == "refresh_signal"

    @property
    def needs_analyze(self) -> bool:
        return self.mode in {"analyze", "refresh_analyze"}


def _yes(env: Mapping[str, str], key: str, default: str = "1") -> bool:
    return str(env.get(key, default) or default).strip().lower() not in {"0", "false", "no", "off"}


def resolve_out_dir(root: Path, env: Mapping[str, str]) -> Path:
    from aa_ops_refresh import resolve_out_dir as _resolve

    return _resolve(root, env)


def has_persisted_analysis(out_dir: Path, env: Optional[Mapping[str, str]] = None) -> bool:
    ok, _ = validate_persisted_analysis(out_dir, env)
    return ok


def _signal_only_env(env: Optional[Mapping[str, str]]) -> bool:
    if env is None:
        import os

        mode = str(os.environ.get("AA_RUN_MODE", "") or "").strip().lower()
    else:
        mode = str(env.get("AA_RUN_MODE", "") or "").strip().lower()
    return mode == "signal"


def validate_persisted_analysis(
    out_dir: Path,
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[bool, str]:
    if _signal_only_env(env):
        portfolio = out_dir / "latest_target_portfolio.csv"
        if not portfolio.is_file():
            return False, "latest_target_portfolio.csv fehlt"
        try:
            import pandas as pd

            pf = pd.read_csv(portfolio)
            if pf.empty or "target_weight" not in pf.columns:
                return False, "latest_target_portfolio.csv ungültig"
            weights = pd.to_numeric(pf["target_weight"], errors="coerce").fillna(0.0)
            if float(weights.sum()) <= 0:
                return False, "Portfolio ohne positive Gewichte"
        except Exception as exc:
            return False, f"latest_target_portfolio.csv unlesbar: {exc}"
        return True, "ok (signal-only)"

    from aa_ops_validation import validate_analytical_integrity

    analytical_ok, analytical_reason, _run_id = validate_analytical_integrity(out_dir)
    if not analytical_ok:
        return False, analytical_reason

    required = (
        out_dir / "strategy_daily_returns.csv",
        out_dir / "backtest_report.txt",
        out_dir / "latest_target_portfolio.csv",
    )
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        return False, "fehlende Dateien: " + ", ".join(missing)

    try:
        import pandas as pd

        returns = pd.read_csv(out_dir / "strategy_daily_returns.csv", index_col=0, nrows=5000)
        if returns.empty:
            return False, "strategy_daily_returns.csv ist leer"
        col = "strategy_return" if "strategy_return" in returns.columns else returns.columns[0]
        series = pd.to_numeric(returns[col], errors="coerce").dropna()
        if series.empty:
            return False, "keine gültigen Strategierenditen"
    except Exception as exc:
        return False, f"strategy_daily_returns.csv unlesbar: {exc}"

    portfolio = out_dir / "latest_target_portfolio.csv"
    try:
        import pandas as pd

        pf = pd.read_csv(portfolio)
        if pf.empty or "target_weight" not in pf.columns:
            return False, "latest_target_portfolio.csv ungültig"
        weights = pd.to_numeric(pf["target_weight"], errors="coerce").fillna(0.0)
        if float(weights.sum()) <= 0:
            return False, "Portfolio ohne positive Gewichte"
    except Exception as exc:
        return False, f"latest_target_portfolio.csv unlesbar: {exc}"

    report = out_dir / "backtest_report.txt"
    if report.stat().st_size < 80:
        return False, "backtest_report.txt zu klein"
    return True, "ok"


def decide_run_plan(
    root: Path,
    env: Mapping[str, str],
    *,
    data_report: Optional[DailyDataReport] = None,
    preflight: Optional[PreflightReport] = None,
) -> RunPlan:
    report = data_report or assess_daily_data(root, env)
    pf = preflight or PreflightReport()
    out_dir = resolve_out_dir(root, env)

    if _yes(env, "AA_FORCE_FULL_ANALYSIS", "0"):
        return RunPlan("analyze", ["AA_FORCE_FULL_ANALYSIS=1"])

    if not _yes(env, "AA_FAST_PATH", "1"):
        if not report.ok:
            return RunPlan("refresh_analyze", ["Fast-Path deaktiviert, Daten veraltet"])
        return RunPlan("analyze", ["Fast-Path deaktiviert"])

    if pf.blocking:
        return RunPlan("analyze", ["Preflight-Fehler — Vollanalyse zur Reparatur"])

    analysis_ok, reason = validate_persisted_analysis(out_dir, env)
    if report.ok and analysis_ok:
        return RunPlan("results", ["Betriebsdaten aktuell, gespeicherte Analyse vorhanden"])

    if not report.ok:
        analysis_ok, reason = validate_persisted_analysis(out_dir, env)
        if analysis_ok and _yes(env, "AA_SIGNAL_REFRESH_ON_STALE_DATA", "1"):
            return RunPlan(
                "refresh_signal",
                ["Betriebsdaten veraltet, Integrität PASS — kein Voll-Backtest (Schritt 6 kurz)"],
            )
        if analysis_ok:
            return RunPlan("refresh_analyze", ["Betriebsdaten veraltet — Vollanalyse"])
        return RunPlan("refresh_analyze", [f"Betriebsdaten veraltet ({reason})"])

    if not analysis_ok:
        if _signal_only_env(env):
            return RunPlan("refresh_signal", [f"Live-Modus: Signal-Update ({reason})"])
        return RunPlan("analyze", [f"Gespeicherte Analyse unvollständig ({reason})"])

    if _signal_only_env(env):
        return RunPlan("refresh_signal", ["Live-Modus: Signal-Update"])

    return RunPlan("analyze", ["Vollanalyse angefordert"])


def _load_strategy_metrics(report_path: Path) -> Dict[str, float]:
    """Parse Strategy metrics block from backtest_report.txt."""
    metrics: Dict[str, float] = {}
    if not report_path.is_file():
        return metrics
    section = ""
    for raw in report_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if line in {"Strategy metrics", "Benchmark metrics", "Portfolio diagnostics"}:
            section = line
            continue
        if section != "Strategy metrics":
            continue
        if ":" not in line or line.startswith("-"):
            continue
        key, val = [part.strip() for part in line.split(":", 1)]
        try:
            metrics[key] = float(val)
        except Exception:
            continue
    return metrics


def load_cached_run_result(root: Path, env: Mapping[str, str]):
    from aa_runtime import RunResult

    out_dir = resolve_out_dir(root, env).resolve()
    ok, reason = validate_persisted_analysis(out_dir, env)
    metrics = _load_strategy_metrics(out_dir / "backtest_report.txt")

    signal_date = "n/a"
    portfolio = out_dir / "latest_target_portfolio.csv"
    if portfolio.is_file():
        try:
            import pandas as pd

            df = pd.read_csv(portfolio, usecols=lambda c: c in {"signal_date"})
            if not df.empty and "signal_date" in df.columns:
                signal_date = str(df["signal_date"].iloc[0])
        except Exception:
            pass

    output_files = [p for p in out_dir.glob("*") if p.is_file()]
    return RunResult(
        metrics=metrics,
        signal_date=signal_date,
        output_files=output_files[:50],
        out_dir=out_dir,
        success=ok,
        error="" if ok else reason,
    )


def update_system_status(
    root: Path,
    *,
    phase: str,
    preflight: PreflightReport,
    data_report: DailyDataReport,
    run_plan: RunPlan,
    exit_code: int = 0,
    message: str = "",
    details: Optional[Dict[str, object]] = None,
    out_dir: Optional[Path] = None,
) -> Path:
    from aa_ops_refresh import resolve_out_dir

    operational = health_from_parts(
        preflight=preflight.status,
        data_ok=data_report.ok,
        exit_code=exit_code,
        ops_degraded=bool((details or {}).get("ops_lock_contended")),
    )
    analytical = str((details or {}).get("analytical_validity", "unknown") or "unknown")
    validated_run_id = str((details or {}).get("validated_run_id", "") or "")
    if out_dir is None:
        try:
            out_dir = resolve_out_dir(root, os.environ)
        except Exception:
            out_dir = None
    if analytical == "unknown" and out_dir is not None:
        from aa_ops_validation import assess_analytical_status

        analytical, validated_run_id = assess_analytical_status(Path(out_dir))
    health = combined_health(operational=operational, analytical=analytical)
    status = SystemStatus(
        phase=phase,
        health=health,
        operational_health=operational,
        analytical_validity=analytical,
        validated_run_id=validated_run_id,
        exit_code=int(exit_code),
        price_date=data_report.price_latest.isoformat() if data_report.price_latest else None,
        signal_date=data_report.signal_date.isoformat() if data_report.signal_date else None,
        paper_mark_today=data_report.paper_mark_today,
        preflight_status=preflight.status,
        run_plan=run_plan.mode,
        message=message or "; ".join(run_plan.reasons),
        details=dict(details or {}),
    )
    return write_system_status(root, status)


def run_preflight_step(
    root: Path,
    env: Mapping[str, str],
    *,
    log: LogFn,
    data_report=None,
) -> PreflightReport:
    return run_launcher_preflight(root, env, log=log, data_report=data_report)
