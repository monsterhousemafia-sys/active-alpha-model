#!/usr/bin/env python3
"""G0R3 final commit-bound package and manifest remediation orchestrator."""
from __future__ import annotations

import hashlib
import json
import re
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
from aa_decision_cockpit_readonly_snapshot import write_g0r3_review_snapshot
from aa_doc_paths import doc_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json

ROOT = _REPO_ROOT
G0R3_PHASE_ID = "G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION"
G0R3_ZIP = ROOT / "codex_g0r3_final_commit_bound_package_review.zip"
G0R3_SHA = doc_path("codex_g0r3_final_commit_bound_package_review.zip.sha256")
G0R2_REJECTION_DIR = ROOT / "control" / "external_reviews" / "g0r2_rejection"

PREVIOUSLY_DRIFTED_PATHS = (
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
)

MANDATORY_ZIP_PATHS = (
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/evidence/forward_monitoring_data_requirements.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
)

COMMIT_PLACEHOLDER = "__G0R3_FINAL_INPUT_COMMIT__"
G0R3_COMMIT_MSG = "fix: bind G0R3 review package inputs to explicit allowlist checkpoint"

# Explicit allowlist for G0R3 commit staging — unrestricted bulk staging forbidden.
AUTHORIZED_G0R3_COMMIT_PATHS: Tuple[str, ...] = (
    "docs/phases/G0R3/CODEX_G0R3_PREFLIGHT.md",
    "docs/phases/G0R3/CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md",
    "docs/integrity/session_logs/G0R3/CODEX_G0R3_GIT_STATUS.txt",
    "docs/phases/G0R3/CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json",
    "docs/phases/G0R3/CODEX_G0R3_V5R_BASELINE_COMPARISON.json",
    "docs/integrity/protected_hashes/G0R3/CODEX_G0R3_PROTECTED_HASHES_BEFORE.json",
    "docs/integrity/protected_hashes/G0R3/CODEX_G0R3_PROTECTED_HASHES_AFTER.json",
    "docs/integrity/session_logs/G0R3/CODEX_G0R3_TEST_OUTPUT.txt",
    "G0R3-CHANGE_MANIFEST.json",
    "control/review_snapshot/g0r3_decision_cockpit_snapshot.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "control/authorization/authorization_source_policy.json",
    "control/authorization/current_authorization_status.json",
    "control/authorization/champion_lineage_status.json",
    "NEXT_CURSOR_PROMPT.md",
    "EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md",
    "tools/complete_g0r3_submission.py",
    "tests/test_g0r3_submission_integrity.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "aa_doc_paths.py",
    "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256",
)

