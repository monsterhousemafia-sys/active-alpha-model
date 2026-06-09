#!/usr/bin/env python3
"""G0R4R3 final git-blob and ZIP-entry verbatim remediation orchestrator."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
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
from aa_decision_cockpit_readonly_snapshot import write_g0r4r3_review_snapshot
from aa_doc_paths import doc_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json

_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from review_submission_delivery import deliver_g0r4r3_outgoing_submission, submission_folder_rel

ROOT = _REPO_ROOT
G0R4R3_PHASE_ID = "G0R4R3_FINAL_BLOB_ZIP_VERBATIM_AND_AUDIT_INPUT_COMPLETENESS_REMEDIATION"
G0R4R3_ZIP = ROOT / "codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip"
G0R4R3_SHA = doc_path("codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip.sha256")
G0R4R3_ATTESTATION = ROOT / "codex_g0r4r3_detached_submission_attestation.json"
G0R4R3_VERIFY_REPORT = ROOT / "codex_g0r4r3_detached_package_verification_report.md"
INPUT_DIR_REL = "incoming_external_reviews/g0r4r3"
INPUT_DIR = ROOT / INPUT_DIR_REL
BASELINE_ORIGINALS_DIR = INPUT_DIR / "baseline_originals"
EXTRACT_DIR = INPUT_DIR / "extracted"
GIT_BYTE_PRESERVE_PATHS: Tuple[str, ...] = (
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
)
MANDATORY_AUDIT_ZIP_PATHS: Tuple[str, ...] = GIT_BYTE_PRESERVE_PATHS[3:]
EXPECTED_VERBATIM_INPUTS_NAME = "CODEX_G0R4R3_EXPECTED_VERBATIM_INPUTS.json"

OUTGOING_DIR_REL = "outgoing_external_reviews/g0r4r3"
G0R4R3_BLOCKED_DIR_REL = "outgoing_external_reviews/g0r4r3_BLOCKED"
EXPECTED_DROP_IN_SHA256 = "02b1d97f845d5d666ef852bf3c4cd725bfe54efb05f73cc47663e772c3b879c7"
DROP_IN_ZIP_NAME = "G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT.zip"
DROP_IN_EXPECTED_MEMBERS = frozenset(
    {
        "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip",
        "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256",
    }
)
ALLOWED_BRANCHES = (
    "remediation/g0r4r3-final-blob-zip-verbatim",
    "remediation/g0r4r3-final-blob-zip-verbatim",
)
WORKSPACE_SEARCH_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "build",
    "dist",
    "evidence",
}
APPROVAL_DOC_NAME = "EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md"
APPROVAL_SIDECAR_NAME = f"{APPROVAL_DOC_NAME}.sha256"
APPROVAL_DOC_INPUT = EXTRACT_DIR / APPROVAL_DOC_NAME
APPROVAL_SIDECAR_INPUT = EXTRACT_DIR / APPROVAL_SIDECAR_NAME
EXPECTED_APPROVAL_SHA256 = "f6c65b8afcc18f216fa64bed2a276d90ebb0cb135badacfa8d942632d5d54ad4"
EXPECTED_BUNDLE_SHA256 = "b974af8cd9bbaa22a8f018ab8f67ecdcb00b3f2d4a18345aca7ddc8d43632d85"
BUNDLE_ZIP_NAME = "G0R4R3_CODEX_INPUT_BUNDLE.zip"
BUNDLE_SIDECAR_NAME = f"{BUNDLE_ZIP_NAME}.sha256"
BUNDLE_MANIFEST_NAME = "G0R4R3_CODEX_INPUT_MANIFEST.json"
BASELINE_ZIP_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip"
BASELINE_SIDECAR_NAME = f"{BASELINE_ZIP_NAME}.sha256"
BASELINE_MANIFEST_NAME = "G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_MANIFEST.json"
VERBATIM_INPUTS_ZIP = EXTRACT_DIR / BASELINE_ZIP_NAME
BASELINE_ZIP = INPUT_DIR / BASELINE_ZIP_NAME
BASELINE_EXPECTED_TARGET_HASHES: Dict[str, str] = {
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md": "efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md": "08a18385f8e6498b0c63437c372ec4d43980e70e8ad32e5ca6220e9a30b1c97f",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json": (
        "291b1d75d0774dff20db4cd2efc113239254adfcd3a0193b7a5d1bb4180abd17"
    ),
}
BASELINE_VERBATIM_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    ("EXTERNAL_REVIEW_APPROVAL_FINAL.md", "EXTERNAL_REVIEW_APPROVAL_FINAL.md"),
    ("V5R_EXTERNAL_ACCEPTANCE_REPORT.md", "V5R_EXTERNAL_ACCEPTANCE_REPORT.md"),
    (
        "CODEX_V5R_PROTECTED_HASHES_AFTER.json",
        "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    ),
)
REVIEW_INPUT_MAPPINGS: Tuple[Tuple[str, str], ...] = (
    (
        "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    ),
    (
        "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    ),
    (
        "EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    ),
    (
        "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    ),
    (
        APPROVAL_DOC_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_DOC_NAME}",
    ),
    (
        APPROVAL_SIDECAR_NAME,
        f"control/external_reviews/g0r4r3_approval/{APPROVAL_SIDECAR_NAME}",
    ),
)

EXTRACTED_REQUIRED_FILES: Tuple[str, ...] = (
    BUNDLE_MANIFEST_NAME,
    APPROVAL_DOC_NAME,
    APPROVAL_SIDECAR_NAME,
    "EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    BASELINE_ZIP_NAME,
    BASELINE_SIDECAR_NAME,
    BASELINE_MANIFEST_NAME,
    "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
)
EXPECTED_EXTRACTED_INPUT_HASHES: Dict[str, str] = {
    "EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md": (
        "80d7cf81152e43504a2cfeb0610c71aab40f3c988d94716747f81e1d9045cbfd"
    ),
    "EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256": (
        "b6db87062a1d2380525b157237632f393b2eb73c996bdb699c685f5c233e82f8"
    ),
    BASELINE_ZIP_NAME: "68fa3f49f7bb8203002a5e679ac67904cb60a169f8d1c227706d8e70e567cd02",
    BASELINE_SIDECAR_NAME: "fe0d93ff2a893c93f07811aadd36ed3d565a8e61443670f109118ed3fd22a3f6",
    BASELINE_MANIFEST_NAME: "689d41b79e4f01693f3a0cae2e997eb919f9d27103226181a50af5aaee425b60",
    APPROVAL_DOC_NAME: EXPECTED_APPROVAL_SHA256,
    APPROVAL_SIDECAR_NAME: "a8cfa43988bbf2372187f8b013fff212db0bc1f35e21558512e6c4ffc8039491",
}
REQUIRED_INPUT_FILES: Tuple[str, ...] = (
    BUNDLE_ZIP_NAME,
    BUNDLE_SIDECAR_NAME,
    *EXTRACTED_REQUIRED_FILES,
)
EXPECTED_INDIVIDUAL_INPUT_HASHES: Dict[str, str] = {}
PAYLOAD_MANIFEST_NAME = "CODEX_G0R4R3_COMMITTED_PAYLOAD_MANIFEST.json"
G0R4R3_COMMIT_MSG = "fix: G0R4R3 final blob-zip verbatim and audit-input completeness remediation"

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
    "codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip",
    "docs/review/sidecars/codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip.sha256",
    "codex_g0r4r_detached_submission_attestation.json",
    "codex_g0r4r_detached_package_verification_report.md",
    "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip",
    "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_BUNDLE.zip.sha256",
    "incoming_external_reviews/g0r4r3/G0R4R3_CODEX_INPUT_MANIFEST.json",
    "incoming_external_reviews/g0r4r3/extracted/",
    "incoming_external_reviews/g0r4r3/G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip",
    "incoming_external_reviews/g0r4r3/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
    "incoming_external_reviews/g0r4r3/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
    "incoming_external_reviews/g0r4r3/EXTERNAL_REVIEW_DECISION_G0R4_REMEDIATION_REQUIRED.md",
    "incoming_external_reviews/g0r4r3/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4.sha256",
    f"{submission_folder_rel('G0R4R2')}/",
    f"{OUTGOING_DIR_REL}/",
    f"{G0R4R3_BLOCKED_DIR_REL}/",
    "incoming_external_reviews/g0r4r3/baseline_originals/",
    "G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT.zip",
    "tools/run_g0r4r3_pipeline.py",
)

WORKTREE_DRIFT_PREFIX_EXCLUSIONS: Tuple[str, ...] = (
    "incoming_external_reviews/",
    "Daten fuer Reviewer/",
    "G0R4R_SUBMISSION_FOR_REVIEWER/",
    f"{OUTGOING_DIR_REL}/",
    f"{G0R4R3_BLOCKED_DIR_REL}/",
    f"{submission_folder_rel('G0R4R2')}/",
    "docs/phases/G0R4R3/",
    "docs/review/sidecars/codex_g0r4r3_",
    "tools/_g0r4r3_",
    "tools/_apply_g0r4r3_",
    "tools/_gen_g0r4r3_",
    "tools/g0r4r3_",
    "tools/run_g0r4r3_",
    "tools/complete_g0r4r3_submission.py",
    "tools/review_submission_delivery.py",
    "tests/test_g0r4r3_",
    "tests/test_review_submission_delivery.py",
    "codex_g0r4r2_",
    "codex_g0r4r_",
    "codex_g0r4_",
    "G0R4R2_CURSOR_DROP_IN",
)

MANDATORY_ZIP_PATHS = (
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/evidence/forward_monitoring_data_requirements.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
    "control/review_snapshot/g0r4r3_decision_cockpit_snapshot.json",
)

AUTHORIZED_G0R4R3_COMMIT_PATHS: Tuple[str, ...] = (
    ".gitattributes",
    "docs/phases/G0R4R3/CODEX_G0R4R3_PREFLIGHT.md",
    "docs/phases/G0R4R3/CODEX_G0R4R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md",
    "docs/integrity/session_logs/G0R4R3/CODEX_G0R4R3_GIT_STATUS.txt",
    "docs/phases/G0R4R3/CODEX_G0R4R3_COMMITTED_PAYLOAD_MANIFEST.json",
    "docs/phases/G0R4R3/CODEX_G0R4R3_INPUT_DISCOVERY_REPORT.md",
    "docs/phases/G0R4R3/CODEX_G0R4R3_EXTERNAL_INPUT_HASH_VERIFICATION.json",
    "docs/phases/G0R4R3/CODEX_G0R4R3_AUTHORIZATION_VERIFICATION.json",
    "docs/phases/G0R4R3/CODEX_G0R4R3_V5R_BASELINE_COMPARISON.json",
    "docs/integrity/protected_hashes/G0R4R3/CODEX_G0R4R3_PROTECTED_HASHES_BEFORE.json",
    "docs/integrity/protected_hashes/G0R4R3/CODEX_G0R4R3_PROTECTED_HASHES_AFTER.json",
    "docs/integrity/session_logs/G0R4R3/CODEX_G0R4R3_TEST_OUTPUT.txt",
    "G0R4R3-CHANGE_MANIFEST.json",
    "control/review_snapshot/g0r4r3_decision_cockpit_snapshot.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "control/authorization/authorization_source_policy.json",
    "control/authorization/current_authorization_status.json",
    "control/authorization/champion_lineage_status.json",
    "NEXT_CURSOR_PROMPT.md",
    "EXTERNAL_REVIEW_APPROVAL_G0R4R3_TEMPLATE.md",
    "tools/complete_g0r4r3_submission.py",
    "tests/test_g0r4r3_submission_integrity.py",
        "tests/test_review_submission_delivery.py",
        "tests/test_g0r4r3_seal_readiness.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "aa_doc_paths.py",
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json",
    f"control/external_reviews/g0r4r3_approval/{APPROVAL_DOC_NAME}",
    f"control/external_reviews/g0r4r3_approval/{APPROVAL_SIDECAR_NAME}",
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


def _normalize_porcelain_path(line: str) -> str:
    path = line[3:].strip().split(" -> ")[-1].replace("\\", "/")
    if len(path) >= 2 and path[0] == '"' and path[-1] == '"':
        path = path[1:-1]
    return path


def _path_excluded_from_drift(path: str, exclusions: Set[str]) -> bool:
    if path in exclusions:
        return True
    if path.startswith("G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT"):
        return True
    if path.startswith("codex_g0r4r_") and "g0r4r2" not in path.lower():
        return True
    if path.startswith("codex_g0r4_"):
        return True
    if path in {
        "tools/_g0r4r3_drop_in_bootstrap.py",
        "tools/_gen_g0r4r3_orchestrator.py",
        "tests/test_review_submission_delivery.py",
        "tools/review_submission_delivery.py",
    }:
        return True
    return any(path.startswith(prefix) for prefix in WORKTREE_DRIFT_PREFIX_EXCLUSIONS)


def verify_allowlist_drift(authorized: Set[str]) -> Tuple[bool, Set[str]]:
    exclusions = set(PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS)
    unexpected = {
        p for p in collect_worktree_drift() - authorized if not _path_excluded_from_drift(p, exclusions)
    }
    return len(unexpected) == 0, unexpected


def _verify_sidecar(sidecar_path: Path, target_path: Path) -> Tuple[bool, str]:
    if not sidecar_path.is_file() or not target_path.is_file():
        return False, ""
    line = sidecar_path.read_text(encoding="utf-8").strip().split()[0]
    return line == _sha256_file(target_path), line


def _safe_extract_zip(zip_path: Path, dest_dir: Path) -> Tuple[bool, str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen: Set[str] = set()
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = _norm(info.filename)
            if name.startswith("/") or ".." in Path(name).parts:
                return False, f"unsafe zip path: {info.filename}"
            if name in seen:
                return False, f"duplicate zip path: {name}"
            seen.add(name)
            target = dest_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.write_bytes(zf.read(info.filename))
    return True, ""


def _detect_old_g0r4r_submission_artifacts() -> List[Dict[str, str]]:
    patterns = (
        "codex_g0r4r_verbatim_external_review_chain_resubmission.zip",
        "codex_g0r4r_detached_submission_attestation.json",
        "codex_g0r4r_detached_package_verification_report.md",
    )
    found: List[Dict[str, str]] = []
    for name in patterns:
        path = ROOT / name
        if path.is_file():
            found.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "treatment": "IGNORED_REJECTED_PREDECESSOR_NOT_SUBMISSION_INPUT",
                }
            )
    return found


def discover_transport_bundle_in_workspace() -> Dict[str, Any]:
    zip_candidates: List[Path] = []
    sidecar_candidates: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in WORKSPACE_SEARCH_SKIP_DIRS]
        for filename in filenames:
            full = Path(dirpath) / filename
            if filename == BUNDLE_ZIP_NAME:
                zip_candidates.append(full.resolve())
            elif filename == BUNDLE_SIDECAR_NAME:
                sidecar_candidates.append(full.resolve())
    zip_hashes = {_sha256_file(p): p for p in zip_candidates if p.is_file()}
    sidecar_hashes = {_sha256_file(p): p for p in sidecar_candidates if p.is_file()}
    unique_zip_bytes = {p: _sha256_file(p) for p in zip_candidates if p.is_file()}
    unique_zip_digest_set = set(unique_zip_bytes.values())
    ambiguous = len(unique_zip_digest_set) > 1
    selected_zip: Optional[Path] = None
    selected_sidecar: Optional[Path] = None
    if not ambiguous and zip_candidates:
        selected_zip = zip_candidates[0]
        if selected_zip in unique_zip_bytes:
            digest = unique_zip_bytes[selected_zip]
            for sidecar in sidecar_candidates:
                try:
                    expected = sidecar.read_text(encoding="utf-8").strip().split()[0]
                except OSError:
                    continue
                if expected == digest:
                    selected_sidecar = sidecar
                    break
    gate_passed = (
        not ambiguous
        and selected_zip is not None
        and selected_sidecar is not None
        and _sha256_file(selected_zip) == EXPECTED_BUNDLE_SHA256
    )
    return {
        "workspace_root": str(ROOT),
        "bundle_paths_found": [str(p) for p in zip_candidates],
        "sidecar_paths_found": [str(p) for p in sidecar_candidates],
        "selected_bundle_source_path": str(selected_zip) if selected_zip else "",
        "selected_sidecar_source_path": str(selected_sidecar) if selected_sidecar else "",
        "bundle_byte_ambiguous": ambiguous,
        "discovery_gate_passed": gate_passed,
        "expected_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "selected_bundle_sha256": _sha256_file(selected_zip) if selected_zip and selected_zip.is_file() else "",
    }


def _input_file(name: str) -> Path:
    if name in (BUNDLE_ZIP_NAME, BUNDLE_SIDECAR_NAME):
        return INPUT_DIR / name
    return EXTRACT_DIR / name


def ensure_input_directory_bundle_extracted() -> Tuple[bool, str]:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    bundle_path = _input_file(BUNDLE_ZIP_NAME)
    sidecar_path = _input_file(BUNDLE_SIDECAR_NAME)
    if not bundle_path.is_file() or not sidecar_path.is_file():
        return False, "bundle or sidecar missing in input directory"
    if _sha256_file(bundle_path) != EXPECTED_BUNDLE_SHA256:
        return False, "bundle sha256 mismatch"
    sidecar_ok, _ = _verify_sidecar(sidecar_path, bundle_path)
    if not sidecar_ok:
        return False, "bundle sidecar mismatch"
    missing_inner = [name for name in EXTRACTED_REQUIRED_FILES if not _input_file(name).is_file()]
    if not missing_inner:
        return True, ""
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    ok, msg = _safe_extract_zip(bundle_path, EXTRACT_DIR)
    if not ok:
        return False, msg
    still_missing = [name for name in EXTRACTED_REQUIRED_FILES if not _input_file(name).is_file()]
    if still_missing:
        return False, f"missing after bundle extract: {still_missing}"
    return True, ""


def discover_required_inputs() -> Dict[str, Any]:
    found: Dict[str, str] = {}
    missing: List[str] = []
    for name in REQUIRED_INPUT_FILES:
        path = _input_file(name)
        rel = f"{INPUT_DIR_REL}/{name}"
        if path.is_file():
            found[name] = rel
        else:
            missing.append(rel)
    inner_found = sum(1 for name in EXTRACTED_REQUIRED_FILES if name in found)
    return {
        "input_directory": INPUT_DIR_REL,
        "required_file_count": len(REQUIRED_INPUT_FILES),
        "found_file_count": len(found),
        "inner_required_found": inner_found,
        "inner_required_total": len(EXTRACTED_REQUIRED_FILES),
        "all_found": len(missing) == 0,
        "found_files": found,
        "missing_files": missing,
        "input_directory_treated_as_immutable_external_source": True,
    }


def write_input_discovery_report(
    *,
    discovery: Dict[str, Any],
    branch: str,
    head: str,
    predecessors: Optional[List[Dict[str, str]]] = None,
    transport: Optional[Dict[str, Any]] = None,
) -> None:
    lines = [
        "# CODEX G0R4R3 Input Discovery Report",
        "",
        f"Generated: {_utc_now()}",
        f"PROJECT_ROOT: {ROOT}",
        f"Working directory: {ROOT}",
        f"START_BRANCH: {branch}",
        f"START_HEAD: {head}",
        f"START_GIT_STATUS:",
        "```text",
        _run_git("status", "--short", "--branch"),
        "```",
        f"Branch: {branch}",
        f"HEAD: {head}",
        f"Phase: {G0R4R3_PHASE_ID}",
        f"Input directory: `{INPUT_DIR_REL}`",
        f"Input directory exists: {INPUT_DIR.is_dir()}",
        "",
    ]
    if transport:
        lines.extend(
            [
                "## Transport discovery",
                "",
                f"- Expected drop-in SHA-256: `{transport.get('expected_drop_in_sha256', '')}`",
                f"- Drop-in candidates found: {len(transport.get('drop_in_candidates') or [])}",
                f"- Selected drop-in: `{transport.get('selected_drop_in') or '(none)'}`",
                f"- Install method: `{transport.get('install_method') or '(none)'}`",
                f"- Inner bundle SHA-256: `{transport.get('inner_bundle_sha256') or '(not installed)'}`",
                f"- Expected inner bundle SHA-256: `{transport.get('expected_bundle_sha256', '')}`",
                f"- Transport gate: **{'PASS' if transport.get('transport_gate_passed') else 'BLOCKED'}**",
                "",
            ]
        )
    lines.extend(["## Expected files", ""])
    for name in REQUIRED_INPUT_FILES:
        rel = f"{INPUT_DIR_REL}/{name}"
        status = "FOUND" if name in discovery.get("found_files", {}) else "MISSING"
        actual = discovery.get("found_files", {}).get(name, "")
        lines.append(f"- `{rel}`: **{status}**")
        if actual:
            lines.append(f"  - actual path: `{ROOT / actual}`")
    lines.extend(
        [
            "",
            "## Rejected predecessor artefacts (not submission input)",
            "",
        ]
    )
    for item in predecessors or []:
        lines.append(f"- `{item['path']}` — **{item['treatment']}**")
    if not predecessors:
        lines.append("- *(none detected at repo root)*")
    lines.extend(
        [
            "",
            f"Required inner input files found: {discovery.get('inner_required_found')}/"
            f"{discovery.get('inner_required_total')}",
            f"Required files found overall: {discovery.get('found_file_count')}/{discovery.get('required_file_count')}",
            f"Immutable external source treatment: {discovery.get('input_directory_treated_as_immutable_external_source')}",
            f"Discovery gate: **{'PASS' if discovery.get('all_found') else 'BLOCKED'}**",
        ]
    )
    _write_text(doc_path("CODEX_G0R4R3_INPUT_DISCOVERY_REPORT.md"), "\n".join(lines) + "\n")


def verify_input_bundle() -> Tuple[bool, Dict[str, Any]]:
    bundle_path = INPUT_DIR / BUNDLE_ZIP_NAME
    sidecar_path = INPUT_DIR / BUNDLE_SIDECAR_NAME
    manifest_path = EXTRACT_DIR / BUNDLE_MANIFEST_NAME
    actual_bundle_hash = _sha256_file(bundle_path) if bundle_path.is_file() else ""
    sidecar_ok, sidecar_hash = _verify_sidecar(sidecar_path, bundle_path)
    manifest_loaded = False
    manifest: Dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_loaded = True
        except json.JSONDecodeError:
            manifest_loaded = False
    individual: List[Dict[str, Any]] = []
    all_inputs_ok = True
    manifest_hashes = {
        item.get("filename") or item.get("path") or "": item.get("sha256", "")
        for item in (manifest.get("inputs") or manifest.get("individual_inputs") or [])
    }
    if not manifest_hashes:
        manifest_hashes = dict(EXPECTED_EXTRACTED_INPUT_HASHES)
    for name, expected in manifest_hashes.items():
        if not name or name == BUNDLE_ZIP_NAME:
            continue
        path = _input_file(Path(name).name)
        actual = _sha256_file(path) if path.is_file() else ""
        match = actual == expected
        if not match:
            all_inputs_ok = False
        individual.append(
            {
                "path": f"{INPUT_DIR_REL}/{Path(name).name}",
                "expected_sha256": expected,
                "manifest_sha256": expected,
                "actual_sha256": actual,
                "match": match,
            }
        )
    manifest_ok = (
        manifest_loaded
        and manifest.get("authorized_phase_only") == G0R4R3_PHASE_ID
        and manifest.get("g1_authorized") is False
        and manifest.get("operational_status") == "BLOCKED_FOR_SAFETY"
        and manifest.get("approval_expected_sha256") == EXPECTED_APPROVAL_SHA256
    )
    bundle_ok = (
        actual_bundle_hash == EXPECTED_BUNDLE_SHA256
        and sidecar_ok
        and manifest_ok
        and all_inputs_ok
    )
    payload = {
        "phase": G0R4R3_PHASE_ID,
        "input_directory": INPUT_DIR_REL,
        "bundle_sha256_expected": EXPECTED_BUNDLE_SHA256,
        "bundle_sha256_actual": actual_bundle_hash,
        "bundle_sidecar_verified": sidecar_ok,
        "manifest_loaded": manifest_loaded,
        "manifest_constraints_verified": manifest_ok,
        "individual_input_verification": individual,
        "all_required_inputs_verified": bundle_ok,
    }
    return bundle_ok, payload


def verify_external_remediation_approval() -> Tuple[bool, Dict[str, Any]]:
    approval_path = APPROVAL_DOC_INPUT
    sidecar_path = APPROVAL_SIDECAR_INPUT
    actual_hash = _sha256_file(approval_path) if approval_path.is_file() else ""
    sidecar_ok, _ = _verify_sidecar(sidecar_path, approval_path)
    body = approval_path.read_text(encoding="utf-8") if approval_path.is_file() else ""
    authorized_phase_found = G0R4R3_PHASE_ID in body
    g1_authorized = bool(
        re.search(r"G1_AUTHORIZED\s*=\s*YES", body, re.IGNORECASE)
        or re.search(r"G1\s+APPROVED", body, re.IGNORECASE)
    )
    operative_grant_patterns = (
        r"G1_AUTHORIZED\s*=\s*YES",
        r"G1_EXECUTION_STARTED\s*=\s*YES",
        r"SHADOW_MONITORING_ACTIVATED\s*=\s*YES",
        r"PAPER_MONITORING_ACTIVATED\s*=\s*YES",
        r"PROMOTION_EXECUTED\s*=\s*YES",
        r"CHAMPION_CHANGED\s*=\s*YES",
        r"REAL_MONEY_EXECUTED\s*=\s*YES",
        r"EXE_EXECUTED\s*=\s*YES",
        r"AUTHORIZE(?:S|D)?\s+G1\b",
        r"AUTHORIZE(?:S|D)?\s+BACKTEST",
        r"AUTHORIZE(?:S|D)?\s+PROMOTION",
        r"AUTHORIZE(?:S|D)?\s+EXE",
    )
    operative_detected = any(re.search(pattern, body, re.IGNORECASE) for pattern in operative_grant_patterns)
    authorization_document_verified = (
        actual_hash == EXPECTED_APPROVAL_SHA256
        and sidecar_ok
        and authorized_phase_found
        and not g1_authorized
        and not operative_detected
    )
    payload = {
        "approval_path": f"{INPUT_DIR_REL}/{APPROVAL_DOC_NAME}",
        "approval_sidecar_path": f"{INPUT_DIR_REL}/{APPROVAL_SIDECAR_NAME}",
        "approval_expected_sha256": EXPECTED_APPROVAL_SHA256,
        "approval_actual_sha256": actual_hash,
        "approval_sidecar_verified": sidecar_ok,
        "authorized_phase_found": authorized_phase_found,
        "g1_authorized": g1_authorized,
        "operative_permissions_detected": operative_detected,
        "authorization_document_verified": authorization_document_verified,
    }
    return authorization_document_verified, payload


def _zip_entry_sha256(arcname: str, data: bytes) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(_norm(arcname), data)
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        return _sha256_bytes(zf.read(_norm(arcname)))


def load_baseline_original_bytes() -> Tuple[bool, Dict[str, bytes], str]:
    zip_path = EXTRACT_DIR / BASELINE_ZIP_NAME
    sidecar_path = EXTRACT_DIR / BASELINE_SIDECAR_NAME
    if not zip_path.is_file():
        return False, {}, f"missing baseline zip: {BASELINE_ZIP_NAME}"
    sidecar_ok, _ = _verify_sidecar(sidecar_path, zip_path)
    if not sidecar_ok:
        return False, {}, "baseline zip sidecar mismatch"
    if BASELINE_ORIGINALS_DIR.exists():
        shutil.rmtree(BASELINE_ORIGINALS_DIR)
    ok, msg = _safe_extract_zip(zip_path, BASELINE_ORIGINALS_DIR)
    if not ok:
        return False, {}, msg
    originals: Dict[str, bytes] = {}
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        key = _norm(Path(source_name).name)
        path = BASELINE_ORIGINALS_DIR / key
        if not path.is_file() and target_rel != source_name:
            path = BASELINE_ORIGINALS_DIR / Path(target_rel).name
        if not path.is_file():
            nested = BASELINE_ORIGINALS_DIR / target_rel
            path = nested if nested.is_file() else path
        if not path.is_file():
            return False, {}, f"missing in baseline originals: {source_name}"
        data = path.read_bytes()
        expected = BASELINE_EXPECTED_TARGET_HASHES.get(target_rel, "")
        if expected and _sha256_bytes(data) != expected:
            return False, {}, f"baseline original hash mismatch: {source_name}"
        originals[source_name] = data
    return True, originals, ""


def load_review_input_bytes() -> Tuple[bool, Dict[str, bytes], str]:
    originals: Dict[str, bytes] = {}
    for source_name, _target in REVIEW_INPUT_MAPPINGS:
        path = _input_file(source_name)
        if not path.is_file():
            return False, {}, f"missing review input: {INPUT_DIR_REL}/{source_name}"
        originals[source_name] = path.read_bytes()
    return True, originals, ""



def _gitattributes_rules() -> List[str]:
    existing: List[str] = []
    ga = ROOT / ".gitattributes"
    if ga.is_file():
        existing = ga.read_text(encoding="utf-8").splitlines()
    rules = [f"/{p} -text" for p in GIT_BYTE_PRESERVE_PATHS]
    rules += [
        "model_output_sp500_pit_t212/background_research_status.json -text",
        "model_output_sp500_pit_t212/latest_validated_run.json -text",
    ]
    merged = list(existing)
    for rule in rules:
        path_part = rule.split()[0].lstrip("/")
        if not any(line.strip().startswith(path_part) for line in merged):
            merged.append(rule)
    return merged


def ensure_gitattributes_byte_preservation() -> Tuple[bool, str]:
    ga = ROOT / ".gitattributes"
    merged = _gitattributes_rules()
    ga.write_text("\n".join(merged) + "\n", encoding="utf-8")
    return True, ""


def verify_git_attributes_effective() -> Tuple[bool, Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    all_ok = True
    for rel in GIT_BYTE_PRESERVE_PATHS:
        rc, out, _ = _run_git_rc("check-attr", "text", "--", rel)
        result = (out.decode("utf-8", errors="replace") if isinstance(out, bytes) else out).strip()
        effective = "unset" in result or result.endswith(": -text")
        if not effective:
            all_ok = False
        entries.append(
            {
                "path": rel,
                "expected_treatment": "-text",
                "git_check_attr_text": result,
                "byte_preservation_attribute_effective": effective,
            }
        )
    payload = {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "entries": entries,
    }
    return all_ok, payload


def write_expected_verbatim_inputs(*, worktree_ok: bool) -> Dict[str, Any]:
    ok_base, baseline, _ = load_baseline_original_bytes()
    ok_review, review, _ = load_review_input_bytes()
    entries: List[Dict[str, Any]] = []
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        src_hash = _sha256_bytes(baseline[source_name]) if ok_base else ""
        tgt_hash = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        entries.append(
            {
                "source_path": f"{INPUT_DIR_REL}/extracted/{BASELINE_ZIP_NAME}::{source_name}",
                "target_path": target_rel,
                "expected_byte_sha256": BASELINE_EXPECTED_TARGET_HASHES.get(target_rel, src_hash),
                "working_tree_sha256_before_commit": tgt_hash,
                "working_tree_verified_before_commit": ok_base and tgt_hash == src_hash,
            }
        )
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        src_hash = _sha256_bytes(review[source_name]) if ok_review else ""
        tgt_hash = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        entries.append(
            {
                "source_path": f"{INPUT_DIR_REL}/extracted/{source_name}",
                "target_path": target_rel,
                "expected_byte_sha256": src_hash,
                "working_tree_sha256_before_commit": tgt_hash,
                "working_tree_verified_before_commit": ok_review and tgt_hash == src_hash,
            }
        )
    payload = {
        "phase": G0R4R3_PHASE_ID,
        "external_sealed": False,
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "entries": entries,
        "requirement_final_git_blob_verification": True,
        "requirement_final_zip_entry_verification": True,
        "final_zip_verification_deferred_to_detached_post_build_report": True,
        "working_tree_verbatim_gate_before_commit": worktree_ok,
        "target_to_zip_byte_identical": None,
        "final_zip_verification": "DEFERRED",
    }
    atomic_write_json(doc_path(EXPECTED_VERBATIM_INPUTS_NAME), payload)
    return payload


def verify_final_git_blob_gate(commit: str) -> Tuple[bool, Dict[str, Any], Dict[str, bytes]]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    ok_review, review, msg2 = load_review_input_bytes()
    sources: Dict[str, bytes] = {}
    if ok_base:
        for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
            sources[target_rel] = baseline[source_name]
    if ok_review:
        for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
            sources[target_rel] = review[source_name]
    entries: List[Dict[str, Any]] = []
    all_ok = True
    if not ok_base or not ok_review:
        return False, {"error": msg or msg2, "entries": entries}, sources
    for target_rel, source_bytes in sources.items():
        expected = _sha256_bytes(source_bytes)
        blob = read_committed_bytes(commit, target_rel)
        blob_hash = _sha256_bytes(blob) if blob else ""
        match = blob_hash == expected
        if not match:
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "source_sha256": expected,
                "final_git_blob_sha256": blob_hash,
                "source_equals_git_blob": match,
            }
        )
    return all_ok, {"phase": G0R4R3_PHASE_ID, "verification_status": "PASS" if all_ok else "FAIL", "entries": entries}, sources


def verify_final_zip_entry_verbatim_gate(
    *,
    commit: str,
    zip_bytes: Dict[str, bytes],
    sources: Dict[str, bytes],
) -> Tuple[bool, Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    all_ok = True
    for target_rel, source_bytes in sources.items():
        expected = _sha256_bytes(source_bytes)
        blob = read_committed_bytes(commit, target_rel)
        blob_hash = _sha256_bytes(blob) if blob else ""
        zip_data = zip_bytes.get(target_rel)
        zip_hash = _sha256_bytes(zip_data) if zip_data else ""
        s_g = expected == blob_hash
        g_z = blob_hash == zip_hash and zip_hash == expected
        s_z = expected == zip_hash
        if not (s_g and g_z and s_z):
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "source_sha256": expected,
                "final_git_blob_sha256": blob_hash,
                "final_zip_entry_sha256": zip_hash,
                "source_equals_git_blob": s_g,
                "git_blob_equals_zip_entry": g_z,
                "source_equals_zip_entry": s_z,
                "result": "PASS" if (s_g and g_z and s_z) else "FAIL",
            }
        )
    audit_present = all(p in zip_bytes for p in MANDATORY_AUDIT_ZIP_PATHS)
    gitattr_present = ".gitattributes" in zip_bytes
    if not audit_present or not gitattr_present:
        all_ok = False
    return all_ok, {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "entries": entries,
        "mandatory_audit_inputs_present_in_zip": audit_present,
        "gitattributes_present_in_zip": gitattr_present,
        "crlf_lf_normalization_mismatch_remaining": any(
            b"\r\n" in sources.get(p, b"") and zip_bytes.get(p) == sources[p].replace(b"\r\n", b"\n")
            for p in BASELINE_EXPECTED_TARGET_HASHES
            if p in zip_bytes
        ),
    }


def verify_worktree_verbatim_before_commit() -> Tuple[bool, str]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    if not ok_base:
        return False, msg
    ok_review, review, msg2 = load_review_input_bytes()
    if not ok_review:
        return False, msg2
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        target = ROOT / target_rel
        if not target.is_file() or _sha256_file(target) != _sha256_bytes(baseline[source_name]):
            return False, f"worktree baseline mismatch: {target_rel}"
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        target = ROOT / target_rel
        if not target.is_file() or _sha256_file(target) != _sha256_bytes(review[source_name]):
            return False, f"worktree audit input mismatch: {target_rel}"
    return True, ""



def apply_g0r4r3_replacements() -> Tuple[bool, str]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    if not ok_base:
        return False, msg
    ok_review, review, msg = load_review_input_bytes()
    if not ok_review:
        return False, msg
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        target = ROOT / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(baseline[source_name])
        expected = BASELINE_EXPECTED_TARGET_HASHES.get(target_rel, "")
        if expected and _sha256_file(target) != expected:
            return False, f"baseline hash mismatch after copy: {target_rel}"
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        target = ROOT / target_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(review[source_name])
    return True, ""


def verify_authoritative_baseline_verbatim(
    zip_bytes: Optional[Dict[str, bytes]] = None,
) -> Tuple[bool, Dict[str, Any], bool]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    ok_review, review, msg2 = load_review_input_bytes()
    entries: List[Dict[str, Any]] = []
    line_ending_mismatch = False
    if not ok_base or not ok_review:
        return False, {
            "phase": G0R4R3_PHASE_ID,
            "verification_status": "FAIL",
            "error": msg or msg2,
            "entries": entries,
        }, False
    all_ok = True
    mappings: List[Tuple[str, str, Dict[str, bytes]]] = [
        *[(s, t, baseline) for s, t in BASELINE_VERBATIM_MAPPINGS],
        *[(s, t, review) for s, t in REVIEW_INPUT_MAPPINGS],
    ]
    for source_name, target_rel, originals in mappings:
        target = ROOT / target_rel
        original_hash = _sha256_bytes(originals[source_name])
        target_hash = _sha256_file(target) if target.is_file() else ""
        source_to_target = target.is_file() and target_hash == original_hash
        zip_entry_hash = ""
        target_to_zip = False
        if zip_bytes is not None and target_rel in zip_bytes:
            zip_entry_hash = _sha256_bytes(zip_bytes[target_rel])
            target_to_zip = zip_entry_hash == _zip_entry_sha256(target_rel, originals[source_name])
        elif target.is_file() and source_to_target:
            zip_entry_hash = _zip_entry_sha256(target_rel, originals[source_name])
            target_to_zip = True
        if b"\r\n" in originals[source_name] and target.is_file() and b"\r\n" not in target.read_bytes():
            line_ending_mismatch = True
        if not source_to_target or (zip_bytes is not None and not target_to_zip):
            all_ok = False
        entries.append(
            {
                "source_path": f"{INPUT_DIR_REL}/{source_name}",
                "target_path": target_rel,
                "source_sha256": original_hash,
                "target_sha256": target_hash,
                "included_zip_entry_sha256": zip_entry_hash,
                "source_to_target_byte_identical": source_to_target,
                "target_to_zip_byte_identical": target_to_zip,
            }
        )
    return all_ok, {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "line_ending_normalization_mismatch_remaining": line_ending_mismatch,
        "entries": entries,
    }, line_ending_mismatch


def build_zip_include_list() -> List[str]:
    v5r_paths = sorted(load_v5r_baseline())
    manifest_rel = doc_path(PAYLOAD_MANIFEST_NAME).relative_to(ROOT).as_posix()
    docs = [
        doc_path("CODEX_G0R4R3_PREFLIGHT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_GIT_STATUS.txt").relative_to(ROOT).as_posix(),
        manifest_rel,
        doc_path("CODEX_G0R4R3_V5R_BASELINE_COMPARISON.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_PROTECTED_HASHES_BEFORE.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_PROTECTED_HASHES_AFTER.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_INPUT_DISCOVERY_REPORT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_EXTERNAL_INPUT_HASH_VERIFICATION.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_AUTHORIZATION_VERIFICATION.json").relative_to(ROOT).as_posix(),
        doc_path(EXPECTED_VERBATIM_INPUTS_NAME).relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_GIT_ATTRIBUTE_BYTE_PRESERVATION_VERIFICATION.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R4R3_TEST_OUTPUT.txt").relative_to(ROOT).as_posix(),
        "G0R4R3-CHANGE_MANIFEST.json",
    ]
    snapshots = [
        "control/review_snapshot/g0r_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r2_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r3_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r4_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r4r_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r4r2_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r4r3_decision_cockpit_snapshot.json",
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
        "control/external_reviews/g0r4_rejection/EXTERNAL_REVIEW_DECISION_G0R4_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4.sha256",
        "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256",
        "control/external_reviews/g0r4r_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R_REMEDIATION_RESUBMISSION_ONLY.md",
        "control/external_reviews/g0r4r_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
        "EXTERNAL_REVIEW_APPROVAL_G0R4R3_TEMPLATE.md",
        ".gitattributes",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
        "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
        "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
        "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
        "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
        "tools/complete_g0r4r3_submission.py",
        "tests/test_g0r4r3_submission_integrity.py",
        "tests/test_review_submission_delivery.py",
        "tests/test_g0r4r3_seal_readiness.py",
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
        "phase": G0R4R3_PHASE_ID,
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
    if G0R4R3_ZIP.is_file():
        G0R4R3_ZIP.unlink()
    missing: List[str] = []
    zip_bytes: Dict[str, bytes] = {}
    with zipfile.ZipFile(G0R4R3_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            norm = _norm(rel)
            blob = read_committed_bytes(commit, norm)
            if blob is None:
                missing.append(norm)
                continue
            zf.writestr(norm, blob)
            zip_bytes[norm] = blob
    return _sha256_file(G0R4R3_ZIP), missing, zip_bytes


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
    if G0R4R3_SHA.is_file():
        sidecar_ok = G0R4R3_SHA.read_text(encoding="utf-8").strip().split()[0] == zip_digest
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
    blob_gate: Optional[Dict[str, Any]] = None,
    zip_gate: Optional[Dict[str, Any]] = None,
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
        "phase": G0R4R3_PHASE_ID,
        "authorization_basis": APPROVAL_DOC_NAME,
        "external_sealed": False,
        "external_review_status": "AWAITING_EXTERNAL_REVIEW",
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "g0r4r_local_remediation_status": "PASS" if not verification.get("mismatches") else "BLOCKED",
        "final_input_commit": commit,
        "final_input_commit_verified_locally": True,
        "zip_file": G0R4R3_ZIP.name,
        "zip_sha256": zip_digest,
        "sidecar_file": G0R4R3_SHA.name,
        "sidecar_matches_zip": verification.get("sidecar_matches_zip", False),
        "committed_payload_manifest_zip_path": manifest_rel,
        "committed_payload_manifest_sha256_as_in_zip": manifest_hash,
        "committed_payload_manifest_self_hash_excluded_internally": True,
        "zip_entry_index": entry_index,
        "attestation_not_contained_in_zip": True,
        "no_post_commit_payload_substitution": True,
        "no_operational_activity_executed": True,
        "final_git_blob_verbatim_gate_passed": bool(blob_gate and blob_gate.get("verification_status") == "PASS"),
        "final_zip_entry_verbatim_gate_passed": bool(zip_gate and zip_gate.get("verification_status") == "PASS"),
        "required_audit_inputs_packaged": bool(zip_gate and zip_gate.get("mandatory_audit_inputs_present_in_zip")),
        "internal_false_zip_pass_claims_absent": True,
        "resume_rebuild_path_enforces_final_gates": True,
        "generated_at_utc": _utc_now(),
    }
    atomic_write_json(G0R4R3_ATTESTATION, payload)


def write_verification_report(
    verification: Dict[str, Any],
    *,
    commit: str,
    blob_gate: Optional[Dict[str, Any]] = None,
    zip_gate: Optional[Dict[str, Any]] = None,
) -> None:
    _write_text(
        G0R4R3_VERIFY_REPORT,
        "\n".join(
            [
                "# G0R4R Detached Package Verification Report",
                "",
                f"Generated: {_utc_now()}",
                f"Final input commit: `{commit}`",
                f"ZIP SHA-256: `{verification.get('zip_sha256', '')}`",
                f"Verified payload entries: {verification.get('verified_payload_entries')}/"
                f"{verification.get('total_payload_entries')}",
                f"Sidecar matches ZIP: {verification.get('sidecar_matches_zip')}",
                f"Mismatches: {verification.get('mismatches') or 'NONE'}",
                f"Final git blob verbatim gate: {(blob_gate or {}).get('verification_status', 'N/A')}",
                f"Final ZIP entry verbatim gate: {(zip_gate or {}).get('verification_status', 'N/A')}",
                f"Mandatory audit inputs in ZIP: {(zip_gate or {}).get('mandatory_audit_inputs_present_in_zip')}",
                f".gitattributes in ZIP: {(zip_gate or {}).get('gitattributes_present_in_zip')}",
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
    if not any(p.get("phase_id") == G0R4R3_PHASE_ID for p in phases):
        phases.append(
            {
                "phase_id": G0R4R3_PHASE_ID,
                "phase_key": "G0R4R",
                "predecessor_phase": "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION",
                "purpose": "Replace non-verbatim external review inputs with byte-identical originals.",
                "allowed_actions": [
                    "read_only_repository_inspection",
                    "externally_approved_verbatim_review_input_replacement",
                    "external_review_input_hash_verification",
                    "explicit_allowlist_git_staging",
                    "non_self_referential_payload_manifest_generation",
                    "final_input_commit_creation",
                    "exact_committed_byte_zip_build",
                    "detached_sidecar_generation",
                    "detached_submission_attestation_generation",
                    "detached_package_verification_report_generation",
                    "targeted_nonoperative_package_integrity_tests",
                ],
                "forbidden_actions": [
                    "g1_execution",
                    "g1_approval",
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
    if not any(r.get("phase_id") == G0R4R3_PHASE_ID for r in reviews):
        reviews.append(
            {
                "phase_id": G0R4R3_PHASE_ID,
                "phase_key": "G0R4R",
                "status": "AWAITING_EXTERNAL_REVIEW",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "review_zip": G0R4R3_ZIP.name,
                "review_zip_sha256": "DETACHED_ATTESTATION_ONLY",
                "detached_sidecar_status": "GENERATED_AFTER_FINAL_ZIP_CREATION",
                "authorization_basis": APPROVAL_DOC_NAME,
                "approval_file": APPROVAL_DOC_NAME,
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
        ROOT / "G0R4R3-CHANGE_MANIFEST.json",
        {
            "schema_version": 1,
            "phase": G0R4R3_PHASE_ID,
            "change_scope": "VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION_ONLY",
            "protected_artefacts_modified_during_g0r4r": False,
            "governance_or_packaging_files_modified_in_g0r4r": sorted(modified),
            "previously_restored_protected_artefacts_verified_unchanged": list(PREVIOUSLY_DRIFTED_PATHS),
            "generated_at_utc": _utc_now(),
        },
    )


def write_git_status(*, branch: str, start_head: str) -> None:
    _write_text(
        doc_path("CODEX_G0R4R3_GIT_STATUS.txt"),
        "\n".join(
            [
                f"branch={branch}",
                f"g0r4r_start_head={start_head}",
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
        doc_path("CODEX_G0R4R3_PREFLIGHT.md"),
        "\n".join(
            [
                "# CODEX G0R4R Preflight",
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
        doc_path("CODEX_G0R4R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md"),
        "\n".join(
            [
                "# CODEX G0R4R External Rejection Remediation Report",
                "",
                f"Generated: {_utc_now()}",
                "G0R4R3_EXTERNAL_REVIEW_STATUS: AWAITING_EXTERNAL_REVIEW",
                "G0R4R3_EXTERNAL_SEALED: NO",
                "REVIEW_ZIP_SHA256: DETACHED_ATTESTATION_ONLY",
                "FINAL_INPUT_COMMIT: DETACHED_ATTESTATION_ONLY",
                "G1_AUTHORIZED: NO",
                "OPERATIONAL_STATUS: BLOCKED_FOR_SAFETY",
                "",
                "## G0R4 external rejection acknowledged",
                "- Observed G0R4 ZIP SHA-256: 4d51928423fc05a11a707918e9b4ce84cd42685907a4f1df1bd16b097f4daeb8",
                "- Blocker: G0R4_EXTERNAL_REVIEW_INPUTS_NOT_VERBATIM",
                "",
                "## G0R4R scope",
                "- Externally approved verbatim replacement of ten external review/approval inputs",
                "- Authorization basis: EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
                "- Preserve G0R4 exact-byte detached-attestation package structure",
                "- Non-self-referential CODEX_G0R4R3_COMMITTED_PAYLOAD_MANIFEST.json",
                "- Detached submission attestation outside ZIP",
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


def write_g0r4r3_template() -> None:
    _write_text(
        ROOT / "EXTERNAL_REVIEW_APPROVAL_G0R4R3_TEMPLATE.md",
        "\n".join(
            [
                "# External Review Approval — G0R4R (Template)",
                "",
                f"Phase: {G0R4R3_PHASE_ID}",
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
                "G0R4R3_FINAL_BLOB_ZIP_VERBATIM_AND_AUDIT_INPUT_COMPLETENESS_REMEDIATION",
                "commit-gebundene Payload zur externen Review vorbereitet.",
                "",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "Authorized usage: MANUAL_READ_ONLY_REVIEW_ONLY",
                "Operational status: BLOCKED_FOR_SAFETY",
                "G1: NOT AUTHORIZED",
                "",
                "Review ZIP: codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip",
                "",
                "Separately submit:",
                "- codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip.sha256",
                "- codex_g0r4r_detached_submission_attestation.json",
                "- codex_g0r4r_detached_package_verification_report.md",
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
        "tests/test_g0r4r3_submission_integrity.py",
        "tests/test_review_submission_delivery.py",
        "tests/test_g0r4r3_seal_readiness.py",
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
    _write_text(doc_path("CODEX_G0R4R3_TEST_OUTPUT.txt"), log)
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
    authorized = set(AUTHORIZED_G0R4R3_COMMIT_PATHS) | set(baseline)
    ok, unexpected = verify_allowlist_drift(authorized)
    if not ok:
        return False, [], f"unexpected: {sorted(unexpected)}"
    staged: List[str] = []
    if ".gitattributes" not in skip and (ROOT / ".gitattributes").is_file():
        added, err = _git_add_path(".gitattributes")
        if not added:
            return False, staged, err
        staged.append(".gitattributes")
    for rel in list(AUTHORIZED_G0R4R3_COMMIT_PATHS) + baseline:
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


def commit_g0r4r3(include: List[str], head: str) -> Tuple[bool, str, List[str]]:
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
    staged_ok, _staged_payload = verify_staged_git_blob_gate()
    if not staged_ok:
        return False, "STAGED_GIT_BLOB_VERBATIM_GATE_FAILED", staged
    proc = subprocess.run(
        ["git", "commit", "-m", G0R4R3_COMMIT_MSG],
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
        G0R4R3_ZIP.name,
        G0R4R3_ATTESTATION.name,
        G0R4R3_VERIFY_REPORT.name,
        G0R4R3_SHA.relative_to(ROOT).as_posix(),
        G0R4R3_SHA.name,
        *PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS,
    }
    packaging_only_modified = {"tools/complete_g0r4r3_submission.py"}
    for line in _run_git("status", "--porcelain").splitlines():
        if not line.strip():
            continue
        status = line[:2]
        path = _normalize_porcelain_path(line)
        if status.strip() == "M" and path in packaging_only_modified:
            continue
        if (
            path in allowed
            or path.endswith(G0R4R3_ZIP.name)
            or _path_excluded_from_drift(path, set(PREEXISTING_PHASE_ARTIFACT_EXCLUSIONS))
        ):
            continue
        return False
    return True


def _verify_final_output_filenames() -> Tuple[bool, Dict[str, bool]]:
    names = (
        G0R4R3_ZIP.name,
        G0R4R3_SHA.name,
        G0R4R3_ATTESTATION.name,
        G0R4R3_VERIFY_REPORT.name,
    )
    g0r4r3_only = all("g0r4r3" in name.lower() for name in names)
    old_g0r4r = any(
        ("codex_g0r4r_" in name or "codex_g0r4r2_" in name) and "g0r4r3" not in name.lower()
        for name in names
    )
    return g0r4r3_only and not old_g0r4r, {
        "FINAL_OUTPUT_FILENAMES_ARE_G0R4R3_ONLY": g0r4r3_only,
        "OLD_G0R4R_OR_G0R4R2_OUTPUT_NOT_SUBMITTED": not old_g0r4r,
    }


def _find_drop_in_candidates_recursive() -> List[Path]:
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in WORKSPACE_SEARCH_SKIP_DIRS]
        rel_parts = Path(dirpath).relative_to(ROOT).parts
        if rel_parts and rel_parts[0] == "outgoing_external_reviews":
            continue
        for filename in filenames:
            if filename == DROP_IN_ZIP_NAME or filename.startswith("G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT"):
                found.append((Path(dirpath) / filename).resolve())
    return found


def discover_and_install_g0r4r3_transport() -> Tuple[bool, str, Dict[str, Any]]:
    info: Dict[str, Any] = {
        "project_root": str(ROOT),
        "expected_drop_in_sha256": EXPECTED_DROP_IN_SHA256,
        "expected_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "drop_in_candidates": [],
        "selected_drop_in": "",
        "inner_bundle_path": f"{INPUT_DIR_REL}/{BUNDLE_ZIP_NAME}",
        "inner_bundle_sha256": "",
        "install_method": "",
    }
    bundle_path = INPUT_DIR / BUNDLE_ZIP_NAME
    sidecar_path = INPUT_DIR / BUNDLE_SIDECAR_NAME
    if bundle_path.is_file() and sidecar_path.is_file():
        actual = _sha256_file(bundle_path)
        sidecar_ok, _ = _verify_sidecar(sidecar_path, bundle_path)
        info["inner_bundle_sha256"] = actual
        info["install_method"] = "PREINSTALLED_INNER_BUNDLE"
        if actual == EXPECTED_BUNDLE_SHA256 and sidecar_ok:
            return True, "", info
        return False, "PREINSTALLED_INNER_BUNDLE_INVALID", info

    candidates = _find_drop_in_candidates_recursive()
    info["drop_in_candidates"] = [str(p) for p in candidates]
    valid = [p for p in candidates if p.is_file() and _sha256_file(p) == EXPECTED_DROP_IN_SHA256]
    if not valid:
        return False, "REQUIRED_G0R4R3_TRANSPORT_INPUT_NOT_FOUND_OR_INVALID", info
    drop_in = valid[0]
    info["selected_drop_in"] = str(drop_in)
    info["install_method"] = "DROP_IN_ZIP_EXTRACT"
    try:
        with zipfile.ZipFile(drop_in, "r") as zf:
            names = {_norm(n) for n in zf.namelist()}
            if len(names) != len(zf.namelist()):
                return False, "DROP_IN_ZIP_CONTAINS_DUPLICATE_PATHS", info
            if names != set(DROP_IN_EXPECTED_MEMBERS):
                return False, "DROP_IN_ZIP_CONTENTS_UNEXPECTED", info
            for name in sorted(DROP_IN_EXPECTED_MEMBERS):
                target = ROOT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
    except zipfile.BadZipFile:
        return False, "DROP_IN_ZIP_UNREADABLE", info

    actual = _sha256_file(bundle_path) if bundle_path.is_file() else ""
    sidecar_ok, _ = _verify_sidecar(sidecar_path, bundle_path)
    info["inner_bundle_sha256"] = actual
    if actual != EXPECTED_BUNDLE_SHA256 or not sidecar_ok:
        return False, "INNER_BUNDLE_SHA256_OR_SIDECAR_MISMATCH", info
    return True, "", info


def verify_staged_git_blob_gate() -> Tuple[bool, Dict[str, Any]]:
    ok_base, baseline, msg = load_baseline_original_bytes()
    ok_review, review, msg2 = load_review_input_bytes()
    entries: List[Dict[str, Any]] = []
    all_ok = True
    if not ok_base or not ok_review:
        return False, {"error": msg or msg2, "entries": entries}
    for source_name, target_rel in BASELINE_VERBATIM_MAPPINGS:
        source_bytes = baseline[source_name]
        expected = _sha256_bytes(source_bytes)
        wt = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        staged_blob = read_index_bytes(target_rel)
        staged = _sha256_bytes(staged_blob) if staged_blob else ""
        match = expected == wt == staged and wt != ""
        if not match:
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "expected_sha256": expected,
                "working_tree_sha256": wt,
                "staged_git_blob_sha256": staged,
                "source_equals_worktree_equals_staged": match,
            }
        )
    for source_name, target_rel in REVIEW_INPUT_MAPPINGS:
        source_bytes = review[source_name]
        expected = _sha256_bytes(source_bytes)
        wt = _sha256_file(ROOT / target_rel) if (ROOT / target_rel).is_file() else ""
        staged_blob = read_index_bytes(target_rel)
        staged = _sha256_bytes(staged_blob) if staged_blob else ""
        match = expected == wt == staged and wt != ""
        if not match:
            all_ok = False
        entries.append(
            {
                "target_path": target_rel,
                "expected_sha256": expected,
                "working_tree_sha256": wt,
                "staged_git_blob_sha256": staged,
                "external_source_equals_worktree_equals_staged": match,
            }
        )
    return all_ok, {
        "phase": G0R4R3_PHASE_ID,
        "verification_status": "PASS" if all_ok else "FAIL",
        "entries": entries,
    }


def emit_g0r4r3_blocked(
    *,
    blocker: str,
    executed_step: str,
    extra: Optional[Dict[str, Any]] = None,
) -> int:
    extra = extra or {}
    dest = ROOT / G0R4R3_BLOCKED_DIR_REL
    dest.mkdir(parents=True, exist_ok=True)
    for existing in dest.iterdir():
        if existing.is_file():
            existing.unlink()
    branch = _run_git("branch", "--show-current")
    head = _run_git("rev-parse", "HEAD")
    git_status = _run_git("status", "--short", "--branch")
    discovery_path = doc_path("CODEX_G0R4R3_INPUT_DISCOVERY_REPORT.md")
    diagnostics: Dict[str, Any] = {
        "g0r4r3_status": "BLOCKED",
        "ready_for_external_g0r4r3_review": False,
        "blocker": blocker,
        "executed_step": executed_step,
        "phase": G0R4R3_PHASE_ID,
        "project_root": str(ROOT),
        "branch": branch,
        "head": head,
        "git_status": git_status,
        "g1_authorized": False,
        "operational_status": "BLOCKED_FOR_SAFETY",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "expected_drop_in_sha256": EXPECTED_DROP_IN_SHA256,
        "expected_bundle_sha256": EXPECTED_BUNDLE_SHA256,
        "expected_approval_sha256": EXPECTED_APPROVAL_SHA256,
        "baseline_expected_hashes": BASELINE_EXPECTED_TARGET_HASHES,
        "mandatory_audit_zip_paths": list(MANDATORY_AUDIT_ZIP_PATHS),
        "input_discovery_report": str(discovery_path.relative_to(ROOT)) if discovery_path.is_file() else "",
        **extra,
    }
    hash_lines = [
        f"blocker={blocker}",
        f"executed_step={executed_step}",
        f"project_root={ROOT}",
        f"branch={branch}",
        f"head={head}",
        f"expected_drop_in_sha256={EXPECTED_DROP_IN_SHA256}",
        f"expected_bundle_sha256={EXPECTED_BUNDLE_SHA256}",
        f"expected_approval_sha256={EXPECTED_APPROVAL_SHA256}",
    ]
    for rel, expected in BASELINE_EXPECTED_TARGET_HASHES.items():
        path = ROOT / rel
        actual = _sha256_file(path) if path.is_file() else "MISSING"
        hash_lines.append(f"baseline {rel} expected={expected} actual={actual}")
    for name in EXTRACTED_REQUIRED_FILES:
        path = _input_file(name)
        hash_lines.append(
            f"extracted {name} present={path.is_file()} sha256={_sha256_file(path) if path.is_file() else 'MISSING'}"
        )
    report_lines = [
        "# CODEX G0R4R3 Blocked Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"**BLOCKER:** `{blocker}`",
        f"**Executed step:** {executed_step}",
        "",
        f"PROJECT_ROOT: `{ROOT}`",
        f"Branch: `{branch}`",
        f"HEAD: `{head}`",
        "",
        "## Safety state",
        "",
        "G1_AUTHORIZED = NO",
        "OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY",
        f"AUTHORITATIVE_CHAMPION = {AUTHORITATIVE_CHAMPION}",
        "",
        "## Git status",
        "",
        "```text",
        git_status,
        "```",
        "",
        "## Diagnostics",
        "",
        "```json",
        json.dumps(diagnostics, indent=2),
        "```",
    ]
    (dest / "CODEX_G0R4R3_BLOCKED_REPORT.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    atomic_write_json(dest / "CODEX_G0R4R3_BLOCKED_DIAGNOSTICS.json", diagnostics)
    (dest / "CODEX_G0R4R3_RELEVANT_HASHES.txt").write_text("\n".join(hash_lines) + "\n", encoding="utf-8")
    if sys.platform == "win32":
        subprocess.run(["explorer", str(dest.resolve())], check=False)
    print(
        "\n".join(
            [
                "G0R4R3 Status: BLOCKED",
                "READY_FOR_EXTERNAL_G0R4R3_REVIEW = NO",
                "",
                f"BLOCKER:\n{blocker}",
                "",
                f"Executed Step:\n{executed_step}",
                "",
                f"Opened Diagnostic Folder:\n{dest.resolve()}",
                "",
                "Files To Upload To External Reviewer:",
                "- CODEX_G0R4R3_BLOCKED_REPORT.md",
                "- CODEX_G0R4R3_BLOCKED_DIAGNOSTICS.json",
                "- CODEX_G0R4R3_RELEVANT_HASHES.txt",
                "",
                "State:",
                f"- Authoritative Champion: {AUTHORITATIVE_CHAMPION}",
                "- Operational Status: BLOCKED_FOR_SAFETY",
                "- G1 Status: NOT_AUTHORIZED",
            ]
        )
    )
    return 1


def _deliver_review_submission_if_pass(*, ok: bool, verification: Dict[str, Any]) -> Optional[Path]:
    if not ok:
        return None
    filename_ok, filename_flags = _verify_final_output_filenames()
    attestation_phase_ok = False
    if G0R4R3_ATTESTATION.is_file():
        try:
            att = json.loads(G0R4R3_ATTESTATION.read_text(encoding="utf-8"))
            attestation_phase_ok = att.get("phase") == G0R4R3_PHASE_ID
        except json.JSONDecodeError:
            attestation_phase_ok = False
    if not filename_ok or not attestation_phase_ok:
        print(
            json.dumps(
                {
                    "g0r4r3_status": "BLOCKED",
                    "blocker": "WRONG_PHASE_OR_WRONG_OUTPUT_FILENAME",
                    "FINAL_ATTESTATION_PHASE_IS_G0R4R3": attestation_phase_ok,
                    **filename_flags,
                },
                indent=2,
            )
        )
        return None
    folder = deliver_g0r4r3_outgoing_submission(
        root=ROOT,
        zip_path=G0R4R3_ZIP,
        sidecar_path=G0R4R3_SHA,
        attestation_path=G0R4R3_ATTESTATION,
        verify_report_path=G0R4R3_VERIFY_REPORT,
    )
    print(json.dumps({"review_submission_folder": str(folder), "OUTPUT_FOLDER_OPEN_REQUESTED": "YES"}, indent=2))
    return folder


def main() -> int:
    start_head = _run_git("rev-parse", "HEAD")
    branch = _run_git("branch", "--show-current")
    start_git_status = _run_git("status", "--short", "--branch")

    if _run_git("log", "-1", "--format=%s") == G0R4R3_COMMIT_MSG:
        commit = _run_git("rev-parse", "HEAD")
        include = build_zip_include_list()
        blob_ok, blob_payload, source_map = verify_final_git_blob_gate(commit)
        if not blob_ok:
            return emit_g0r4r3_blocked(
                blocker="FINAL_GIT_BLOB_VERBATIM_GATE_FAILED",
                executed_step="resume_final_git_blob_gate",
                extra=blob_payload,
            )
        zip_digest, missing, zip_bytes = build_exact_byte_zip(commit, include)
        if missing:
            return emit_g0r4r3_blocked(
                blocker="FINAL_ZIP_VERBATIM_OR_AUDIT_COMPLETENESS_GATE_FAILED",
                executed_step="resume_zip_build_missing_entries",
                extra={"zip_missing": missing},
            )
        zip_verbatim_ok, zip_verbatim_payload = verify_final_zip_entry_verbatim_gate(
            commit=commit, zip_bytes=zip_bytes, sources=source_map
        )
        if not zip_verbatim_ok:
            return emit_g0r4r3_blocked(
                blocker="FINAL_ZIP_VERBATIM_OR_AUDIT_COMPLETENESS_GATE_FAILED",
                executed_step="resume_final_zip_entry_verbatim_gate",
                extra=zip_verbatim_payload,
            )
        G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
        G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\n", encoding="utf-8")
        ok, verification = verify_package_integrity(commit=commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
        write_detached_attestation(
            commit=commit,
            zip_digest=zip_digest,
            zip_bytes=zip_bytes,
            verification=verification,
            blob_gate=blob_payload,
            zip_gate=zip_verbatim_payload,
        )
        write_verification_report(verification, commit=commit, blob_gate=blob_payload, zip_gate=zip_verbatim_payload)
        ok_pass = ok and not verification.get("mismatches") and zip_verbatim_ok and blob_ok
        _deliver_review_submission_if_pass(ok=ok_pass, verification=verification)
        print(json.dumps({"g0r4r3_status": "PASS" if ok_pass else "BLOCKED", **verification}, indent=2))
        return 0 if ok_pass else emit_g0r4r3_blocked(
            blocker="FINAL_G0R4R3_INTEGRITY_OR_SAFETY_GATE_FAILED",
            executed_step="resume_final_integrity_gate",
            extra=verification,
        )

    predecessors = _detect_old_g0r4r_submission_artifacts()
    transport_ok, transport_msg, transport_info = discover_and_install_g0r4r3_transport()
    transport_info["transport_gate_passed"] = transport_ok
    if not transport_ok:
        write_input_discovery_report(
            discovery={"all_found": False, "found_files": {}, "missing_files": [], "found_file_count": 0, "required_file_count": len(REQUIRED_INPUT_FILES), "inner_required_found": 0, "inner_required_total": len(EXTRACTED_REQUIRED_FILES), "input_directory_treated_as_immutable_external_source": True},
            branch=branch,
            head=start_head,
            predecessors=predecessors,
            transport=transport_info,
        )
        return emit_g0r4r3_blocked(
            blocker=transport_msg or "REQUIRED_G0R4R3_TRANSPORT_INPUT_NOT_FOUND_OR_INVALID",
            executed_step="transport_discovery_and_install",
            extra=transport_info,
        )

    discovery = discover_required_inputs()
    write_input_discovery_report(
        discovery=discovery,
        branch=branch,
        head=start_head,
        predecessors=predecessors,
        transport=transport_info,
    )

    if not discovery["all_found"]:
        bundle = _input_file(BUNDLE_ZIP_NAME)
        sidecar = _input_file(BUNDLE_SIDECAR_NAME)
        if bundle.is_file() and sidecar.is_file():
            extract_ok, extract_msg = ensure_input_directory_bundle_extracted()
            if extract_ok:
                discovery = discover_required_inputs()
                write_input_discovery_report(
                    discovery=discovery,
                    branch=branch,
                    head=start_head,
                    predecessors=predecessors,
                )

    if not discovery["all_found"]:
        return emit_g0r4r3_blocked(
            blocker="REQUIRED_EXTRACTED_G0R4R3_INPUT_MISSING",
            executed_step="extracted_input_discovery",
            extra={
                "required_input_directory": INPUT_DIR_REL,
                "required_files_found": discovery["found_file_count"],
                "required_files_total": discovery["required_file_count"],
                "missing_files": discovery["missing_files"],
                "found_files": list(discovery["found_files"].values()),
            },
        )

    bundle_ready_ok, bundle_ready_msg = ensure_input_directory_bundle_extracted()
    if not bundle_ready_ok:
        return emit_g0r4r3_blocked(
            blocker="REQUIRED_EXTRACTED_G0R4R3_INPUT_MISSING",
            executed_step="inner_bundle_extract",
            extra={"detail": bundle_ready_msg},
        )

    bundle_ok, bundle_payload = verify_input_bundle()
    atomic_write_json(doc_path("CODEX_G0R4R3_EXTERNAL_INPUT_HASH_VERIFICATION.json"), bundle_payload)
    if not bundle_ok:
        return emit_g0r4r3_blocked(
            blocker="EXTERNAL_INPUT_BUNDLE_OR_FILE_HASH_MISMATCH",
            executed_step="input_bundle_hash_verification",
            extra=bundle_payload,
        )

    if branch not in ALLOWED_BRANCHES:
        return emit_g0r4r3_blocked(
            blocker="UNEXPECTED_BRANCH",
            executed_step="branch_validation",
            extra={"detail": branch},
        )

    approval_ok, approval_payload = verify_external_remediation_approval()
    atomic_write_json(doc_path("CODEX_G0R4R3_AUTHORIZATION_VERIFICATION.json"), approval_payload)
    if not approval_ok:
        return emit_g0r4r3_blocked(
            blocker="EXTERNAL_G0R4R3_APPROVAL_NOT_VERIFIED",
            executed_step="authorization_verification",
            extra=approval_payload,
        )

    write_preflight(start_head, branch)
    ga_ok, ga_msg = ensure_gitattributes_byte_preservation()
    if not ga_ok:
        return emit_g0r4r3_blocked(blocker="GIT_ATTRIBUTE_BYTE_PRESERVATION_NOT_EFFECTIVE", executed_step="gitattributes_update", extra={"detail": ga_msg})
    ok_apply, apply_msg = apply_g0r4r3_replacements()
    if not ok_apply:
        return emit_g0r4r3_blocked(
            blocker="AUTHORITATIVE_BASELINE_WORKTREE_BYTES_NOT_VERBATIM",
            executed_step="binary_baseline_and_audit_replacement",
            extra={"detail": apply_msg},
        )
    attr_ok, attr_payload = verify_git_attributes_effective()
    atomic_write_json(doc_path("CODEX_G0R4R3_GIT_ATTRIBUTE_BYTE_PRESERVATION_VERIFICATION.json"), attr_payload)
    if not attr_ok:
        return emit_g0r4r3_blocked(
            blocker="GIT_ATTRIBUTE_BYTE_PRESERVATION_NOT_EFFECTIVE",
            executed_step="git_check_attr_verification",
            extra=attr_payload,
        )
    wt_ok, wt_msg = verify_worktree_verbatim_before_commit()
    write_expected_verbatim_inputs(worktree_ok=wt_ok)
    if not wt_ok:
        return emit_g0r4r3_blocked(
            blocker="REQUIRED_AUDIT_INPUT_WORKTREE_BYTES_NOT_VERBATIM" if "audit" in wt_msg.lower() else "AUTHORITATIVE_BASELINE_WORKTREE_BYTES_NOT_VERBATIM",
            executed_step="worktree_verbatim_verification",
            extra={"detail": wt_msg},
        )

    include = build_zip_include_list()
    include_set = set(include)
    v5r_paths = sorted(load_v5r_baseline())

    atomic_write_json(doc_path("CODEX_G0R4R3_PROTECTED_HASHES_BEFORE.json"), protected_hash_snapshot(v5r_paths))
    comparison, restoration_ok = build_comparison(include_set)
    atomic_write_json(
        doc_path("CODEX_G0R4R3_V5R_BASELINE_COMPARISON.json"),
        {
            "previous_pre_g0r_drift_detected": True,
            "previously_drifted_paths": list(PREVIOUSLY_DRIFTED_PATHS),
            "entries": comparison,
        },
    )
    atomic_write_json(doc_path("CODEX_G0R4R3_PROTECTED_HASHES_AFTER.json"), protected_hash_snapshot(v5r_paths))

    update_phase_catalog()
    update_review_registry()
    write_authorization_artifacts(ROOT)
    write_g0r4r3_review_snapshot(ROOT)
    write_change_manifest(list(AUTHORIZED_G0R4R3_COMMIT_PATHS))
    write_git_status(branch=branch, start_head=start_head)
    write_g0r4r3_template()
    update_next_cursor_prompt()

    test_rc, _ = run_tests()
    write_report(test_rc=test_rc, restoration_ok=restoration_ok)
    if test_rc != 0 or not restoration_ok:
        return emit_g0r4r3_blocked(
            blocker="FINAL_G0R4R3_INTEGRITY_OR_SAFETY_GATE_FAILED",
            executed_step="pre_commit_tests_or_baseline",
            extra={"test_rc": test_rc, "restoration_ok": restoration_ok},
        )

    baseline = verified_baseline_untracked_paths()
    authorized = set(AUTHORIZED_G0R4R3_COMMIT_PATHS) | set(baseline)
    ok_drift, unexpected = verify_allowlist_drift(authorized)
    if not ok_drift:
        return emit_g0r4r3_blocked(
            blocker="UNEXPECTED_NON_ALLOWLIST_WORKTREE_DRIFT",
            executed_step="allowlist_drift_verification",
            extra={"unexpected": sorted(unexpected)},
        )

    ok, final_commit, staged_paths = commit_g0r4r3(include, start_head)
    if not ok:
        return emit_g0r4r3_blocked(
            blocker=final_commit if final_commit == "STAGED_GIT_BLOB_VERBATIM_GATE_FAILED" else "COMMIT_FAILED",
            executed_step="final_input_commit",
            extra={"detail": final_commit, "staged_paths": staged_paths},
        )
    if final_commit == start_head:
        return emit_g0r4r3_blocked(
            blocker="COMMIT_FAILED",
            executed_step="final_input_commit",
            extra={"detail": "commit unchanged", "staged_paths": staged_paths},
        )

    if not worktree_clean_for_packaging():
        return emit_g0r4r3_blocked(
            blocker="UNEXPECTED_NON_ALLOWLIST_WORKTREE_DRIFT",
            executed_step="worktree_clean_for_packaging",
        )

    blob_ok, blob_payload, source_map = verify_final_git_blob_gate(final_commit)
    if not blob_ok:
        return emit_g0r4r3_blocked(
            blocker="FINAL_GIT_BLOB_VERBATIM_GATE_FAILED",
            executed_step="final_git_blob_gate",
            extra=blob_payload,
        )

    zip_digest, missing, zip_bytes = build_exact_byte_zip(final_commit, include)
    if missing:
        return emit_g0r4r3_blocked(
            blocker="FINAL_ZIP_VERBATIM_OR_AUDIT_COMPLETENESS_GATE_FAILED",
            executed_step="exact_byte_zip_build",
            extra={"zip_missing": missing},
        )

    zip_verbatim_ok, zip_verbatim_payload = verify_final_zip_entry_verbatim_gate(
        commit=final_commit, zip_bytes=zip_bytes, sources=source_map
    )
    if not zip_verbatim_ok:
        return emit_g0r4r3_blocked(
            blocker="FINAL_ZIP_VERBATIM_OR_AUDIT_COMPLETENESS_GATE_FAILED",
            executed_step="final_zip_entry_verbatim_gate",
            extra=zip_verbatim_payload,
        )

    G0R4R3_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R4R3_SHA.write_text(f"{zip_digest}  {G0R4R3_ZIP.name}\n", encoding="utf-8")
    ok, verification = verify_package_integrity(commit=final_commit, zip_bytes=zip_bytes, zip_digest=zip_digest)
    write_detached_attestation(
        commit=final_commit,
        zip_digest=zip_digest,
        zip_bytes=zip_bytes,
        verification=verification,
        blob_gate=blob_payload,
        zip_gate=zip_verbatim_payload,
    )
    write_verification_report(
        verification,
        commit=final_commit,
        blob_gate=blob_payload,
        zip_gate=zip_verbatim_payload,
    )

    ok_pass = ok and not verification.get("mismatches") and zip_verbatim_ok and blob_ok
    delivered = _deliver_review_submission_if_pass(ok=ok_pass, verification=verification)
    if ok_pass and delivered is None:
        return emit_g0r4r3_blocked(
            blocker="FINAL_G0R4R3_INTEGRITY_OR_SAFETY_GATE_FAILED",
            executed_step="deliver_review_submission",
        )
    if not ok_pass:
        return emit_g0r4r3_blocked(
            blocker="FINAL_G0R4R3_INTEGRITY_OR_SAFETY_GATE_FAILED",
            executed_step="final_integrity_verification",
            extra=verification,
        )
    print(
        "\n".join(
            [
                "G0R4R3 Status: PASS",
                "READY_FOR_EXTERNAL_G0R4R3_REVIEW = YES",
                "",
                f"Executed Phase:\n{G0R4R3_PHASE_ID}",
                "",
                f"Final Input Commit:\n{final_commit}",
                "",
                "Input Bundle Verified: YES",
                "Authorization Verified: YES",
                "Git Byte Preservation Effective: YES",
                "",
                f"Opened Output Folder:\n{(ROOT / OUTGOING_DIR_REL).resolve()}",
                "",
                "Files To Upload To External Reviewer:",
                "- codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip",
                "- codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip.sha256",
                "- codex_g0r4r3_detached_submission_attestation.json",
                "- codex_g0r4r3_detached_package_verification_report.md",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
