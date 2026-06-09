"""Phase I external review submission."""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from aa_champion_evidence_phase_i import (
    APPROVAL_SUBMISSION,
    PHASE_ID,
    REVIEW_ZIP_NAME,
    build_submission_approval_md,
    run_phase_i,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION


def test_submission_doc_states_champion_unchanged() -> None:
    text = build_submission_approval_md(Path("."), review_zip_sha256="abc123")
    assert "Champion changed" in text or "Champion changed in this remediation" in text
    assert "NO" in text
    assert AUTHORITATIVE_CHAMPION in text


def test_phase_i_run_minimal(tmp_path: Path) -> None:
    (tmp_path / "control" / "vision_automation" / "review_registry").mkdir(parents=True)
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "docs" / "review" / "status").mkdir(parents=True)
    (tmp_path / "control" / "vision_automation" / "review_registry" / "review_registry.json").write_text(
        json.dumps({"program": "TEST", "reviews": []}),
        encoding="utf-8",
    )
    (tmp_path / "VISION_PROGRESS.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control" / "pipeline_pending.json").write_text(
        json.dumps({"schema_version": 1, "status": "IDLE", "has_work": False, "details": {}}),
        encoding="utf-8",
    )
    (tmp_path / "control" / "champion_decision_charter.md").write_text("# c\n", encoding="utf-8")
    (tmp_path / "control" / "champion_change_criteria.yaml").write_text(
        yaml.dump({"authoritative_champion": AUTHORITATIVE_CHAMPION}),
        encoding="utf-8",
    )
    (tmp_path / "evidence" / "canonical_model_comparison.json").write_text("{}", encoding="utf-8")

    summary = run_phase_i(tmp_path)
    assert summary["status"] == "AWAITING_EXTERNAL_REVIEW"
    assert summary["champion_unchanged"] is True
    assert (tmp_path / REVIEW_ZIP_NAME).is_file()
    assert (tmp_path / f"{REVIEW_ZIP_NAME}.sha256").is_file()
    assert (tmp_path / APPROVAL_SUBMISSION).is_file()
    assert (tmp_path / "evidence" / "phase_i_external_review_summary.json").is_file()

    reg = json.loads(
        (tmp_path / "control" / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    entry = next(r for r in reg["reviews"] if r["phase_id"] == PHASE_ID)
    assert entry["champion_changed"] is False
    assert entry.get("champion_unchanged_explicit") is True

    vision = json.loads((tmp_path / "VISION_PROGRESS.json").read_text(encoding="utf-8"))
    assert vision["champion_evidence_remediation"]["champion_unchanged"] is True
