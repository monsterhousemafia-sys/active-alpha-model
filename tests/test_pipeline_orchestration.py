"""Tests for pipeline phase orchestration (auto-continue after PASS)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aa_failsafe import activate_failsafe, clear_failsafe
from aa_job_lock import JobLock
from aa_pipeline_orchestration import (
    MAX_ATTEMPT_COUNT,
    PENDING_STATUS_BLOCKED,
    PENDING_STATUS_PENDING,
    build_followup_prompt,
    claim_pending_phase,
    enqueue_eligible_phase,
    enqueue_next_phase,
    hook_evaluate,
    load_pending,
    loop_may_continue,
    mark_pending_blocked,
    merge_maintenance_details,
    save_pending,
    validate_pending_phase,
)


def _write_pipeline(root: Path, *, p0: str = "PASS", p1: str = "PASS", p2: str = "NOT_STARTED", auto: bool = True) -> None:
    payload = {
        "auto_continue_after_pass": auto,
        "current_phase": "P2_PREDICTION_OUTCOME_LEDGER",
        "control_policy": {
            "enqueue_next_phase_after_pass": True,
            "never_chain_multiple_phases_inside_same_work_unit": True,
            "one_new_phase_per_run": True,
        },
        "phases": [
            {"id": "P0_SAFETY_CONTROL_PLANE", "status": p0, "next_phase": "P1_INTEGRITY_FOUNDATION"},
            {"id": "P1_INTEGRITY_FOUNDATION", "status": p1, "next_phase": "P2_PREDICTION_OUTCOME_LEDGER"},
            {"id": "P2_PREDICTION_OUTCOME_LEDGER", "status": p2, "next_phase": "P3_BACKGROUND_RESEARCH_EXISTING_MODELS"},
        ],
    }
    (root / "DEVELOPMENT_PIPELINE.json").write_text(json.dumps(payload), encoding="utf-8")


def test_p1_pass_enqueues_p2(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    ok, msg = enqueue_eligible_phase(tmp_path)
    assert ok, msg
    pending = load_pending(tmp_path)
    assert pending["has_work"] is True
    assert pending["pending_phase"] == "P2_PREDICTION_OUTCOME_LEDGER"
    assert pending["created_from_phase"] == "P1_INTEGRITY_FOUNDATION"
    assert pending["status"] == PENDING_STATUS_PENDING


def test_p1_not_pass_does_not_enqueue(tmp_path: Path) -> None:
    _write_pipeline(tmp_path, p1="NOT_STARTED")
    ok, _ = enqueue_eligible_phase(tmp_path)
    assert not ok
    assert load_pending(tmp_path)["has_work"] is False


def test_failsafe_blocks_enqueue(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    activate_failsafe(tmp_path, reason="test")
    ok, msg = enqueue_eligible_phase(tmp_path)
    assert not ok
    assert "FAILSAFE" in msg
    clear_failsafe(tmp_path)


def test_invalid_pending_phase_blocked(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    save_pending(
        tmp_path,
        {
            "schema_version": 1,
            "has_work": True,
            "pending_phase": "P3_BACKGROUND_RESEARCH_EXISTING_MODELS",
            "created_from_phase": "P1_INTEGRITY_FOUNDATION",
            "status": PENDING_STATUS_PENDING,
            "attempt_count": 0,
        },
    )
    ok, reason = validate_pending_phase(tmp_path, load_pending(tmp_path))
    assert not ok
    assert "not permitted" in reason or "!=" in reason


def test_only_one_claim_under_lock(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    lock = JobLock(tmp_path, "pipeline_phase")
    assert lock.acquire()
    try:
        ok, _, reason = claim_pending_phase(tmp_path)
        assert not ok
        assert "lock" in reason.lower()
    finally:
        lock.release()
    ok, pending, _ = claim_pending_phase(tmp_path)
    assert ok
    assert pending["attempt_count"] == 1


def test_failed_phase_does_not_enqueue_next(tmp_path: Path) -> None:
    _write_pipeline(tmp_path, p2="FAILED")
    ok, _ = enqueue_eligible_phase(tmp_path)
    assert not ok


def test_successful_pass_enqueues_only_next(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    ok, _ = enqueue_eligible_phase(tmp_path)
    assert ok
    pending = load_pending(tmp_path)
    assert pending["pending_phase"] == "P2_PREDICTION_OUTCOME_LEDGER"
    assert pending["pending_phase"] != "P3_BACKGROUND_RESEARCH_EXISTING_MODELS"


def test_max_attempts_blocks(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    pending = load_pending(tmp_path)
    pending["attempt_count"] = MAX_ATTEMPT_COUNT
    pending["status"] = PENDING_STATUS_PENDING
    save_pending(tmp_path, pending)
    ok, reason = validate_pending_phase(tmp_path, load_pending(tmp_path))
    assert not ok
    assert "attempt" in reason.lower()


def test_corrupt_pending_not_executable(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "pipeline_pending.json").write_text("{not-json", encoding="utf-8")
    pending = load_pending(tmp_path)
    assert pending["has_work"] is False


def test_maintenance_merge_preserves_phase_pending(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    merge_maintenance_details(tmp_path, details={"batch_busy": False}, maintenance_has_work=False)
    pending = load_pending(tmp_path)
    assert pending["has_work"] is True
    assert pending["pending_phase"] == "P2_PREDICTION_OUTCOME_LEDGER"


def test_hook_emits_followup(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    should, prompt = hook_evaluate(tmp_path)
    assert should
    assert "P2_PREDICTION_OUTCOME_LEDGER" in prompt


def test_loop_may_continue_with_pending(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    ok, reason = loop_may_continue(tmp_path)
    assert ok
    assert "pending" in reason.lower()


def test_mark_blocked_clears_work(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    mark_pending_blocked(tmp_path, "test block")
    pending = load_pending(tmp_path)
    assert pending["has_work"] is False
    assert pending["status"] == PENDING_STATUS_BLOCKED


def test_build_followup_mentions_phase(tmp_path: Path) -> None:
    _write_pipeline(tmp_path)
    pipeline = json.loads((tmp_path / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    text = build_followup_prompt({"pending_phase": "P2_PREDICTION_OUTCOME_LEDGER"}, pipeline)
    assert "one_new_phase_per_run" in text.lower() or "ONLY" in text


def _write_p7_p9_pipeline(root: Path) -> None:
    p7 = "P7_AUTO_PROMOTION_EXE_VISIBILITY"
    p9 = "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION"
    payload = {
        "auto_continue_after_pass": True,
        "current_phase": p9,
        "control_policy": {
            "enqueue_next_phase_after_pass": True,
            "never_chain_multiple_phases_inside_same_work_unit": True,
            "one_new_phase_per_run": True,
        },
        "phases": [
            {"id": p7, "status": "PASS", "next_phase": p9, "goal": "P7 goal"},
            {
                "id": p9,
                "status": "NOT_STARTED",
                "next_phase": None,
                "goal": "Champion als Referenz belassen; Challenger nur Shadow/Paper prüfen; M1-Kontrolle; keine Promotion.",
            },
        ],
    }
    (root / "DEVELOPMENT_PIPELINE.json").write_text(json.dumps(payload), encoding="utf-8")


def test_p7_pass_allows_transition_to_p9(tmp_path: Path) -> None:
    _write_p7_p9_pipeline(tmp_path)
    ok, msg = enqueue_eligible_phase(tmp_path)
    assert ok, msg
    pending = load_pending(tmp_path)
    assert pending["pending_phase"] == "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION"
    assert pending["created_from_phase"] == "P7_AUTO_PROMOTION_EXE_VISIBILITY"


def test_p9_consistent_in_json_and_yaml(tmp_path: Path) -> None:
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _write_p7_p9_pipeline(tmp_path)
    pipeline = json.loads((tmp_path / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    _sync_pipeline_yaml(tmp_path, pipeline)
    yaml_text = (tmp_path / "DEVELOPMENT_PIPELINE.yaml").read_text(encoding="utf-8")
    assert "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION" in yaml_text
    assert "P7_AUTO_PROMOTION_EXE_VISIBILITY" in yaml_text
    assert "next_phase: P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION" in yaml_text


def test_p9_pending_not_cleared_by_maintenance(tmp_path: Path) -> None:
    _write_p7_p9_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    merge_maintenance_details(tmp_path, details={"m1_complete": True}, maintenance_has_work=False)
    pending = load_pending(tmp_path)
    assert pending["has_work"] is True
    assert pending["pending_phase"] == "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION"


def test_next_cursor_prompt_for_p9(tmp_path: Path) -> None:
    from aa_control_plane import write_next_cursor_prompt
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _write_p7_p9_pipeline(tmp_path)
    enqueue_eligible_phase(tmp_path)
    pipeline = json.loads((tmp_path / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    _sync_pipeline_yaml(tmp_path, pipeline)
    write_next_cursor_prompt(tmp_path, pipeline)
    text = (tmp_path / "NEXT_CURSOR_PROMPT.md").read_text(encoding="utf-8")
    assert "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION" in text
    assert "unknown" not in text.lower()
    assert "Do NOT change the active champion" in text
