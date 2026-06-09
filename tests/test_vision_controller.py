"""Tests for aa_vision_controller — V1R3 authorized completion gate."""
from __future__ import annotations

from aa_doc_paths import doc_path, doc_rel, write_root_doc_file

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from aa_vision_controller import (
    PENDING_EXTERNAL_SEAL,
    REVIEW_REGISTRY,
    TRANSITION_LOG,
    V1R3_PHASE,
    V1R3_REVIEW_ZIP,
    AUTOMATION_STATE,
    STATUS_AUTHORIZED,
    STATUS_AWAITING,
    STATUS_RUNNING,
    STATUS_TESTS_PASSED,
    begin_authorized_phase,
    bootstrap_vision_automation,
    complete_authorized_phase,
    load_automation_state,
    precheck_start_phase,
    record_phase_test_pass,
    register_external_approval,
    run_authorized_phase_pipeline,
    seal_predecessor_review,
    select_next_phase_automatically,
    write_review_sidecar,
)
from aa_vision_phase_catalog import sync_phase_catalog

V1R2_HASH = "595d5fc0f5cf8d399ef5ba066fdb9973994aa46e94c3740960ea08c7a5921017"


def _status_files(root: Path) -> None:
    (root / "control" / "auto_promotion_status.json").write_text(
        json.dumps(
            {
                "champion_variant_id": "R3_w075_q065_noexit",
                "promotion_allowed": False,
                "auto_execute_real_money_enabled": False,
                "automation_modes": {
                    "AUTO_RESEARCH": "DISABLED",
                    "AUTO_PROMOTE_PAPER": "DISABLED",
                    "AUTO_PROMOTE_SIGNAL": "DISABLED",
                    "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
                },
                "gate_evaluation": {"promotion_allowed": False, "gates": {}},
            }
        ),
        encoding="utf-8",
    )
    (root / "control" / "promotion_status.json").write_text(
        json.dumps({"all_gates_pass": False, "auto_execute_real_money": False}),
        encoding="utf-8",
    )


