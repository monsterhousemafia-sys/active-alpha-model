"""Read-only evidence manifest validation for Decision Cockpit (fail-closed)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

MANIFEST_NAME = "evidence_manifest.json"

REQUIRED_FIELDS = (
    "run_id",
    "variant",
    "created_at_utc",
    "runtime_mode",
    "output_dir",
    "source_commit",
    "config_snapshot_hash",
    "strategy_returns_hash",
    "benchmark_report_hash",
    "constraint_history_hash",
    "cost_report_hash",
    "gate_status_hash",
    "evidence_stage",
    "promotion_allowed",
    "shadow_allowed",
    "paper_allowed",
    "real_money_allowed",
)

HASH_ARTIFACTS = {
    "config_snapshot_hash": "run_config_snapshot.txt",
    "strategy_returns_hash": "strategy_daily_returns.csv",
    "benchmark_report_hash": "backtest_report.txt",
    "constraint_history_hash": "constraint_binding_history.csv",
    "cost_report_hash": "backtest_report.txt",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _gate_status_hash(root: Path) -> str:
    parts: List[str] = []
    for rel in (
        "control/evidence/cost_stress_status.json",
        "control/evidence/robustness_status.json",
        "control/evidence/multiple_testing_status.json",
        "control/auto_promotion_status.json",
    ):
        p = root / rel
        if p.is_file():
            parts.append(f"{rel}:{file_sha256(p)}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _resolve_source_commit(root: Path) -> str:
    git_log = root / ".git" / "logs" / "HEAD"
    if git_log.is_file():
        try:
            last = git_log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
            token = last.split()[1] if len(last.split()) > 1 else ""
            if len(token) >= 8:
                return token[:40]
        except Exception:
            pass
    return "UNKNOWN"


def compose_evidence_manifest(
    root: Path,
    out_dir: Path,
    *,
    variant: str = "",
    runtime_mode: str = "backtest",
    evidence_stage: str = "BACKTESTED",
    run_id: str = "",
) -> Dict[str, Any]:
    root = Path(root)
    out_dir = Path(out_dir)
    pointer = _read_json(out_dir / "latest_validated_run.json")
    run_dir_rel = str(pointer.get("run_dir") or out_dir)
    run_dir = Path(run_dir_rel) if Path(run_dir_rel).is_absolute() else root / run_dir_rel
    if not run_dir.is_dir():
        run_dir = out_dir

    resolved_run_id = str(run_id or pointer.get("run_id") or run_dir.name)
    resolved_variant = str(variant or pointer.get("variant_id") or "")

    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": resolved_run_id,
        "variant": resolved_variant,
        "created_at_utc": _utc_now(),
        "runtime_mode": runtime_mode,
        "output_dir": str(out_dir.relative_to(root)) if str(out_dir).startswith(str(root)) else str(out_dir),
        "source_commit": _resolve_source_commit(root),
        "evidence_stage": evidence_stage,
        "promotion_allowed": False,
        "shadow_allowed": False,
        "paper_allowed": False,
        "real_money_allowed": False,
        "gate_status_hash": _gate_status_hash(root),
    }
    for field, rel_name in HASH_ARTIFACTS.items():
        candidate = run_dir / rel_name
        if not candidate.is_file():
            candidate = out_dir / rel_name
        manifest[field] = file_sha256(candidate)
    return manifest


def validate_evidence_manifest(root: Path, manifest: Dict[str, Any]) -> Tuple[bool, List[str], Dict[str, str]]:
    root = Path(root)
    errors: List[str] = []
    checks: Dict[str, str] = {}

    if not manifest:
        return False, ["EVIDENCE_MANIFEST_MISSING"], checks

    for field in REQUIRED_FIELDS:
        if field not in manifest or manifest[field] in (None, ""):
            errors.append(f"MANIFEST_FIELD_MISSING:{field}")
            checks[field] = "MISSING"
        else:
            checks[field] = "PRESENT"

    out_rel = str(manifest.get("output_dir") or "")
    out_dir = root / out_rel if out_rel else root
    if out_rel and not out_dir.is_dir():
        errors.append("OUTPUT_DIR_MISSING")
        checks["output_dir_exists"] = "MISSING"
    else:
        checks["output_dir_exists"] = "OK"

    for field, rel_name in HASH_ARTIFACTS.items():
        expected = str(manifest.get(field) or "")
        if not expected:
            continue
        artifact = out_dir / rel_name
        if not artifact.is_file():
            run_pointer = _read_json(out_dir / "latest_validated_run.json")
            run_dir = Path(str(run_pointer.get("run_dir") or out_dir))
            if not run_dir.is_absolute():
                run_dir = root / run_dir
            artifact = run_dir / rel_name
        actual = file_sha256(artifact)
        if not actual:
            errors.append(f"ARTIFACT_MISSING:{rel_name}")
            checks[f"hash_{field}"] = "ARTIFACT_MISSING"
        elif actual != expected:
            errors.append(f"HASH_MISMATCH:{field}")
            checks[f"hash_{field}"] = "MISMATCH"
        else:
            checks[f"hash_{field}"] = "OK"

    for flag in ("promotion_allowed", "shadow_allowed", "paper_allowed", "real_money_allowed"):
        if manifest.get(flag) is True:
            errors.append(f"ACTIVATION_FLAG_TRUE:{flag}")
            checks[flag] = "UNSAFE"

    if manifest.get("evidence_stage") not in (None, "BACKTESTED", "UNKNOWN"):
        checks["evidence_stage"] = str(manifest.get("evidence_stage"))

    ok = len(errors) == 0
    checks["validation_status"] = "PASS" if ok else "FAIL"
    return ok, errors, checks


def load_evidence_manifest(root: Path, out_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], str]:
    root = Path(root)
    search_dirs: List[Path] = []
    if out_dir is not None:
        search_dirs.append(Path(out_dir))
    prod = root / "model_output_sp500_pit_t212"
    if prod.is_dir():
        search_dirs.append(prod)
    for directory in search_dirs:
        path = directory / MANIFEST_NAME
        if path.is_file():
            return _read_json(path), "OK"
    return {}, "MISSING"
