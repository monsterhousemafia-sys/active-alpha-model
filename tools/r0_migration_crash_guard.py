#!/usr/bin/env python3
"""Crash / stale-lock recovery for R0 migration M1 matrix (fail-closed, non-blocking)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_evidence_schema import AUTHORITATIVE_CHAMPION  # noqa: E402
from aa_runtime_profile import BATCH_LOCK_FILE, cleanup_stale_batch_lock, is_batch_work_active  # noqa: E402
from aa_safe_io import atomic_write_json  # noqa: E402

EVIDENCE_REL = Path("evidence") / "r0_migration"
CONTROL_REL = Path("control") / "r0_migration"
MATRIX_LOG = EVIDENCE_REL / "validation_matrix_run.log"
MATRIX_JOB = EVIDENCE_REL / "matrix_job.json"
CRASH_RECOVERY = EVIDENCE_REL / "crash_recovery.json"
PHASE_STATUS = CONTROL_REL / "phase_status.json"

M1_VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _matrix_log_complete(root: Path) -> bool:
    log_path = root / MATRIX_LOG
    if not log_path.is_file():
        return False
    return "Summary: PASS=" in log_path.read_text(encoding="utf-8", errors="replace")


def _m1_returns_complete(root: Path) -> bool:
    manifest_path = root / EVIDENCE_REL / "returns_manifest.json"
    if manifest_path.is_file():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return bool(data.get("all_m1_variants_integrity_pass"))
        except Exception:
            pass
    try:
        from tools.run_r0_migration_phase_m1 import build_returns_manifest

        return bool(build_returns_manifest(root).get("all_m1_variants_integrity_pass"))
    except (ValueError, OSError, FileNotFoundError):
        return False


def append_matrix_log_session(root: Path, cmd: List[str], *, session: str) -> Path:
    """Append a new matrix session (never truncate prior crash logs)."""
    log_path = root / MATRIX_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n\n--- matrix session {session} started {_utc_now()} ---\n")
        log.write(" ".join(str(c) for c in cmd) + "\n\n")
        log.flush()
    return log_path


def _batch_lock_pid(root: Path) -> int:
    path = root / BATCH_LOCK_FILE
    if not path.is_file():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").split()[0])
    except Exception:
        return 0


def resolve_matrix_job_status(
    root: Path,
    *,
    returncode: Optional[int] = None,
    foreground: Optional[bool] = None,
) -> Dict[str, Any]:
    """Derive matrix_job status from live signals (not PID alone)."""
    batch_active = is_batch_work_active(root)
    returns_ok = _m1_returns_complete(root)
    log_ok = _matrix_log_complete(root)
    if batch_active:
        status = "RUNNING"
        reason = "batch_lock_active"
    elif returns_ok and log_ok:
        status = "FINISHED"
        reason = "returns_and_log_summary"
    elif returns_ok:
        status = "FINISHED_PARTIAL"
        reason = "returns_without_log_summary"
    elif log_ok:
        status = "FINISHED_PARTIAL"
        reason = "log_summary_without_returns"
    elif returncode is not None and int(returncode) != 0:
        status = "CRASHED"
        reason = f"nonzero_returncode_{returncode}"
    else:
        status = "INCOMPLETE"
        reason = "work_stopped_early"
    return {
        "status": status,
        "reason": reason,
        "batch_active": batch_active,
        "returns_ok": returns_ok,
        "log_summary_ok": log_ok,
        "returncode": returncode,
        "foreground": foreground,
        "resolved_at_utc": _utc_now(),
    }


def write_matrix_job(
    root: Path,
    job: Dict[str, Any],
    *,
    returncode: Optional[int] = None,
    foreground: Optional[bool] = None,
) -> Dict[str, Any]:
    """Merge job payload with resolved status and atomically persist."""
    resolved = resolve_matrix_job_status(
        root,
        returncode=returncode if returncode is not None else job.get("returncode"),
        foreground=foreground if foreground is not None else job.get("foreground"),
    )
    out = {**job, **resolved, "schema_version": 2, "updated_at_utc": _utc_now()}
    if resolved.get("batch_active"):
        lock_pid = _batch_lock_pid(root)
        if lock_pid > 0:
            out["pid"] = lock_pid
            out["lock_pid"] = lock_pid
    atomic_write_json(root / MATRIX_JOB, out)
    return out


def reconcile_matrix_job(root: Path) -> Dict[str, Any]:
    job_path = root / MATRIX_JOB
    job: Dict[str, Any] = {}
    if job_path.is_file():
        try:
            job = json.loads(job_path.read_text(encoding="utf-8"))
        except Exception:
            job = {}
    rc = job.get("returncode")
    return write_matrix_job(
        root,
        job,
        returncode=int(rc) if rc is not None else None,
        foreground=job.get("foreground"),
    )


def _m1_blockers(root: Path) -> List[str]:
    blockers: List[str] = []
    if not _m1_returns_complete(root):
        blockers.append("M1_VARIANT_RETURNS_MISSING")
    try:
        from tools.run_r0_migration_phase_m1 import build_env_audit

        env = build_env_audit(root)
        if env.get("issues"):
            blockers.append("ENV_ALPHA_MODEL_MODE_DRIFT")
    except (ValueError, OSError, FileNotFoundError):
        pass
    job = reconcile_matrix_job(root)
    st = str(job.get("status", "")).upper()
    if st in ("INCOMPLETE", "CRASHED"):
        blockers.append("MATRIX_INCOMPLETE_OR_CRASHED")
    elif st == "RUNNING":
        blockers.append("MATRIX_RUNNING")
    return blockers


def reconcile_m1_phase_status(root: Path) -> Dict[str, Any]:
    """Keep phase_status honest: IN_PROGRESS when blockers, SEALED only via seal tool."""
    from tools.r0_migration_phase_guard import is_phase_sealed

    status_path = root / PHASE_STATUS
    data: Dict[str, Any] = {}
    if status_path.is_file():
        data = json.loads(status_path.read_text(encoding="utf-8"))
    phases = data.get("phases") or {}
    if is_phase_sealed(root, "M1"):
        return data
    blockers = _m1_blockers(root)
    if blockers:
        phases["M1"] = {
            "status": "IN_PROGRESS",
            "updated_at_utc": _utc_now(),
            "blockers": blockers,
        }
        phases["M2"] = {"status": "PENDING", "blocked_by": blockers[0]}
        data["current_phase"] = "M1"
        data["last_completed_phase"] = "M0" if is_phase_sealed(root, "M0") else data.get("last_completed_phase", "M0")
    else:
        phases["M1"] = {"status": "READY_TO_SEAL", "updated_at_utc": _utc_now(), "blockers": []}
        phases["M2"] = {"status": "READY", "blocked_by": None}
        data["current_phase"] = "M1"
    data["phases"] = phases
    data["updated_at_utc"] = _utc_now()
    atomic_write_json(status_path, data)
    atomic_write_json(
        root / "control" / "r0_migration_program.json",
        {
            "schema_version": 1,
            "program": "R0_LONG_TERM_MIGRATION",
            "current_phase": data.get("current_phase"),
            "last_completed_phase": data.get("last_completed_phase"),
            "updated_at_utc": _utc_now(),
            "m1_blockers": blockers,
            "recovery_note": "reconcile_m1_phase_status",
        },
    )
    return data


def write_crash_recovery_snapshot(root: Path, *, actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    from tools.r0_migration_m1_control import m1_hints

    lock_path = root / BATCH_LOCK_FILE
    lock_text = lock_path.read_text(encoding="utf-8").strip() if lock_path.is_file() else ""
    payload = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "authoritative_champion_unchanged": AUTHORITATIVE_CHAMPION,
        "batch_lock_present": lock_path.is_file(),
        "batch_lock_line": lock_text or None,
        "batch_active": is_batch_work_active(root),
        "matrix_job": reconcile_matrix_job(root),
        "m1_blockers": _m1_blockers(root),
        "returns_complete": _m1_returns_complete(root),
        "log_summary_present": _matrix_log_complete(root),
        "actions": actions,
        **m1_hints(),
    }
    atomic_write_json(root / CRASH_RECOVERY, payload)
    return payload


def ensure_m1_unblocked(root: Path) -> Dict[str, Any]:
    """Run at every M1 entry: remove stale locks, reconcile job + phase status."""
    actions: List[Dict[str, Any]] = []
    lock_result = cleanup_stale_batch_lock(root)
    actions.append({"action": "cleanup_stale_batch_lock", **lock_result})
    job = reconcile_matrix_job(root)
    actions.append({"action": "reconcile_matrix_job", "status": job.get("status")})
    phase = reconcile_m1_phase_status(root)
    actions.append({"action": "reconcile_m1_phase_status", "m1_status": (phase.get("phases") or {}).get("M1", {}).get("status")})
    snapshot = write_crash_recovery_snapshot(root, actions=actions)
    return {"unblocked": not snapshot.get("batch_active") or snapshot.get("returns_complete"), "snapshot": snapshot}