def _root(tmp_path: Path) -> Path:
    (tmp_path / ".cursor").mkdir(parents=True)
    (tmp_path / ".cursor" / "hooks.json").write_text('{"version":1,"hooks":{}}', encoding="utf-8")
    cfg = {
        "auto_research_enabled": False,
        "auto_promote_paper_enabled": False,
        "auto_promote_signal_enabled": False,
        "auto_execute_real_money_enabled": False,
    }
    (tmp_path / "promotion_gate_config.yaml").write_text(yaml.dump(cfg), encoding="utf-8")
    (tmp_path / "control").mkdir()
    _status_files(tmp_path)
    (tmp_path / "control" / "system_health.json").write_text(
        json.dumps({"operational_health": "OK", "critical_errors": []}),
        encoding="utf-8",
    )
    (tmp_path / "control" / "last_known_good_state.json").write_text(
        json.dumps({"validated_variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    sync_phase_catalog(tmp_path)
    return tmp_path


def _write_v1r3_approval(root: Path, *, hash_value: str = V1R2_HASH) -> None:
    (root / "EXTERNAL_REVIEW_APPROVAL_V1R3.md").write_text(
        f"""# External Review Approval — V1R3

V1R3_AUTHORIZED_COMPLETION_GATE

Observed external SHA-256: `{hash_value}`
""",
        encoding="utf-8",
    )


def _seed_v1r2_awaiting_v1r3(root: Path) -> None:
    from aa_safe_io import atomic_write_json

    bootstrap_vision_automation(root)
    atomic_write_json(
        root / AUTOMATION_STATE,
        {
            "current_executed_phase": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "expected_next_phase": V1R3_PHASE,
            "execution_status": STATUS_AWAITING,
            "authorized_phase": "",
            "current_running_phase": "",
        },
    )
    atomic_write_json(
        root / REVIEW_REGISTRY,
        {
            "schema_version": 1,
            "program": "MARKTANALYSE_DECISION_COCKPIT",
            "reviews": [
                {
                    "phase_id": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
                    "review_zip": "codex_v1r2_review_chain_review.zip",
                    "review_zip_sha256": PENDING_EXTERNAL_SEAL,
                }
            ],
        },
    )


def _seed_v1r2_with_sidecar(root: Path) -> None:
    _seed_v1r2_awaiting_v1r3(root)
    zip_bytes = b"v1r2-review-content"
    actual = hashlib.sha256(zip_bytes).hexdigest()
    (root / "codex_v1r2_review_chain_review.zip").write_bytes(zip_bytes)
    write_review_sidecar(root, "codex_v1r2_review_chain_review.zip", actual)
    return None


def _log_lines(root: Path) -> int:
    path = root / TRANSITION_LOG
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _run_through_tests_passed(root: Path) -> str:
    _write_v1r3_approval(root)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is True
    begin = begin_authorized_phase(root, V1R3_PHASE)
    assert begin["started"] is True
    test_rel = doc_rel("CODEX_V1R3_TEST_OUTPUT.txt")
    test_path = write_root_doc_file(root, "CODEX_V1R3_TEST_OUTPUT.txt", "pass\n")
    test_hash = hashlib.sha256(test_path.read_bytes()).hexdigest()
    rec = record_phase_test_pass(
        root,
        phase_id=V1R3_PHASE,
        test_output_file=test_rel,
        test_output_sha256=test_hash,
    )
    assert rec["recorded"] is True
    return test_rel


# --- Catalog / chain (via controller registration) ---


def test_v2_accepts_only_v1r3_predecessor_not_v1r2(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    (root / "EXTERNAL_REVIEW_APPROVAL_V2.md").write_text(
        f"V2_COST_STRESS_AND_ROBUSTNESS_ENGINE\nObserved external SHA-256: `{V1R2_HASH}`\n",
        encoding="utf-8",
    )
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        root / AUTOMATION_STATE,
        {
            "current_executed_phase": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "expected_next_phase": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
            "execution_status": STATUS_AWAITING,
            "authorized_phase": "",
        },
    )
    reg = register_external_approval(root, phase_id="V2_COST_STRESS_AND_ROBUSTNESS_ENGINE")
    assert reg["registered"] is False
    assert "transition_not_allowed" in reg["errors"] or "expected_next_phase_mismatch" in reg["errors"]


def test_v1r2_cannot_authorize_v2_directly(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        root / AUTOMATION_STATE,
        {
            "current_executed_phase": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "expected_next_phase": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
            "execution_status": STATUS_AWAITING,
            "authorized_phase": "",
        },
    )
    (root / "EXTERNAL_REVIEW_APPROVAL_V2.md").write_text(
        f"V2_COST_STRESS_AND_ROBUSTNESS_ENGINE\nObserved external SHA-256: `{V1R2_HASH}`\n",
        encoding="utf-8",
    )
    reg = register_external_approval(root, phase_id="V2_COST_STRESS_AND_ROBUSTNESS_ENGINE")
    assert reg["registered"] is False


def test_v1r3_seals_v1r2_with_observed_hash(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is True
    registry = json.loads((root / REVIEW_REGISTRY).read_text(encoding="utf-8"))
    v1r2 = next(r for r in registry["reviews"] if r["phase_id"] == "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING")
    assert v1r2["external_sealed"] is True
    assert v1r2["review_zip_sha256"] == V1R2_HASH


def test_v1r3_review_stays_pending_after_completion(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _run_through_tests_passed(root)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is True
    assert comp["state"]["last_review_zip_sha256"] == PENDING_EXTERNAL_SEAL
    registry = json.loads((root / REVIEW_REGISTRY).read_text(encoding="utf-8"))
    v1r3 = next(r for r in registry["reviews"] if r["phase_id"] == V1R3_PHASE)
    assert v1r3["review_zip_sha256"] == PENDING_EXTERNAL_SEAL
    assert v1r3["external_sealed"] is False


# --- Authorization ---


def test_no_approval_file_blocks(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is False
    assert "approval_file_missing_or_template" in reg["errors"]


def test_template_approval_blocks(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    (root / "TEMPLATE_EXTERNAL_REVIEW_APPROVAL_V1R3.md").write_text(
        f"V1R3_AUTHORIZED_COMPLETION_GATE\nObserved external SHA-256: `{V1R2_HASH}`\n",
        encoding="utf-8",
    )
    reg = register_external_approval(
        root, phase_id=V1R3_PHASE, approval_filename="TEMPLATE_EXTERNAL_REVIEW_APPROVAL_V1R3.md"
    )
    assert reg["registered"] is False


def test_wrong_predecessor_hash_blocks(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    zip_bytes = b"v1r2-review-content"
    actual = hashlib.sha256(zip_bytes).hexdigest()
    (root / "codex_v1r2_review_chain_review.zip").write_bytes(zip_bytes)
    write_review_sidecar(root, "codex_v1r2_review_chain_review.zip", actual)
    _write_v1r3_approval(root, hash_value="0" * 64)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is False
    assert "predecessor_zip_hash_mismatch_sidecar" in reg["errors"]


def test_wrong_predecessor_state_blocks(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        root / AUTOMATION_STATE,
        {
            "current_executed_phase": "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
            "expected_next_phase": V1R3_PHASE,
            "execution_status": STATUS_AWAITING,
            "authorized_phase": "",
        },
    )
    _write_v1r3_approval(root)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is False


def test_missing_safety_evidence_blocks(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    (root / "control" / "last_known_good_state.json").write_text("{}", encoding="utf-8")
    _write_v1r3_approval(root)
    reg = register_external_approval(root, phase_id=V1R3_PHASE)
    assert reg["registered"] is False


# --- Begin state ---


def test_begin_blocks_without_authorized_not_started(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    begin = begin_authorized_phase(root, V1R3_PHASE)
    assert begin["started"] is False


def test_begin_blocks_wrong_phase(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    begin = begin_authorized_phase(root, "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE")
    assert begin["started"] is False


def test_begin_sets_running_state(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    begin = begin_authorized_phase(root, V1R3_PHASE)
    assert begin["started"] is True
    state = load_automation_state(root)
    assert state["execution_status"] == STATUS_RUNNING
    assert state["current_running_phase"] == V1R3_PHASE


# --- Test PASS ---


def test_test_pass_blocks_without_running(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    rec = record_phase_test_pass(
        root,
        phase_id=V1R3_PHASE,
        test_output_file="out.txt",
        test_output_sha256="a" * 64,
    )
    assert rec["recorded"] is False


def test_test_pass_blocks_missing_file(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    begin_authorized_phase(root, V1R3_PHASE)
    rec = record_phase_test_pass(
        root,
        phase_id=V1R3_PHASE,
        test_output_file="missing.txt",
        test_output_sha256="a" * 64,
    )
    assert rec["recorded"] is False


def test_test_pass_blocks_hash_mismatch(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    begin_authorized_phase(root, V1R3_PHASE)
    (root / "out.txt").write_text("x", encoding="utf-8")
    rec = record_phase_test_pass(
        root,
        phase_id=V1R3_PHASE,
        test_output_file="out.txt",
        test_output_sha256="0" * 64,
    )
    assert rec["recorded"] is False


def test_test_pass_sets_ready_to_complete(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _run_through_tests_passed(root)
    state = load_automation_state(root)
    assert state["execution_status"] == STATUS_TESTS_PASSED
    assert state["test_result"] == "PASS"


# --- Completion ---


def test_completion_blocks_without_authorized_phase(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is False


def test_completion_blocks_without_running(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is False


def test_completion_blocks_without_test_pass(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    register_external_approval(root, phase_id=V1R3_PHASE)
    begin_authorized_phase(root, V1R3_PHASE)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is False


def test_completion_blocks_wrong_review_zip(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _run_through_tests_passed(root)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name="wrong.zip")
    assert comp["completed"] is False


def test_completion_blocks_on_safety_failure(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _run_through_tests_passed(root)
    (root / "control" / "auto_promotion_status.json").write_text(
        json.dumps({"promotion_allowed": True, "champion_variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is False


def test_blocked_completion_leaves_state_registry_log_unchanged(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    state_before = (root / AUTOMATION_STATE).read_text(encoding="utf-8")
    registry_before = (root / REVIEW_REGISTRY).read_text(encoding="utf-8")
    logs_before = _log_lines(root)
    comp = complete_authorized_phase(root, phase_id=V1R3_PHASE, review_zip_name=V1R3_REVIEW_ZIP)
    assert comp["completed"] is False
    assert (root / AUTOMATION_STATE).read_text(encoding="utf-8") == state_before
    assert (root / REVIEW_REGISTRY).read_text(encoding="utf-8") == registry_before
    assert _log_lines(root) == logs_before


def test_full_pipeline_completes_v1r3(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    _write_v1r3_approval(root)
    test_rel = doc_rel("CODEX_V1R3_TEST_OUTPUT.txt")
    write_root_doc_file(root, "CODEX_V1R3_TEST_OUTPUT.txt", "ok\n")
    result = run_authorized_phase_pipeline(
        root,
        phase_id=V1R3_PHASE,
        review_zip_name=V1R3_REVIEW_ZIP,
        test_output_file=test_rel,
    )
    assert result["ok"] is True
    state = load_automation_state(root)
    assert state["current_executed_phase"] == V1R3_PHASE
    assert state["expected_next_phase"] == "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE"
    assert state["execution_status"] == STATUS_AWAITING
    assert state["authorized_phase"] == ""
    assert state["current_running_phase"] == ""


def test_direct_seal_bypass_removed(tmp_path: Path):
    root = _root(tmp_path)
    seal = seal_predecessor_review(root, predecessor_phase_id="V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING", observed_hash=V1R2_HASH)
    assert seal["ok"] is False


def test_v2_not_authorized_without_state_machine(tmp_path: Path):
    root = _root(tmp_path)
    _seed_v1r2_awaiting_v1r3(root)
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        root / AUTOMATION_STATE,
        {
            "current_executed_phase": V1R3_PHASE,
            "expected_next_phase": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
            "execution_status": STATUS_AWAITING,
            "authorized_phase": "",
        },
    )
    result = precheck_start_phase(root, "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE")
    assert result["authorized"] is False


def test_v3_no_auto_branch(tmp_path: Path):
    root = _root(tmp_path)
    bootstrap_vision_automation(root)
    assert select_next_phase_automatically(root, "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION") is None


def test_complete_v1r2_bypass_raises():
    from aa_vision_controller import complete_v1r2_phase

    with pytest.raises(RuntimeError, match="bypass removed"):
        complete_v1r2_phase(Path("."))
