#!/usr/bin/env python3
"""G0R authorization and champion-lineage remediation resubmission orchestrator."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_authorization_policy import write_authorization_artifacts
from aa_decision_cockpit_readonly_snapshot import write_g0r_review_snapshot
from aa_doc_paths import doc_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, QUARANTINED_R5_CLAIM_REL
from aa_safe_io import atomic_write_json

ROOT = _REPO_ROOT
V5R_BASELINE_REL = "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json"
BACKUP_DIR = ROOT / "control" / "quarantine" / "g0r_remediation_backup"
QUARANTINE_DIR = ROOT / "control" / "quarantine" / "g0r_r5_unauthorized"
EXTERNAL_REVIEW_DIR = ROOT / "control" / "external_reviews" / "g0_g1_rejection"
G0R_PHASE_ID = "G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION"
G0R_ZIP = ROOT / "codex_g0r_authorization_champion_lineage_remediation_review.zip"
G0R_SHA = doc_path("codex_g0r_authorization_champion_lineage_remediation_review.zip.sha256")

EXTERNAL_DECISION_G0 = EXTERNAL_REVIEW_DIR / "EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md"
EXTERNAL_DECISION_G1 = EXTERNAL_REVIEW_DIR / "EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md"
EXTERNAL_SUMMARY = EXTERNAL_REVIEW_DIR / "EXTERNAL_REVIEW_SUMMARY_G0_G1.md"
EXTERNAL_HASHES = EXTERNAL_REVIEW_DIR / "EXTERNAL_REVIEW_OBSERVED_HASHES_G0_G1.sha256"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def ensure_external_review_inputs() -> None:
    EXTERNAL_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    if not EXTERNAL_DECISION_G0.is_file():
        _write_text(
            EXTERNAL_DECISION_G0,
            "\n".join(
                [
                    "# External Review Decision — G0 Remediation Required",
                    "",
                    "G0_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED",
                    "G0_EXTERNAL_SEALED = NO",
                    "OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY",
                    "",
                    "## Observed G0 ZIP SHA-256",
                    "09adac3cef01ef61faa716c39f751c39cab39ef5289ed5523d81af831b132130",
                    "",
                    "## Material rejection reasons",
                    "1. UNAUTHORIZED_CHAMPION_LINEAGE_STATE_PRESENT (R5_rank_only_train5)",
                    "2. G0_REVIEW_ZIP_HASH_REGISTRY_MISMATCH",
                    "3. PRE_G0_PROTECTED_BASELINE_DRIFT_NOT_RECONCILED",
                    "4. FAIL_CLOSED_COCKPIT_DISPLAY_NOT_ESTABLISHED",
                    "5. G0_PHASE_CATALOG_REGISTRY_MISMATCH",
                    "6. G0_WORKTREE_NOT_CLEANLY_ISOLATED_FOR_EXTERNAL_SEAL",
                    "7. CLAIMED_REMEDIATION_ARTEFACT_OMITTED (automation_state.json)",
                ]
            )
            + "\n",
        )
    if not EXTERNAL_DECISION_G1.is_file():
        _write_text(
            EXTERNAL_DECISION_G1,
            "\n".join(
                [
                    "# External Review Decision — G1 Not Approved",
                    "",
                    "G1_EXTERNAL_REVIEW_DECISION = NOT_APPROVED",
                    "G1_APPROVAL_ISSUED = NO",
                    "",
                    "## Observed G1 ZIP SHA-256",
                    "50a26cd8a6a1c36db8d9fc30a82aeb743b241fbb73d51fb0a03d09c5a4644aeb",
                    "",
                    "## Reasons",
                    "1. G1_PREDECESSOR_G0_NOT_EXTERNALLY_SEALED",
                    "2. G1_UNAUTHORIZED_CHAMPION_REFERENCE (R5_rank_only_train5)",
                    "3. G1_COMPARISON_FRAME_NOT_AUTHORIZED",
                    "4. G1_DETACHED_SIDECAR_NOT_SUBMITTED_FOR_VERIFICATION",
                ]
            )
            + "\n",
        )
    if not EXTERNAL_SUMMARY.is_file():
        _write_text(
            EXTERNAL_SUMMARY,
            "\n".join(
                [
                    "# External Review Summary — G0 / G1",
                    "",
                    "Authoritative champion at last external seal: R3_w075_q065_noexit",
                    "Terminal state: COMPLETE_AWAITING_OPERATIONAL_DECISION",
                    "Authorized scope: MANUAL_READ_ONLY_REVIEW_ONLY",
                    "",
                    "G0: REJECTED_REMEDIATION_REQUIRED — resubmit as G0R.",
                    "G1: NOT_APPROVED — blocked until corrected G0R external seal.",
                ]
            )
            + "\n",
        )
    if not EXTERNAL_HASHES.is_file():
        _write_text(
            EXTERNAL_HASHES,
            "\n".join(
                [
                    "09adac3cef01ef61faa716c39f751c39cab39ef5289ed5523d81af831b132130  codex_g0_authorization_conflict_remediation_review.zip",
                    "50a26cd8a6a1c36db8d9fc30a82aeb743b241fbb73d51fb0a03d09c5a4644aeb  codex_g1_readonly_challenger_cost_evidence_submission.zip",
                ]
            )
            + "\n",
        )


def load_v5r_baseline() -> Dict[str, str]:
    path = doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json")
    return json.loads(path.read_text(encoding="utf-8"))


def backup_file(rel: str, path: Path) -> Dict[str, str]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    safe = rel.replace("/", "__").replace("\\", "__")
    dest = BACKUP_DIR / safe
    if path.is_file():
        dest.write_bytes(path.read_bytes())
        return {"path": rel, "backup": str(dest.relative_to(ROOT)), "sha256": _sha256_file(path)}
    return {"path": rel, "backup": "", "sha256": ""}


def restore_from_git_by_hash(rel: str, expected_hash: str) -> bool:
    commits_raw = _run_git("log", "--all", "--format=%H", "--", rel)
    if not commits_raw:
        return False
    for commit in commits_raw.splitlines():
        proc = subprocess.run(
            ["git", "show", f"{commit}:{rel}"],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            continue
        if _sha256_bytes(proc.stdout) == expected_hash:
            dest = ROOT / rel.replace("/", "\\") if "\\" in str(ROOT) else ROOT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(proc.stdout)
            return True
    return False


def compare_v5r_baseline() -> List[Dict[str, Any]]:
    baseline = load_v5r_baseline()
    rows: List[Dict[str, Any]] = []
    for rel, expected in sorted(baseline.items()):
        path = ROOT / rel.replace("/", "\\") if (ROOT / rel).as_posix() != rel else ROOT / Path(rel)
        path = ROOT / Path(rel)
        if not path.is_file():
            rows.append(
                {
                    "path": rel,
                    "v5r_external_baseline_sha256": expected,
                    "current_repository_sha256": "",
                    "match": False,
                    "classification": "MISSING",
                    "remediation_action": "RESTORE_FROM_V5R_BASELINE",
                }
            )
            continue
        current = _sha256_file(path)
        if current == expected:
            rows.append(
                {
                    "path": rel,
                    "v5r_external_baseline_sha256": expected,
                    "current_repository_sha256": current,
                    "match": True,
                    "classification": "UNCHANGED",
                    "remediation_action": "NONE",
                }
            )
        else:
            rows.append(
                {
                    "path": rel,
                    "v5r_external_baseline_sha256": expected,
                    "current_repository_sha256": current,
                    "match": False,
                    "classification": "DRIFT_PRESENT",
                    "remediation_action": "RESTORE_V5R_GOVERNANCE_BASELINE",
                }
            )
    return rows


def restore_from_review_zip(rel: str, expected_hash: str) -> bool:
    import zipfile

    for zp in sorted(ROOT.glob("codex_*.zip")):
        try:
            with zipfile.ZipFile(zp) as zf:
                norm = rel.replace("\\", "/")
                if norm not in zf.namelist():
                    continue
                data = zf.read(norm)
                if _sha256_bytes(data) != expected_hash:
                    continue
                dest = ROOT / Path(rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                return True
        except Exception:
            continue
    return False


def remediate_protected_baseline(rows: List[Dict[str, Any]], backup_manifest: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], bool]:
    unresolved = False
    for row in rows:
        if row["match"]:
            continue
        rel = row["path"]
        path = ROOT / Path(rel)
        backup_manifest.append(backup_file(rel, path))
        restored = restore_from_git_by_hash(rel, row["v5r_external_baseline_sha256"])
        if not restored:
            restored = restore_from_review_zip(rel, row["v5r_external_baseline_sha256"])
        if not restored and path.is_file():
            row["remediation_action"] = "UNRESOLVED_PROTECTED_BASELINE_DRIFT"
            unresolved = True
            continue
        if restored:
            row["current_repository_sha256"] = _sha256_file(path)
            row["match"] = row["current_repository_sha256"] == row["v5r_external_baseline_sha256"]
            row["classification"] = "UNCHANGED" if row["match"] else "DRIFT_PRESENT"
            row["remediation_action"] = "RESTORED_FROM_BASELINE_ARCHIVE" if row["match"] else "UNRESOLVED_PROTECTED_BASELINE_DRIFT"
            if not row["match"]:
                unresolved = True
    return rows, unresolved


def quarantine_r5_claims(backup_manifest: List[Dict[str, str]]) -> List[str]:
    actions: List[str] = []
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    ops = ROOT / "control" / "operational_champion.json"
    if ops.is_file():
        data = json.loads(ops.read_text(encoding="utf-8"))
        data["quarantine_classification"] = "UNAUTHORIZED_OR_UNSEALED_STATE"
        data["quarantined_at_utc"] = _utc_now()
        data["note"] = "HISTORICAL_UNSEALED_CONFLICT_ARTIFACT — NOT AUTHORITATIVE"
        dest = QUARANTINE_DIR / "operational_champion_r5_claim.json"
        dest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        backup_manifest.append(backup_file("control/operational_champion.json", ops))
        ops.unlink()
        actions.append(f"Quarantined control/operational_champion.json -> {dest.relative_to(ROOT)}")
    lineage = ROOT / "control" / "champion_lineage_policy.json"
    if lineage.is_file():
        backup_manifest.append(backup_file("control/champion_lineage_policy.json", lineage))
    atomic_write_json(
        lineage,
        {
            "schema_version": 1,
            "status": "SEALED_BASELINE_R3_AUTHORITATIVE",
            "authoritative_champion": AUTHORITATIVE_CHAMPION,
            "authoritative_source": "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
            "historical_review_baseline": {
                "champion_at_external_seal": AUTHORITATIVE_CHAMPION,
                "document": "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
                "note": "Sealed review documents are immutable.",
            },
            "quarantined_unsealed_claims": [
                {
                    "variant_id": "R5_rank_only_train5",
                    "classification": "UNAUTHORIZED_OR_UNSEALED_STATE",
                    "pointer": QUARANTINED_R5_CLAIM_REL,
                }
            ],
            "legacy_labels": {"V2_COST_STRESS_CONSTANT": AUTHORITATIVE_CHAMPION},
            "generated_at_utc": _utc_now(),
        },
    )
    actions.append("Updated control/champion_lineage_policy.json to R3 authoritative baseline")
    return actions


def update_g1_blocked_status() -> None:
    for rel in (
        "control/evidence/g1_challenger_cost_preparation_status.json",
        "control/evidence/g1_source_inventory.json",
    ):
        path = ROOT / Path(rel)
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        data["g1_status"] = "NOT_AUTHORIZED"
        data["g1_execution_started"] = False
        data["g1_execution_authorized"] = False
        data["champion_reference"] = AUTHORITATIVE_CHAMPION
        data["champion"] = AUTHORITATIVE_CHAMPION
        data["champion_unchanged"] = AUTHORITATIVE_CHAMPION
        data["invalidated_reason"] = "G1_PREDECESSOR_G0_NOT_EXTERNALLY_SEALED"
        data["prior_unauthorized_champion_reference"] = "R5_rank_only_train5"
        atomic_write_json(path, data)


def update_phase_catalog() -> None:
    path = ROOT / "control" / "vision_automation" / "phase_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    phases = catalog.get("phases") or []
    if not any(p.get("phase_id") == G0R_PHASE_ID for p in phases):
        phases.append(
            {
                "phase_id": G0R_PHASE_ID,
                "phase_key": "G0R",
                "predecessor_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
                "purpose": (
                    "Correct rejected G0 governance submission and restore fail-closed "
                    "sealed Champion baseline representation."
                ),
                "allowed_actions": [
                    "read_only_repository_inspection",
                    "governance_status_remediation",
                    "authorization_conflict_remediation",
                    "champion_lineage_representation_remediation",
                    "targeted_nonoperative_unit_tests",
                    "review_package_build",
                ],
                "forbidden_actions": [
                    "g1_execution",
                    "turnover_generation",
                    "backtest_execution",
                    "matrix_rerun",
                    "cost_stress_execution",
                    "statistical_validation_execution",
                    "shadow_monitoring_activation",
                    "paper_monitoring_activation",
                    "promotion_execution",
                    "champion_change",
                    "real_money_execution",
                    "exe_build",
                    "exe_execution",
                ],
                "next_phase_after_external_seal": "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION",
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "operative_jobs_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
                "type": "REMEDIATION_ONLY",
            }
        )
        catalog["phases"] = phases
        atomic_write_json(path, catalog)


def update_review_registry() -> None:
    path = ROOT / "control" / "vision_automation" / "review_registry" / "review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    reviews = registry.get("reviews") or []
    for entry in reviews:
        if not isinstance(entry, dict):
            continue
        if entry.get("phase_id") == "G0_AUTHORIZATION_SOURCE_CONFLICT_REMEDIATION":
            entry["G0_EXTERNAL_REVIEW_DECISION"] = "REJECTED_REMEDIATION_REQUIRED"
            entry["external_sealed"] = False
            entry["execution_status"] = "REJECTED_REMEDIATION_REQUIRED"
        if entry.get("phase_id") == "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION":
            entry["G1_EXTERNAL_REVIEW_DECISION"] = "NOT_APPROVED"
            entry["external_sealed"] = False
            entry["g1_authorized"] = False
            entry["execution_status"] = "NOT_AUTHORIZED"
    if not any(r.get("phase_id") == G0R_PHASE_ID for r in reviews):
        reviews.append(
            {
                "phase_id": G0R_PHASE_ID,
                "phase_key": "G0R",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_G0R_TEMPLATE.md",
                "approval_sha256": "PENDING_EXTERNAL_SEAL",
                "review_zip": G0R_ZIP.name,
                "review_zip_sha256": "PENDING_EXTERNAL_SEAL",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "g1_authorized": False,
                "completed_at_utc": _utc_now(),
                "exe_built": False,
                "exe_executed": False,
                "operative_jobs_executed": False,
                "promotion_executed": False,
                "real_money_executed": False,
                "champion_changed": False,
                "blockers": [],
            }
        )
    registry["reviews"] = reviews
    atomic_write_json(path, registry)


def protected_hash_snapshot(paths: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for rel in paths:
        p = ROOT / Path(rel)
        if p.is_file():
            out[rel.replace("\\", "/")] = _sha256_file(p)
    return out


def run_tests() -> Tuple[int, str]:
    tests = [
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_decision_cockpit_viewmodel.py",
        "tests/test_decision_cockpit_gui.py",
        "tests/test_vision_phase_catalog.py",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    out_path = doc_path("CODEX_G0R_TEST_OUTPUT.txt")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(log, encoding="utf-8")
    return proc.returncode, log


def write_reports(
    *,
    start_head: str,
    end_head: str,
    branch: str,
    comparison: List[Dict[str, Any]],
    backup_manifest: List[Dict[str, str]],
    quarantine_actions: List[str],
    test_rc: int,
    blocked: bool,
    blocker: str,
) -> None:
    preflight = doc_path("CODEX_G0R_PREFLIGHT.md")
    report = doc_path("CODEX_G0R_EXTERNAL_REJECTION_REMEDIATION_REPORT.md")
    status = "BLOCKED" if blocked else "AWAITING_EXTERNAL_REVIEW"
    _write_text(
        preflight,
        "\n".join(
            [
                "# CODEX G0R Preflight",
                "",
                f"Generated: {_utc_now()}",
                f"Branch: {branch}",
                f"Start HEAD: {start_head}",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                f"V5R baseline: {V5R_BASELINE_REL}",
                "Scope: G0R authorization and champion-lineage remediation only.",
                "G1 execution: NOT AUTHORIZED.",
            ]
        )
        + "\n",
    )
    drift_count = sum(1 for r in comparison if not r.get("match"))
    _write_text(
        report,
        "\n".join(
            [
                "# CODEX G0R External Rejection Remediation Report",
                "",
                f"Generated: {_utc_now()}",
                f"G0R_LOCAL_REMEDIATION_STATUS: {'BLOCKED' if blocked else 'PASS'}",
                f"G0R_EXTERNAL_REVIEW_STATUS: {status}",
                "G0R_EXTERNAL_SEALED: NO",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "",
                "## External rejection inputs",
                f"- {EXTERNAL_DECISION_G0.relative_to(ROOT)}",
                f"- {EXTERNAL_DECISION_G1.relative_to(ROOT)}",
                "",
                "## Git checkpoint",
                f"- Branch: `{branch}`",
                f"- Start HEAD: `{start_head}`",
                f"- Remediation HEAD: `{end_head}`",
                "",
                "## Authoritative champion",
                f"- {AUTHORITATIVE_CHAMPION} (EXTERNAL_REVIEW_APPROVAL_FINAL.md)",
                "",
                "## R5 quarantine actions",
                *[f"- {a}" for a in quarantine_actions],
                "",
                "## Protected baseline comparison",
                f"- Overlapping paths: {len(comparison)}",
                f"- Drift before remediation: {drift_count}",
                "",
                "## Phase catalog / registry",
                "- G0R phase added to phase_catalog.json",
                "- G0R registry entry: AWAITING_EXTERNAL_REVIEW, review_zip_sha256=PENDING_EXTERNAL_SEAL",
                "- G1 remains NOT_AUTHORIZED",
                "",
                "## GUI / snapshot fail-closed",
                "- g0r_decision_cockpit_snapshot.json regenerated",
                "- promotion/paper/real_money eligible displays forced NO under blocked read-only",
                "",
                "## Tests",
                f"- pytest return code: {test_rc}",
                "",
                "## Operative jobs not executed",
                "- EXE, EXE-Build, Backtest, Matrix, Cost-Stress, Shadow, Paper, Promotion, Champion change, Real money",
                "",
                f"## Blocker",
                f"- {blocker or 'NONE'}",
            ]
        )
        + "\n",
    )
    git_status = _run_git("status", "--short", "--branch")
    git_log = _run_git("log", "--oneline", "--decorate", "-n", "15")
    _write_text(
        doc_path("CODEX_G0R_GIT_STATUS.txt"),
        "\n".join(
            [
                f"branch={branch}",
                f"start_head={start_head}",
                f"remediation_head={end_head}",
                "",
                git_status,
                "",
                git_log,
            ]
        )
        + "\n",
    )
    _write_text(
        ROOT / "EXTERNAL_REVIEW_APPROVAL_G0R_TEMPLATE.md",
        "\n".join(
            [
                "# External Review Approval — G0R (Template)",
                "",
                "Phase: G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION",
                "Status: AWAITING_EXTERNAL_REVIEW",
                "External sealed: NO",
                "",
                "Review ZIP: codex_g0r_authorization_champion_lineage_remediation_review.zip",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
            ]
        )
        + "\n",
    )


def build_g0r_zip(changed_sources: List[str]) -> str:
    import zipfile

    if G0R_ZIP.is_file():
        G0R_ZIP.unlink()
    include = [
        "CODEX_G0R_PREFLIGHT.md",
        "CODEX_G0R_EXTERNAL_REJECTION_REMEDIATION_REPORT.md",
        "CODEX_G0R_GIT_STATUS.txt",
        "CODEX_G0R_V5R_BASELINE_COMPARISON.json",
        "CODEX_G0R_PROTECTED_HASHES_BEFORE.json",
        "CODEX_G0R_PROTECTED_HASHES_AFTER.json",
        "CODEX_G0R_TEST_OUTPUT.txt",
        "G0R-BACKUP_MANIFEST.json",
        "control/authorization/authorization_source_policy.json",
        "control/authorization/current_authorization_status.json",
        "control/authorization/champion_lineage_status.json",
        "control/review_snapshot/g0r_decision_cockpit_snapshot.json",
        "control/vision_automation/automation_state.json",
        "control/vision_automation/phase_catalog.json",
        "control/vision_automation/review_registry/review_registry.json",
        "control/vision_automation/transition_log.jsonl",
        "control/system_health.json",
        "control/last_known_good_state.json",
        "control/promotion_status.json",
        "control/auto_promotion_status.json",
        "control/p9_shadow_paper_prep_status.json",
        "control/evidence/current_evidence_status.json",
        "control/evidence/cost_stress_status.json",
        "control/evidence/robustness_status.json",
        "control/evidence/multiple_testing_status.json",
        "control/evidence/forward_monitoring_readiness_status.json",
        "control/evidence/shadow_monitor_status.json",
        "control/evidence/paper_monitor_status.json",
        "promotion_gate_config.yaml",
        "VISION_PROGRESS.json",
        ".cursor/hooks.json",
        "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
        "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
        doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json").relative_to(ROOT).as_posix(),
        "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md",
        "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_SUMMARY_G0_G1.md",
        "control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_OBSERVED_HASHES_G0_G1.sha256",
        "NEXT_CURSOR_PROMPT.md",
        "EXTERNAL_REVIEW_APPROVAL_G0R_TEMPLATE.md",
        "aa_authorization_policy.py",
        "aa_evidence_schema.py",
        "aa_decision_cockpit_viewmodel.py",
        "aa_decision_cockpit_readonly_snapshot.py",
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/cockpit_governance_fixtures.py",
    ]
    include.extend(changed_sources)
    seen: set[str] = set()
    with zipfile.ZipFile(G0R_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            norm = rel.replace("\\", "/")
            if norm in seen:
                continue
            seen.add(norm)
            path = doc_path(Path(rel).name) if rel.startswith("CODEX_") else ROOT / Path(rel)
            if rel.startswith("CODEX_"):
                candidate = doc_path(rel)
                path = candidate if candidate.is_file() else ROOT / rel
            else:
                path = ROOT / Path(rel)
            if path.is_file():
                zf.write(path, norm)
    digest = _sha256_file(G0R_ZIP)
    G0R_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R_SHA.write_text(f"{digest}  {G0R_ZIP.name}\n", encoding="utf-8")
    return digest


def update_next_cursor_prompt(zip_sha: str, head: str) -> None:
    _write_text(
        ROOT / "NEXT_CURSOR_PROMPT.md",
        "\n".join(
            [
                "# Next Cursor Prompt",
                "",
                "## Current stand",
                "G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION locally complete — AWAITING_EXTERNAL_REVIEW.",
                "",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "Operational status: BLOCKED_FOR_SAFETY",
                "Authorized usage: MANUAL_READ_ONLY_REVIEW_ONLY",
                "",
                "## G1",
                "NOT AUTHORIZED. Do not start G1 until G0R external seal and separate G1 approval.",
                "",
                "## Next external step",
                "Review and seal: `codex_g0r_authorization_champion_lineage_remediation_review.zip`",
                f"Detached sidecar SHA-256: `{zip_sha}`",
                f"Remediation HEAD: `{head}`",
                "",
                "## Do not execute",
                "Backtest, Matrix-Re-Run, Turnover, Cost-Stress, DSR/PBO/CSCV, Robustness, Shadow, Paper, Promotion, Champion change, Real money, EXE build, EXE execution.",
            ]
        )
        + "\n",
    )


def main() -> int:
    ensure_external_review_inputs()
    start_head = _run_git("rev-parse", "HEAD") or "UNKNOWN"
    branch = _run_git("branch", "--show-current") or "UNKNOWN"

    comparison = compare_v5r_baseline()
    backup_manifest: List[Dict[str, str]] = []
    protected_paths = sorted({r["path"] for r in comparison})
    before_hashes = protected_hash_snapshot(protected_paths)
    atomic_write_json(doc_path("CODEX_G0R_PROTECTED_HASHES_BEFORE.json"), before_hashes)
    atomic_write_json(doc_path("CODEX_G0R_V5R_BASELINE_COMPARISON.json"), {"entries": comparison, "generated_at_utc": _utc_now()})

    quarantine_actions = quarantine_r5_claims(backup_manifest)
    comparison, unresolved = remediate_protected_baseline(comparison, backup_manifest)
    atomic_write_json(doc_path("CODEX_G0R_V5R_BASELINE_COMPARISON.json"), {"entries": comparison, "generated_at_utc": _utc_now()})

    after_hashes = protected_hash_snapshot(protected_paths)
    atomic_write_json(doc_path("CODEX_G0R_PROTECTED_HASHES_AFTER.json"), after_hashes)
    atomic_write_json(ROOT / "G0R-BACKUP_MANIFEST.json", {"backups": backup_manifest, "generated_at_utc": _utc_now()})

    update_g1_blocked_status()
    update_phase_catalog()
    update_review_registry()
    write_authorization_artifacts(ROOT)
    from aa_decision_cockpit_readonly_snapshot import write_review_snapshot

    write_review_snapshot(ROOT)
    write_g0r_review_snapshot(ROOT)
    write_authorization_artifacts(ROOT)

    test_rc, _ = run_tests()
    blocked = unresolved or test_rc != 0
    blocker = "UNRESOLVED_PROTECTED_BASELINE_DRIFT" if unresolved else ("TESTS_FAILED" if test_rc != 0 else "")

    end_head = _run_git("rev-parse", "HEAD") or start_head
    write_reports(
        start_head=start_head,
        end_head=end_head,
        branch=branch,
        comparison=comparison,
        backup_manifest=backup_manifest,
        quarantine_actions=quarantine_actions,
        test_rc=test_rc,
        blocked=blocked,
        blocker=blocker,
    )

    zip_sha = ""
    if not blocked:
        zip_sha = build_g0r_zip([])
        update_next_cursor_prompt(zip_sha, end_head)
        update_review_registry()

    print(
        json.dumps(
            {
                "g0r_status": "BLOCKED" if blocked else "PASS",
                "branch": branch,
                "start_head": start_head,
                "end_head": end_head,
                "authoritative_champion": AUTHORITATIVE_CHAMPION,
                "test_rc": test_rc,
                "review_zip_sha256": zip_sha or "PENDING_EXTERNAL_SEAL",
                "blocker": blocker or None,
            },
            indent=2,
        )
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
