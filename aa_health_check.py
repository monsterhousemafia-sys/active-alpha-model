"""Aggregate operational and analytical health for the control plane."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aa_failsafe import is_failsafe_active, load_failsafe_state, pipeline_status_label
from aa_model_status import build_model_status, resolve_integrity_label
from aa_ops_validation import validate_analytical_integrity
from aa_runtime_profile import BATCH_LOCK_FILE, is_batch_work_active


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_health_check(root: Path, out_dir: Path) -> Dict[str, Any]:
    """Return health snapshot without writing files."""
    root = Path(root)
    out_dir = Path(out_dir)
    model_status = build_model_status(out_dir)
    integrity_label = resolve_integrity_label(out_dir)
    analytical_ok, analytical_reason, run_id = validate_analytical_integrity(out_dir)
    system_status = _read_json(root / "system_status.json")
    batch_active = is_batch_work_active(root)
    batch_lock_pid = None
    lock_path = root / BATCH_LOCK_FILE
    if lock_path.is_file():
        try:
            batch_lock_pid = int(lock_path.read_text(encoding="utf-8").split()[0])
        except Exception:
            batch_lock_pid = None

    operational = "OK"
    if str(system_status.get("operational_health", "")).upper() in {"ERROR", "WARN"}:
        operational = str(system_status.get("operational_health", "WARN")).upper()
    elif batch_active:
        operational = "BUSY"

    analytical = "PASS" if analytical_ok else ("INVALID" if integrity_label == "FAIL" else "NOT_VALIDATED")
    overall = "OK"
    if analytical != "PASS":
        overall = "DEGRADED"
    if operational == "ERROR":
        overall = "ERROR"

    return {
        "checked_at_utc": _utc_now(),
        "overall_status": overall,
        "operational_health": operational,
        "analytical_validity": analytical,
        "integrity_status": integrity_label,
        "validated_run_id": run_id,
        "analytical_reason": analytical_reason if not analytical_ok else "",
        "batch_work_active": batch_active,
        "batch_lock_pid": batch_lock_pid,
        "active_variant_label": model_status.get("active_variant_label", ""),
        "auto_promotion_status": model_status.get("auto_promotion_status", "DISABLED"),
        "auto_research_status": model_status.get("auto_research_status", "NOT_IMPLEMENTED"),
        "next_development_step": model_status.get("next_development_step", ""),
    }


def build_system_health_record(root: Path, out_dir: Path, *, job_running: bool = False) -> Dict[str, Any]:
    """P0-compliant control/system_health.json payload."""
    base = run_health_check(root, out_dir)
    failsafe = load_failsafe_state(root)
    lkg_path = Path(root) / "control" / "last_known_good_state.json"
    lkg = _read_json(lkg_path)

    operational = str(base.get("operational_health", "OK")).upper()
    if operational == "BUSY":
        operational_health = "DEGRADED"
    elif operational == "ERROR":
        operational_health = "FAIL"
    else:
        operational_health = "OK"

    analytical = str(base.get("analytical_validity", "NOT_VALIDATED")).upper()
    if analytical == "INVALID":
        analytical_validity = "FAIL"
    elif analytical == "PASS":
        analytical_validity = "PASS"
    else:
        analytical_validity = "NOT_VALIDATED"

    active_signal = "NOT_AVAILABLE"
    if analytical_validity == "PASS":
        active_signal = "PASS"
    elif analytical_validity == "FAIL":
        active_signal = "FAIL"

    pipeline_status = pipeline_status_label(root, job_running=job_running)
    if is_failsafe_active(root):
        pipeline_status = "FAILSAFE_MODE"

    return {
        "operational_health": operational_health,
        "analytical_validity": analytical_validity,
        "active_signal_validity": active_signal,
        "pipeline_status": pipeline_status,
        "last_successful_job": str(base.get("last_successful_job", "") or ""),
        "last_failed_job": str(base.get("last_failed_job", "") or ""),
        "last_known_good_run_id": str(lkg.get("validated_run_id", lkg.get("run_id", "")) or ""),
        "last_known_good_model_id": str(lkg.get("validated_model_id", lkg.get("variant_id", "")) or ""),
        "last_updated_at_utc": base.get("checked_at_utc", _utc_now()),
        "critical_errors": list(failsafe.get("critical_errors") or []),
        # extended diagnostics (backward compatible)
        "integrity_status": base.get("integrity_status", ""),
        "validated_run_id": base.get("validated_run_id", ""),
        "active_variant_label": base.get("active_variant_label", ""),
        "batch_work_active": base.get("batch_work_active", False),
    }


def health_is_production_ready(health: Dict[str, Any]) -> bool:
    if str(health.get("pipeline_status", "")).upper() == "FAILSAFE_MODE":
        return False
    analytical = str(health.get("analytical_validity", "")).upper()
    integrity = str(health.get("integrity_status", "")).upper()
    if analytical == "PASS" and integrity in {"PASS", ""}:
        return True
    return (
        str(health.get("overall_status", "")).upper() == "OK"
        and analytical == "PASS"
        and integrity == "PASS"
    )
