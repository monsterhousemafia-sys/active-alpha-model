"""Phase I — External review submission (ZIP, approval doc, registry, progress)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion
from aa_safe_io import atomic_write_json, atomic_write_text

REVIEW_ZIP_NAME = "codex_champion_evidence_remediation_review.zip"
PHASE_ID = "CHAMPION_EVIDENCE_GOVERNANCE_REMEDIATION_A_THROUGH_I"
APPROVAL_SUBMISSION = "EXTERNAL_REVIEW_APPROVAL_CHAMPION_EVIDENCE_REMEDIATION.md"
APPROVAL_TEMPLATE = "EXTERNAL_REVIEW_APPROVAL_CHAMPION_EVIDENCE_REMEDIATION_TEMPLATE.md"
GIT_STATUS_REL = "CODEX_CHAMPION_EVIDENCE_GIT_STATUS.txt"
SUBMISSION_MD = Path("docs") / "CHAMPION_EVIDENCE_EXTERNAL_REVIEW_SUBMISSION.md"
STATUS_MD = Path("docs") / "review" / "status" / "CHAMPION_EVIDENCE_REMEDIATION_EXTERNAL_REVIEW_STATUS.md"
EVIDENCE_SUMMARY = Path("evidence") / "phase_i_external_review_summary.json"
PENDING_SEAL = "PENDING_EXTERNAL_SEAL"

ZIP_INCLUDE: Tuple[str, ...] = (
    "AGENTS.md",
    "CHAMPION_CHALLENGER_GOVERNANCE.md",
    "VISION_PROGRESS.json",
    "DEVELOPMENT_PIPELINE.json",
    "control/pipeline_pending.json",
    APPROVAL_TEMPLATE,
    str(EVIDENCE_SUMMARY).replace("\\", "/"),
    "docs/CODEX_CHAMPION_EVIDENCE_REMEDIATION_REPORT.md",
    "docs/CHAMPION_EVIDENCE_GOVERNANCE_IMPROVEMENT_PLAN.md",
    "docs/CHAMPION_STRATEGIC_DECISION_RECORD.md",
    "docs/PHASE_G_LIVE_OPERATIONS_REPORT.md",
    "docs/PHASE_H_OPERATOR_TRANSPARENCY_REPORT.md",
    "docs/LIVE_TRADING_REBALANCE_PHASE5_VALIDATION.md",
    "control/champion_decision_charter.md",
    "control/champion_change_criteria.yaml",
    "control/champion_operational_status.json",
    "control/champion_rejected_alternatives.json",
    "control/champion_lineage_policy.json",
    "control/challenger_report.json",
    "evidence/canonical_model_comparison.json",
    "evidence/canonical_model_comparison.md",
    "evidence/phase_a_truth_inventory_summary.json",
    "evidence/phase_b_remediation_summary.json",
    "evidence/phase_c_canonical_comparison_summary.json",
    "evidence/phase_d_governance_summary.json",
    "evidence/phase_e_strategic_decision_summary.json",
    "evidence/phase_f_statistical_evidence_summary.json",
    "evidence/phase_f_gate_matrix.json",
    "evidence/phase_f_gate_matrix.md",
    "evidence/phase_g_live_operations_summary.json",
    "evidence/phase_g_planning_cash_audit.json",
    "evidence/phase_h_operator_transparency_summary.json",
    "evidence/v5r_live_rebalance_phase5_validation.json",
    "evidence/champion_pointer_audit.json",
    "evidence/governance_baseline.json",
    "research_evidence/trial_ledger_preregistered.json",
    "research_evidence/cost_stress_gate_report.md",
    "research_evidence/robustness_gate_report.md",
    "research_evidence/dsr_multiple_testing_report.md",
    GIT_STATUS_REL,
    "aa_champion_governance.py",
    "aa_champion_cockpit_phase_h.py",
    "aa_canonical_comparison.py",
    "aa_champion_evidence_phase_f.py",
    "tools/build_champion_evidence_remediation_review_zip.py",
    "tools/run_champion_evidence_phase_i.py",
    "tests/test_champion_evidence_phase_i.py",
    "tests/test_champion_cockpit_phase_h.py",
    "tests/test_canonical_model_comparison.py",
    "tests/test_champion_governance_phase_d.py",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def capture_git_status(root: Path) -> str:
    root = Path(root)
    try:
        proc = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        body = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            body = f"git status exit {proc.returncode}\n{body}"
    except Exception as exc:
        body = f"git status failed: {exc}"
    return body.strip() + "\n"


def build_submission_approval_md(root: Path, *, review_zip_sha256: str) -> str:
    locked = resolve_locked_champion(root)
    return f"""# External Review Submission — Champion Evidence Remediation (Phases A–I)

