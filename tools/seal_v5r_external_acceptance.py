"""Seal V5R external acceptance and advance to COMPLETE_AWAITING_OPERATIONAL_DECISION."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FINAL_PHASE = "COMPLETE_AWAITING_OPERATIONAL_DECISION"
V5R_PHASE = "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR"
V5R_ZIP = "codex_v5r_standalone_exe_review.zip"
V5R_ZIP_HASH = "b0e687522cdb7a5966b872756e3df97ba62a676ab0f3a8aa01acaf7b4eadffc3"
TEST_OUTPUT = doc_rel("CODEX_V5R_POSTBUILD_TEST_OUTPUT.txt")


def patch_v5r_registry() -> None:
    from aa_safe_io import atomic_write_json

    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V5R_PHASE:
            entry["artifact_acceptance"] = "APPROVED_FOR_NEXT_PHASE"
            entry["V5R_EXTERNAL_ACCEPTANCE"] = "APPROVED_FOR_NEXT_PHASE"
            if not entry.get("external_sealed"):
                entry["review_zip_sha256"] = V5R_ZIP_HASH
    atomic_write_json(path, registry)


def update_vision_progress() -> None:
    from aa_safe_io import atomic_write_json

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": FINAL_PHASE,
        "v5r_external_acceptance": "APPROVED_FOR_NEXT_PHASE",
        "v5r_standalone_exe_rebuild": True,
        "exe_built": True,
        "exe_executed": False,
        "distribution_type": "ONEFILE_STANDALONE",
        "next_expected_phase": "NONE",
        "next_phase_authorized": False,
        "build_source_commit": "bde017fb41819efd821100aaa68fecb08dbac26f",
        "submission_exe_sha256": "eb5f4b89e30a9d34b7e728638c7e668cb94b7f66d1fa73641c08789f0bb8be57",
        "review_zip_sha256": V5R_ZIP_HASH,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)


def main() -> int:
    from aa_vision_controller import (
        begin_authorized_phase,
        complete_authorized_phase,
        load_automation_state,
        record_phase_test_pass,
        register_external_approval,
    )
    from aa_vision_review_gate import file_sha256

    approval = ROOT / "EXTERNAL_REVIEW_APPROVAL_FINAL.md"
    if not approval.is_file():
        raise SystemExit("EXTERNAL_REVIEW_APPROVAL_FINAL.md missing")

    test_path = ROOT / TEST_OUTPUT
    if not test_path.is_file():
        raise SystemExit(f"{TEST_OUTPUT} missing — run V5R tests first")

    reg = register_external_approval(ROOT, phase_id=FINAL_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"register_external_approval failed: {reg.get('errors')}")

    begin = begin_authorized_phase(ROOT, FINAL_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"begin_authorized_phase failed: {begin.get('errors')}")

    test_hash = file_sha256(test_path)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=FINAL_PHASE,
        test_output_file=TEST_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"record_phase_test_pass failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=FINAL_PHASE, review_zip_name="")
    if not comp.get("completed"):
        raise SystemExit(f"complete_authorized_phase failed: {comp.get('errors')}")

    patch_v5r_registry()
    update_vision_progress()

    from aa_decision_cockpit_readonly_snapshot import refresh_live_review_snapshot

    snap_path = refresh_live_review_snapshot(ROOT)
    state = load_automation_state(ROOT)
    print(
        json.dumps(
            {
                "status": "V5R_EXTERNAL_ACCEPTANCE_SEALED",
                "current_executed_phase": state.get("current_executed_phase"),
                "expected_next_phase": state.get("expected_next_phase"),
                "execution_status": state.get("execution_status"),
                "v5r_review_zip_sha256": V5R_ZIP_HASH,
                "live_snapshot": str(snap_path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
