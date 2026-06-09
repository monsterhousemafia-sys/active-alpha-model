"""V1 experiment registry — atomic manifests under control/experiments/."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aa_evidence_schema import LOCKED_CHAMPION
from aa_safe_io import atomic_write_yaml

REGISTRY_DIR = Path("control") / "experiments"
SCHEMA_VERSION = 1
INITIAL_EXPERIMENT_ID = "EXP_INITIAL_MOM_63_TOP12"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def experiments_dir(root: Path) -> Path:
    return Path(root) / REGISTRY_DIR


def manifest_path(root: Path, experiment_id: str) -> Path:
    safe = experiment_id.replace("/", "_")
    return experiments_dir(root) / f"{safe}.yaml"


def list_experiment_ids(root: Path) -> List[str]:
    root = Path(root)
    out: List[str] = []
    d = experiments_dir(root)
    if not d.is_dir():
        return out
    for path in sorted(d.glob("*.yaml")):
        out.append(path.stem)
    return out


def load_manifest(root: Path, experiment_id: str) -> Dict[str, Any]:
    path = manifest_path(root, experiment_id)
    if not path.is_file():
        return {}
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_manifest(root: Path, manifest: Dict[str, Any], *, allow_overwrite: bool = False) -> Path:
    root = Path(root)
    exp_id = str(manifest.get("experiment_id", "") or "")
    if not exp_id:
        raise ValueError("experiment_id required")
    path = manifest_path(root, exp_id)
    if path.is_file() and not allow_overwrite:
        existing = load_manifest(root, exp_id)
        if existing.get("experiment_id") == exp_id:
            raise ValueError(f"duplicate experiment_id: {exp_id}")
    data = dict(manifest)
    data["schema_version"] = int(data.get("schema_version", SCHEMA_VERSION) or SCHEMA_VERSION)
    data["updated_at_utc"] = _utc_now()
    atomic_write_yaml(path, data, sort_keys=False)
    return path


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest_provenance(root: Path, manifest: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Read-only provenance verification; no filesystem mutations."""
    root = Path(root)
    if not manifest:
        return False, ["EVIDENCE_PROVENANCE_MISSING"]

    provenance = manifest.get("provenance") or {}
    source_files = provenance.get("source_files") or []
    source_hashes = provenance.get("source_hashes") or {}
    if not source_files:
        return False, ["EVIDENCE_PROVENANCE_MISSING"]

    blockers: List[str] = []
    for rel in source_files:
        rel_str = str(rel)
        path = root / rel_str
        if not path.is_file():
            if "EVIDENCE_PROVENANCE_MISSING" not in blockers:
                blockers.append("EVIDENCE_PROVENANCE_MISSING")
            continue
        expected = source_hashes.get(rel_str)
        actual = file_sha256(path)
        if not expected or actual != expected:
            if "EVIDENCE_PROVENANCE_HASH_MISMATCH" not in blockers:
                blockers.append("EVIDENCE_PROVENANCE_HASH_MISMATCH")

    return len(blockers) == 0, blockers


def build_initial_mom_manifest(root: Path) -> Dict[str, Any]:
    root = Path(root)
    provenance_files: List[str] = []
    source_hashes: Dict[str, str] = {}
    for rel in (
        "control/auto_promotion_status.json",
        "model_output_sp500_pit_t212/background_research_status.json",
    ):
        p = root / rel
        if p.is_file():
            provenance_files.append(rel)
            source_hashes[rel] = file_sha256(p)

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": INITIAL_EXPERIMENT_ID,
        "created_at_utc": _utc_now(),
        "hypothesis": "Existing momentum challenger carried forward for evidence normalization only.",
        "candidate_variant": "MOM_63_TOP12",
        "champion_reference": LOCKED_CHAMPION,
        "control_reference": "M1_MOM_BLEND_MATCHED_CONTROLS",
        "data_cutoff_utc": None,
        "feature_set_version": "UNKNOWN",
        "cost_model_version": "NOT_VALIDATED",
        "evaluation_protocol_version": "EVIDENCE_V1",
        "source_classification": "PREEXISTING_UNREVIEWED",
        "current_evidence_stage": "BACKTESTED",
        "promotion_eligible": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "decision_status": "RESEARCH_ONLY",
        "blockers": ["COST_STRESS_NOT_EVALUATED", "P9_NOT_EXTERNALLY_REVIEWED"],
        "provenance": {"source_files": provenance_files, "source_hashes": source_hashes},
        "notes": [
            "Historical or pre-existing preparation evidence must not be interpreted as externally reviewed forward readiness."
        ],
    }


def ensure_initial_experiment(root: Path) -> Path:
    """Explicit setup/migration path only — not for read-only aggregation."""
    root = Path(root)
    path = manifest_path(root, INITIAL_EXPERIMENT_ID)
    if path.is_file():
        return path
    return save_manifest(root, build_initial_mom_manifest(root))
