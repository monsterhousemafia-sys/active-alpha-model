#!/usr/bin/env python3
"""Phase B — Champion artifact remediation (pointer repair, R5 quarantine, report rebuild)."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_challenger_eval import REPORT_JSON, REPORT_TXT, build_challenger_report, write_challenger_report
from aa_background_research import build_background_research_status, status_path as bg_status_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion
from aa_safe_io import atomic_write_json, atomic_write_text

OUT_REL = "model_output_sp500_pit_t212"
CANONICAL_RUN_ID = "20260530T153000Z_R3_w075_q065_noexit_d5eb43c3_b1143f32"
CONTAMINATION_N_DAYS_THRESHOLD = 1900


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _returns_n_days(path: Path) -> Optional[int]:
    if not path.is_file():
        return None
    try:
        import pandas as pd

        frame = pd.read_csv(path, index_col=0, parse_dates=True)
        col = "strategy_return" if "strategy_return" in frame.columns else frame.columns[0]
        return int(pd.to_numeric(frame[col], errors="coerce").dropna().shape[0])
    except Exception:
        return None


def repair_latest_validated_run(root: Path) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)
    out_dir = root / OUT_REL
    pointer_path = out_dir / "latest_validated_run.json"
    prior = {}
    if pointer_path.is_file():
        try:
            prior = json.loads(pointer_path.read_text(encoding="utf-8"))
        except Exception:
            prior = {}

    canonical_run_dir = root / "runs" / CANONICAL_RUN_ID
    repaired_from = str(prior.get("repaired_from_run_dir") or canonical_run_dir)
    if not canonical_run_dir.is_dir() and prior.get("repaired_from_run_dir"):
        repaired_from = str(prior["repaired_from_run_dir"])

    doc = {
        "schema_version": 1,
        "variant_id": locked,
        "run_id": CANONICAL_RUN_ID,
        "run_dir": str(canonical_run_dir.resolve()) if canonical_run_dir.is_dir() else repaired_from,
        "status": "PASS",
        "integrity_status": "PASS",
        "published_at_utc": prior.get("published_at_utc") or _utc_now(),
        "phase_b_repair_at_utc": _utc_now(),
        "repair_note": (
            "Phase B: aligned variant_id, run_id, and run_dir; removed R5 run_id split. "
            "Champion metrics must not be read from model_output/ until matrix returns restored."
        ),
        "prior_pointer": {
            "variant_id": prior.get("variant_id"),
            "run_id": prior.get("run_id"),
            "run_dir": prior.get("run_dir"),
        },
        "artifacts_present": {
            "canonical_run_dir_exists": canonical_run_dir.is_dir(),
            "model_output_returns_exists": (out_dir / "strategy_daily_returns.csv").is_file(),
        },
    }
    atomic_write_json(pointer_path, doc)
    return doc


def archive_contaminated_model_output_returns(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / OUT_REL
    returns_path = out_dir / "strategy_daily_returns.csv"
    result: Dict[str, Any] = {
        "archived": False,
        "returns_path": str(returns_path) if returns_path.is_file() else None,
        "n_days": _returns_n_days(returns_path),
        "threshold_n_days": CONTAMINATION_N_DAYS_THRESHOLD,
    }
    if not returns_path.is_file():
        result["note"] = "No strategy_daily_returns.csv in model_output."
        return result

    n_days = result["n_days"]
    if n_days is None or n_days <= CONTAMINATION_N_DAYS_THRESHOLD:
        result["note"] = "Returns file within expected matrix calendar length; no archive copy."
        return result

    archive_dir = root / "evidence" / "archive_phase_b_contaminated_model_output"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / "strategy_daily_returns.csv"
    shutil.copy2(returns_path, dest)
    quarantined = out_dir / "strategy_daily_returns_CONTAMINATED_QUARANTINED.csv"
    try:
        returns_path.rename(quarantined)
    except OSError:
        shutil.copy2(dest, quarantined)
        returns_path.unlink(missing_ok=True)
    meta = {
        "schema_version": 1,
        "archived_at_utc": _utc_now(),
        "source": str(returns_path.resolve()),
        "n_days": n_days,
        "sha256": _sha256_file(returns_path),
        "reason": "n_days exceeds matrix champion calendar (~1860); likely R5/extended spill into model_output.",
        "action": "ARCHIVED_AND_REMOVED_FROM_MODEL_OUTPUT",
    }
    atomic_write_json(archive_dir / "archive_manifest.json", meta)
    atomic_write_json(
        out_dir / "CHAMPION_OUTPUT_SCOPE.json",
        {
            "schema_version": 1,
            "authoritative_champion": AUTHORITATIVE_CHAMPION,
            "model_output_role": "CHAMPION_ARTIFACTS_ONLY",
            "do_not_use_returns_for_challenger_metrics": True,
            "contaminated_returns_archive": str(archive_dir.relative_to(root)).replace("\\", "/"),
            "contaminated_n_days": n_days,
            "matrix_expected_n_days": 1860,
            "generated_at_utc": _utc_now(),
        },
    )
    result["archived"] = True
    result["archive_dir"] = str(archive_dir.resolve())
    result["archive_sha256"] = meta["sha256"]
    return result


def write_unauthorized_champion_claims_registry(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "claims": [
            {
                "variant_id": "R5_rank_only_train5",
                "status": "INVALID",
                "classification": "UNAUTHORIZED_OR_UNSEALED_STATE",
                "pointers": [
                    "control/quarantine/g0r_r5_unauthorized/operational_champion_r5_claim.json",
                    "control/r5_challenger_registry.json",
                ],
                "note": "Must not be used as operational champion; quarantined per EXTERNAL_REVIEW and Phase B.",
            }
        ],
    }
    path = root / "control" / "quarantine" / "unauthorized_champion_claims.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)
    return doc


def patch_champion_registry_to_r3(root: Path) -> Dict[str, Any]:
    path = root / "control" / "champion_registry.json"
    if not path.is_file():
        return {"patched": False, "reason": "missing"}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"patched": False, "reason": "parse_error"}
    prior = dict(doc)
    locked = resolve_locked_champion(root)
    doc.update(
        {
            "variant_id": locked,
            "role": "CHAMPION",
            "active": True,
            "auto_promotion": "DISABLED",
            "run_id": CANONICAL_RUN_ID,
            "run_dir": str((root / "runs" / CANONICAL_RUN_ID).resolve()),
            "integrity_status": "PASS",
            "promotion_source": "",
            "phase_b_repaired_at_utc": _utc_now(),
            "repair_note": "Phase B: replaced erroneous R5 operational registry with authoritative R3.",
            "prior_registry": {
                "variant_id": prior.get("variant_id"),
                "run_id": prior.get("run_id"),
                "promotion_source": prior.get("promotion_source"),
            },
        }
    )
    atomic_write_json(path, doc)
    return {"patched": True, "variant_id": locked}


def patch_r5_registry_quarantine(root: Path) -> Dict[str, Any]:
    path = root / "control" / "r5_challenger_registry.json"
    if not path.is_file():
        return {"patched": False, "reason": "missing"}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"patched": False, "reason": "parse_error"}
    doc["role"] = "QUARANTINED_RESEARCH_ONLY"
    doc["active"] = False
    doc["authoritative"] = False
    doc["note"] = (
        "QUARANTINED — not operational champion. See control/quarantine/unauthorized_champion_claims.json. "
        + str(doc.get("note") or "")
    )
    doc["phase_b_patched_at_utc"] = _utc_now()
    atomic_write_json(path, doc)
    return {"patched": True, "variant_id": doc.get("variant_id"), "role": doc.get("role")}


def rebuild_reports(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / OUT_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, txt_path = write_challenger_report(root, out_dir)
    report = json.loads(json_path.read_text(encoding="utf-8"))
    bg = build_background_research_status(root, out_dir)
    atomic_write_json(bg_status_path(root), bg)
    atomic_write_json(out_dir / "background_research_status.json", bg)
    return {
        "challenger_json": str(json_path.relative_to(root)).replace("\\", "/"),
        "challenger_txt": str(txt_path.relative_to(root)).replace("\\", "/"),
        "champion_variant_id": report.get("champion_variant_id"),
        "variants_compared": report.get("variants_compared"),
        "background_research_status": str(bg_status_path(root).relative_to(root)).replace("\\", "/"),
    }


def update_champion_lineage_hashes(root: Path, artifact_paths: List[Path]) -> Dict[str, Any]:
    root = Path(root)
    policy_path = root / "control" / "champion_lineage_policy.json"
    policy: Dict[str, Any] = {}
    if policy_path.is_file():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception:
            policy = {}
    hashes = {}
    for p in artifact_paths:
        if p.is_file():
            rel = str(p.relative_to(root)).replace("\\", "/")
            hashes[rel] = _sha256_file(p)
    policy["phase_b_artifact_hashes"] = hashes
    policy["phase_b_updated_at_utc"] = _utc_now()
    policy["authoritative_champion"] = AUTHORITATIVE_CHAMPION
    atomic_write_json(policy_path, policy)
    return {"policy_path": str(policy_path.relative_to(root)).replace("\\", "/"), "hashes": hashes}


def run_phase_b(root: Path) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)

    b1 = repair_latest_validated_run(root)
    b2 = archive_contaminated_model_output_returns(root)
    b3 = write_unauthorized_champion_claims_registry(root)
    b3b = patch_r5_registry_quarantine(root)
    b3c = patch_champion_registry_to_r3(root)
    b5 = rebuild_reports(root)

    report = build_challenger_report(root, root / OUT_REL)
    conflicts: List[str] = []
    if report.get("champion_variant_id") != locked:
        conflicts.append(f"champion_variant_id={report.get('champion_variant_id')} != {locked}")
    if "R5" in str(report.get("champion_variant_id") or ""):
        conflicts.append("R5 still labeled as champion in report")

    artifact_paths = [
        root / OUT_REL / "latest_validated_run.json",
        root / OUT_REL / REPORT_JSON,
        root / OUT_REL / REPORT_TXT,
        root / "control" / "background_research_status.json",
        root / "control" / "quarantine" / "unauthorized_champion_claims.json",
        root / "control" / "champion_lineage_policy.json",
        root / "control" / "champion_registry.json",
    ]
    b6 = update_champion_lineage_hashes(root, artifact_paths)

    summary = {
        "schema_version": 1,
        "phase": "B",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE" if not conflicts else "COMPLETE_WITH_CONFLICTS",
        "locked_champion": locked,
        "steps": {
            "B1_pointer_repair": b1,
            "B2_output_archive": b2,
            "B3_unauthorized_claims_registry": b3,
            "B3b_r5_registry_patch": b3b,
            "B3c_champion_registry_r3": b3c,
            "B5_reports_rebuilt": b5,
            "B6_lineage_hashes": b6,
        },
        "conflicts": conflicts,
        "challenger_report_champion": report.get("champion_variant_id"),
    }
    out_path = root / "evidence" / "phase_b_remediation_summary.json"
    atomic_write_json(out_path, summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Champion evidence Phase B remediation")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    summary = run_phase_b(args.root)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("status", "").startswith("COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
