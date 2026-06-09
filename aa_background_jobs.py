"""Async background job registry (Phase C scaffold — disabled by default)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from aa_job_lock import JobLock
from aa_safe_io import atomic_write_json

JOB_NAMES = (
    "realtime_collect",
    "eod_finalize",
    "rebalance_signal",
    "portfolio_review_live",
    "feedback_update",
    "background_validate",
    "operational_refinement",
    "adaptive_marktanalyse",
)

ENV_ENABLE_PREFIX = "AA_JOB_"
ENV_ENABLE_SUFFIX = "_ENABLED"
STATUS_FILE = "background_job_status.json"


@dataclass
class JobSpec:
    name: str
    description: str
    default_enabled: bool = False
    env_var: str = ""

    def __post_init__(self) -> None:
        if not self.env_var:
            key = self.name.upper()
            self.env_var = f"{ENV_ENABLE_PREFIX}{key}{ENV_ENABLE_SUFFIX}"


@dataclass
class JobRunResult:
    job: str
    status: str  # OK | SKIPPED | LOCKED | FAIL | DISABLED
    exit_code: int = 0
    message: str = ""
    started_at_utc: str = ""
    finished_at_utc: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


JOB_SPECS: Dict[str, JobSpec] = {
    "realtime_collect": JobSpec(
        name="realtime_collect",
        description="Append-only intraday bars/quotes; no alpha decisions.",
    ),
    "eod_finalize": JobSpec(
        name="eod_finalize",
        description="Finalize session aggregates and behavioral feature inputs after close.",
    ),
    "rebalance_signal": JobSpec(
        name="rebalance_signal",
        description="Champion-only rebalance signal on valid rebalance dates.",
    ),
    "portfolio_review_live": JobSpec(
        name="portfolio_review_live",
        description="Read-only portfolio review and action suggestions.",
    ),
    "feedback_update": JobSpec(
        name="feedback_update",
        description="Mature prediction outcomes; no champion changes.",
    ),
    "background_validate": JobSpec(
        name="background_validate",
        description="Offline walk-forward validation and challenger reports.",
    ),
    "operational_refinement": JobSpec(
        name="operational_refinement",
        description="Full daily chain: Tagesdaten, R3-Diagnose, Signal, Cockpit.",
        default_enabled=False,
    ),
    "adaptive_marktanalyse": JobSpec(
        name="adaptive_marktanalyse",
        description="Adaptive runtime: dynamic plan, refine, optional retrain.",
        default_enabled=False,
    ),
}


def job_enabled(spec: JobSpec, env: Optional[Dict[str, str]] = None) -> bool:
    env = env or dict(os.environ)
    raw = str(env.get(spec.env_var, "1" if spec.default_enabled else "0") or "0").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def status_path(root: Path) -> Path:
    return Path(root) / STATUS_FILE


def read_job_status(root: Path) -> Dict[str, Any]:
    path = status_path(root)
    if not path.is_file():
        return {"jobs": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": {}}


def write_job_status(root: Path, result: JobRunResult) -> None:
    path = status_path(root)
    payload = read_job_status(root)
    jobs = dict(payload.get("jobs") or {})
    jobs[result.job] = result.to_dict()
    payload["jobs"] = jobs
    payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(path, payload)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_realtime_collect(root: Path, env: Dict[str, str]) -> JobRunResult:
    provider = str(env.get("AA_REALTIME_PROVIDER", "replay") or "replay").strip().lower()
    if provider in {"", "none", "disabled"}:
        return JobRunResult(
            job="realtime_collect",
            status="SKIPPED",
            exit_code=0,
            message="REALTIME_PROVIDER_NOT_CONFIGURED",
        )
    if provider == "replay":
        from aa_ops_refresh import resolve_out_dir
        from aa_realtime_replay import run_realtime_replay_sync

        out_dir = resolve_out_dir(root, env)
        try:
            summary = run_realtime_replay_sync(root, out_dir)
            return JobRunResult(
                job="realtime_collect",
                status="OK" if summary.get("status") == "OK" else "FAIL",
                exit_code=0 if summary.get("status") == "OK" else 1,
                message=f"replay quality={summary.get('data_quality_status')}",
                details=summary,
            )
        except Exception as exc:
            return JobRunResult(job="realtime_collect", status="FAIL", exit_code=1, message=str(exc))
    return JobRunResult(
        job="realtime_collect",
        status="SKIPPED",
        exit_code=0,
        message=f"Provider scaffold only ({provider}); live collection not yet implemented.",
    )


def _run_eod_finalize(root: Path, env: Dict[str, str]) -> JobRunResult:
    provider = str(env.get("AA_REALTIME_PROVIDER", "replay") or "replay").strip().lower()
    if provider in {"", "none", "disabled"}:
        return JobRunResult(
            job="eod_finalize",
            status="SKIPPED",
            exit_code=0,
            message="REALTIME_PROVIDER_NOT_CONFIGURED",
        )
    if provider == "replay":
        from aa_ops_refresh import resolve_out_dir
        from aa_behavioral_research import run_eod_behavioral_finalize

        out_dir = resolve_out_dir(root, env)
        try:
            summary = run_eod_behavioral_finalize(root, out_dir)
            ok = summary.get("status") in {"OK", "QUALITY_BLOCKED", "DATA_BLOCKED"}
            return JobRunResult(
                job="eod_finalize",
                status="OK" if summary.get("status") == "OK" else "FAIL",
                exit_code=0 if ok else 1,
                message=f"behavioral finalize={summary.get('behavioral_research_status')}",
                details=summary,
            )
        except Exception as exc:
            return JobRunResult(job="eod_finalize", status="FAIL", exit_code=1, message=str(exc))
    return JobRunResult(
        job="eod_finalize",
        status="SKIPPED",
        exit_code=0,
        message=f"EOD finalize scaffold only ({provider}).",
    )


def _run_rebalance_signal(root: Path, env: Dict[str, str]) -> JobRunResult:
    from aa_ops_validation import validate_analytical_integrity
    from aa_ops_refresh import resolve_out_dir

    out_dir = resolve_out_dir(root, env)
    ok, reason, run_id = validate_analytical_integrity(out_dir)
    if not ok:
        return JobRunResult(
            job="rebalance_signal",
            status="FAIL",
            exit_code=2,
            message=f"Champion/analytical gate failed: {reason}",
            details={"run_id": run_id},
        )
    py = sys.executable
    cmd = [
        py,
        str(root / "active_alpha_model.py"),
        "--mode",
        "signal",
        "--no-gui",
        "--plain-progress",
        "--out-dir",
        str(out_dir),
    ]
    if env.get("AA_SHARED_CACHE_DIR"):
        cmd += ["--shared-cache-dir", str(env["AA_SHARED_CACHE_DIR"])]
    proc = subprocess.run(cmd, cwd=str(root), env={**os.environ, **env})
    if proc.returncode != 0:
        return JobRunResult(
            job="rebalance_signal",
            status="FAIL",
            exit_code=int(proc.returncode),
            message="Signal run failed",
        )
    return JobRunResult(
        job="rebalance_signal",
        status="OK",
        exit_code=0,
        message="Champion signal refreshed (manual execution still required).",
        details={"run_id": run_id, "out_dir": str(out_dir)},
    )


def _run_portfolio_review_live(root: Path, env: Dict[str, str]) -> JobRunResult:
    return JobRunResult(
        job="portfolio_review_live",
        status="SKIPPED",
        exit_code=0,
        message="Portfolio review live scaffold — use paper_trading_engine until Phase H.",
    )


def _run_feedback_update(root: Path, env: Dict[str, str]) -> JobRunResult:
    from aa_ops_refresh import resolve_out_dir
    from aa_prediction_outcomes import update_prediction_outcomes

    out_dir = resolve_out_dir(root, env)
    try:
        summary = update_prediction_outcomes(out_dir)
        metrics = summary.get("metrics") or {}
        return JobRunResult(
            job="feedback_update",
            status="OK",
            exit_code=0,
            message=(
                f"added={summary.get('added', 0)} matured={summary.get('matured', 0)} "
                f"mature_total={metrics.get('n_mature', 0)}"
            ),
            details=summary,
        )
    except Exception as exc:
        return JobRunResult(
            job="feedback_update",
            status="FAIL",
            exit_code=1,
            message=str(exc),
        )


def _run_background_validate(root: Path, env: Dict[str, str]) -> JobRunResult:
    if str(env.get("AA_BACKGROUND_VALIDATE_ENABLED", "0")).strip().lower() not in {"1", "true", "yes", "on"}:
        return JobRunResult(
            job="background_validate",
            status="DISABLED",
            exit_code=0,
            message="Set AA_BACKGROUND_VALIDATE_ENABLED=1 to run validation matrix.",
        )
    py = sys.executable
    cmd = [
        py,
        str(root / "tools" / "run_validation_matrix.py"),
        "--phase",
        "reference",
        "--runtime-profile",
        "background",
    ]
    proc = subprocess.run(cmd, cwd=str(root), env={**os.environ, **env})
    rc = int(proc.returncode)
    return JobRunResult(
        job="background_validate",
        status="OK" if rc == 0 else "FAIL",
        exit_code=rc,
        message="Reference validation finished" if rc == 0 else "Reference validation failed",
    )


def _run_adaptive_marktanalyse(root: Path, env: Dict[str, str]) -> JobRunResult:
    from aa_adaptive_runtime import run_adaptive_marktanalyse

    try:
        report = run_adaptive_marktanalyse(root, env, log_print=False, allow_retrain=True)
        plan = report.plan
        return JobRunResult(
            job="adaptive_marktanalyse",
            status="OK" if report.ok else "FAIL",
            exit_code=0 if report.ok else 1,
            message=f"mode={getattr(plan, 'mode', 'n/a')} price={getattr(plan, 'price_source', 'n/a')}",
            details={"notes": getattr(plan, "notes", []) if plan else []},
        )
    except Exception as exc:
        return JobRunResult(job="adaptive_marktanalyse", status="FAIL", exit_code=1, message=str(exc))


def _run_operational_refinement(root: Path, env: Dict[str, str]) -> JobRunResult:
    from aa_operational_refinement import load_refinement_config, run_operational_refinement

    try:
        cfg = load_refinement_config(root)
        report = run_operational_refinement(root, env, cfg=cfg, log_print=False)
        return JobRunResult(
            job="operational_refinement",
            status="OK" if report.ok else "FAIL",
            exit_code=0 if report.ok else 1,
            message=f"steps={len(report.steps)} r3_match={report.r3_regime_match}",
            details={"steps": report.steps, "r3_regime_match": report.r3_regime_match},
        )
    except Exception as exc:
        return JobRunResult(job="operational_refinement", status="FAIL", exit_code=1, message=str(exc))


_JOB_HANDLERS: Dict[str, Callable[[Path, Dict[str, str]], JobRunResult]] = {
    "realtime_collect": _run_realtime_collect,
    "eod_finalize": _run_eod_finalize,
    "rebalance_signal": _run_rebalance_signal,
    "portfolio_review_live": _run_portfolio_review_live,
    "feedback_update": _run_feedback_update,
    "background_validate": _run_background_validate,
    "operational_refinement": _run_operational_refinement,
    "adaptive_marktanalyse": _run_adaptive_marktanalyse,
}


def run_job(job: str, root: Path, env: Optional[Dict[str, str]] = None) -> JobRunResult:
    """Execute one background job with lock and status persistence."""
    env = dict(env or os.environ)
    root = Path(root)
    name = str(job).strip().lower()
    if name not in JOB_SPECS:
        return JobRunResult(job=name, status="FAIL", exit_code=2, message=f"Unknown job: {job}")

    spec = JOB_SPECS[name]
    started = _utc_now()
    if not job_enabled(spec, env):
        result = JobRunResult(
            job=name,
            status="DISABLED",
            exit_code=0,
            message=f"Job disabled — set {spec.env_var}=1 to enable.",
            started_at_utc=started,
            finished_at_utc=_utc_now(),
        )
        write_job_status(root, result)
        return result

    lock = JobLock(root, name)
    if not lock.acquire():
        result = JobRunResult(
            job=name,
            status="LOCKED",
            exit_code=3,
            message="Concurrent job instance already running.",
            started_at_utc=started,
            finished_at_utc=_utc_now(),
        )
        write_job_status(root, result)
        return result

    try:
        handler = _JOB_HANDLERS[name]
        result = handler(root, env)
        result.started_at_utc = started
        result.finished_at_utc = _utc_now()
        write_job_status(root, result)
        return result
    except Exception as exc:
        result = JobRunResult(
            job=name,
            status="FAIL",
            exit_code=1,
            message=str(exc),
            started_at_utc=started,
            finished_at_utc=_utc_now(),
        )
        write_job_status(root, result)
        return result
    finally:
        lock.release()
