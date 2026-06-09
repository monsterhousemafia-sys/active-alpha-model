"""Pipeline phase orchestration — controlled auto-continue after PASS."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_control_plane import append_incident, load_pipeline, phase_by_id
from aa_failsafe import is_failsafe_active
from aa_job_lock import JobLock
from aa_safe_io import atomic_write_json, atomic_write_yaml

PENDING_SCHEMA_VERSION = 1
PENDING_FILE = "control/pipeline_pending.json"
PHASE_LOCK_JOB = "pipeline_phase"
MAX_ATTEMPT_COUNT = 3

PENDING_STATUS_IDLE = "IDLE"
PENDING_STATUS_PENDING = "PENDING"
PENDING_STATUS_CLAIMED = "CLAIMED"
PENDING_STATUS_RUNNING = "RUNNING"
PENDING_STATUS_BLOCKED = "BLOCKED"
PENDING_STATUS_FAILED = "FAILED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _pending_path(root: Path) -> Path:
    return Path(root) / PENDING_FILE


def empty_pending() -> Dict[str, Any]:
    return {
        "schema_version": PENDING_SCHEMA_VERSION,
        "has_work": False,
        "pending_phase": "",
        "created_from_phase": "",
        "reason": "",
        "created_at_utc": "",
        "requires_preflight": True,
        "status": PENDING_STATUS_IDLE,
        "attempt_count": 0,
        "last_attempt_at_utc": "",
        "blocked_reason": "",
        "followup_prompt": "",
        "details": {},
        "updated_at_utc": _utc_now(),
    }


def load_pending(root: Path) -> Dict[str, Any]:
    path = _pending_path(root)
    if not path.is_file():
        return empty_pending()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return empty_pending()
    if not isinstance(raw, dict):
        return empty_pending()
    if int(raw.get("schema_version", 0) or 0) != PENDING_SCHEMA_VERSION:
        # Legacy file — preserve has_work but upgrade shape on next write.
        migrated = empty_pending()
        migrated.update({k: v for k, v in raw.items() if k in migrated or k == "details"})
        migrated["schema_version"] = PENDING_SCHEMA_VERSION
        if raw.get("has_work") and not migrated.get("pending_phase"):
            pipeline = load_pipeline(root)
            migrated["pending_phase"] = current_phase_id(pipeline)
            migrated["status"] = PENDING_STATUS_PENDING
        return migrated
    return raw


def save_pending(root: Path, payload: Dict[str, Any]) -> Path:
    data = dict(payload)
    data["schema_version"] = PENDING_SCHEMA_VERSION
    data["updated_at_utc"] = _utc_now()
    return atomic_write_json(_pending_path(root), data)


def current_phase_id(pipeline: Dict[str, Any]) -> str:
    if pipeline.get("current_phase"):
        return str(pipeline["current_phase"])
    return str(pipeline.get("current_stage", "unknown"))


def phase_status(pipeline: Dict[str, Any], phase_id: str) -> str:
    phase = phase_by_id(pipeline, phase_id)
    return str(phase.get("status", "NOT_STARTED")).upper()


def permitted_next_phase(pipeline: Dict[str, Any], from_phase_id: str) -> Optional[str]:
    phase = phase_by_id(pipeline, from_phase_id)
    nxt = phase.get("next_phase")
    if nxt is None or nxt == "":
        return None
    return str(nxt)


def auto_continue_enabled(pipeline: Dict[str, Any]) -> bool:
    if not bool(pipeline.get("auto_continue_after_pass", False)):
        return False
    policy = pipeline.get("control_policy") or {}
    return bool(policy.get("enqueue_next_phase_after_pass", True))


def resolve_enqueue_target(pipeline: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Return (pending_phase, created_from_phase) when auto-enqueue is eligible."""
    phases = list(pipeline.get("phases") or [])
    if not phases:
        return None
    current = current_phase_id(pipeline)
    current_st = phase_status(pipeline, current)
    if current_st not in {"NOT_STARTED", "PENDING"}:
        return None
    for idx, phase in enumerate(phases):
        pid = str(phase.get("id", ""))
        if pid != current:
            continue
        if idx == 0:
            return None
        prev = phases[idx - 1]
        prev_id = str(prev.get("id", ""))
        if str(prev.get("status", "")).upper() != "PASS":
            return None
        expected = permitted_next_phase(pipeline, prev_id)
        if expected != current:
            return None
        return current, prev_id
    return None