**Status:** AWAITING_EXTERNAL_REVIEW (this document is a **submission**, not an approval seal).

UTC: {_utc_now()}

## Phase under review

`{PHASE_ID}`

## Champion policy (explicit — Phase I3)

| Field | Value |
|-------|--------|
| **Authoritative champion** | `{locked}` |
| **Champion changed in this remediation** | **NO** |
| **Champion change requires** | Separate `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md` + criteria PASS |
| **Phase E decision** | E1_RETAIN_R3 (see `docs/CHAMPION_STRATEGIC_DECISION_RECORD.md`) |

## Submission artefact

- Review ZIP: `{REVIEW_ZIP_NAME}`
- Sidecar: `{REVIEW_ZIP_NAME}.sha256`
- REVIEW_ZIP_SHA256: `{review_zip_sha256}`

## Scope delivered (read-only evidence & governance)

- Phases **A–I**: truth inventory, artifact remediation, canonical comparison, charter, strategic decision (R3 retained), statistical gate matrix, live-ops hardening, cockpit transparency panels.
- **No** auto-promotion, **no** champion switch, **no** signal-weight / economic parameter change, **no** real-money execution.

## What is NOT claimed

- No operational authorization beyond existing `EXTERNAL_REVIEW_APPROVAL_FINAL.md` scope.
- No approval of champion **change** (unchanged by design).
- No new backtests executed for this submission unless listed in phase summaries.

## Required external action

1. Verify ZIP hash against sidecar and this document.
2. Review gate matrix (`evidence/phase_f_gate_matrix.md`) and canonical comparison frames.
3. Copy checklist from `{APPROVAL_TEMPLATE}` only if approving follow-on work; register hash in `control/vision_automation/review_registry/review_registry.json`.

## Review decision (for external controller)

- [ ] APPROVED — evidence remediation accepted; champion unchanged confirmed
- [ ] REJECTED — hold; document blockers

Reviewer signature / date: ____________________

REVIEW_ZIP_SHA256: {review_zip_sha256}
"""


def build_submission_template_md() -> str:
    return f"""# TEMPLATE — External Review Approval (Champion Evidence Remediation)

**This file is a TEMPLATE only. It does NOT authorize execution.**

Copy to `{APPROVAL_SUBMISSION}` only after external controller review (replace submission stub).

---

## Phase authorized (if approved)

`{PHASE_ID}`

## Champion policy

- **Champion unchanged** must remain explicit: `{AUTHORITATIVE_CHAMPION}`
- **Champion change** requires a **separate** approval document — not this remediation.

## Scope

- Accept Phases A–I evidence artefacts (canonical comparison, gate matrix, live-ops, cockpit panels)
- **No** promotion, shadow/paper activation, real-money, or auto-promotion enablement

## Explicitly NOT authorized

- Champion switch without `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md`
- Productive signal-weight or risk-off parameter changes
- Operative backtests, replay, broker trading

## Review decision

- [ ] APPROVED — remediation accepted; champion unchanged
- [ ] REJECTED

Reviewer signature / date: ____________________

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
"""


def build_external_submission_md(root: Path, *, review_zip_sha256: str) -> str:
    locked = resolve_locked_champion(root)
    return f"""# Champion Evidence — External Review Submission

UTC: {_utc_now()}

## Request

External controller review of **`{PHASE_ID}`** (Phases A through I).

## Submission artefact

- `{REVIEW_ZIP_NAME}`
- `{REVIEW_ZIP_NAME}.sha256`
- REVIEW_ZIP_SHA256: `{review_zip_sha256}`

## Champion unchanged (I3)

Productive champion remains **`{locked}`**. Phase E executed **E1_RETAIN_R3** — no variant switch.

## Contents (high level)

