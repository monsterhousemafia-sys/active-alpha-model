"""P8 acceptance audit helpers — backup, verification, safe commissioning."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from aa_safe_io import atomic_write_json, atomic_write_text, atomic_write_yaml

AUDIT_BACKUP_ROOT = Path("control") / "audit_backups"

PHASE_EVIDENCE: Dict[str, Dict[str, Any]] = {
    "P0_SAFETY_CONTROL_PLANE": {
        "modules": ["aa_safe_io.py", "aa_job_lock.py", "aa_failsafe.py", "aa_recovery.py", "aa_p0_paths.py"],
        "tests": ["tests/test_p0_safety_control_plane.py"],
    },
    "P1_INTEGRITY_FOUNDATION": {
        "modules": ["aa_integrity.py", "aa_model_status.py"],
        "tests": ["tests/test_p1_integrity_foundation.py", "tests/test_phase1_foundation.py"],
    },
    "P2_PREDICTION_OUTCOME_LEDGER": {
        "modules": ["aa_prediction_outcomes.py"],
        "artifacts": ["prediction_ledger.parquet", "prediction_outcomes.parquet", "prediction_feedback_summary.json"],
        "tests": ["tests/test_p2_prediction_outcome_ledger.py"],
    },
    "P3_BACKGROUND_RESEARCH_EXISTING_MODELS": {
        "modules": ["aa_background_research.py"],
        "artifacts": ["background_research_status.json"],
        "tests": ["tests/test_p3_background_research.py"],
    },
    "P4_SHADOW_CHAMPION_FRAMEWORK": {
        "modules": ["aa_shadow_champion.py"],
        "artifacts": ["champion_registry.json", "challenger_registry.json", "shadow_signals.parquet", "shadow_outcomes.parquet", "promotion_status.json"],
        "tests": ["tests/test_p4_shadow_champion.py"],
    },
    "P5_REALTIME_REPLAY_FOUNDATION": {
        "modules": ["aa_market_data.py", "aa_realtime_replay.py", "aa_intraday_data_quality.py"],
        "artifacts": ["realtime_replay_status.json", "intraday_data_quality.json"],
        "tests": ["tests/test_p5_realtime_replay.py"],
    },
    "P6_BEHAVIORAL_FEATURE_RESEARCH": {
        "modules": ["aa_behavioral_features.py", "aa_behavioral_research.py"],
        "artifacts": ["behavioral_research_status.json", "behavioral_features.parquet"],
        "tests": ["tests/test_p6_behavioral_feature_research.py"],
    },
    "P7_AUTO_PROMOTION_EXE_VISIBILITY": {
        "modules": ["aa_auto_promotion.py"],
        "artifacts": ["promotion_gate_config.yaml", "auto_promotion_status.json"],
        "tests": ["tests/test_p7_auto_promotion.py"],
    },
    "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION": {
        "modules": ["aa_p9_shadow_paper_prep.py"],
        "artifacts": ["p9_shadow_paper_prep_status.json"],
        "tests": ["tests/test_p9_controlled_shadow_paper_validation.py"],
    },
}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def backup_paths_for_audit() -> List[Path]:
    return [
        Path("promotion_gate_config.yaml"),
        Path("DEVELOPMENT_PIPELINE.yaml"),
        Path("DEVELOPMENT_PIPELINE.json"),
        Path("IMPLEMENTATION_STATUS.md"),
        Path("NEXT_CURSOR_PROMPT.md"),
        Path("control/system_health.json"),
        Path("control/last_known_good_state.json"),
        Path("control/auto_promotion_status.json"),
        Path("control/promotion_status.json"),
        Path("control/pipeline_pending.json"),
        Path("model_output_sp500_pit_t212/auto_promotion_status.json"),
        Path("model_output_sp500_pit_t212/promotion_status.json"),
    ]


def create_audit_backup(root: Path, *, stamp: str = "") -> Path:
    root = Path(root)
    stamp = stamp or _utc_stamp()
    dest = root / AUDIT_BACKUP_ROOT / stamp
    dest.mkdir(parents=True, exist_ok=True)
    for rel in backup_paths_for_audit():
        src = root / rel
        if not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "stamp": stamp,
        "files": [str(p) for p in backup_paths_for_audit() if (root / p).is_file()],
    }
    atomic_write_json(dest / "manifest.json", manifest)
    return dest


def verify_phase_evidence(root: Path, out_dir: Path) -> Dict[str, str]:
    root = Path(root)
    out_dir = Path(out_dir)
    results: Dict[str, str] = {}
    for phase_id, spec in PHASE_EVIDENCE.items():
        ok = True
        for mod in spec.get("modules") or []:
            if not (root / mod).is_file():
                ok = False
        for test in spec.get("tests") or []:
            if not (root / test).is_file():
                ok = False
        for art in spec.get("artifacts") or []:
            if not (out_dir / art).is_file() and not (root / art).is_file() and not (root / "control" / art).is_file():
                ok = False
        results[phase_id] = "PASS" if ok else "NOT_CONFIRMED"
    return results


def load_promotion_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / "promotion_gate_config.yaml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["auto_execute_real_money_enabled"] = False
    return data


def promotion_modes_from_config(config: Dict[str, Any]) -> Dict[str, str]:
    return {
        "AUTO_RESEARCH": "ENABLED" if config.get("auto_research_enabled") else "DISABLED",
        "AUTO_PROMOTE_PAPER": "ENABLED" if config.get("auto_promote_paper_enabled") else "DISABLED",
        "AUTO_PROMOTE_SIGNAL": "ENABLED" if config.get("auto_promote_signal_enabled") else "DISABLED",
        "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
    }


def write_secure_promotion_config(root: Path, *, auto_research: bool) -> Dict[str, Any]:
    root = Path(root)
    path = root / "promotion_gate_config.yaml"
    config = load_promotion_config(root)
    if not config:
        raise FileNotFoundError("promotion_gate_config.yaml missing")
    config.update(
        {
            "auto_research_enabled": bool(auto_research),
            "auto_promote_paper_enabled": False,
            "auto_promote_signal_enabled": False,
            "auto_execute_real_money_enabled": False,
        }
    )
    atomic_write_yaml(path, config, sort_keys=False)
    return config


def check_status_consistency(root: Path, out_dir: Path) -> Tuple[bool, List[str]]:
    root = Path(root)
    out_dir = Path(out_dir)
    issues: List[str] = []
    lkg = _read_json(root / "control" / "last_known_good_state.json")
    pointer = _read_json(out_dir / "latest_validated_run.json")
    if lkg.get("validated_run_id") and pointer.get("run_id"):
        if str(lkg.get("validated_run_id")) != str(pointer.get("run_id")):
            issues.append("LKG run_id != latest_validated_run.run_id")
    ctrl_auto = _read_json(root / "control" / "auto_promotion_status.json")
    out_auto = _read_json(out_dir / "auto_promotion_status.json")
    if ctrl_auto and out_auto:
        if ctrl_auto.get("champion_variant_id") != out_auto.get("champion_variant_id"):
            issues.append("control vs out_dir champion_variant_id mismatch")
    health = _read_json(root / "control" / "system_health.json")
    if health.get("pipeline_version") in {0, "0", None} and _read_json(root / "DEVELOPMENT_PIPELINE.json").get("pipeline_version"):
        issues.append("system_health.json stale (pipeline_version=0)")
    return not issues, issues


def enqueue_p9_pending(root: Path) -> Tuple[bool, str]:
    from aa_pipeline_orchestration import empty_pending, save_pending

    root = Path(root)
    pending = empty_pending()
    pending.update(
        {
            "has_work": True,
            "pending_phase": "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION",
            "created_from_phase": "P7_AUTO_PROMOTION_EXE_VISIBILITY",
            "reason": "P8 acceptance audit PASS; controlled shadow/paper preparation permitted",
            "requires_preflight": True,
            "status": "PENDING",
            "followup_prompt": (
                "Active Alpha Autopilot — isolated run for `P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION`.\n\n"
                "Leave champion `R3_w075_q065_noexit` active. Run challenger shadow/paper validation only.\n"
                "Include M1_MOM_BLEND_MATCHED_CONTROLS. No promotion. No real-money orders."
            ),
            "details": {"audit_passed_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat()},
        }
    )
    save_pending(root, pending)
    return True, "P9 enqueued"


def update_pipeline_for_p9(root: Path) -> None:
    from aa_control_plane import load_pipeline
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    root = Path(root)
    pipeline = load_pipeline(root)
    phases = list(pipeline.get("phases") or [])
    p9_id = "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION"
    for phase in phases:
        pid = str(phase.get("id", ""))
        if pid == "P7_AUTO_PROMOTION_EXE_VISIBILITY":
            phase["next_phase"] = p9_id
        if pid == p9_id:
            phase.setdefault("status", "NOT_STARTED")
            phase.setdefault("next_phase", None)
            phase.setdefault(
                "goal",
                "Champion als Referenz belassen; Challenger nur Shadow/Paper prüfen; M1-Kontrolle; keine Promotion.",
            )
    if not any(str(p.get("id")) == p9_id for p in phases):
        phases.append(
            {
                "id": p9_id,
                "status": "NOT_STARTED",
                "next_phase": None,
                "goal": "Champion als Referenz belassen; Challenger nur Shadow/Paper prüfen; M1-Kontrolle; keine Promotion.",
            }
        )
    pipeline["phases"] = phases
    pipeline["current_phase"] = p9_id
    pipeline["acceptance_audit_p8"] = "PASS"
    atomic_write_json(root / "DEVELOPMENT_PIPELINE.json", pipeline)
    _sync_pipeline_yaml(root, pipeline)
