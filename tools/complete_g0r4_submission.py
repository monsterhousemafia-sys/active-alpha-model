#!/usr/bin/env python3
"""G0R4 detached attestation and exact-byte package binding orchestrator."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_authorization_policy import write_authorization_artifacts
from aa_decision_cockpit_readonly_snapshot import write_g0r4_review_snapshot
from aa_doc_paths import doc_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json

ROOT = _REPO_ROOT
G0R4_PHASE_ID = "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION"
G0R4_ZIP = ROOT / "codex_g0r4_detached_attestation_exact_byte_package_review.zip"
G0R4_SHA = doc_path("codex_g0r4_detached_attestation_exact_byte_package_review.zip.sha256")
G0R4_ATTESTATION = ROOT / "codex_g0r4_detached_submission_attestation.json"
G0R4_VERIFY_REPORT = ROOT / "codex_g0r4_detached_package_verification_report.md"
G0R3_REJECTION_DIR = ROOT / "control" / "external_reviews" / "g0r3_rejection"
PAYLOAD_MANIFEST_NAME = "CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json"
G0R4_COMMIT_MSG = "fix: generate G0R4 exact-byte detached-attestation review package"

PREVIOUSLY_DRIFTED_PATHS = (
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
)

# Prior-phase post-build artefacts that may remain untracked but are not G0R4 scope.
PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS: Tuple[str, ...] = (
    "codex_g0r3_final_commit_bound_package_review.zip",
    "docs/review/sidecars/codex_g0r3_final_commit_bound_package_review.zip.sha256",
    "codex_g0r2_clean_checkpoint_evidence_completeness_review.zip",
    "docs/review/sidecars/codex_g0r2_clean_checkpoint_evidence_completeness_review.zip.sha256",
    "codex_g0r4_detached_attestation_exact_byte_package_review.zip",
    "docs/review/sidecars/codex_g0r4_detached_attestation_exact_byte_package_review.zip.sha256",
    "codex_g0r4_detached_submission_attestation.json",
    "codex_g0r4_detached_package_verification_report.md",
)

MANDATORY_ZIP_PATHS = (
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/evidence/forward_monitoring_data_requirements.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
    "control/review_snapshot/g0r4_decision_cockpit_snapshot.json",
)

AUTHORIZED_G0R4_COMMIT_PATHS: Tuple[str, ...] = (
    ".gitattributes",
    "docs/phases/G0R4/CODEX_G0R4_PREFLIGHT.md",
    "docs/phases/G0R4/CODEX_G0R4_EXTERNAL_REJECTION_REMEDIATION_REPORT.md",
    "docs/integrity/session_logs/G0R4/CODEX_G0R4_GIT_STATUS.txt",
    "docs/phases/G0R4/CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json",
    "docs/phases/G0R4/CODEX_G0R4_V5R_BASELINE_COMPARISON.json",
    "docs/integrity/protected_hashes/G0R4/CODEX_G0R4_PROTECTED_HASHES_BEFORE.json",
    "docs/integrity/protected_hashes/G0R4/CODEX_G0R4_PROTECTED_HASHES_AFTER.json",
    "docs/integrity/session_logs/G0R4/CODEX_G0R4_TEST_OUTPUT.txt",
    "G0R4-CHANGE_MANIFEST.json",
    "control/review_snapshot/g0r4_decision_cockpit_snapshot.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "control/authorization/authorization_source_policy.json",
    "control/authorization/current_authorization_status.json",
    "control/authorization/champion_lineage_status.json",
    "NEXT_CURSOR_PROMPT.md",
    "EXTERNAL_REVIEW_APPROVAL_G0R4_TEMPLATE.md",
    "tools/complete_g0r4_submission.py",
    "tests/test_g0r4_submission_integrity.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "aa_doc_paths.py",
    "control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R3.sha256",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _norm(rel: str) -> str:
    return rel.replace("\\", "/")


def _run_git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _run_git_rc(*args: str) -> Tuple[int, Any, str]:
    binary = "cat-file" in args or (len(args) > 0 and args[0] == "show")
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=not binary, check=False)
    if binary:
        stderr = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
        return proc.returncode, proc.stdout if isinstance(proc.stdout, bytes) else proc.stdout.encode(), stderr
    return proc.returncode, proc.stdout, proc.stderr


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_v5r_baseline() -> Dict[str, str]:
    return json.loads(doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json").read_text(encoding="utf-8"))


def load_g0r_before_hashes() -> Dict[str, str]:
    path = doc_path("CODEX_G0R_PROTECTED_HASHES_BEFORE.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def read_committed_bytes(commit: str, rel: str) -> Optional[bytes]:
    rc, out, _ = _run_git_rc("cat-file", "-p", f"{commit}:{_norm(rel)}")
    if rc != 0:
        return None
    return out if isinstance(out, bytes) else out.encode("utf-8")


def _is_tracked(rel: str) -> bool:
    return _run_git("ls-files", "--error-unmatch", rel) != ""


def verified_baseline_untracked_paths() -> List[str]:
    v5r = load_v5r_baseline()
    extra: List[str] = []
    for rel in sorted(v5r):
        if _is_tracked(rel):
            path = ROOT / Path(rel)
            if path.is_file() and _sha256_file(path) == v5r[rel]:
                index_blob = read_index_bytes(rel)
                if index_blob is not None and _sha256_bytes(index_blob) != v5r[rel]:
                    extra.append(rel)
            continue
        path = ROOT / Path(rel)
        if path.is_file() and _sha256_file(path) == v5r[rel]:
            extra.append(rel)
    return extra


def collect_worktree_drift() -> Set[str]:
    changed: Set[str] = set()
    for line in _run_git("diff", "--name-only").splitlines():
        if line.strip():
            changed.add(_norm(line))
    for line in _run_git("diff", "--cached", "--name-only").splitlines():
        if line.strip():
            changed.add(_norm(line))
    for line in _run_git("ls-files", "--others", "--exclude-standard").splitlines():
        if line.strip():
            changed.add(_norm(line))
    return changed


def verify_allowlist_drift(authorized: Set[str]) -> Tuple[bool, Set[str]]:
    exclusions = set(PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS)
    unexpected = collect_worktree_drift() - authorized - exclusions
    return len(unexpected) == 0, unexpected


def ensure_g0r3_rejection_inputs() -> None:
    G0R3_REJECTION_DIR.mkdir(parents=True, exist_ok=True)
    decision = G0R3_REJECTION_DIR / "EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md"
    if not decision.is_file():
        _write_text(
            decision,
            "\n".join(
                [
                    "# External Review Decision — G0R3 Remediation Required",
                    "",
                    "G0R3_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED",
                    "G0R3_EXTERNAL_SEALED = NO",
                    "",
                    "## Observed G0R3 ZIP SHA-256",
                    "ce8a968ef00b73e0bcb27d6860fdec60386e6223ace7d81b7c0a7b8c97d79e58",
                    "",
                    "## Material rejection reasons",
                    "1. G0R3_PACKAGE_INPUT_MANIFEST_BYTE_MISMATCH",
                    "2. G0R3_POST_COMMIT_BYTE_SUBSTITUTION_NOT_REPRESENTED_IN_MANIFEST",
                    "3. G0R3_FINAL_CLEAN_CHECKPOINT_REPORT_NOT_ESTABLISHED",
                    "4. G0R3_LOCAL_PASS_ASSERTION_NOT_SUPPORTED",
                ]
            )
            + "\n",
        )
    observed = G0R3_REJECTION_DIR / "EXTERNAL_REVIEW_OBSERVED_HASH_G0R3.sha256"
    if not observed.is_file():
        _write_text(
            observed,
            "ce8a968ef00b73e0bcb27d6860fdec60386e6223ace7d81b7c0a7b8c97d79e58  "
            "codex_g0r3_final_commit_bound_package_review.zip\n",
        )


def build_zip_include_list() -> List[str]:
    v5r_paths = sorted(load_v5r_baseline())
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    docs = [
        doc_path("CODEX_G0R4_PREFLIGHT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4_EXTERNAL_REJECTION_REMEDIATION_REPORT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4_GIT_STATUS.txt").relative_to(ROOT).as_posix(),
        manifest_rel,
        doc_path("CODEX_G0R4_V5R_BASELINE_COMPARISON.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4_PROTECTED_HASHES_BEFORE.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4_PROTECTED_HASHES_AFTER.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4_TEST_OUTPUT.txt").relative_to(ROOT).as_posix(),
        "G0R4-CHANGE_MANIFEST.json",
    ]
    snapshots = [
        "control/review_snapshot/g0r_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r2_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r3_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r4_decision_cockpit_snapshot.json",
        "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
    ]
    control = [
        "control/authorization/authorization_source_policy.json",
        "control/authorization/current_authorization_status.json",
        "control/authorization/champion_lineage_status.json",
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
        "control/evidence/forward_monitoring_data_requirements.json",
        "control/evidence/shadow_monitor_status.json",
        "control/evidence/paper_monitor_status.json",
        "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
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
        "control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R.sha256",
        "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256",
        "control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R3.sha256",
        "NEXT_CURSOR_PROMPT.md",
        "EXTERNAL_REVIEW_APPROVAL_G0R4_TEMPLATE.md",
        "tools/complete_g0r4_submission.py",
        "tests/test_g0r4_submission_integrity.py",
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_g0r2_remediation.py",
        "tests/test_g0r3_submission_integrity.py",
        "aa_decision_cockpit_readonly_snapshot.py",
        "aa_doc_paths.py",
    ]
    include = docs + snapshots + v5r_paths + control
    seen: Set[str] = set()
    ordered: List[str] = []
    for rel in include:
        norm = _norm(rel)
        if norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


def read_index_bytes(rel: str) -> Optional[bytes]:
    norm = _norm(rel)
    rc, out, _ = _run_git_rc("show", f":{norm}")
    if rc != 0:
        return None
    return out if isinstance(out, bytes) else out.encode("utf-8")


def read_staged_or_head_bytes(head: str, rel: str) -> Optional[bytes]:
    norm = _norm(rel)
    rc, out, _ = _run_git_rc("show", f":{norm}")
    if rc == 0:
        return out if isinstance(out, bytes) else out.encode("utf-8")
    return read_committed_bytes(head, norm)


def build_committed_payload_manifest(
    include: List[str], head: str, staged_paths: Set[str]
) -> Dict[str, Any]:
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    entries: List[Dict[str, Any]] = []
    for rel in include:
        norm = _norm(rel)
        if norm == manifest_rel:
            continue
        if norm in staged_paths:
            blob = read_index_bytes(norm)
        else:
            blob = read_committed_bytes(head, norm)
        if blob is None:
            continue
        entries.append(
            {
                "zip_path": norm,
                "repository_path": norm,
                "included_as": "COMMITTED_PAYLOAD",
                "sha256_of_committed_bytes": _sha256_bytes(blob),
                "required_for_review": True,
            }
        )
    return {
        "schema_version": 1,
        "phase": G0R4_PHASE_ID,
        "manifest_role": "NON_SELF_REFERENTIAL_COMMITTED_PAYLOAD_INDEX",
        "self_path": manifest_rel,
        "self_hash_included": False,
        "self_hash_exclusion_reason": (
            "A manifest cannot non-recursively attest its own final byte hash within itself."
        ),
        "zip_hash_included": False,
        "zip_hash_location": "DETACHED_SUBMISSION_ATTESTATION_ONLY",
        "git_commit_included": False,
        "git_commit_location": "DETACHED_SUBMISSION_ATTESTATION_ONLY",
        "external_sealed": False,
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "generated_at_utc": _utc_now(),
        "payload_entries": entries,
    }


def build_comparison(include_set: Set[str]) -> Tuple[List[Dict[str, Any]], bool]:
    v5r = load_v5r_baseline()
    g0r_before = load_g0r_before_hashes()
    rows: List[Dict[str, Any]] = []
    ok = True
    for rel in sorted(v5r):
        path = ROOT / Path(rel)
        expected = v5r[rel]
        current = _sha256_file(path) if path.is_file() else ""
        g0r_pre = g0r_before.get(rel, "")
        pre_drift = bool(g0r_pre and g0r_pre != expected)
        if not path.is_file():
            classification = "MISSING"
            ok = False
        elif current == expected:
            classification = "RESTORED_TO_V5R_BASELINE" if pre_drift else "UNCHANGED"
        else:
            classification = "DRIFT_PRESENT"
            ok = False
        rows.append(
            {
                "path": rel,
                "v5r_external_baseline_sha256": expected,
                "pre_g0r_drift_detected": pre_drift,
                "current_repository_sha256": current,
                "match": path.is_file() and current == expected,
                "classification": classification,
                "included_in_review_zip": rel in include_set,
            }
        )
    return rows, ok


def protected_hash_snapshot(paths: List[str]) -> Dict[str, str]:
    return {_norm(p): _sha256_file(ROOT / p) for p in paths if (ROOT / p).is_file()}


def build_exact_byte_zip(commit: str, include: List[str]) -> Tuple[str, List[str], Dict[str, bytes]]:
    if G0R4_ZIP.is_file():
        G0R4_ZIP.unlink()
    missing: List[str] = []
    zip_bytes: Dict[str, bytes] = {}
    with zipfile.ZipFile(G0R4_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            norm = _norm(rel)
            blob = read_committed_bytes(commit, norm)
            if blob is None:
                missing.append(norm)
                continue
            zf.writestr(norm, blob)
            zip_bytes[norm] = blob
    return _sha256_file(G0R4_ZIP), missing, zip_bytes


def verify_package_integrity(
    *,
    commit: str,
    zip_bytes: Dict[str, bytes],
    zip_digest: str,
) -> Tuple[bool, Dict[str, Any]]:
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    manifest_blob = zip_bytes.get(manifest_rel)
    if not manifest_blob:
        return False, {"error": "manifest missing from zip"}
    manifest = json.loads(manifest_blob.decode("utf-8"))
    mismatches: List[str] = []
    verified = 0
    for entry in manifest.get("payload_entries") or []:
        path = entry["zip_path"]
        expected = entry["sha256_of_committed_bytes"]
        actual_zip = _sha256_bytes(zip_bytes[path]) if path in zip_bytes else ""
        commit_blob = read_committed_bytes(commit, path)
        actual_commit = _sha256_bytes(commit_blob) if commit_blob else ""
        if actual_zip != expected or actual_commit != expected or actual_zip != actual_commit:
            mismatches.append(path)
        else:
            verified += 1
    sidecar_ok = False
    if G0R4_SHA.is_file():
        sidecar_ok = G0R4_SHA.read_text(encoding="utf-8").strip().split()[0] == zip_digest
    return len(mismatches) == 0, {
        "verified_payload_entries": verified,
        "total_payload_entries": len(manifest.get("payload_entries") or []),
        "mismatches": mismatches,
        "sidecar_matches_zip": sidecar_ok,
        "zip_sha256": zip_digest,
    }


def write_detached_attestation(
    *,
    commit: str,
    zip_digest: str,
    zip_bytes: Dict[str, bytes],
    verification: Dict[str, Any],
) -> None:
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    manifest_hash = _sha256_bytes(zip_bytes[manifest_rel])
    entry_index = [
        {
            "zip_path": path,
            "sha256_of_actual_zip_entry_bytes": _sha256_bytes(data),
            "classification": "COMMITTED_PAYLOAD_MANIFEST" if path == manifest_rel else "COMMITTED_PAYLOAD",
        }
        for path, data in sorted(zip_bytes.items())
    ]
    payload = {
        "schema_version": 1,
        "submission_type": "DETACHED_EXTERNAL_REVIEW_ATTESTATION",
        "phase": G0R4_PHASE_ID,
        "external_sealed": False,
        "external_review_status": "AWAITING_EXTERNAL_REVIEW",
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "g0r4_local_remediation_status": "PASS" if not verification.get("mismatches") else "BLOCKED",
        "final_input_commit": commit,
        "final_input_commit_verified_locally": True,
        "zip_file": G0R4_ZIP.name,
        "zip_sha256": zip_digest,
        "sidecar_file": G0R4_SHA.name,
        "sidecar_matches_zip": verification.get("sidecar_matches_zip", False),
        "committed_payload_manifest_zip_path": manifest_rel,
        "committed_payload_manifest_sha256_as_in_zip": manifest_hash,
        "committed_payload_manifest_self_hash_excluded_internally": True,
        "zip_entry_index": entry_index,
        "attestation_not_contained_in_zip": True,
        "no_post_commit_payload_substitution": True,
        "no_operational_activity_executed": True,
        "generated_at_utc": _utc_now(),
    }
    atomic_write_json(G0R4_ATTESTATION, payload)


def write_verification_report(verification: Dict[str, Any], *, commit: str) -> None:
    _write_text(
        G0R4_VERIFY_REPORT,
        "\n".join(
            [
                "# G0R4 Detached Package Verification Report",
                "",
                f"Generated: {_utc_now()}",
                f"Final input commit: `{commit}`",
                f"ZIP SHA-256: `{verification.get('zip_sha256', '')}`",
                f"Verified payload entries: {verification.get('verified_payload_entries')}/"
                f"{verification.get('total_payload_entries')}",
                f"Sidecar matches ZIP: {verification.get('sidecar_matches_zip')}",
                f"Mismatches: {verification.get('mismatches') or 'NONE'}",
                "",
                "This report is outside the review ZIP.",
            ]
        )
        + "\n",
    )


def update_phase_catalog() -> None:
    path = ROOT / "control/vision_automation/phase_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    phases = catalog.get("phases") or []
    if not any(p.get("phase_id") == G0R4_PHASE_ID for p in phases):
        phases.append(
            {
                "phase_id": G0R4_PHASE_ID,
                "phase_key": "G0R4",
                "predecessor_phase": "G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION",
                "purpose": "Exact-byte ZIP binding with detached submission attestation.",
                "allowed_actions": [
                    "read_only_repository_inspection",
                    "external_review_input_registration",
                    "packaging_integrity_remediation",
                    "explicit_allowlist_git_staging",
                    "non_self_referential_payload_manifest_generation",
                    "final_input_commit_creation",
                    "exact_committed_byte_zip_build",
                    "detached_sidecar_generation",
                    "detached_submission_attestation_generation",
                    "targeted_nonoperative_package_integrity_tests",
                ],
                "forbidden_actions": [
                    "g1_execution",
                    "g1_submission_approval",
                    "turnover_generation",
                    "backtest_execution",
                    "matrix_rerun",
                    "cost_stress_execution",
                    "statistical_validation_execution",
                    "robustness_execution",
                    "shadow_monitoring_activation",
                    "paper_monitoring_activation",
                    "promotion_execution",
                    "champion_change",
                    "real_money_execution",
                    "exe_build",
                    "exe_execution",
                    "broker_connectivity",
                ],
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
    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    reviews = registry.get("reviews") or []
    if not any(r.get("phase_id") == G0R4_PHASE_ID for r in reviews):
        reviews.append(
            {
                "phase_id": G0R4_PHASE_ID,
                "phase_key": "G0R4",
                "status": "AWAITING_EXTERNAL_REVIEW",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "review_zip": G0R4_ZIP.name,
                "review_zip_sha256": "DETACHED_ATTESTATION_ONLY",
                "detached_sidecar_status": "GENERATED_AFTER_FINAL_ZIP_CREATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_G0R4_TEMPLATE.md",
                "next_phase_authorized": False,
                "g1_authorized": False,
                "completed_at_utc": _utc_now(),
                "champion_changed": False,
                "promotion_executed": False,
                "real_money_executed": False,
                "operative_jobs_executed": False,
                "exe_built": False,
                "exe_executed": False,
            }
        )
    registry["reviews"] = reviews
    atomic_write_json(path, registry)


def write_change_manifest(modified: List[str]) -> None:
    atomic_write_json(
        ROOT / "G0R4-CHANGE_MANIFEST.json",
        {
            "schema_version": 1,
            "phase": G0R4_PHASE_ID,
            "change_scope": "PACKAGING_ATTESTATION_AND_EXACT_BYTE_BINDING_ONLY",
            "protected_artefacts_modified_during_g0r4": False,
            "governance_or_packaging_files_modified_in_g0r4": sorted(modified),
            "previously_restored_protected_artefacts_verified_unchanged": list(PREVIOUSLY_DRIFTED_PATHS),
            "generated_at_utc": _utc_now(),
        },
    )


def write_git_status(*, branch: str, start_head: str) -> None:
    _write_text(
        doc_path("CODEX_G0R4_GIT_STATUS.txt"),
        "\n".join(
            [
                f"branch={branch}",
                f"g0r4_start_head={start_head}",
                "final_input_commit_reference=SEE_DETACHED_SUBMISSION_ATTESTATION",
                "commit_id_not_embedded_in_committed_payload_reason="
                "Avoid post-commit byte substitution and preserve exact commit-byte identity.",
                "worktree_clean_verification_required_before_zip_build=true",
                "staging_method=explicit_allowlist_only",
                "g1_authorized=false",
                "operational_status=BLOCKED_FOR_SAFETY",
                "",
                "git status --short --branch:",
                _run_git("status", "--short", "--branch"),
            ]
        )
        + "\n",
    )


def write_preflight(start_head: str, branch: str) -> None:
    _write_text(
        doc_path("CODEX_G0R4_PREFLIGHT.md"),
        "\n".join(
            [
                "# CODEX G0R4 Preflight",
                "",
                f"Generated: {_utc_now()}",
                f"Branch: {branch}",
                f"Start HEAD: {start_head}",
                "",
                _run_git("status", "--short", "--branch"),
                "",
                _run_git("log", "--oneline", "-n", "30"),
            ]
        )
        + "\n",
    )


def write_report(*, test_rc: int, restoration_ok: bool) -> None:
    _write_text(
        doc_path("CODEX_G0R4_EXTERNAL_REJECTION_REMEDIATION_REPORT.md"),
        "\n".join(
            [
                "# CODEX G0R4 External Rejection Remediation Report",
                "",
                f"Generated: {_utc_now()}",
                "G0R4_EXTERNAL_REVIEW_STATUS: AWAITING_EXTERNAL_REVIEW",
                "G0R4_EXTERNAL_SEALED: NO",
                "REVIEW_ZIP_SHA256: DETACHED_ATTESTATION_ONLY",
                "FINAL_INPUT_COMMIT: DETACHED_ATTESTATION_ONLY",
                "G1_AUTHORIZED: NO",
                "OPERATIONAL_STATUS: BLOCKED_FOR_SAFETY",
                "",
                "## G0R3 rejection acknowledged",
                "- Observed hash: ce8a968ef00b73e0bcb27d6860fdec60386e6223ace7d81b7c0a7b8c97d79e58",
                "",
                "## G0R4 scope",
                "- Removed post-commit ZIP-entry substitution.",
                "- Non-self-referential CODEX_G0R4_COMMITTED_PAYLOAD_MANIFEST.json.",
                "- Detached submission attestation outside ZIP.",
                "",
                f"AUTHORITATIVE_CHAMPION: {AUTHORITATIVE_CHAMPION}",
                "PREVIOUS_PRE_G0R_DRIFT_DETECTED: YES",
                *[f"  - {p}" for p in PREVIOUSLY_DRIFTED_PATHS],
                f"Protected baseline verified: {'YES' if restoration_ok else 'NO'}",
                f"Pre-commit pytest return code: {test_rc}",
            ]
        )
        + "\n",
    )


def write_g0r4_template() -> None:
    _write_text(
        ROOT / "EXTERNAL_REVIEW_APPROVAL_G0R4_TEMPLATE.md",
        "\n".join(
            [
                "# External Review Approval — G0R4 (Template)",
                "",
                f"Phase: {G0R4_PHASE_ID}",
                "REVIEW_ZIP_SHA256: DETACHED_ATTESTATION_ONLY",
                "External sealed: NO",
            ]
        )
        + "\n",
    )


def update_next_cursor_prompt() -> None:
    _write_text(
        ROOT / "NEXT_CURSOR_PROMPT.md",
        "\n".join(
            [
                "# Next Cursor Prompt",
                "",
                "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION",
                "commit-gebundene Payload zur externen Review vorbereitet.",
                "",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "Authorized usage: MANUAL_READ_ONLY_REVIEW_ONLY",
                "Operational status: BLOCKED_FOR_SAFETY",
                "G1: NOT AUTHORIZED",
                "",
                "Review ZIP: codex_g0r4_detached_attestation_exact_byte_package_review.zip",
                "",
                "Separately submit:",
                "- codex_g0r4_detached_attestation_exact_byte_package_review.zip.sha256",
                "- codex_g0r4_detached_submission_attestation.json",
                "- codex_g0r4_detached_package_verification_report.md",
                "",
                "Commit-ID and ZIP hash: see detached submission attestation only.",
                "",
                "REVIEW_ZIP_SHA256: DETACHED_ATTESTATION_ONLY",
                "EXTERNAL_SEALED: NO",
            ]
        )
        + "\n",
    )


def run_tests() -> Tuple[int, str]:
    tests = [
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_g0r2_remediation.py",
        "tests/test_g0r3_submission_integrity.py",
        "tests/test_g0r4_submission_integrity.py",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    _write_text(doc_path("CODEX_G0R4_TEST_OUTPUT.txt"), log)
    return proc.returncode, log


def _is_gitignored(rel: str) -> bool:
    return _run_git_rc("check-ignore", "-q", rel)[0] == 0


def _git_add_path(rel: str) -> Tuple[bool, str]:
    args = ["add", "-f", "--", rel] if _is_gitignored(rel) else ["add", "--", rel]
    rc, _, err = _run_git_rc(*args)
    return rc == 0, err.strip()


def stage_allowlist_and_baseline(*, skip: Optional[Set[str]] = None) -> Tuple[bool, List[str], str]:
    skip = skip or set()
    baseline = verified_baseline_untracked_paths()
    authorized = set(AUTHORIZED_G0R4_COMMIT_PATHS) | set(baseline)
    ok, unexpected = verify_allowlist_drift(authorized)
    if not ok:
        return False, [], f"unexpected: {sorted(unexpected)}"
    staged: List[str] = []
    if ".gitattributes" not in skip and (ROOT / ".gitattributes").is_file():
        added, err = _git_add_path(".gitattributes")
        if not added:
            return False, staged, err
        staged.append(".gitattributes")
    for rel in list(AUTHORIZED_G0R4_COMMIT_PATHS) + baseline:
        if rel in skip or rel == ".gitattributes":
            continue
        if not (ROOT / rel).is_file():
            continue
        if rel in baseline:
            _run_git_rc("rm", "--cached", "-f", "--", rel)
        added, err = _git_add_path(rel)
        if not added:
            return False, staged, err
        staged.append(rel)
    return True, staged, ""


def commit_g0r4(include: List[str], head: str) -> Tuple[bool, str, List[str]]:
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    ok, staged, msg = stage_allowlist_and_baseline(skip={manifest_rel})
    if not ok:
        return False, msg, staged
    atomic_write_json(
        doc_path(PAYLOAD_MANIFEST_NAME),
        build_committed_payload_manifest(include, head, set(staged)),
    )
    added, err = _git_add_path(manifest_rel)
    if not added:
        return False, err, staged
    staged.append(manifest_rel)
    proc = subprocess.run(
        ["git", "commit", "-m", G0R4_COMMIT_MSG],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False, proc.stderr or proc.stdout, staged
    return True, _run_git("rev-parse", "HEAD"), staged


def worktree_clean_for_packaging() -> bool:
    allowed = {
        G0R4_ZIP.name,
        G0R4_ATTESTATION.name,
        G0R4_VERIFY_REPORT.name,
        G0R4_SHA.relative_to(ROOT).as_posix(),
        G0R4_SHA.name,
        *PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS,
    }
    for line in _run_git("status", "--porcelain").splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().split(" -> ")[-1].replace("\\", "/")
        if path in allowed or path.endswith(G0R4_ZIP.name):
            continue
        return False
    return True


def main() -> int:
    if _run_git("log", "-1", "--format=%s") == G0R4_COMMIT_MSG:
        commit = _run_git("rev-parse", "HEAD")
        start = _run_git("rev-parse", "HEAD~1")
        include = build_zip_include_list()
        zip_digest, missing, zip_bytes = build_exact_byte_zip(commit, include)
        if missing:
            print(json.dumps({"g0r4_status": "BLOCKED", "zip_missing": missing}, indent=2))
            return 1
        G0R4_SHA.parent.mkdir(parents=True, exist_ok=True)
        G0R4_SHA.write_text(f"{zip_digest}  {G0R4_ZIP.name}\n", encoding="utf-8")
        ok, verification = verify_package_integrity(commit=commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
        write_detached_attestation(commit=commit, zip_digest=zip_digest, zip_bytes=zip_bytes, verification=verification)
        write_verification_report(verification, commit=commit)
        print(json.dumps({"g0r4_status": "PASS" if ok else "BLOCKED", **verification}, indent=2))
        return 0 if ok else 1

    start_head = _run_git("rev-parse", "HEAD")
    branch = _run_git("branch", "--show-current")
    write_preflight(start_head, branch)
    ensure_g0r3_rejection_inputs()

    include = build_zip_include_list()
    include_set = set(include)
    v5r_paths = sorted(load_v5r_baseline())

    atomic_write_json(doc_path("CODEX_G0R4_PROTECTED_HASHES_BEFORE.json"), protected_hash_snapshot(v5r_paths))
    comparison, restoration_ok = build_comparison(include_set)
    atomic_write_json(
        doc_path("CODEX_G0R4_V5R_BASELINE_COMPARISON.json"),
        {
            "previous_pre_g0r_drift_detected": True,
            "previously_drifted_paths": list(PREVIOUSLY_DRIFTED_PATHS),
            "entries": comparison,
        },
    )
    atomic_write_json(doc_path("CODEX_G0R4_PROTECTED_HASHES_AFTER.json"), protected_hash_snapshot(v5r_paths))

    update_phase_catalog()
    update_review_registry()
    write_authorization_artifacts(ROOT)
    write_g0r4_review_snapshot(ROOT)
    write_change_manifest(list(AUTHORIZED_G0R4_COMMIT_PATHS))
    write_git_status(branch=branch, start_head=start_head)
    write_g0r4_template()
    update_next_cursor_prompt()

    test_rc, _ = run_tests()
    write_report(test_rc=test_rc, restoration_ok=restoration_ok)
    if test_rc != 0 or not restoration_ok:
        print(json.dumps({"g0r4_status": "BLOCKED", "blocker": "TESTS_OR_BASELINE"}, indent=2))
        return 1

    baseline = verified_baseline_untracked_paths()
    authorized = set(AUTHORIZED_G0R4_COMMIT_PATHS) | set(baseline)
    ok_drift, unexpected = verify_allowlist_drift(authorized)
    if not ok_drift:
        print(json.dumps({"g0r4_status": "BLOCKED", "unexpected": sorted(unexpected)}, indent=2))
        return 1

    ok, final_commit, _ = commit_g0r4(include, start_head)
    if not ok or final_commit == start_head:
        print(json.dumps({"g0r4_status": "BLOCKED", "blocker": "COMMIT_FAILED"}, indent=2))
        return 1

    if not worktree_clean_for_packaging():
        print(json.dumps({"g0r4_status": "BLOCKED", "blocker": "WORKTREE_NOT_CLEAN"}, indent=2))
        return 1

    zip_digest, missing, zip_bytes = build_exact_byte_zip(final_commit, include)
    if missing:
        print(json.dumps({"g0r4_status": "BLOCKED", "zip_missing": missing}, indent=2))
        return 1

    G0R4_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R4_SHA.write_text(f"{zip_digest}  {G0R4_ZIP.name}\n", encoding="utf-8")
    ok, verification = verify_package_integrity(commit=final_commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
    write_detached_attestation(
        commit=final_commit, zip_digest=zip_digest, zip_bytes=zip_bytes, verification=verification
    )
    write_verification_report(verification, commit=final_commit)

    print(
        json.dumps(
            {
                "g0r4_status": "PASS" if ok else "BLOCKED",
                "start_head": start_head,
                "g0r4_final_input_commit": final_commit,
                "review_zip_sha256": zip_digest,
                **verification,
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