| Phase | Deliverable |
|-------|-------------|
| A | Truth inventory, pointer audit |
| B | Artifact remediation, contaminated returns quarantine |
| C | `evidence/canonical_model_comparison.*` |
| D | Charter + `control/champion_change_criteria.yaml` |
| E | Strategic decision record (R3 retained) |
| F | Gate matrix, trial ledger, cost/robustness reports |
| G | Live-ops validation (Phase 5 dry-run) |
| H | Cockpit panels H1–H4 |
| I | This submission ZIP + status |

## Status

**AWAITING_EXTERNAL_REVIEW** — operative execution not authorized by this package alone.

See `{STATUS_MD.as_posix()}` and `{APPROVAL_SUBMISSION}`.
"""


def build_review_zip(root: Path) -> Dict[str, Any]:
    root = Path(root)
    git_text = capture_git_status(root)
    atomic_write_text(root / GIT_STATUS_REL, git_text)

    zip_path = root / REVIEW_ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()

    included: List[str] = []
    missing: List[str] = []
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in ZIP_INCLUDE:
            path = root / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
                included.append(rel)
            else:
                missing.append(rel)

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = root / f"{REVIEW_ZIP_NAME}.sha256"
    sidecar.write_text(f"{digest}  {REVIEW_ZIP_NAME}\n", encoding="ascii")
    return {
        "zip_path": str(zip_path),
        "sha256": digest,
        "included_count": len(included),
        "missing": missing,
        "included": included,
    }


def register_review_registry_entry(root: Path, *, review_zip_sha256: str) -> Dict[str, Any]:
    root = Path(root)
    registry_path = root / "control" / "vision_automation" / "review_registry" / "review_registry.json"
    if not registry_path.is_file():
        return {"ok": False, "error": "review_registry_missing"}

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    reviews = [r for r in (registry.get("reviews") or []) if r.get("phase_id") != PHASE_ID]
    entry = {
        "phase_id": PHASE_ID,
        "phase_key": "CHAMPION_EVIDENCE",
        "approval_file": APPROVAL_SUBMISSION,
        "approval_sha256": PENDING_SEAL,
        "review_zip": REVIEW_ZIP_NAME,
        "review_zip_sha256": review_zip_sha256,
        "external_sealed": False,
        "completed_at_utc": _utc_now(),
        "execution_status": "AWAITING_EXTERNAL_REVIEW",
        "champion_changed": False,
        "champion_unchanged_explicit": True,
        "promotion_executed": False,
        "real_money_executed": False,
        "operative_jobs_executed": False,
        "exe_built": False,
        "exe_executed": False,
        "blockers": [],
        "note": "Phases A–I governance remediation; not a champion-change approval.",
    }
    reviews.append(entry)
    registry["reviews"] = reviews
    atomic_write_json(registry_path, registry)
    return {"ok": True, "phase_id": PHASE_ID, "review_zip_sha256": review_zip_sha256}


def update_vision_progress(root: Path, *, review_zip_sha256: str) -> Dict[str, Any]:
    root = Path(root)
    path = root / "VISION_PROGRESS.json"
    doc: Dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            doc = {}
    locked = resolve_locked_champion(root)
    doc["champion_evidence_remediation"] = {
        "track": PHASE_ID,
        "phases_completed": ["A", "B", "C", "D", "E", "F", "G", "H", "I"],
        "status": "AWAITING_EXTERNAL_REVIEW",
        "champion_unchanged": True,
        "authoritative_champion": locked,
        "strategic_decision": "E1_RETAIN_R3",
        "review_zip": REVIEW_ZIP_NAME,
        "review_zip_sha256": review_zip_sha256,
        "submission_approval_file": APPROVAL_SUBMISSION,
        "updated_at_utc": _utc_now(),
        "informational_only": True,
        "note": "Does not supersede EXTERNAL_REVIEW_APPROVAL_FINAL.md or authorize champion change.",
    }
    atomic_write_json(path, doc)
    return doc.get("champion_evidence_remediation") or {}


def update_pipeline_pending(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / "control" / "pipeline_pending.json"
    doc: Dict[str, Any] = {"schema_version": 1, "status": "IDLE", "has_work": False}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    details = dict(doc.get("details") or {})
    details["champion_evidence_remediation"] = {
        "status": "AWAITING_EXTERNAL_REVIEW",
        "review_zip": REVIEW_ZIP_NAME,
        "followup": f"External review of {PHASE_ID}; champion unchanged.",
    }
    doc["details"] = details
    doc["has_work"] = False
    doc["status"] = doc.get("status") or "IDLE"
    doc["updated_at_utc"] = _utc_now()
    doc["followup_prompt"] = (
        f"Champion evidence Phases A–I submitted for external review ({REVIEW_ZIP_NAME}). "
        "Champion unchanged (R3). Await seal before any champion-change discussion."
    )
    atomic_write_json(path, doc)
    return doc


def write_status_md(root: Path, *, review_zip_sha256: str) -> None:
    root = Path(root)
    path = root / STATUS_MD
    path.parent.mkdir(parents=True, exist_ok=True)
    text = f"""# Champion Evidence Remediation — External Review Status