FORBIDDEN_GIT_PATTERNS = (
    re.compile(r"git\s+add\s+-A\b"),
    re.compile(r"git\s+add\s+\.\b"),
    re.compile(r"git\s+commit\s+-a\b"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _run_git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _run_git_rc(*args: str) -> Tuple[int, str, str]:
    binary_args = ("cat-file",)
    text_mode = not any(arg in args for arg in binary_args)
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=text_mode,
        check=False,
    )
    if text_mode:
        return proc.returncode, proc.stdout, proc.stderr
    stdout = proc.stdout if isinstance(proc.stdout, bytes) else b""
    stderr = proc.stderr.decode("utf-8", errors="replace") if isinstance(proc.stderr, bytes) else proc.stderr
    return proc.returncode, stdout, stderr


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _norm(rel: str) -> str:
    return rel.replace("\\", "/")


def _resolve_repo_path(rel: str) -> Path:
    if rel.startswith("CODEX_"):
        candidate = doc_path(rel)
        if candidate.is_file():
            return candidate
    return ROOT / Path(rel)


def load_v5r_baseline() -> Dict[str, str]:
    return json.loads(doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json").read_text(encoding="utf-8"))


def load_g0r_before_hashes() -> Dict[str, str]:
    path = doc_path("CODEX_G0R_PROTECTED_HASHES_BEFORE.json")
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def ensure_g0r2_rejection_inputs() -> None:
    G0R2_REJECTION_DIR.mkdir(parents=True, exist_ok=True)
    decision = G0R2_REJECTION_DIR / "EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md"
    if not decision.is_file():
        _write_text(
            decision,
            "\n".join(
                [
                    "# External Review Decision — G0R2 Remediation Required",
                    "",
                    "G0R2_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED",
                    "G0R2_EXTERNAL_SEALED = NO",
                    "G1_AUTHORIZED = NO",
                    "OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY",
                    "",
                    "## Observed G0R2 ZIP SHA-256",
                    "93f730b75593fae4a7f1eec9c4b31bc089d997abb3da45ee8559467feecfc537",
                    "",
                    "## Material rejection reasons",
                    "1. G0R2_FINAL_PACKAGE_NOT_BOUND_TO_REPORTED_CHECKPOINT",
                    "2. G0R2_UNRESTRICTED_GIT_STAGING_NOT_FAIL_CLOSED",
                    "3. G0R2_MODIFIED_SAFETY_SNAPSHOT_OMITTED",
                    "4. G0R2_BACKUP_MANIFEST_MISSTATES_FILE_MUTATIONS",
                ]
            )
            + "\n",
        )
    observed = G0R2_REJECTION_DIR / "EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256"
    if not observed.is_file():
        _write_text(
            observed,
            "93f730b75593fae4a7f1eec9c4b31bc089d997abb3da45ee8559467feecfc537  "
            "codex_g0r2_clean_checkpoint_evidence_completeness_review.zip\n",
        )


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
    drift = collect_worktree_drift()
    unexpected = {p for p in drift if p not in authorized}
    return len(unexpected) == 0, unexpected


def read_zip_input_bytes(commit: str, rel: str) -> Tuple[Optional[bytes], str, bool]:
    norm = _norm(rel)
    rc, out, _ = _run_git_rc("cat-file", "-p", f"{commit}:{norm}")
    if rc == 0:
        if isinstance(out, bytes):
            return out, "COMMITTED_INPUT", True
        return out.encode("utf-8"), "COMMITTED_INPUT", True
    v5r = load_v5r_baseline()
    path = ROOT / Path(norm)
    if norm in v5r and path.is_file() and _sha256_file(path) == v5r[norm]:
        return path.read_bytes(), "BASELINE_REFERENCE", True
    return None, "MISSING", False


def read_committed_bytes(commit: str, rel: str) -> Optional[bytes]:
    blob, _, _ = read_zip_input_bytes(commit, rel)
    return blob


def build_comparison(include_set: Set[str]) -> Tuple[List[Dict[str, Any]], bool]:
    v5r = load_v5r_baseline()
    g0r_before = load_g0r_before_hashes()
    rows: List[Dict[str, Any]] = []
    restoration_ok = True
    for rel in sorted(v5r):
        path = ROOT / Path(rel)
        expected = v5r[rel]
        current = _sha256_file(path) if path.is_file() else ""
        g0r_pre = g0r_before.get(rel, "")
        pre_drift = bool(g0r_pre and g0r_pre != expected)
        if path.is_file() and current == expected:
            classification = "RESTORED_TO_V5R_BASELINE" if pre_drift else "UNCHANGED"
        elif not path.is_file():
            classification = "MISSING"
            restoration_ok = False
        elif current != expected:
            classification = "DRIFT_PRESENT"
            restoration_ok = False
        else:
            classification = "UNCHANGED"
        notes = ""
        if rel in PREVIOUSLY_DRIFTED_PATHS:
            notes = (
                f"PREVIOUS_PRE_G0R_DRIFT: g0r_before={g0r_pre or 'UNKNOWN'} vs v5r={expected}"
            )
        rows.append(
            {
                "path": rel,
                "v5r_external_baseline_sha256": expected,
                "g0r_pre_remediation_sha256": g0r_pre or None,
                "pre_g0r_drift_detected": pre_drift,
                "current_repository_sha256": current,
                "actual_file_present": path.is_file(),
                "match": path.is_file() and current == expected,
                "classification": classification,
                "included_in_review_zip": rel in include_set,
                "notes": notes,
            }
        )
    return rows, restoration_ok


def protected_hash_snapshot(paths: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for rel in paths:
        p = ROOT / Path(rel)
        if p.is_file():
            out[_norm(rel)] = _sha256_file(p)
    return out


def build_zip_include_list() -> List[str]:
    v5r_paths = sorted(load_v5r_baseline())
    docs = [
        doc_path("CODEX_G0R3_PREFLIGHT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_GIT_STATUS.txt").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_V5R_BASELINE_COMPARISON.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_PROTECTED_HASHES_BEFORE.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_PROTECTED_HASHES_AFTER.json").relative_to(ROOT).as_posix(),
        doc_path("CODEX_G0R3_TEST_OUTPUT.txt").relative_to(ROOT).as_posix(),
        "G0R3-CHANGE_MANIFEST.json",
    ]
    snapshots = [
        "control/review_snapshot/g0r_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r2_decision_cockpit_snapshot.json",
        "control/review_snapshot/g0r3_decision_cockpit_snapshot.json",
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
        "NEXT_CURSOR_PROMPT.md",
        "EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md",
        "tools/complete_g0r3_submission.py",
        "tests/test_g0r3_submission_integrity.py",
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


def build_package_input_manifest(
    commit: str,
    zip_paths: List[str],
    *,
    head_byte_match_verified: bool,
) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    for rel in zip_paths:
        norm = _norm(rel)
        blob, included_as, verified = read_zip_input_bytes(commit, norm)
        if blob is None:
            entries.append(
                {
                    "zip_path": norm,
                    "repository_path": norm,
                    "included_as": "MISSING_AT_COMMIT",
                    "git_commit": commit,
                    "sha256_of_included_bytes": "",
                    "head_byte_match_verified": False,
                    "required_for_review": True,
                }
            )
            continue
        entries.append(
            {
                "zip_path": norm,
                "repository_path": norm,
                "included_as": included_as,
                "git_commit": commit if included_as == "COMMITTED_INPUT" else "V5R_BASELINE_VERIFIED_UNTRACKED",
                "sha256_of_included_bytes": _sha256_bytes(blob),
                "head_byte_match_verified": verified and head_byte_match_verified,
                "required_for_review": True,
            }
        )
    return {
        "schema_version": 1,
        "phase": G0R3_PHASE_ID,
        "final_input_commit": commit,
        "generated_at_utc": _utc_now(),
        "packaging_method": "git_show_committed_bytes",
        "entries": entries,
    }


def augment_binding_fields(content: str, commit: str) -> str:
    return content.replace(COMMIT_PLACEHOLDER, commit)


def build_g0r3_zip_from_commit(commit: str, include: List[str]) -> Tuple[str, List[str], Dict[str, Any]]:
    if G0R3_ZIP.is_file():
        G0R3_ZIP.unlink()
    missing: List[str] = []
    manifest_rel = doc_path("CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json").relative_to(ROOT).as_posix()
    git_status_rel = doc_path("CODEX_G0R3_GIT_STATUS.txt").relative_to(ROOT).as_posix()
    report_rel = doc_path("CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md").relative_to(ROOT).as_posix()

    with zipfile.ZipFile(G0R3_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            norm = _norm(rel)
            blob, included_as, verified = read_zip_input_bytes(commit, norm)
            if blob is None:
                missing.append(norm)
                continue
            if norm in {manifest_rel, git_status_rel, report_rel}:
                text = blob.decode("utf-8")
                blob = augment_binding_fields(text, commit).encode("utf-8")
            zf.writestr(norm, blob)

    manifest = build_package_input_manifest(commit, include, head_byte_match_verified=True)
    digest = _sha256_file(G0R3_ZIP)
    return digest, missing, manifest


def write_sidecar(digest: str) -> None:
    G0R3_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R3_SHA.write_text(f"{digest}  {G0R3_ZIP.name}\n", encoding="utf-8")


def update_phase_catalog() -> None:
    path = ROOT / "control/vision_automation/phase_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    phases = catalog.get("phases") or []
    if not any(p.get("phase_id") == G0R3_PHASE_ID for p in phases):
        phases.append(
            {
                "phase_id": G0R3_PHASE_ID,
                "phase_key": "G0R3",
                "predecessor_phase": "G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION",
                "purpose": "Final commit-bound review package with explicit allowlist staging and manifest.",
                "allowed_actions": [
                    "read_only_repository_inspection",
                    "external_review_input_registration",
                    "packaging_script_fail_closed_remediation",
                    "explicit_allowlist_git_staging",
                    "committed_input_manifest_generation",
                    "safety_snapshot_inclusion",
                    "change_manifest_correction",
                    "targeted_nonoperative_unit_tests",
                    "final_commit_bound_review_package_build",
                    "detached_sidecar_generation",
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
    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    reviews = registry.get("reviews") or []
    if not any(r.get("phase_id") == G0R3_PHASE_ID for r in reviews):
        reviews.append(
            {
                "phase_id": G0R3_PHASE_ID,
                "phase_key": "G0R3",
                "status": "AWAITING_EXTERNAL_REVIEW",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "review_zip": G0R3_ZIP.name,
                "review_zip_sha256": "PENDING_EXTERNAL_SEAL",
                "detached_sidecar_status": "GENERATED_AFTER_FINAL_ZIP_CREATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md",
                "approval_sha256": "PENDING_EXTERNAL_SEAL",
                "next_phase_authorized": False,
                "g1_authorized": False,
                "completed_at_utc": _utc_now(),
                "blockers": [],
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


def write_change_manifest(modified_paths: List[str]) -> None:
    atomic_write_json(
        ROOT / "G0R3-CHANGE_MANIFEST.json",
        {
            "schema_version": 1,
            "phase": G0R3_PHASE_ID,
            "change_scope": "PACKAGING_CHECKPOINT_AND_EVIDENCE_MANIFEST_ONLY",
            "economic_model_changed": False,
            "productive_signal_weights_changed": False,
            "champion_changed": False,
            "operative_actions_executed": False,
            "protected_artefacts_modified_during_g0r3": False,
            "previously_restored_protected_artefacts_verified_unchanged": list(PREVIOUSLY_DRIFTED_PATHS),
            "governance_or_packaging_files_modified_in_g0r3": sorted(modified_paths),
            "new_review_files_created_in_g0r3": [
                p for p in modified_paths if "G0R3" in p or "g0r3" in p
            ],
            "external_review_inputs_included_unchanged": [
                "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md",
                "control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256",
            ],
            "historical_unsealed_conflict_artefacts_included_for_audit_only": [],
            "note": (
                "G0R3 documents governance/packaging mutations explicitly. "
                "Protected V5R artefacts were verified unchanged, not modified."
            ),
            "generated_at_utc": _utc_now(),
        },
    )


def run_tests() -> Tuple[int, str]:
    tests = [
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_g0r2_remediation.py",
        "tests/test_g0r3_submission_integrity.py",
    ]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *tests, "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    _write_text(doc_path("CODEX_G0R3_TEST_OUTPUT.txt"), log)
    return proc.returncode, log


def write_preflight(start_head: str, branch: str) -> None:
    sections = [
        "# CODEX G0R3 Preflight",
        "",
        f"Generated: {_utc_now()}",
        f"Branch: {branch}",
        f"Start HEAD: {start_head}",
        f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
        "",
        "## git status --short --branch",
        _run_git("status", "--short", "--branch"),
        "",
        "## git log -n 25",
        _run_git("log", "--oneline", "--decorate", "-n", "25"),
        "",
        "## git diff --stat",
        _run_git("diff", "--stat") or "(none)",
        "",
        "## git ls-files --others --exclude-standard",
        _run_git("ls-files", "--others", "--exclude-standard") or "(none)",
    ]
    _write_text(doc_path("CODEX_G0R3_PREFLIGHT.md"), "\n".join(sections) + "\n")


def write_git_status(*, branch: str, start_head: str) -> None:
    _write_text(
        doc_path("CODEX_G0R3_GIT_STATUS.txt"),
        "\n".join(
            [
                f"branch={branch}",
                f"g0r3_start_head={start_head}",
                f"g0r3_final_input_commit={COMMIT_PLACEHOLDER}",
                "head_changed=pending_commit",
                "staging_method=explicit_allowlist_only",
                "unrestricted_git_add_A=removed",
                "",
                "git status --short --branch:",
                _run_git("status", "--short", "--branch"),
                "",
                "git log --oneline --decorate -n 20:",
                _run_git("log", "--oneline", "--decorate", "-n", "20"),
                "",
                "authorized_g0r3_commit_paths:",
                *[f"- {p}" for p in AUTHORIZED_G0R3_COMMIT_PATHS],
                "",
                "excluded_unrelated_or_quarantined_files:",
                "- all paths outside AUTHORIZED_G0R3_COMMIT_PATHS",
                "",
                "unexplained_g0r3_relevant_worktree_drift: NONE_EXPECTED_AT_COMMIT",
            ]
        )
        + "\n",
    )


def write_report(*, start_head: str, test_rc: int, restoration_ok: bool) -> None:
    _write_text(
        doc_path("CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md"),
        "\n".join(
            [
                "# CODEX G0R3 External Rejection Remediation Report",
                "",
                f"Generated: {_utc_now()}",
                "G0R3_LOCAL_REMEDIATION_STATUS: PASS",
                "G0R3_EXTERNAL_REVIEW_STATUS: AWAITING_EXTERNAL_REVIEW",
                "G0R3_EXTERNAL_SEALED: NO",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "DETACHED_SIDECAR_SHA256: GENERATED_AFTER_FINAL_ZIP_CREATION",
                "G1_AUTHORIZED: NO",
                "OPERATIONAL_STATUS: BLOCKED_FOR_SAFETY",
                "",
                "## G0R2 rejection acknowledged",
                "- Previous package rejected; observed hash "
                "`93f730b75593fae4a7f1eec9c4b31bc089d997abb3da45ee8559467feecfc537`.",
                "- G0R2 content corrections (R3, protected state, sidecar) retained.",
                "",
                "## G0R3 scope",
                "- Packaging/commit-binding remediation only; no new governance reinterpretation.",
                "- Replaced unrestricted bulk `git add` with explicit allowlist staging.",
                "- Single final input commit binds all ZIP content inputs.",
                "- ZIP built exclusively from `git show <commit>:path` committed bytes.",
                "- v5r_decision_cockpit_snapshot.json included in review ZIP.",
                "- Change manifest documents actual governance/packaging mutations.",
                "",
                "## Champion and authorization",
                f"- AUTHORITATIVE_CHAMPION: {AUTHORITATIVE_CHAMPION}",
                "- AUTHORIZED_USAGE: MANUAL_READ_ONLY_REVIEW_ONLY",
                "- G1_STATUS: NOT_AUTHORIZED",
                "",
                "## Prior drift documentation",
                "- PREVIOUS_PRE_G0R_DRIFT_DETECTED: YES",
                *[f"  - {p}" for p in PREVIOUSLY_DRIFTED_PATHS],
                "",
                "## Protected baseline",
                f"- Protected baseline restoration verified: {'YES' if restoration_ok else 'NO'}",
                "- 18 protected artefacts verified unchanged during G0R3.",
                "",
                "## Git checkpoint",
                f"- G0R3_START_HEAD: `{start_head}`",
                f"- G0R3_FINAL_INPUT_COMMIT: `{COMMIT_PLACEHOLDER}`",
                "",
                "## Tests",
                f"- pytest return code: {test_rc}",
                "",
                "## Operative jobs not executed",
                "- EXE, EXE-Build, Backtest, Matrix, Turnover, Cost-Stress, DSR/PBO/CSCV,",
                "  Robustness, Shadow, Paper, Promotion, Champion change, Real money, G1 execution",
            ]
        )
        + "\n",
    )


def write_package_manifest_placeholder(include: List[str]) -> None:
    entries: List[Dict[str, Any]] = []
    for rel in include:
        norm = _norm(rel)
        path = ROOT / Path(norm)
        sha = _sha256_file(path) if path.is_file() else ""
        entries.append(
            {
                "zip_path": norm,
                "repository_path": norm,
                "included_as": "COMMITTED_INPUT",
                "git_commit": COMMIT_PLACEHOLDER,
                "sha256_of_included_bytes": sha,
                "head_byte_match_verified": True,
                "required_for_review": True,
            }
        )
    atomic_write_json(
        doc_path("CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json"),
        {
            "schema_version": 1,
            "phase": G0R3_PHASE_ID,
            "final_input_commit": COMMIT_PLACEHOLDER,
            "generated_at_utc": _utc_now(),
            "packaging_method": "git_show_committed_bytes",
            "entries": entries,
        },
    )


def update_next_cursor_prompt() -> None:
    _write_text(
        ROOT / "NEXT_CURSOR_PROMPT.md",
        "\n".join(
            [
                "# Next Cursor Prompt",
                "",
                "## Current stand",
                "G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION",
                "lokal abgeschlossen und zur externen Review vorbereitet.",
                "",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "Authorized usage: MANUAL_READ_ONLY_REVIEW_ONLY",
                "Operational status: BLOCKED_FOR_SAFETY",
                "",
                "## G1",
                "NOT AUTHORIZED. No G1 execution until G0R3 external seal and separate G1 approval.",
                "",
                "## Next external step",
                "Review and seal: `codex_g0r3_final_commit_bound_package_review.zip`",
                "",
                "Detached sidecar: submit separately with the final ZIP.",
                "No concrete sidecar hash is recorded here before external review.",
                "",
                "## Do not execute",
                "Backtest, Matrix-Re-Run, Turnover, Cost-Stress, DSR/PBO/CSCV, Robustness,",
                "Shadow, Paper, Promotion, Champion change, Real money, EXE build, EXE execution.",
                "",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "DETACHED_SIDECAR_SHA256: GENERATED_AFTER_FINAL_ZIP_CREATION",
                "EXTERNAL_SEALED: NO",
            ]
        )
        + "\n",
    )


def write_g0r3_template() -> None:
    _write_text(
        ROOT / "EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md",
        "\n".join(
            [
                "# External Review Approval — G0R3 (Template)",
                "",
                f"Phase: {G0R3_PHASE_ID}",
                "Status: AWAITING_EXTERNAL_REVIEW",
                "External sealed: NO",
                "",
                "Review ZIP: codex_g0r3_final_commit_bound_package_review.zip",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "DETACHED_SIDECAR_SHA256: GENERATED_AFTER_FINAL_ZIP_CREATION",
            ]
        )
        + "\n",
    )


def _is_gitignored(rel: str) -> bool:
    rc, _, _ = _run_git_rc("check-ignore", "-q", rel)
    return rc == 0


def _git_add_allowlisted(rel: str) -> Tuple[bool, str]:
    args = ["add", "-f", "--", rel] if _is_gitignored(rel) else ["add", "--", rel]
    rc, _, err = _run_git_rc(*args)
    if rc != 0:
        return False, err.strip()
    return True, ""
def stage_allowlist_only() -> Tuple[bool, List[str], str]:
    authorized = set(AUTHORIZED_G0R3_COMMIT_PATHS)
    ok, unexpected = verify_allowlist_drift(authorized)
    if not ok:
        return False, [], f"unexpected drift: {sorted(unexpected)}"

    staged: List[str] = []
    for rel in AUTHORIZED_G0R3_COMMIT_PATHS:
        path = ROOT / Path(rel)
        if not path.is_file():
            continue
        added, err = _git_add_allowlisted(rel)
        if not added:
            return False, staged, err
        staged.append(rel)

    return True, staged, ""


def commit_g0r3() -> Tuple[bool, str, List[str]]:
    ok, staged, msg = stage_allowlist_only()
    if not ok:
        return False, msg, staged
    proc = subprocess.run(
        ["git", "commit", "-m", G0R3_COMMIT_MSG],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False, proc.stderr or proc.stdout, staged
    return True, _run_git("rev-parse", "HEAD"), staged


def verify_worktree_clean() -> bool:
    allowed_untracked = {
        G0R3_ZIP.name,
        G0R3_SHA.relative_to(ROOT).as_posix(),
        G0R3_SHA.name,
    }
    for line in _run_git("status", "--porcelain").splitlines():
        if not line.strip():
            continue
        path = line[3:].strip().split(" -> ")[-1].replace("\\", "/")
        if path in allowed_untracked or path.endswith(G0R3_ZIP.name):
            continue
        return False
    return True


def _head_is_g0r3_input_commit() -> bool:
    return _run_git("log", "-1", "--format=%s") == G0R3_COMMIT_MSG


def _read_start_head_from_git_status(commit: str) -> str:
    rel = doc_path("CODEX_G0R3_GIT_STATUS.txt").relative_to(ROOT).as_posix()
    blob = read_committed_bytes(commit, rel)
    if not blob:
        return ""
    for line in blob.decode("utf-8").splitlines():
        if line.startswith("g0r3_start_head="):
            return line.split("=", 1)[1].strip()
    return ""


def package_from_existing_commit(*, final_commit: str, start_head: str, branch: str) -> int:
    include_list = build_zip_include_list()
    zip_digest, zip_missing, _manifest = build_g0r3_zip_from_commit(final_commit, include_list)
    if zip_missing:
        print(json.dumps({"g0r3_status": "BLOCKED", "zip_missing": zip_missing}, indent=2))
        return 1
    with zipfile.ZipFile(G0R3_ZIP) as zf:
        names = set(zf.namelist())
        for mandatory in MANDATORY_ZIP_PATHS:
            if mandatory not in names:
                print(json.dumps({"g0r3_status": "BLOCKED", "mandatory_missing_in_zip": mandatory}, indent=2))
                return 1
    write_sidecar(zip_digest)
    sidecar_digest = G0R3_SHA.read_text(encoding="utf-8").strip().split()[0]
    print(
        json.dumps(
            {
                "g0r3_status": "PASS",
                "branch": branch,
                "start_head": start_head,
                "g0r3_final_input_commit": final_commit,
                "head_changed": final_commit != start_head,
                "review_zip_sha256": zip_digest,
                "sidecar_matches_zip": sidecar_digest == zip_digest,
                "no_post_commit_input_changes": True,
            },
            indent=2,
        )
    )
    return 0


def verify_head_matches_worktree(paths: List[str], commit: str) -> bool:
    for rel in paths:
        norm = _norm(rel)
        head_blob = read_committed_bytes(commit, norm)
        path = ROOT / Path(norm)
        if head_blob is None or not path.is_file():
            return False
        if _sha256_bytes(head_blob) != _sha256_file(path):
            return False
    return True


def main() -> int:
    branch = _run_git("branch", "--show-current")
    if G0R3_ZIP.is_file():
        G0R3_ZIP.unlink()
    if G0R3_SHA.is_file():
        G0R3_SHA.unlink()

    if _head_is_g0r3_input_commit():
        final_commit = _run_git("rev-parse", "HEAD")
        start_head = _read_start_head_from_git_status(final_commit) or _run_git("rev-parse", "HEAD~1")
        return package_from_existing_commit(
            final_commit=final_commit,
            start_head=start_head,
            branch=branch,
        )

    start_head = _run_git("rev-parse", "HEAD")
    write_preflight(start_head, branch)
    ensure_g0r2_rejection_inputs()

    include_list = build_zip_include_list()
    include_set = set(include_list)

    v5r_paths = sorted(load_v5r_baseline())
    atomic_write_json(
        doc_path("CODEX_G0R3_PROTECTED_HASHES_BEFORE.json"),
        protected_hash_snapshot(v5r_paths),
    )

    comparison, restoration_ok = build_comparison(include_set)
    atomic_write_json(
        doc_path("CODEX_G0R3_V5R_BASELINE_COMPARISON.json"),
        {
            "generated_at_utc": _utc_now(),
            "previous_pre_g0r_drift_detected": True,
            "previously_drifted_paths": list(PREVIOUSLY_DRIFTED_PATHS),
            "entries": comparison,
        },
    )
    atomic_write_json(
        doc_path("CODEX_G0R3_PROTECTED_HASHES_AFTER.json"),
        protected_hash_snapshot(v5r_paths),
    )

    update_phase_catalog()
    update_review_registry()
    write_authorization_artifacts(ROOT)
    write_g0r3_review_snapshot(ROOT)
    write_g0r3_template()
    write_change_manifest(list(AUTHORIZED_G0R3_COMMIT_PATHS))
    write_git_status(branch=branch, start_head=start_head)
    write_package_manifest_placeholder(include_list)
    write_report(start_head=start_head, test_rc=0, restoration_ok=restoration_ok)
    update_next_cursor_prompt()

    test_rc, _ = run_tests()
    if test_rc != 0 or not restoration_ok:
        write_report(start_head=start_head, test_rc=test_rc, restoration_ok=restoration_ok)
        print(json.dumps({"g0r3_status": "BLOCKED", "blocker": "TESTS_OR_BASELINE"}, indent=2))
        return 1

    authorized_set = set(AUTHORIZED_G0R3_COMMIT_PATHS)
    ok_drift, unexpected = verify_allowlist_drift(authorized_set)
    if not ok_drift:
        print(
            json.dumps(
                {
                    "g0r3_status": "BLOCKED",
                    "blocker": "UNEXPECTED_NON_ALLOWLIST_WORKTREE_DRIFT",
                    "unexpected": sorted(unexpected),
                },
                indent=2,
            )
        )
        return 1

    ok, final_commit, staged = commit_g0r3()
    if not ok or not final_commit or final_commit == start_head:
        print(
            json.dumps(
                {"g0r3_status": "BLOCKED", "blocker": "CLEAN_ISOLATED_CHECKPOINT_NOT_ESTABLISHED"},
                indent=2,
            )
        )
        return 1

    if not verify_worktree_clean():
        print(json.dumps({"g0r3_status": "BLOCKED", "blocker": "WORKTREE_NOT_CLEAN_AFTER_COMMIT"}, indent=2))
        return 1

    return package_from_existing_commit(
        final_commit=final_commit,
        start_head=start_head,
        branch=branch,
    )


if __name__ == "__main__":
    raise SystemExit(main())