def validate_pending_phase(
    root: Path,
    pending: Dict[str, Any],
    *,
    pipeline: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    pipeline = pipeline or load_pipeline(root)
    if is_failsafe_active(root):
        return False, "FAILSAFE_MODE active"
    if not pending.get("has_work"):
        return False, "no pending work"
    status = str(pending.get("status", "")).upper()
    if status in {PENDING_STATUS_BLOCKED, PENDING_STATUS_FAILED}:
        return False, f"pending status {status}"
    if int(pending.get("attempt_count", 0) or 0) >= MAX_ATTEMPT_COUNT:
        return False, "max attempt count exceeded"
    pending_phase = str(pending.get("pending_phase", "") or "")
    if not pending_phase:
        return False, "missing pending_phase"
    current = current_phase_id(pipeline)
    if pending_phase != current:
        return False, f"pending_phase {pending_phase} != current_phase {current}"
    created_from = str(pending.get("created_from_phase", "") or "")
    if created_from and phase_status(pipeline, created_from) != "PASS":
        return False, f"created_from_phase {created_from} not PASS"
    expected = resolve_enqueue_target(pipeline)
    if expected is None:
        return False, "enqueue target not eligible"
    exp_pending, exp_from = expected
    if pending_phase != exp_pending or (created_from and created_from != exp_from):
        return False, "pending_phase not permitted by pipeline"
    if phase_status(pipeline, pending_phase) not in {"NOT_STARTED", "PENDING"}:
        return False, f"phase {pending_phase} not enqueueable"
    return True, ""


def build_followup_prompt(pending: Dict[str, Any], pipeline: Dict[str, Any]) -> str:
    custom = str(pending.get("followup_prompt") or "").strip()
    if custom:
        return custom
    phase_id = str(pending.get("pending_phase") or current_phase_id(pipeline))
    phase = phase_by_id(pipeline, phase_id)
    goal = str(phase.get("goal", phase_id)).strip()
    return (
        f"Active Alpha Autopilot — isolated phase run for `{phase_id}`.\n\n"
        f"Read CURSOR_ACTIVE_ALPHA_AUTOPILOT_MASTERPROMPT.md, IMPLEMENTATION_STATUS.md, "
        f"DEVELOPMENT_PIPELINE.yaml, and control/pipeline_pending.json.\n\n"
        f"Execute ONLY `{phase_id}` in this run (one_new_phase_per_run). "
        f"Do not change economic model parameters. Do not enable real-money orders.\n\n"
        f"Phase goal: {goal}\n\n"
        f"Run fast preflight tests, implement/verify the phase gate, update status atomically, "
        f"then enqueue the next permitted phase if auto_continue_after_pass is enabled."
    )


def enqueue_next_phase(
    root: Path,
    *,
    pending_phase: str,
    created_from_phase: str,
    reason: str,
    followup_prompt: str = "",
) -> Tuple[bool, str]:
    root = Path(root)
    if is_failsafe_active(root):
        return False, "FAILSAFE_MODE active"
    pipeline = load_pipeline(root)
    if not auto_continue_enabled(pipeline):
        return False, "auto_continue_after_pass disabled"
    if phase_status(pipeline, created_from_phase) != "PASS":
        return False, f"{created_from_phase} not PASS"
    expected = permitted_next_phase(pipeline, created_from_phase)
    if expected != pending_phase:
        return False, f"{pending_phase} not next after {created_from_phase}"
    if phase_status(pipeline, pending_phase) not in {"NOT_STARTED", "PENDING"}:
        return False, f"{pending_phase} not NOT_STARTED"
    current = current_phase_id(pipeline)
    if pending_phase != current:
        return False, f"current_phase {current} != {pending_phase}"
    existing = load_pending(root)
    if existing.get("has_work") and str(existing.get("pending_phase")) == pending_phase:
        if str(existing.get("status", "")).upper() not in {PENDING_STATUS_BLOCKED, PENDING_STATUS_FAILED}:
            return True, "already enqueued"
    prompt = followup_prompt or build_followup_prompt(
        {"pending_phase": pending_phase, "followup_prompt": ""},
        pipeline,
    )
    payload = empty_pending()
    payload.update(
        {
            "has_work": True,
            "pending_phase": pending_phase,
            "created_from_phase": created_from_phase,
            "reason": reason,
            "created_at_utc": _utc_now(),
            "requires_preflight": True,
            "status": PENDING_STATUS_PENDING,
            "attempt_count": 0,
            "blocked_reason": "",
            "followup_prompt": prompt,
            "details": existing.get("details") or {},
        }
    )
    save_pending(root, payload)
    return True, "enqueued"


def enqueue_eligible_phase(root: Path, *, reason: str = "") -> Tuple[bool, str]:
    pipeline = load_pipeline(root)
    if not auto_continue_enabled(pipeline):
        return False, "auto_continue disabled"
    target = resolve_enqueue_target(pipeline)
    if target is None:
        return False, "no eligible target"
    pending_phase, created_from = target
    default_reason = reason or f"{created_from} passed; next phase permitted"
    return enqueue_next_phase(
        root,
        pending_phase=pending_phase,
        created_from_phase=created_from,
        reason=default_reason,
    )


def clear_pending_on_failsafe(root: Path) -> None:
    if not is_failsafe_active(root):
        return
    pending = load_pending(root)
    if not pending.get("has_work"):
        return
    pending["has_work"] = False
    pending["status"] = PENDING_STATUS_BLOCKED
    pending["blocked_reason"] = "FAILSAFE_MODE active"
    save_pending(root, pending)
    append_incident(
        Path(root) / "control",
        event="pending_cleared_failsafe",
        details={"pending_phase": pending.get("pending_phase", "")},
    )


def merge_maintenance_details(
    root: Path,
    *,
    details: Optional[Dict[str, Any]] = None,
    maintenance_has_work: bool = False,
    maintenance_prompt: str = "",
) -> Dict[str, Any]:
    """Update maintenance details without clearing an active phase pending job."""
    pending = load_pending(root)
    merged_details = dict(pending.get("details") or {})
    if details:
        merged_details.update(details)
    pending["details"] = merged_details
    phase_active = bool(pending.get("has_work")) and str(pending.get("pending_phase", ""))
    if phase_active:
        save_pending(root, pending)
        return pending
    pending["has_work"] = bool(maintenance_has_work)
    if maintenance_prompt:
        pending["followup_prompt"] = maintenance_prompt
    if not maintenance_has_work:
        pending["status"] = PENDING_STATUS_IDLE
    save_pending(root, pending)
    return pending


def claim_pending_phase(root: Path) -> Tuple[bool, Dict[str, Any], str]:
    """Atomically claim pending phase work (single consumer)."""
    root = Path(root)
    clear_pending_on_failsafe(root)
    pending = load_pending(root)
    ok, reason = validate_pending_phase(root, pending)
    if not ok:
        return False, pending, reason
    lock = JobLock(root, PHASE_LOCK_JOB)
    if not lock.acquire():
        return False, pending, "phase lock held by another process"
    try:
        pending = load_pending(root)
        ok, reason = validate_pending_phase(root, pending)
        if not ok:
            return False, pending, reason
        attempt = int(pending.get("attempt_count", 0) or 0)
        status = str(pending.get("status", PENDING_STATUS_IDLE)).upper()
        if status == PENDING_STATUS_PENDING:
            attempt += 1
            pending["attempt_count"] = attempt
            pending["status"] = PENDING_STATUS_CLAIMED
        elif status in {PENDING_STATUS_CLAIMED, PENDING_STATUS_RUNNING}:
            pass
        else:
            return False, pending, f"cannot claim status {status}"
        if attempt > MAX_ATTEMPT_COUNT:
            mark_pending_blocked(root, "max attempt count exceeded")
            return False, pending, "max attempt count exceeded"
        pending["last_attempt_at_utc"] = _utc_now()
        save_pending(root, pending)
        return True, pending, ""
    finally:
        lock.release()


def mark_pending_blocked(root: Path, reason: str) -> None:
    pending = load_pending(root)
    pending["has_work"] = False
    pending["status"] = PENDING_STATUS_BLOCKED
    pending["blocked_reason"] = reason
    save_pending(root, pending)


def mark_pending_failed(root: Path, reason: str) -> None:
    pending = load_pending(root)
    if int(pending.get("attempt_count", 0) or 0) >= MAX_ATTEMPT_COUNT:
        pending["has_work"] = False
        pending["status"] = PENDING_STATUS_BLOCKED
        pending["blocked_reason"] = f"max attempts: {reason}"
    else:
        pending["status"] = PENDING_STATUS_FAILED
        pending["blocked_reason"] = reason
    save_pending(root, pending)


def hook_evaluate(root: Path) -> Tuple[bool, str]:
    """Evaluate whether Cursor stop hook should emit a follow-up message."""
    root = Path(root)
    if is_failsafe_active(root):
        clear_pending_on_failsafe(root)
        return False, ""
    pending = load_pending(root)
    if not pending.get("has_work"):
        return False, ""
    ok, reason = validate_pending_phase(root, pending)
    if not ok:
        if "max attempt" in reason or "not permitted" in reason:
            mark_pending_blocked(root, reason)
        return False, ""
    claimed, pending, claim_reason = claim_pending_phase(root)
    if not claimed:
        return False, ""
    pipeline = load_pipeline(root)
    prompt = build_followup_prompt(pending, pipeline)
    return True, prompt


def loop_may_continue(root: Path) -> Tuple[bool, str]:
    if is_failsafe_active(root):
        return False, "FAILSAFE_MODE"
    pending = load_pending(root)
    if pending.get("has_work"):
        ok, reason = validate_pending_phase(root, pending)
        if ok:
            return True, "phase pending"
        return False, reason
    return False, "no pending work"


def _build_pipeline_yaml_document(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    """Build a YAML-serializable document mirroring canonical JSON pipeline state."""
    doc: Dict[str, Any] = {
        "pipeline_name": pipeline.get("pipeline_name", "active_alpha_continuous_improvement"),
        "pipeline_version": pipeline.get("pipeline_version", pipeline.get("version", 4)),
        "auto_continue_after_pass": bool(pipeline.get("auto_continue_after_pass", True)),
        "automatic_real_money_execution": bool(pipeline.get("automatic_real_money_execution", False)),
        "failsafe_required": bool(pipeline.get("failsafe_required", True)),
        "current_phase": str(pipeline.get("current_phase", "")),
    }
    if pipeline.get("control_policy"):
        doc["control_policy"] = dict(pipeline["control_policy"])
    if pipeline.get("automation_defaults"):
        doc["automation_defaults"] = dict(pipeline["automation_defaults"])
    phases: List[Dict[str, Any]] = []
    for phase in pipeline.get("phases") or []:
        entry: Dict[str, Any] = {
            "id": str(phase.get("id", "")),
            "status": str(phase.get("status", "NOT_STARTED")),
        }
        nxt = phase.get("next_phase")
        entry["next_phase"] = None if nxt in {None, ""} else str(nxt)
        goal = str(phase.get("goal", "") or "").strip()
        if goal:
            entry["goal"] = goal
        phases.append(entry)
    doc["phases"] = phases
    stages = pipeline.get("stages")
    if stages:
        doc["stages"] = stages
    if pipeline.get("acceptance_audit_p8"):
        doc["acceptance_audit_p8"] = pipeline["acceptance_audit_p8"]
    return doc


def _sync_pipeline_yaml(root: Path, pipeline: Dict[str, Any]) -> None:
    """Mirror full canonical pipeline state into YAML (JSON is canonical)."""
    yaml_path = Path(root) / "DEVELOPMENT_PIPELINE.yaml"
    doc = _build_pipeline_yaml_document(pipeline)
    atomic_write_yaml(yaml_path, doc, sort_keys=False)


def mark_phase_pass_and_enqueue(root: Path, passed_phase_id: str) -> Tuple[bool, str]:
    """After a phase gate passes: update pipeline status and enqueue next phase."""
    from aa_control_plane import load_pipeline as _load

    pipeline = _load(root)
    phases = list(pipeline.get("phases") or [])
    updated = False
    for phase in phases:
        if str(phase.get("id")) == passed_phase_id:
            phase["status"] = "PASS"
            updated = True
            nxt = phase.get("next_phase")
            if nxt:
                pipeline["current_phase"] = str(nxt)
            break
    if not updated:
        return False, f"unknown phase {passed_phase_id}"
    atomic_write_json(Path(root) / "DEVELOPMENT_PIPELINE.json", pipeline)
    _sync_pipeline_yaml(root, pipeline)
    if not auto_continue_enabled(pipeline):
        return True, "phase marked PASS; auto_continue disabled"
    nxt_phase = permitted_next_phase(pipeline, passed_phase_id)
    if not nxt_phase:
        pending = load_pending(root)
        if str(pending.get("pending_phase", "")) == passed_phase_id:
            cleared = empty_pending()
            cleared["details"] = dict(pending.get("details") or {})
            save_pending(root, cleared)
        return True, "phase marked PASS; no next phase"
    return enqueue_next_phase(
        root,
        pending_phase=nxt_phase,
        created_from_phase=passed_phase_id,
        reason=f"{passed_phase_id} passed; next phase permitted",
    )