Status: **AWAITING_EXTERNAL_REVIEW**

Phase: `{PHASE_ID}`

Submission ZIP: `{REVIEW_ZIP_NAME}`

REVIEW_ZIP_SHA256: `{review_zip_sha256}`

Approval / submission document: `{APPROVAL_SUBMISSION}`

Template (do not execute): `{APPROVAL_TEMPLATE}`

**Champion unchanged:** `{resolve_locked_champion(root)}` (Phase E: E1_RETAIN_R3)

Operative execution: **NOT AUTHORIZED** by this submission alone.

Generated: {_utc_now()}
"""
    atomic_write_text(path, text)


def run_phase_i(root: Path) -> Dict[str, Any]:
    root = Path(root)
    template_path = root / APPROVAL_TEMPLATE
    if not template_path.is_file():
        atomic_write_text(template_path, build_submission_template_md())

    zip_info = build_review_zip(root)
    sha = str(zip_info["sha256"])
    atomic_write_text(root / APPROVAL_SUBMISSION, build_submission_approval_md(root, review_zip_sha256=sha))
    atomic_write_text(root / SUBMISSION_MD, build_external_submission_md(root, review_zip_sha256=sha))
    write_status_md(root, review_zip_sha256=sha)

    registry = register_review_registry_entry(root, review_zip_sha256=sha)
    vision = update_vision_progress(root, review_zip_sha256=sha)
    pending = update_pipeline_pending(root)

    conflicts: List[str] = []
    if zip_info.get("missing"):
        conflicts.append("zip_missing_files")
    if not registry.get("ok"):
        conflicts.append(str(registry.get("error") or "registry_update_failed"))

    summary = {
        "schema_version": 1,
        "phase": "I",
        "generated_at_utc": _utc_now(),
        "status": "AWAITING_EXTERNAL_REVIEW",
        "phase_id": PHASE_ID,
        "champion_unchanged": True,
        "authoritative_champion": resolve_locked_champion(root),
        "review_zip": REVIEW_ZIP_NAME,
        "review_zip_sha256": sha,
        "zip": zip_info,
        "registry": registry,
        "vision_progress": vision,
        "pipeline_pending": pending,
        "conflicts": conflicts,
        "documents": {
            "submission": APPROVAL_SUBMISSION,
            "template": APPROVAL_TEMPLATE,
            "submission_md": str(SUBMISSION_MD).replace("\\", "/"),
            "status_md": str(STATUS_MD).replace("\\", "/"),
        },
    }
    atomic_write_json(root / EVIDENCE_SUMMARY, summary)

    report_lines = [
        "# CODEX Champion Evidence Remediation — Phase I Report",
        "",
        f"Generated: {summary['generated_at_utc']}",
        f"Status: **{summary['status']}**",
        "",
        f"- Review ZIP: `{REVIEW_ZIP_NAME}`",
        f"- SHA256: `{sha}`",
        f"- Champion unchanged: **{summary['authoritative_champion']}**",
        f"- Registry: {'OK' if registry.get('ok') else 'FAILED'}",
        f"- Missing ZIP files: {len(zip_info.get('missing') or [])}",
        "",
        "External controller: verify ZIP, then seal or reject via approval template.",
        "",
    ]
    atomic_write_text(root / "docs" / "CODEX_CHAMPION_EVIDENCE_REMEDIATION_REPORT.md", "\n".join(report_lines) + "\n")
    return summary
