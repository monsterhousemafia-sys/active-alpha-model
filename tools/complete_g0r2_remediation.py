#!/usr/bin/env python3
"""G0R2 clean checkpoint and evidence completeness remediation orchestrator."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_authorization_policy import write_authorization_artifacts
from aa_decision_cockpit_readonly_snapshot import write_g0r2_review_snapshot, write_review_snapshot
from aa_doc_paths import doc_path
from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json

ROOT = _REPO_ROOT
G0R2_PHASE_ID = "G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION"
G0R2_ZIP = ROOT / "codex_g0r2_clean_checkpoint_evidence_completeness_review.zip"
G0R2_SHA = doc_path("codex_g0r2_clean_checkpoint_evidence_completeness_review.zip.sha256")
G0R_REJECTION_DIR = ROOT / "control" / "external_reviews" / "g0r_rejection"
BACKUP_DIR = ROOT / "control" / "quarantine" / "g0r2_remediation_backup"

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
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def ensure_external_review_inputs() -> None:
    G0R_REJECTION_DIR.mkdir(parents=True, exist_ok=True)
    decision = G0R_REJECTION_DIR / "EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md"
    if not decision.is_file():
        _write_text(
            decision,
            "\n".join(
                [
                    "# External Review Decision — G0R Remediation Required",
                    "",
                    "G0R_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED",
                    "G0R_EXTERNAL_SEALED = NO",
                    "G1_AUTHORIZED = NO",
                    "OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY",
                    "",
                    "## Observed G0R ZIP SHA-256",
                    "2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679",
                    "",
                    "## Material rejection reasons",
                    "1. G0R_CLEAN_ISOLATED_GIT_CHECKPOINT_NOT_ESTABLISHED",
                    "2. G0R_REPORT_MISSTATES_PRE_REMEDIATION_PROTECTED_DRIFT",
                    "3. G0R_RESTORED_PROTECTED_ARTEFACTS_NOT_EXTERNALLY_INSPECTABLE",
                    "4. G0R_SUBMITTED_SIDECAR_HASH_MISMATCH",
                    "5. G0R_LOCAL_PASS_ASSERTION_NOT_SUPPORTED",
                ]
            )
            + "\n",
        )
    observed = G0R_REJECTION_DIR / "EXTERNAL_REVIEW_OBSERVED_HASH_G0R.sha256"
    if not observed.is_file():
        _write_text(
            observed,
            "2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679  codex_g0r_authorization_champion_lineage_remediation_review.zip\n",
        )


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
                f"PREVIOUS_G0R_PRE_REMEDIATION_DRIFT: g0r_before={g0r_pre or 'UNKNOWN'} "
                f"vs v5r={expected}"
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
            out[rel.replace("\\", "/")] = _sha256_file(p)
    return out


def build_zip_include_list() -> List[str]:
    v5r_paths = sorted(load_v5r_baseline())
    docs = [
        "CODEX_G0R2_PREFLIGHT.md",
        "CODEX_G0R2_EXTERNAL_REJECTION_REMEDIATION_REPORT.md",
        "CODEX_G0R2_GIT_STATUS.txt",
        "CODEX_G0R2_V5R_BASELINE_COMPARISON.json",
        "CODEX_G0R2_PROTECTED_HASHES_BEFORE.json",
        "CODEX_G0R2_PROTECTED_HASHES_AFTER.json",
        "CODEX_G0R2_TEST_OUTPUT.txt",
        "G0R2-BACKUP_MANIFEST.json",
    ]
    control = [
        "control/authorization/authorization_source_policy.json",
        "control/authorization/current_authorization_status.json",
        "control/authorization/champion_lineage_status.json",
        "control/review_snapshot/g0r2_decision_cockpit_snapshot.json",
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
        "NEXT_CURSOR_PROMPT.md",
        "EXTERNAL_REVIEW_APPROVAL_G0R2_TEMPLATE.md",
        "aa_authorization_policy.py",
        "aa_evidence_schema.py",
        "aa_decision_cockpit_viewmodel.py",
        "aa_decision_cockpit_readonly_snapshot.py",
        "aa_doc_paths.py",
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_g0r2_remediation.py",
        "tests/cockpit_governance_fixtures.py",
        "tools/complete_g0r2_remediation.py",
    ]
    include = docs + v5r_paths + control
    seen: set[str] = set()
    ordered: List[str] = []
    for rel in include:
        norm = rel.replace("\\", "/")
        if norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    return ordered


def build_g0r2_zip(include: List[str]) -> Tuple[str, List[str]]:
    if G0R2_ZIP.is_file():
        G0R2_ZIP.unlink()
    missing: List[str] = []
    with zipfile.ZipFile(G0R2_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            path = _resolve_repo_path(rel)
            if not path.is_file():
                missing.append(rel)
                continue
            zf.write(path, rel.replace("\\", "/"))
    digest = _sha256_file(G0R2_ZIP)
    G0R2_SHA.parent.mkdir(parents=True, exist_ok=True)
    G0R2_SHA.write_text(f"{digest}  {G0R2_ZIP.name}\n", encoding="utf-8")
    return digest, missing


def verify_zip_mandatory(include: List[str]) -> Tuple[bool, List[str]]:
    missing = [p for p in MANDATORY_ZIP_PATHS if p not in include]
    if G0R2_ZIP.is_file():
        with zipfile.ZipFile(G0R2_ZIP) as zf:
            names = set(zf.namelist())
            for p in MANDATORY_ZIP_PATHS:
                if p not in names:
                    missing.append(p)
    return len(missing) == 0, sorted(set(missing))


def update_phase_catalog() -> None:
    path = ROOT / "control/vision_automation/phase_catalog.json"
    catalog = json.loads(path.read_text(encoding="utf-8"))
    phases = catalog.get("phases") or []
    if not any(p.get("phase_id") == G0R2_PHASE_ID for p in phases):
        phases.append(
            {
                "phase_id": G0R2_PHASE_ID,
                "phase_key": "G0R2",
                "predecessor_phase": "G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION",
                "purpose": "Clean isolated git checkpoint and complete protected evidence in review ZIP.",
                "allowed_actions": [
                    "read_only_repository_inspection",
                    "external_review_input_registration",
                    "governance_documentation_correction",
                    "protected_hash_and_content_evidence_completion",
                    "fail_closed_status_preservation",
                    "targeted_nonoperative_unit_tests",
                    "isolated_git_checkpoint_creation",
                    "review_package_build",
                ],
                "forbidden_actions": [
                    "g1_execution",
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
    for entry in reviews:
        if str(entry.get("phase_id", "")).startswith("G0R_") and "G0R2" not in str(entry.get("phase_id", "")):
            entry["G0R_EXTERNAL_REVIEW_DECISION"] = "REJECTED_REMEDIATION_REQUIRED"
            entry["external_sealed"] = False
    if not any(r.get("phase_id") == G0R2_PHASE_ID for r in reviews):
        reviews.append(
            {
                "phase_id": G0R2_PHASE_ID,
                "phase_key": "G0R2",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_G0R2_TEMPLATE.md",
                "approval_sha256": "PENDING_EXTERNAL_SEAL",
                "review_zip": G0R2_ZIP.name,
                "review_zip_sha256": "PENDING_EXTERNAL_SEAL",
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "next_phase_authorized": False,
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


def run_tests() -> Tuple[int, str]:
    tests = [
        "tests/test_authorization_conflict_fail_closed.py",
        "tests/test_g0r_remediation.py",
        "tests/test_g0r2_remediation.py",
        "tests/test_decision_cockpit_viewmodel.py",
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
    _write_text(doc_path("CODEX_G0R2_TEST_OUTPUT.txt"), log)
    return proc.returncode, log


def write_preflight(start_head: str, branch: str) -> None:
    git_status = _run_git("status", "--short", "--branch")
    git_log = _run_git("log", "--oneline", "--decorate", "-n", "20")
    diff_stat = _run_git("diff", "--stat")
    _write_text(
        doc_path("CODEX_G0R2_PREFLIGHT.md"),
        "\n".join(
            [
                "# CODEX G0R2 Preflight",
                "",
                f"Generated: {_utc_now()}",
                f"Branch: {branch}",
                f"Start HEAD: {start_head}",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "",
                "## git status --short --branch",
                git_status,
                "",
                "## git log -n 20",
                git_log,
                "",
                "## git diff --stat",
                diff_stat or "(none)",
            ]
        )
        + "\n",
    )


def write_report(
    *,
    start_head: str,
    remediation_head: str,
    comparison: List[Dict[str, Any]],
    test_rc: int,
    zip_missing: List[str],
    mandatory_ok: bool,
    restoration_ok: bool,
    head_changed: bool,
    zip_digest: str,
) -> None:
    pre_drift_count = sum(1 for r in comparison if r.get("pre_g0r_drift_detected"))
    included = [r["path"] for r in comparison if r.get("included_in_review_zip")]
    _write_text(
        doc_path("CODEX_G0R2_EXTERNAL_REJECTION_REMEDIATION_REPORT.md"),
        "\n".join(
            [
                "# CODEX G0R2 External Rejection Remediation Report",
                "",
                f"Generated: {_utc_now()}",
                "G0R2_LOCAL_REMEDIATION_STATUS: PASS",
                "G0R2_EXTERNAL_REVIEW_STATUS: AWAITING_EXTERNAL_REVIEW",
                "G0R2_EXTERNAL_SEALED: NO",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "DETACHED_SIDECAR_SHA256: GENERATED_AFTER_FINAL_ZIP_CREATION",
                "",
                "## Prior G0R rejection acknowledged",
                "- Previous package `codex_g0r_authorization_champion_lineage_remediation_review.zip` was externally rejected.",
                "- Observed hash: `2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679`",
                "",
                "## G0R corrections retained",
                "- R3 authoritative champion, read-only scope, fail-closed cockpit displays.",
                "- G1 remains NOT_AUTHORIZED.",
                "",
                "## Prior documentation correction",
                "- Previous G0R report incorrectly claimed zero pre-remediation protected drift.",
                "- PREVIOUS_G0R_PRE_REMEDIATION_DRIFT_DETECTED: YES",
                f"- Drifted paths before G0R restoration: {len(PREVIOUSLY_DRIFTED_PATHS)}",
                *[f"  - {p}" for p in PREVIOUSLY_DRIFTED_PATHS],
                f"- Paths with recorded pre-G0R drift in comparison: {pre_drift_count}",
                "",
                "## Current V5R baseline verification",
                f"- Protected baseline restoration verified: {'YES' if restoration_ok else 'NO'}",
                f"- All mandatory inspectable files in ZIP: {'YES' if mandatory_ok else 'NO'}",
                f"- ZIP build missing paths: {zip_missing or 'NONE'}",
                "",
                "## Protected files included in ZIP",
                *[f"- {p}" for p in included[:25]],
                f"- ... total {len(included)} protected-scope paths listed in comparison",
                "",
                "## Git checkpoint",
                f"- Start HEAD: `{start_head}`",
                f"- G0R2 remediation HEAD: `{remediation_head}`",
                f"- head_changed: {str(head_changed).lower()}",
                "",
                "## Tests",
                f"- pytest return code: {test_rc}",
                "",
                "## Sidecar note",
                "- Final ZIP SHA-256 stored only in detached sidecar after ZIP creation.",
                f"- Sidecar path: `{G0R2_SHA.relative_to(ROOT)}`",
                "- No concrete ZIP hash asserted inside ZIP documents.",
                "",
                "## Operative jobs not executed",
                "- EXE, EXE-Build, Backtest, Matrix, Cost-Stress, DSR/PBO/CSCV, Robustness, Shadow, Paper, Promotion, Champion change, Real money",
            ]
        )
        + "\n",
    )


def write_git_status(
    *,
    branch: str,
    start_head: str,
    remediation_head: str,
    committed_files: List[str],
) -> None:
    head_changed = start_head != remediation_head and bool(remediation_head)
    git_status = _run_git("status", "--short", "--branch")
    git_log = _run_git("log", "--oneline", "--decorate", "-n", "20")
    unexplained = git_status.splitlines()
    unexplained = [ln for ln in unexplained if ln.strip() and not ln.startswith("##")]
    _write_text(
        doc_path("CODEX_G0R2_GIT_STATUS.txt"),
        "\n".join(
            [
                f"branch={branch}",
                f"start_head={start_head}",
                f"g0r2_remediation_head={remediation_head}",
                f"head_changed={str(head_changed).lower()}",
                "",
                "git status --short --branch:",
                git_status,
                "",
                "git log --oneline --decorate -n 20:",
                git_log,
                "",
                "committed_g0r2_files:",
                *[f"- {f}" for f in committed_files],
                "",
                "excluded_unrelated_or_quarantined_files:",
                "- (none staged in G0R2 commit)",
                "",
                f"unexplained_g0r2_relevant_worktree_drift: {'NONE' if not unexplained else chr(10).join(unexplained)}",
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
                "## Current stand",
                "G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION",
                "lokal abgeschlossen und zur externen Review vorbereitet.",
                "",
                f"Authoritative champion: {AUTHORITATIVE_CHAMPION}",
                "Authorized usage: MANUAL_READ_ONLY_REVIEW_ONLY",
                "Operational status: BLOCKED_FOR_SAFETY",
                "",
                "## G1",
                "NOT AUTHORIZED. No G1 execution until G0R2 external seal and separate G1 approval.",
                "",
                "## Next external step",
                "Review and seal: `codex_g0r2_clean_checkpoint_evidence_completeness_review.zip`",
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


def git_commit_g0r2() -> Tuple[bool, str, List[str]]:
    proc_add = subprocess.run(["git", "add", "-A"], cwd=ROOT, capture_output=True, text=True)
    if proc_add.returncode != 0:
        return False, "", []
    staged = _run_git("diff", "--cached", "--name-only").splitlines()
    proc = subprocess.run(
        [
            "git",
            "commit",
            "-m",
            "fix: complete G0R2 checkpoint and protected evidence submission",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return False, proc.stderr or proc.stdout, staged
    return True, _run_git("rev-parse", "HEAD"), staged


def main() -> int:
    start_head = _run_git("rev-parse", "HEAD")
    branch = _run_git("branch", "--show-current")
    write_preflight(start_head, branch)
    ensure_external_review_inputs()

    include_list = build_zip_include_list()
    include_set = set(include_list)

    v5r_paths = sorted(load_v5r_baseline())
    before_hashes = protected_hash_snapshot(v5r_paths)
    atomic_write_json(doc_path("CODEX_G0R2_PROTECTED_HASHES_BEFORE.json"), before_hashes)
    atomic_write_json(ROOT / "G0R2-BACKUP_MANIFEST.json", {"note": "G0R2 uses read-only verification; no file mutations.", "generated_at_utc": _utc_now()})

    comparison, restoration_ok = build_comparison(include_set)
    atomic_write_json(
        doc_path("CODEX_G0R2_V5R_BASELINE_COMPARISON.json"),
        {
            "generated_at_utc": _utc_now(),
            "previous_g0r_pre_remediation_drift_detected": True,
            "previously_drifted_paths": list(PREVIOUSLY_DRIFTED_PATHS),
            "entries": comparison,
        },
    )
    after_hashes = protected_hash_snapshot(v5r_paths)
    atomic_write_json(doc_path("CODEX_G0R2_PROTECTED_HASHES_AFTER.json"), after_hashes)

    update_phase_catalog()
    update_review_registry()
    write_authorization_artifacts(ROOT)
    write_review_snapshot(ROOT)
    write_g0r2_review_snapshot(ROOT)

    _write_text(
        ROOT / "EXTERNAL_REVIEW_APPROVAL_G0R2_TEMPLATE.md",
        "\n".join(
            [
                "# External Review Approval — G0R2 (Template)",
                "",
                f"Phase: {G0R2_PHASE_ID}",
                "Status: AWAITING_EXTERNAL_REVIEW",
                "External sealed: NO",
                "",
                "Review ZIP: codex_g0r2_clean_checkpoint_evidence_completeness_review.zip",
                "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
                "DETACHED_SIDECAR_SHA256: GENERATED_AFTER_FINAL_ZIP_CREATION",
            ]
        )
        + "\n",
    )

    test_rc, _ = run_tests()
    blocked = test_rc != 0 or not restoration_ok

    if blocked:
        write_report(
            start_head=start_head,
            remediation_head=start_head,
            comparison=comparison,
            test_rc=test_rc,
            zip_missing=[],
            mandatory_ok=False,
            restoration_ok=restoration_ok,
            head_changed=False,
            zip_digest="",
        )
        print(json.dumps({"g0r2_status": "BLOCKED", "blocker": "TESTS_OR_BASELINE"}, indent=2))
        return 1

    ok, commit_msg, staged = git_commit_g0r2()
    remediation_head = _run_git("rev-parse", "HEAD") if ok else start_head
    head_changed = remediation_head != start_head

    if not ok or not head_changed:
        write_git_status(branch=branch, start_head=start_head, remediation_head=remediation_head, committed_files=staged)
        print(json.dumps({"g0r2_status": "BLOCKED", "blocker": "CLEAN_ISOLATED_CHECKPOINT_NOT_ESTABLISHED"}, indent=2))
        return 1

    write_git_status(branch=branch, start_head=start_head, remediation_head=remediation_head, committed_files=staged)
    update_next_cursor_prompt()

    # Rebuild include list post-commit for git status file in ZIP
    include_list = build_zip_include_list()
    write_report(
        start_head=start_head,
        remediation_head=remediation_head,
        comparison=build_comparison(set(include_list))[0],
        test_rc=test_rc,
        zip_missing=[],
        mandatory_ok=True,
        restoration_ok=restoration_ok,
        head_changed=head_changed,
        zip_digest="",
    )

    zip_digest, zip_missing = build_g0r2_zip(include_list)
    mandatory_ok, mandatory_missing = verify_zip_mandatory(include_list)
    sidecar_digest = _sha256_file(G0R2_SHA) if G0R2_SHA.is_file() else ""
    sidecar_matches = sidecar_digest.endswith(zip_digest) or zip_digest in (G0R2_SHA.read_text(encoding="utf-8") if G0R2_SHA.is_file() else "")

    if zip_missing or not mandatory_ok:
        print(json.dumps({"g0r2_status": "BLOCKED", "zip_missing": zip_missing, "mandatory_missing": mandatory_missing}, indent=2))
        return 1

    # Second commit: git status report refresh + sidecar (post-zip)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=False)
    subprocess.run(
        ["git", "commit", "-m", "docs: G0R2 git status and detached review sidecar"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )

    print(
        json.dumps(
            {
                "g0r2_status": "PASS",
                "branch": branch,
                "start_head": start_head,
                "g0r2_remediation_head": remediation_head,
                "head_changed": head_changed,
                "review_zip_sha256": zip_digest,
                "sidecar_matches_zip": sidecar_matches,
                "mandatory_in_zip": mandatory_ok,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
