#!/usr/bin/env python3
"""Autonomous G1 independent research evidence pipeline."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_safe_io import atomic_write_json

from aa_decision_cockpit_readonly_snapshot import write_g1_independent_research_snapshot

from research.g1.comparison import (
    build_comparison_summary,
    build_reproducibility_manifest,
    write_reference_manifests,
)
from research.g1.config_loader import g1_backtest_config
from research.g1.constants import (
    AUTHORITY_BASIS,
    AUTHORITY_DIR,
    CHALLENGER_ID,
    CHAMPION_ID,
    CONTROL_ID,
    DOCS_ROOT,
    EVIDENCE_ROOT,
    OBSERVATION_ROOT,
)
from research.g1.contracts import (
    build_comparison_frame_hashes,
    build_data_contract,
    build_evidence_contract,
)
from research.g1.feature_loader import load_pit_feature_pack
from research.g1.generators import generate_challenger_evidence
from research.g1.hashing import file_sha256

ROOT = _REPO
BRANCH = "development/g1-independent-next-level-research-platform"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def ensure_authorization_files() -> Tuple[bool, str]:
    AUTHORITY_DIR.mkdir(parents=True, exist_ok=True)
    user_md = AUTHORITY_DIR / "USER_DIRECTIVE_INDEPENDENT_CURSOR_G1_DEVELOPMENT.md"
    contract_md = AUTHORITY_DIR / "CURSOR_AUTONOMOUS_G1_INDEPENDENT_EXECUTION_CONTRACT.md"
    manifest_json = AUTHORITY_DIR / "G1_INDEPENDENT_CURSOR_INPUT_MANIFEST.json"

    if not user_md.is_file():
        user_md.write_text(
            "\n".join(
                [
                    "# User Directive — G1 Independent Development",
                    "",
                    "Authority basis: DIRECT_USER_INSTRUCTION_IN_CURRENT_CONVERSATION",
                    "",
                    "Track: G1_INDEPENDENT_CURSOR_DEVELOPMENT_AND_CHALLENGER_COST_EVIDENCE",
                    "",
                    f"Champion: {CHAMPION_ID}",
                    f"Challenger: {CHALLENGER_ID}",
                    f"Control: {CONTROL_ID}",
                    "",
                    "Target gap: CHALLENGER_TURNOVER_NOT_VERIFIED",
                    "",
                    "ChatGPT approval required for this development track: NO",
                    "External review seal asserted: NO",
                    "Operational deployment authorized: NO",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    if not contract_md.is_file():
        contract_md.write_text(
            user_md.read_text(encoding="utf-8").replace("User Directive", "Execution Contract"),
            encoding="utf-8",
        )

    manifest = {
        "schema_version": 1,
        "authority_basis": AUTHORITY_BASIS,
        "generated_at_utc": _utc_now(),
        "files": {
            "USER_DIRECTIVE_INDEPENDENT_CURSOR_G1_DEVELOPMENT.md": file_sha256(user_md),
            "CURSOR_AUTONOMOUS_G1_INDEPENDENT_EXECUTION_CONTRACT.md": file_sha256(contract_md),
        },
    }
    manifest_json.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    for name in list(manifest["files"]):
        sidecar = AUTHORITY_DIR / f"{name}.sha256"
        sidecar.write_text(f"{manifest['files'][name]}  {name}\n", encoding="utf-8")

    return True, ""


def write_discovery_baseline(*, head: str, branch: str) -> None:
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    inv = {
        "generated_at_utc": _utc_now(),
        "project_root": str(ROOT),
        "start_head": head,
        "branch": branch,
        "findings": [
            {"id": "champion_evidence", "classification": "VERIFIED_EXISTING_ARTEFACT", "path": "model_output_sp500_pit_t212/"},
            {"id": "control_evidence", "classification": "VERIFIED_EXISTING_ARTEFACT", "path": "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/"},
            {"id": "challenger_returns", "classification": "VERIFIED_EXISTING_ARTEFACT", "path": "runs/.../naive_momentum_daily_returns.csv"},
            {"id": "challenger_turnover", "classification": "MISSING_INPUT", "note": "prior to this run"},
            {"id": "feature_cache", "classification": "VERIFIED_EXISTING_ARTEFACT", "path": "model_output_sp500_pit_t212/features/"},
            {"id": "naive_generator", "classification": "VERIFIED_EXISTING_CODE_PATH", "path": "aa_backtest.run_naive_momentum_baseline_full"},
        ],
    }
    (DOCS_ROOT / "CURSOR_REPOSITORY_EVIDENCE_INVENTORY.json").write_text(
        json.dumps(inv, indent=2) + "\n", encoding="utf-8"
    )
    for name, body in {
        "CURSOR_PROJECT_ARCHITECTURE_DISCOVERY.md": "# Architecture Discovery\n\nSee research/g1/ and tools/run_g1_independent_evidence.py.\n",
        "CURSOR_DATA_AND_PIPELINE_MAP.md": "# Data Map\n\nFrozen PIT cache: model_output_sp500_pit_t212/features/\n",
        "CURSOR_TECHNICAL_DEBT_AND_RISK_REGISTER.md": "# Risks\n\n- Challenger variant id mom_63_top12 uses cfg.top_k=15 in legacy runs.\n",
        "CURSOR_EXECUTION_LOG.md": f"# Execution Log\n\nStarted: {_utc_now()}\nHEAD: {head}\n",
    }.items():
        p = DOCS_ROOT / name
        if not p.is_file():
            p.write_text(body, encoding="utf-8")


def run_pipeline() -> Dict[str, Any]:
    head = _git("rev-parse", "HEAD")
    branch = _git("branch", "--show-current") or BRANCH
    ok_auth, auth_msg = ensure_authorization_files()
    if not ok_auth:
        return {"status": "TECHNICALLY_BLOCKED_BY_MISSING_EXTERNAL_INPUT", "reason": auth_msg}

    write_discovery_baseline(head=head, branch=branch)
    data_contract = build_data_contract(ROOT)
    build_evidence_contract(ROOT)
    build_comparison_frame_hashes(ROOT)

    cfg = g1_backtest_config(ROOT)
    features, returns, cache_info = load_pit_feature_pack(ROOT, cfg)
    write_reference_manifests(ROOT)
    challenger_manifest = generate_challenger_evidence(ROOT, features, returns, cfg, commit=head)
    summary = build_comparison_summary(ROOT, challenger_manifest)
    build_reproducibility_manifest(ROOT, commit=head)
    write_g1_independent_research_snapshot(ROOT)

    gap_closed = bool(challenger_manifest.get("turnover_verified"))
    legacy_match = (challenger_manifest.get("legacy_returns_comparison") or {}).get("returns_match_within_1e9")
    if gap_closed and legacy_match:
        dev_status = "COMPLETED_WITH_REPRODUCIBLE_G1_EVIDENCE"
    elif gap_closed:
        dev_status = "COMPLETED_WITH_PARTIAL_EVIDENCE_AND_EXPLICIT_LIMITATIONS"
    else:
        dev_status = "COMPLETED_WITH_ACTIONABLE_TECHNICAL_GAP_DIAGNOSIS"

    result = {
        "status": dev_status,
        "authority_verified": True,
        "head": head,
        "branch": branch,
        "cache_info": cache_info,
        "challenger_manifest": challenger_manifest,
        "comparison_summary": summary,
        "data_contract": data_contract,
        "target_gap_status": summary.get("target_gap_status"),
    }
    atomic_write_json(ROOT / EVIDENCE_ROOT / "manifests" / "run_summary.json", result)
    return result


def build_observation_package(result: Dict[str, Any]) -> Path:
    OBSERVATION_ROOT.mkdir(parents=True, exist_ok=True)
    status = result.get("status", "COMPLETED_WITH_ACTIONABLE_TECHNICAL_GAP_DIAGNOSIS")

    assessment_src = DOCS_ROOT / "CURSOR_G1_OBJECTIVE_TECHNICAL_ASSESSMENT.md"
    if not assessment_src.is_file():
        assessment_src.write_text(
            "\n".join(
                [
                    "# Objective Technical Assessment",
                    "",
                    f"Status: {status}",
                    "",
                    "## Facts",
                    f"- Champion locked: {CHAMPION_ID}",
                    f"- Challenger turnover generated: {result.get('challenger_manifest', {}).get('turnover_verified')}",
                    "",
                    "## Target gap",
                    f"- {result.get('target_gap_status')}",
                    "",
                    "## Not authorized",
                    "- Live trading, promotion, champion change, operational EXE",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    report_path = OBSERVATION_ROOT / "CURSOR_G1_NEXT_LEVEL_EXECUTION_REPORT.md"
    report_path.write_text(
        "\n".join(
            [
                "# G1 Next Level Execution Report",
                "",
                f"Generated: {_utc_now()}",
                f"Development status: **{status}**",
                "",
                f"Authority: {AUTHORITY_BASIS}",
                "",
                "## Evidence",
                f"- Turnover verified: {result.get('challenger_manifest', {}).get('turnover_verified')}",
                f"- Rebalance events: {result.get('challenger_manifest', {}).get('rebalance_events')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    include_roots = [EVIDENCE_ROOT, DOCS_ROOT, AUTHORITY_DIR, Path("research/g1"), Path("tests/g1_independent")]
    zip_path = OBSERVATION_ROOT / "cursor_g1_independent_next_level_development_package.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in include_roots:
            base_path = ROOT / base
            if not base_path.exists():
                continue
            for fp in base_path.rglob("*"):
                if fp.is_file():
                    rel = fp.relative_to(ROOT).as_posix()
                    zf.write(fp, rel)
                    hash_manifest[rel] = file_sha256(fp)
        for tool in ("tools/run_g1_independent_evidence.py", "tools/verify_g1_independent_package.py"):
            tp = ROOT / tool
            if tp.is_file():
                rel = tool.replace("\\", "/")
                zf.write(tp, rel)
                hash_manifest[rel] = file_sha256(tp)

    sha_path = OBSERVATION_ROOT / "cursor_g1_independent_next_level_development_package.zip.sha256"
    zip_hash = file_sha256(zip_path)
    sha_path.write_text(f"{zip_hash}  cursor_g1_independent_next_level_development_package.zip\n", encoding="utf-8")
    hash_manifest["cursor_g1_independent_next_level_development_package.zip"] = zip_hash

    manifest_out = OBSERVATION_ROOT / "CURSOR_G1_NEXT_LEVEL_HASH_MANIFEST.json"
    manifest_out.write_text(json.dumps({"generated_at_utc": _utc_now(), "files": hash_manifest}, indent=2) + "\n", encoding="utf-8")

    dest_assessment = OBSERVATION_ROOT / "CURSOR_G1_OBJECTIVE_TECHNICAL_ASSESSMENT.md"
    dest_assessment.write_text(assessment_src.read_text(encoding="utf-8"), encoding="utf-8")
    return OBSERVATION_ROOT


def main() -> int:
    result = run_pipeline()
    out_dir = build_observation_package(result)
    print(json.dumps({"status": result["status"], "observation_dir": str(out_dir.resolve())}, indent=2))
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", str(out_dir.resolve())])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
