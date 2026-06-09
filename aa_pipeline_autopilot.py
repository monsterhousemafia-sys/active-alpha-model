"""Unattended development pipeline runner — no manual Run required."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_job_lock import pid_alive, read_lock_owner
from aa_ops_refresh import AutopilotOutDirError, resolve_autopilot_out_dir
from aa_runtime_profile import BATCH_LOCK_FILE
from aa_pipeline_orchestration import merge_maintenance_details, load_pending
from aa_safe_io import atomic_write_json

M1_KEY = "M1_MOM_BLEND_MATCHED_CONTROLS"
AUTOPILOT_CONFIG = "control/autopilot.json"
PENDING_FILE = "control/pipeline_pending.json"
RUNNER_LOG = "control/pipeline_runner.jsonl"
RUNNER_STATE = "control/pipeline_runner_state.json"

DEFAULT_AUTOPILOT = {
    "enabled": True,
    "cursor_auto_continue": True,
    "local_loop_enabled": True,
    "loop_interval_seconds": 300,
    "tick_timeout_seconds": 900,
    "quick_tests_timeout_seconds": 600,
    "run_m1_validation": True,
    "run_challenger_eval": True,
    "run_quick_tests": True,
    "sync_control_plane": True,
    "sync_outcome_ledger": True,
    "run_operational_refinement": True,
    "stuck_run_timeout_minutes": 45,
    "stale_pending_max_age_hours": 168,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_event(root: Path, event: str, **details: Any) -> None:
    ctrl = Path(root) / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"at_utc": _utc_now(), "event": event, **details}, ensure_ascii=False, sort_keys=True)
    with (ctrl / "pipeline_runner.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_autopilot_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / AUTOPILOT_CONFIG
    cfg = dict(DEFAULT_AUTOPILOT)
    if path.is_file():
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_runner_state(root: Path, state: Dict[str, Any]) -> None:
    atomic_write_json(Path(root) / RUNNER_STATE, state)


def write_pending(root: Path, *, has_work: bool, followup_prompt: str = "", details: Optional[Dict[str, Any]] = None) -> None:
    """Legacy helper — preserves active phase pending jobs."""
    merge_maintenance_details(
        root,
        details=details,
        maintenance_has_work=has_work,
        maintenance_prompt=followup_prompt,
    )


def _integrity_pass(out_dir: Path) -> bool:
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        return False
    try:
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        if str(meta.get("integrity_status", meta.get("status", ""))) != "PASS":
            return False
    except Exception:
        return False
    report = out_dir / "integrity_report.json"
    if not report.is_file():
        return False
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
        return str(data.get("status", "")) == "PASS" and not data.get("errors")
    except Exception:
        return False


def find_m1_pass_dir(root: Path) -> Optional[Path]:
    validation_root = Path(root) / "validation_runs"
    if not validation_root.is_dir():
        return None
    candidates: List[Path] = []
    for child in validation_root.iterdir():
        if child.is_dir() and child.name.endswith(f"_{M1_KEY}") and _integrity_pass(child):
            matched = child / "mom_blend_matched_controls_daily_returns.csv"
            if matched.is_file():
                candidates.append(child)
    return sorted(candidates)[-1] if candidates else None


def find_m1_work_dir(root: Path) -> Optional[Path]:
    validation_root = Path(root) / "validation_runs"
    if not validation_root.is_dir():
        return None
    candidates: List[Path] = []
    for child in validation_root.iterdir():
        if child.is_dir() and child.name.endswith(f"_{M1_KEY}"):
            candidates.append(child)
    if not candidates:
        return None
    return sorted(candidates)[-1]


def cleanup_stale_batch_lock(root: Path) -> bool:
    path = Path(root) / BATCH_LOCK_FILE
    if not path.is_file():
        return False
    pid = read_lock_owner(path)
    if pid is None or not pid_alive(pid):
        try:
            path.unlink(missing_ok=True)
            _log_event(root, "stale_batch_lock_removed", pid=pid)
            return True
        except OSError:
            return False
    return False


def _dir_stuck(out_dir: Path, timeout_minutes: int) -> bool:
    markers = [
        out_dir / "integrity_report.json",
        out_dir / "strategy_daily_returns.csv",
        out_dir / "backtest_report.txt",
    ]
    if any(p.is_file() for p in markers):
        return False
    cache = out_dir / "prediction_cache.pkl"
    if not cache.is_file():
        return False
    age_s = time.time() - cache.stat().st_mtime
    return age_s > max(60, int(timeout_minutes) * 60)


def kill_stuck_batch_owner(root: Path, *, timeout_minutes: int) -> bool:
    path = Path(root) / BATCH_LOCK_FILE
    if not path.is_file():
        return False
    pid = read_lock_owner(path)
    if pid is None or not pid_alive(pid):
        return cleanup_stale_batch_lock(root)
    work_dir = find_m1_work_dir(root)
    if work_dir is None or not _dir_stuck(work_dir, timeout_minutes):
        return False
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    time.sleep(1.0)
    cleanup_stale_batch_lock(root)
    _log_event(root, "killed_stuck_batch", pid=pid, work_dir=str(work_dir))
    return True


def is_batch_work_active(root: Path) -> bool:
    path = Path(root) / BATCH_LOCK_FILE
    if not path.is_file():
        return False
    pid = read_lock_owner(path)
    return pid is not None and pid_alive(pid)


@dataclass
class AutopilotReport:
    steps: List[Dict[str, Any]] = field(default_factory=list)
    has_pending_work: bool = False
    followup_prompt: str = ""

    def add(self, name: str, status: str, **extra: Any) -> None:
        self.steps.append({"step": name, "status": status, **extra})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "at_utc": _utc_now(),
            "steps": self.steps,
            "has_pending_work": self.has_pending_work,
            "followup_prompt": self.followup_prompt,
        }


def _python(root: Path) -> str:
    venv = Path(root) / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        return str(venv)
    return sys.executable


def run_quick_tests(root: Path, *, timeout_s: int = 600) -> Tuple[str, str]:
    cmd = [
        _python(root),
        "-m",
        "pytest",
        "tests/test_prediction_outcomes.py",
        "tests/test_control_plane.py",
        "tests/test_challenger_eval.py",
        "tests/test_p5_realtime_replay.py",
        "tests/test_p6_behavioral_feature_research.py",
        "tests/test_p7_auto_promotion.py",
        "tests/test_p8_acceptance_audit.py",
        "tests/test_pipeline_autopilot.py",
        "tests/test_pipeline_orchestration.py",
        "tests/test_phase1_foundation.py",
        "-q",
        "--tb=line",
    ]
    timeout_s = int(timeout_s or 600)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=max(60, timeout_s),
        )
    except subprocess.TimeoutExpired:
        _log_event(root, "quick_tests_timeout", timeout_s=timeout_s)
        return "FAIL", f"pytest timeout after {timeout_s}s"
    tail = (proc.stdout or proc.stderr or "")[-500:]
    return ("OK" if proc.returncode == 0 else "FAIL"), tail


def run_m1_validation(root: Path, *, cpu_cores: int = 16) -> Tuple[str, str]:
    py = _python(root)
    cmd = [
        py,
        str(Path(root) / "tools" / "run_validation_matrix.py"),
        "--phase",
        "matrix",
        "--variant",
        M1_KEY,
        "--parallel-jobs",
        "1",
        "--cpu-cores",
        str(cpu_cores),
        "--runtime-profile",
        "turbo",
        "--no-skip-complete",
    ]
    env = dict(os.environ)
    env.setdefault("AA_CPU_CORES", str(cpu_cores))
    env.setdefault("AA_RESERVE_CPU_CORES", "0")
    env.setdefault("AA_RUNTIME_PROFILE", "turbo")
    env.setdefault("AA_PROCESS_PRIORITY", "high")
    proc = subprocess.run(cmd, cwd=str(root), env=env)
    return ("OK" if proc.returncode == 0 else "FAIL"), f"rc={proc.returncode}"


def update_pipeline_blockers(root: Path) -> str:
    m1_dir = find_m1_pass_dir(root)
    pipeline_json = Path(root) / "DEVELOPMENT_PIPELINE.json"
    if not pipeline_json.is_file():
        return "SKIP"
    try:
        pipeline = json.loads(pipeline_json.read_text(encoding="utf-8"))
    except Exception:
        return "FAIL"
    stages = dict(pipeline.get("stages") or {})
    p2 = dict(stages.get("phase2_outcome_ledger") or {})
    blockers = list(p2.get("blockers") or [])
    m1_blocker = "M1 matched-controls reference run not yet archived in validation_runs"
    if m1_dir is not None:
        blockers = [b for b in blockers if b != m1_blocker]
        if m1_blocker not in blockers and not blockers:
            p2["blockers"] = []
    else:
        if m1_blocker not in blockers:
            blockers.append(m1_blocker)
        p2["blockers"] = blockers
    stages["phase2_outcome_ledger"] = p2
    pipeline["stages"] = stages
    atomic_write_json(pipeline_json, pipeline)
    return "OK"


def release_stale_pending_work(root: Path, *, max_age_hours: int = 168) -> bool:
    """Clear phantom pending jobs that were never claimed (prevents infinite wait)."""
    from aa_pipeline_orchestration import load_pending, save_pending

    pending = load_pending(root)
    if not pending.get("has_work"):
        return False
    if int(pending.get("attempt_count") or 0) > 0:
        return False
    created = str(pending.get("created_at_utc") or pending.get("updated_at_utc") or "")
    if not created:
        return False
    try:
        ts = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0
    if age_h < float(max_age_hours):
        return False
    pending["has_work"] = False
    pending["status"] = "STALE_RELEASED"
    pending["blocked_reason"] = f"stale_pending_auto_released_after_{int(age_h)}h"
    pending["updated_at_utc"] = _utc_now()
    save_pending(root, pending)
    _log_event(root, "stale_pending_released", age_hours=round(age_h, 1))
    return True


def run_autopilot_once(root: Path, *, cfg: Optional[Dict[str, Any]] = None) -> AutopilotReport:
    root = Path(root)
    cfg = cfg or load_autopilot_config(root)
    report = AutopilotReport()
    if not cfg.get("enabled", True):
        report.add("autopilot", "DISABLED")
        write_pending(root, has_work=False)
        return report

    if release_stale_pending_work(
        root, max_age_hours=int(cfg.get("stale_pending_max_age_hours", 168) or 168)
    ):
        report.add("stale_pending_release", "OK")

    try:
        out_dir, _resolved_env = resolve_autopilot_out_dir(root)
    except AutopilotOutDirError as exc:
        report.add("resolve_out_dir", "FAIL", error=str(exc))
        merge_maintenance_details(
            root,
            details={"out_dir_error": str(exc)},
            maintenance_has_work=False,
        )
        return report

    if kill_stuck_batch_owner(root, timeout_minutes=int(cfg.get("stuck_run_timeout_minutes", 45))):
        report.add("kill_stuck_batch", "OK")
    elif cleanup_stale_batch_lock(root):
        report.add("cleanup_stale_lock", "OK")

    if cfg.get("run_operational_refinement", True) and not is_batch_work_active(root):
        try:
            from aa_operational_refinement import load_refinement_config, run_operational_refinement

            ref_cfg = load_refinement_config(root)
            ref_report = run_operational_refinement(root, cfg=ref_cfg, log_print=False)
            report.add(
                "operational_refinement",
                "OK" if ref_report.ok else "WARN",
                r3_regime_match=ref_report.r3_regime_match,
                steps=len(ref_report.steps),
            )
        except Exception as exc:
            report.add("operational_refinement", "FAIL", error=str(exc))

    if cfg.get("sync_control_plane", True):
        try:
            from aa_control_plane import sync_control_plane, write_next_cursor_prompt

            sync_control_plane(root, out_dir)
            write_next_cursor_prompt(root)
            report.add("sync_control_plane", "OK")
        except Exception as exc:
            report.add("sync_control_plane", "FAIL", error=str(exc))

    if cfg.get("sync_outcome_ledger", True):
        try:
            from aa_prediction_outcomes import update_prediction_outcomes

            summary = update_prediction_outcomes(out_dir)
            report.add("sync_outcome_ledger", "OK", mature=summary.get("metrics", {}).get("n_mature", 0))
        except Exception as exc:
            report.add("sync_outcome_ledger", "FAIL", error=str(exc))

    m1_done = find_m1_pass_dir(root) is not None
    batch_busy = is_batch_work_active(root)

    if m1_done:
        report.add("m1_validation", "SKIP", reason="already_pass")
    elif batch_busy:
        report.add("m1_validation", "BUSY")
        report.has_pending_work = True
        report.followup_prompt = (
            "M1 validation still running. Check control/pipeline_runner.jsonl and validation_runs. "
            "When batch lock clears, continue pipeline autopilot."
        )
    elif cfg.get("run_m1_validation", True):
        status, detail = run_m1_validation(root, cpu_cores=int(os.environ.get("AA_CPU_CORES", "16") or 16))
        report.add("m1_validation", status, detail=detail)
        m1_done = status == "OK" and find_m1_pass_dir(root) is not None
        if status == "FAIL":
            report.has_pending_work = True
            report.followup_prompt = "M1 validation failed. Inspect validation_runs and fix; then continue autopilot."

    update_pipeline_blockers(root)

    if cfg.get("run_challenger_eval", True) and m1_done:
        try:
            from aa_background_research import run_background_research

            summary = run_background_research(root, out_dir)
            report.add(
                "background_research",
                "OK" if summary.get("status") == "OK" else str(summary.get("status", "FAIL")),
                research_status=summary.get("research_status"),
                variants_checked=summary.get("variants_checked"),
            )
        except Exception as exc:
            report.add("background_research", "FAIL", error=str(exc))

    if cfg.get("run_quick_tests", True) and not batch_busy:
        q_timeout = int(cfg.get("quick_tests_timeout_seconds", 600) or 600)
        status, tail = run_quick_tests(root, timeout_s=q_timeout)
        report.add("quick_tests", status, tail=tail[-200:] if tail else "")

    if not m1_done and cfg.get("run_m1_validation", True) and not batch_busy:
        report.has_pending_work = True
        if not report.followup_prompt:
            report.followup_prompt = "Continue development pipeline: complete M1 matched-controls validation."

    merge_maintenance_details(
        root,
        details={"m1_complete": m1_done, "batch_busy": batch_busy},
        maintenance_has_work=report.has_pending_work,
        maintenance_prompt=report.followup_prompt,
    )
    pending = load_pending(root)
    report.has_pending_work = bool(pending.get("has_work"))
    report.followup_prompt = str(pending.get("followup_prompt") or report.followup_prompt or "")
    save_runner_state(root, report.to_dict())
    _log_event(root, "autopilot_tick", **report.to_dict())
    return report
