"""Repository-side gated cascade controller — no operative job execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_evidence_schema import LOCKED_CHAMPION
from aa_experiment_registry import ensure_initial_experiment
from aa_safe_io import atomic_write_json, atomic_write_text
from aa_vision_phase_catalog import (
    build_default_catalog,
    get_phase,
    is_transition_allowed,
    pending_branch_options,
    sync_phase_catalog,
)
from aa_vision_review_gate import (
    _common_prechecks,
    file_sha256 as gate_file_sha256,
    is_template_path,
    parse_predecessor_zip_hash,
    validate_approval_content,
    verify_sidecar_hash,
)

VISION_ROOT = Path("control") / "vision_automation"
AUTOMATION_STATE = VISION_ROOT / "automation_state.json"
CASCADE_POLICY = VISION_ROOT / "cascade_policy.json"
TRANSITION_LOG = VISION_ROOT / "transition_log.jsonl"
REVIEW_REGISTRY = VISION_ROOT / "review_registry" / "review_registry.json"

PENDING_EXTERNAL_SEAL = "PENDING_EXTERNAL_SEAL"

V1R3_PHASE = "V1R3_AUTHORIZED_COMPLETION_GATE"
V1R3_REVIEW_ZIP = "codex_v1r3_authorized_completion_review.zip"

STATUS_AWAITING = "AWAITING_EXTERNAL_REVIEW"
STATUS_AUTHORIZED = "AUTHORIZED_NOT_STARTED"
STATUS_RUNNING = "RUNNING_AUTHORIZED_PHASE"
STATUS_TESTS_PASSED = "TESTS_PASSED_READY_TO_COMPLETE"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_cascade_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "policy": "FAIL_CLOSED_EXTERNAL_REVIEW_GATED",
        "global_invariants": {
            "locked_champion_variant": LOCKED_CHAMPION,
            "require_hooks_disabled": True,
            "require_git_available": True,
            "require_atomic_control_writes": True,
            "auto_research_must_be_disabled_by_default": True,
            "auto_promote_paper_must_be_disabled": True,
            "auto_promote_signal_must_be_disabled": True,
            "auto_execute_real_money_must_be_disabled": True,
            "real_money_execution_never_allowed": True,
            "autonomous_promotion_never_allowed": True,
            "exe_execution_by_automation_never_allowed": True,
        },
        "review_rules": {
            "external_approval_required_before_each_phase": True,
            "review_zip_required_after_each_phase": True,
            "authorized_completion_chain_required": True,
            "test_pass_required_before_completion": True,
            "codex_may_create_future_approval_files": False,
            "review_zip_sidecar_required": True,
            "review_zip_self_hash_forbidden": True,
            "predecessor_from_current_executed_phase": True,
        },
        "operational_rules": {
            "historical_computation_requires_specific_phase_approval": True,
            "shadow_activation_requires_separate_phase": True,
            "paper_activation_requires_separate_phase": True,
            "exe_build_requires_v5_approval": True,
        },
    }


def ensure_vision_directories(root: Path) -> None:
    root = Path(root)
    base = root / VISION_ROOT
    for sub in ("authorization_checks", "run_logs", "review_registry", "templates", "authorized_tasks"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (root / "control" / "evidence").mkdir(parents=True, exist_ok=True)


def bootstrap_vision_automation(root: Path) -> Dict[str, Path]:
    root = Path(root)
    ensure_vision_directories(root)
    ensure_initial_experiment(root)
    paths: Dict[str, Path] = {"phase_catalog": sync_phase_catalog(root)}
    policy_path = root / CASCADE_POLICY
    if not policy_path.is_file():
        atomic_write_json(policy_path, build_cascade_policy())
    paths["cascade_policy"] = policy_path
    if not (root / AUTOMATION_STATE).is_file():
        atomic_write_json(root / AUTOMATION_STATE, _default_automation_state(root))
    paths["automation_state"] = root / AUTOMATION_STATE
    registry_path = root / REVIEW_REGISTRY
    if not registry_path.is_file():
        atomic_write_json(
            registry_path,
            {"schema_version": 1, "program": "MARKTANALYSE_DECISION_COCKPIT", "reviews": []},
        )
    paths["review_registry"] = registry_path
    log_path = root / TRANSITION_LOG
    if not log_path.is_file():
        atomic_write_text(log_path, "")
    paths["transition_log"] = log_path
    return paths


def _default_automation_state(root: Path) -> Dict[str, Any]:
    return {
        "schema_version": 3,
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "mode": "CONTROLLED_PHASE_EXECUTION",
        "controller_policy": "EXTERNAL_REVIEW_GATED",
        "current_executed_phase": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
        "expected_next_phase": V1R3_PHASE,
        "authorized_phase": "",
        "current_running_phase": "",
        "execution_status": STATUS_AWAITING,
        "test_result": None,
        "test_output_file": None,
        "test_output_sha256": None,
        "tests_recorded_at_utc": None,
        "phase_catalog_path": str(VISION_ROOT / "phase_catalog.json").replace("\\", "/"),
        "cascade_policy_path": str(CASCADE_POLICY).replace("\\", "/"),
        "approval_file_pattern": "EXTERNAL_REVIEW_APPROVAL_<PHASE_KEY>.md",
        "template_file_prefix": "TEMPLATE_",
        "external_review_required_after_each_phase": True,
        "auto_research_allowed": False,
        "auto_promotion_allowed": False,
        "real_money_execution_allowed": False,
        "exe_build_allowed": False,
        "exe_execution_allowed": False,
        "operative_jobs_allowed": False,
        "last_review_zip": "codex_v1r2_review_chain_review.zip",
        "last_review_zip_sha256": PENDING_EXTERNAL_SEAL,
        "last_external_approval_file": "",
        "last_external_approval_sha256": "",
    }


def append_transition_log(root: Path, entry: Dict[str, Any]) -> None:
    path = Path(root) / TRANSITION_LOG
    line = json.dumps({**entry, "logged_at_utc": _utc_now()}, sort_keys=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_automation_state(root: Path) -> Dict[str, Any]:
    return _read_json(Path(root) / AUTOMATION_STATE)


def save_automation_state(root: Path, state: Dict[str, Any]) -> Path:
    path = Path(root) / AUTOMATION_STATE
    atomic_write_json(path, state)
    return path


def _find_reviews_for_phase(root: Path, phase_id: str) -> List[Dict[str, Any]]:
    registry = _read_json(Path(root) / REVIEW_REGISTRY)
    return [r for r in (registry.get("reviews") or []) if r.get("phase_id") == phase_id]


def _seal_predecessor_review_internal(
    root: Path,
    *,
    predecessor_phase_id: str,
    observed_hash: str,
    sealing_approval_file: str,
) -> Dict[str, Any]:
    """Internal — only via register_external_approval."""
    root = Path(root)
    result: Dict[str, Any] = {"ok": False, "errors": []}
    matches = _find_reviews_for_phase(root, predecessor_phase_id)
    if len(matches) != 1:
        result["errors"].append("predecessor_review_not_unique")
        return result

    pred_review = matches[0]
    pred_zip = str(pred_review.get("review_zip") or "")
    sidecar = root / f"{pred_zip}.sha256"
    zip_path = root / pred_zip
    observed = observed_hash.lower()

    if sidecar.is_file() and zip_path.is_file():
        ok, detail = verify_sidecar_hash(zip_path, sidecar)
        if not ok or detail.lower() != observed:
            result["errors"].append("predecessor_zip_hash_mismatch_sidecar")
            return result
    else:
        stored = str(pred_review.get("review_zip_sha256") or "").lower()
        if stored and stored not in {PENDING_EXTERNAL_SEAL.lower(), ""}:
            if stored != observed:
                result["errors"].append("predecessor_zip_hash_mismatch_registry")
                return result

    registry_path = root / REVIEW_REGISTRY
    registry = _read_json(registry_path)
    updated: List[Dict[str, Any]] = []
    sealed = False
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == predecessor_phase_id:
            entry = dict(entry)
            entry["review_zip_sha256"] = observed
            entry["external_sealed"] = True
            entry["external_sealed_by_approval"] = sealing_approval_file
            entry["external_sealed_at_utc"] = _utc_now()
            sealed = True
        updated.append(entry)
    if not sealed:
        result["errors"].append("predecessor_review_not_found")
        return result
    registry["reviews"] = updated
    atomic_write_json(registry_path, registry)
    result["ok"] = True
    return result


def register_external_approval(
    root: Path,
    *,
    phase_id: str,
    approval_filename: Optional[str] = None,
) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"registered": False, "phase_id": phase_id, "errors": []}

    state = load_automation_state(root)
    if state.get("execution_status") != STATUS_AWAITING:
        result["errors"].append("execution_status_not_awaiting_external_review")

    expected = str(state.get("expected_next_phase") or "")
    pending = [str(p) for p in (state.get("pending_external_branch_options") or [])]
    branch_selection = not expected and phase_id in pending
    if expected != phase_id and not branch_selection:
        result["errors"].append("expected_next_phase_mismatch")
    if branch_selection and phase_id == "V3S_SHADOW_OBSERVATION_ACTIVATION":
        result["errors"].append("v3s_branch_not_selected_via_this_approval")

    predecessor = str(state.get("current_executed_phase") or "")
    if not predecessor:
        result["errors"].append("current_executed_phase_missing")

    phase = get_phase(root, phase_id)
    if not phase:
        result["errors"].append("unknown_phase")
        return result

    if predecessor and not is_transition_allowed(root, predecessor, phase_id):
        result["errors"].append("transition_not_allowed")

    if predecessor and len(_find_reviews_for_phase(root, predecessor)) != 1:
        result["errors"].append("predecessor_review_not_completed")

    approval_name = approval_filename or phase.get("approval_file")
    if not approval_name:
        result["errors"].append("no_approval_file")
        return result

    approval_path = root / str(approval_name)
    if is_template_path(approval_path) or not approval_path.is_file():
        result["errors"].append("approval_file_missing_or_template")
        return result

    text = approval_path.read_text(encoding="utf-8")
    ok_content, content_errors = validate_approval_content(text, phase_id)
    if not ok_content:
        result["errors"].extend(content_errors)

    observed_hash = parse_predecessor_zip_hash(text)
    if predecessor and not observed_hash:
        result["errors"].append("predecessor_zip_hash_missing_in_approval")

    result["errors"].extend(_common_prechecks(root, phase_id))

    if result["errors"]:
        return result

    if predecessor and observed_hash:
        seal = _seal_predecessor_review_internal(
            root,
            predecessor_phase_id=predecessor,
            observed_hash=observed_hash,
            sealing_approval_file=str(approval_name),
        )
        if not seal["ok"]:
            result["errors"].extend(seal["errors"])
            return result

    approval_hash = gate_file_sha256(approval_path)
    new_state = dict(state)
    new_state["authorized_phase"] = phase_id
    new_state["execution_status"] = STATUS_AUTHORIZED
    new_state["current_running_phase"] = ""
    new_state["last_external_approval_file"] = str(approval_name)
    new_state["last_external_approval_sha256"] = approval_hash
    new_state["test_result"] = None
    new_state["test_output_file"] = None
    new_state["test_output_sha256"] = None
    new_state["tests_recorded_at_utc"] = None
    if branch_selection:
        new_state["expected_next_phase"] = phase_id
        new_state["pending_external_branch_options"] = []
        new_state["selected_external_branch"] = phase_id
    save_automation_state(root, new_state)
    append_transition_log(
        root,
        {
            "event": "external_approval_registered",
            "phase_id": phase_id,
            "approval_file": approval_name,
            "prior_status": STATUS_AWAITING,
            "new_status": STATUS_AUTHORIZED,
        },
    )
    result["registered"] = True
    result["approval_sha256"] = approval_hash
    result["predecessor_phase"] = predecessor
    return result


def begin_authorized_phase(root: Path, phase_id: str) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"started": False, "phase_id": phase_id, "errors": []}
    state = load_automation_state(root)

    if state.get("authorized_phase") != phase_id:
        result["errors"].append("authorized_phase_mismatch")
    if state.get("execution_status") != STATUS_AUTHORIZED:
        result["errors"].append("execution_status_not_authorized_not_started")

    if result["errors"]:
        return result

    prior = state.get("execution_status")
    new_state = dict(state)
    new_state["current_running_phase"] = phase_id
    new_state["execution_status"] = STATUS_RUNNING
    save_automation_state(root, new_state)
    append_transition_log(
        root,
        {
            "event": "phase_running",
            "phase_id": phase_id,
            "prior_status": prior,
            "new_status": STATUS_RUNNING,
        },
    )
    result["started"] = True
    return result


def record_phase_test_pass(
    root: Path,
    *,
    phase_id: str,
    test_output_file: str,
    test_output_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"recorded": False, "phase_id": phase_id, "errors": []}
    state = load_automation_state(root)

    if state.get("authorized_phase") != phase_id:
        result["errors"].append("authorized_phase_mismatch")
    if state.get("current_running_phase") != phase_id:
        result["errors"].append("current_running_phase_mismatch")
    if state.get("execution_status") != STATUS_RUNNING:
        result["errors"].append("execution_status_not_running")

    test_path = root / test_output_file
    if not test_path.is_file():
        result["errors"].append("test_output_file_missing")

    actual_hash = gate_file_sha256(test_path) if test_path.is_file() else ""
    expected_hash = (test_output_sha256 or actual_hash).lower()
    if test_path.is_file() and actual_hash.lower() != expected_hash:
        result["errors"].append("test_output_sha256_mismatch")

    if result["errors"]:
        return result

    prior = state.get("execution_status")
    new_state = dict(state)
    new_state["test_result"] = "PASS"
    new_state["test_output_file"] = test_output_file.replace("\\", "/")
    new_state["test_output_sha256"] = expected_hash
    new_state["tests_recorded_at_utc"] = _utc_now()
    new_state["execution_status"] = STATUS_TESTS_PASSED
    save_automation_state(root, new_state)
    append_transition_log(
        root,
        {
            "event": "phase_tests_passed",
            "phase_id": phase_id,
            "test_output_file": test_output_file,
            "prior_status": prior,
            "new_status": STATUS_TESTS_PASSED,
        },
    )
    result["recorded"] = True
    return result


def complete_authorized_phase(
    root: Path,
    *,
    phase_id: str,
    review_zip_name: str,
) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"completed": False, "phase_id": phase_id, "errors": []}

    state = load_automation_state(root)
    phase = get_phase(root, phase_id)
    if not phase:
        result["errors"].append("unknown_phase")
        return result

    catalog_zip = str(phase.get("review_zip") or "")
    if catalog_zip != review_zip_name:
        result["errors"].append("review_zip_name_mismatch")

    if state.get("authorized_phase") != phase_id:
        result["errors"].append("authorized_phase_mismatch")
    if state.get("current_running_phase") != phase_id:
        result["errors"].append("current_running_phase_mismatch")
    if state.get("execution_status") != STATUS_TESTS_PASSED:
        result["errors"].append("execution_status_not_tests_passed")
    if state.get("test_result") != "PASS":
        result["errors"].append("test_result_not_pass")

    test_file = str(state.get("test_output_file") or "")
    test_hash = str(state.get("test_output_sha256") or "")
    if not test_file:
        result["errors"].append("test_output_file_missing_in_state")
    else:
        tp = root / test_file
        if not tp.is_file():
            result["errors"].append("test_output_file_missing")
        elif gate_file_sha256(tp).lower() != test_hash.lower():
            result["errors"].append("test_output_sha256_mismatch")

    if not state.get("last_external_approval_file") or not state.get("last_external_approval_sha256"):
        result["errors"].append("approval_not_stored_in_state")

    result["errors"].extend(_common_prechecks(root, phase_id))

    if result["errors"]:
        return result

    expected_next = phase.get("allowed_next_after_external_review")
    branch_opts = pending_branch_options(root, phase_id)
    if branch_opts:
        next_phase = None
    elif isinstance(expected_next, str) and " OR " not in expected_next:
        next_phase = expected_next
    else:
        next_phase = None

    prior_status = state.get("execution_status")
    approval_file = state.get("last_external_approval_file")
    approval_hash = state.get("last_external_approval_sha256")

    new_state = dict(state)
    new_state["current_executed_phase"] = phase_id
    new_state["expected_next_phase"] = next_phase or ""
    if branch_opts:
        new_state["pending_external_branch_options"] = branch_opts
    else:
        new_state.pop("pending_external_branch_options", None)
    new_state["next_phase_authorized"] = False
    new_state["authorized_phase"] = ""
    new_state["current_running_phase"] = ""
    new_state["execution_status"] = STATUS_AWAITING
    new_state["last_review_zip"] = review_zip_name
    new_state["last_review_zip_sha256"] = PENDING_EXTERNAL_SEAL
    new_state["test_result"] = None
    new_state["test_output_file"] = None
    new_state["test_output_sha256"] = None
    new_state["tests_recorded_at_utc"] = None
    save_automation_state(root, new_state)

    registry_path = root / REVIEW_REGISTRY
    registry = _read_json(registry_path)
    reviews = [r for r in (registry.get("reviews") or []) if r.get("phase_id") != phase_id]
    reviews.append(
        {
            "phase_id": phase_id,
            "phase_key": phase.get("phase_key", phase_id.split("_")[0]),
            "approval_file": approval_file,
            "approval_sha256": approval_hash,
            "review_zip": review_zip_name,
            "review_zip_sha256": PENDING_EXTERNAL_SEAL,
            "external_sealed": False,
            "completed_at_utc": _utc_now(),
            "execution_status": STATUS_AWAITING,
            "champion_changed": False,
            "promotion_executed": False,
            "real_money_executed": False,
            "operative_jobs_executed": False,
            "exe_built": False,
            "exe_executed": False,
            "blockers": [],
        }
    )
    registry["reviews"] = reviews
    atomic_write_json(registry_path, registry)

    append_transition_log(
        root,
        {
            "event": "phase_completed",
            "phase_id": phase_id,
            "review_zip": review_zip_name,
            "approval_file": approval_file,
            "prior_status": prior_status,
            "new_status": STATUS_AWAITING,
        },
    )
    result["completed"] = True
    result["state"] = new_state
    return result


def run_authorized_phase_pipeline(
    root: Path,
    *,
    phase_id: str,
    review_zip_name: str,
    test_output_file: str,
    approval_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Full authorized chain — the only supported completion path."""
    root = Path(root)
    reg = register_external_approval(root, phase_id=phase_id, approval_filename=approval_filename)
    if not reg.get("registered"):
        return {"ok": False, "step": "register", "errors": reg.get("errors", [])}

    begin = begin_authorized_phase(root, phase_id)
    if not begin.get("started"):
        return {"ok": False, "step": "begin", "errors": begin.get("errors", [])}

    test_path = root / test_output_file
    if not test_path.is_file():
        return {"ok": False, "step": "tests", "errors": ["test_output_file_missing"]}

    test_hash = gate_file_sha256(test_path)
    rec = record_phase_test_pass(
        root,
        phase_id=phase_id,
        test_output_file=test_output_file,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        return {"ok": False, "step": "record_tests", "errors": rec.get("errors", [])}

    comp = complete_authorized_phase(root, phase_id=phase_id, review_zip_name=review_zip_name)
    if not comp.get("completed"):
        return {"ok": False, "step": "complete", "errors": comp.get("errors", [])}

    return {"ok": True, "step": "complete", "state": comp.get("state")}


def precheck_authorized_phase(root: Path, phase_id: str) -> Dict[str, Any]:
    root = Path(root)
    result: Dict[str, Any] = {"authorized": False, "phase_id": phase_id, "errors": []}
    state = load_automation_state(root)
    if state.get("authorized_phase") != phase_id:
        result["errors"].append("authorized_phase_mismatch")
    if state.get("execution_status") not in {STATUS_AUTHORIZED, STATUS_RUNNING, STATUS_TESTS_PASSED}:
        result["errors"].append("execution_status_not_authorized")
    result["errors"].extend(_common_prechecks(root, phase_id))
    if not result["errors"]:
        result["authorized"] = True
    return result


def precheck_start_phase(root: Path, phase_id: str, *, predecessor: Optional[str] = None) -> Dict[str, Any]:
    result = precheck_authorized_phase(root, phase_id)
    if not result["authorized"]:
        result["errors"].append("approval_file_alone_insufficient_use_state_machine")
    state = load_automation_state(root)
    if state.get("expected_next_phase") != phase_id:
        result["authorized"] = False
        result["errors"].append("expected_next_phase_mismatch")
    if predecessor and predecessor != state.get("current_executed_phase"):
        result["authorized"] = False
        result["errors"].append("explicit_predecessor_mismatch_with_state")
    return result


def seal_predecessor_review(*args, **kwargs) -> Dict[str, Any]:
    """Bypass removed — sealing only occurs inside register_external_approval."""
    return {"ok": False, "errors": ["direct_seal_predecessor_review_bypass_removed"]}


def complete_v1r2_phase(root: Path) -> Dict[str, Any]:
    raise RuntimeError("complete_v1r2_phase bypass removed; use run_authorized_phase_pipeline")


def complete_v1_phase(*args, **kwargs) -> Dict[str, Any]:
    raise RuntimeError("complete_v1_phase bypass removed; use run_authorized_phase_pipeline")


def select_next_phase_automatically(root: Path, current_phase: str) -> Optional[str]:
    phase = get_phase(root, current_phase)
    if not phase:
        return None
    if phase.get("automatic_selection_allowed") is False:
        return None
    if pending_branch_options(root, current_phase):
        return None
    allowed = phase.get("allowed_next_after_external_review")
    if isinstance(allowed, str) and " OR " in allowed:
        return None
    return None


def write_review_sidecar(root: Path, zip_name: str, sha256_hex: str) -> Path:
    sidecar = Path(root) / f"{zip_name}.sha256"
    atomic_write_text(sidecar, f"{sha256_hex.lower()}  {zip_name}\n")
    return sidecar
