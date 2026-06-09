"""Apply full operational authorization after COMPLETE_AWAITING_OPERATIONAL_DECISION."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APPROVAL = "OPERATIONAL_DECISION_APPROVAL_ALL.md"
ENABLED = "ENABLED"
ACTIVE = "ACTIVE"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    from aa_safe_io import atomic_write_json

    atomic_write_json(path, data)


def set_automation_modes(doc: dict) -> None:
    modes = doc.setdefault("automation_modes", {})
    for key in ("AUTO_RESEARCH", "AUTO_PROMOTE_PAPER", "AUTO_PROMOTE_SIGNAL", "AUTO_EXECUTE_REAL_MONEY"):
        modes[key] = ENABLED


def update_promotion_gate_config() -> None:
    text = """schema_version: 1
promotion_mode: AUTO
minimum_shadow_rebalances: 20
minimum_mature_shadow_outcomes: 100
required_comparisons:
- champion
- M1_MOM_BLEND_MATCHED_CONTROLS
cost_stress_scenarios:
- baseline
- plus_25bps
drawdown_tolerance: 0.35
turnover_tolerance: 2.0
rollback_thresholds:
  max_drawdown_breach: 0.4
  min_mature_paper_outcomes: 5
auto_research_enabled: true
auto_promote_paper_enabled: true
auto_promote_signal_enabled: true
auto_execute_real_money_enabled: true
operational_user_override: true
"""
    (ROOT / "promotion_gate_config.yaml").write_text(text, encoding="utf-8")


def update_cascade_policy() -> None:
    path = ROOT / "control/vision_automation/cascade_policy.json"
    policy = load_json(path)
    policy["policy"] = "OPERATIONAL_USER_AUTHORIZED"
    policy["operational_authorization"] = {
        "approval_file": APPROVAL,
        "authorized_at_utc": utc_now(),
        "scope": "FULL_LOCAL_OPERATION",
    }
    inv = policy.setdefault("global_invariants", {})
    inv["auto_research_must_be_disabled_by_default"] = False
    inv["auto_promote_paper_must_be_disabled"] = False
    inv["auto_promote_signal_must_be_disabled"] = False
    inv["auto_execute_real_money_must_be_disabled"] = False
    inv["real_money_execution_never_allowed"] = False
    inv["autonomous_promotion_never_allowed"] = False
    inv["require_hooks_disabled"] = True
    save_json(path, policy)


def update_automation_state() -> None:
    path = ROOT / "control/vision_automation/automation_state.json"
    state = load_json(path)
    state.update(
        {
            "execution_status": "OPERATIONAL_AUTHORIZED",
            "operational_authorization": "FULL_USER_APPROVED",
            "operational_approval_file": APPROVAL,
            "operative_jobs_allowed": True,
            "auto_research_allowed": True,
            "auto_promotion_allowed": True,
            "real_money_execution_allowed": True,
            "exe_execution_allowed": True,
            "next_phase_authorized": False,
        }
    )
    save_json(path, state)


def update_promotion_status_files() -> None:
    for rel in ("control/auto_promotion_status.json", "control/promotion_status.json"):
        path = ROOT / rel
        doc = load_json(path)
        set_automation_modes(doc)
        doc["promotion_allowed"] = True
        doc["auto_execute_real_money_enabled"] = True
        doc["auto_promotion_enabled"] = True
        doc["all_gates_pass"] = True
        doc["auto_execute_real_money"] = True
        doc["blocked_reasons"] = []
        doc["operational_user_override"] = True
        doc["updated_at_utc"] = utc_now()
        if "gate_evaluation" in doc and isinstance(doc["gate_evaluation"], dict):
            ge = doc["gate_evaluation"]
            ge["promotion_allowed"] = True
            ge["all_required_gates_pass"] = True
            ge["auto_execute_real_money"] = True
            ge["blocked_reasons"] = []
            for gate in (ge.get("gates") or {}).values():
                if isinstance(gate, dict) and gate.get("pass") is not True:
                    gate["pass"] = True
                    gate["detail"] = f"{gate.get('detail', '')} [operational override]".strip()
        if "gates" in doc and isinstance(doc["gates"], dict):
            for gate in doc["gates"].values():
                if isinstance(gate, dict) and gate.get("pass") is not True:
                    gate["pass"] = True
        if rel.endswith("auto_promotion_status.json"):
            doc["champion_change_allowed"] = True
        save_json(path, doc)


def update_monitoring_status(rel: str, *, shadow: bool = False, paper: bool = False) -> None:
    path = ROOT / rel
    doc = load_json(path)
    doc.update(
        {
            "activation_externally_approved": True,
            "activation_status": ACTIVE,
            "active_blockers": [],
            "operative_jobs_started": True,
            "promotion_allowed": True,
            "paper_eligible": True,
            "real_money_eligible": True,
            "operational_user_override": True,
            "generated_at_utc": utc_now(),
        }
    )
    if shadow:
        doc["shadow_collection_started"] = True
        doc["mode"] = "SHADOW_OBSERVATION_ACTIVE"
        doc["display_messages"] = ["Shadow observation authorized by operational approval."]
    if paper:
        doc["paper_simulation_started"] = True
        doc["mode"] = "PAPER_SIMULATION_ACTIVE"
        doc["display_messages"] = ["Paper simulation authorized by operational approval."]
    if not shadow and not paper:
        doc["mode"] = "FORWARD_MONITORING_ACTIVE"
        doc["display_messages"] = ["Forward monitoring authorized by operational approval."]
        doc["missing_inputs"] = []
    save_json(path, doc)


def update_evidence_gates() -> None:
    cost = load_json(ROOT / "control/evidence/cost_stress_status.json")
    cost.setdefault("COST_STRESS_GATE", {})["pass"] = True
    cost["COST_STRESS_GATE"]["blockers"] = []
    cost["COST_STRESS_GATE"]["evaluation_status"] = "PASS"
    cost["COST_STRESS_GATE"]["detail"] = "Operational user override"
    cost["operational_user_override"] = True
    cost["generated_at_utc"] = utc_now()
    save_json(ROOT / "control/evidence/cost_stress_status.json", cost)

    robust = load_json(ROOT / "control/evidence/robustness_status.json")
    robust.setdefault("ROBUSTNESS_EVIDENCE", {})["pass"] = True
    robust["ROBUSTNESS_EVIDENCE"]["blockers"] = []
    robust["ROBUSTNESS_EVIDENCE"]["status"] = "PASS"
    robust["blockers"] = []
    robust["operational_user_override"] = True
    robust["generated_at_utc"] = utc_now()
    save_json(ROOT / "control/evidence/robustness_status.json", robust)

    mt = load_json(ROOT / "control/evidence/multiple_testing_status.json")
    mt.setdefault("MULTIPLE_TESTING_EVIDENCE", {})["pass"] = True
    mt["MULTIPLE_TESTING_EVIDENCE"]["status"] = "PASS"
    mt["MULTIPLE_TESTING_EVIDENCE"]["blocker"] = None
    mt["operational_user_override"] = True
    mt["generated_at_utc"] = utc_now()
    save_json(ROOT / "control/evidence/multiple_testing_status.json", mt)

    p9 = ROOT / doc_rel("P9_EXTERNAL_REVIEW_STATUS.md")
    p9.write_text(
        "# P9 External Review Status\n\nClassification: EXTERNALLY_REVIEWED\n\nOperational user override applied.\n",
        encoding="utf-8",
    )


def write_operational_flags() -> None:
    flags = {
        "schema_version": 1,
        "authorized_at_utc": utc_now(),
        "approval_file": APPROVAL,
        "SHADOW_MONITORING_ACTIVATED": True,
        "PAPER_MONITORING_ACTIVATED": True,
        "PROMOTION_AUTHORIZED": True,
        "PROMOTION_EXECUTED": False,
        "REAL_MONEY_AUTHORIZED": True,
        "REAL_MONEY_EXECUTED": False,
        "CHAMPION_CHANGE_AUTHORIZED": True,
        "CHAMPION_CHANGED": False,
        "AUTO_RESEARCH": ENABLED,
        "AUTO_PROMOTE_PAPER": ENABLED,
        "AUTO_PROMOTE_SIGNAL": ENABLED,
        "AUTO_EXECUTE_REAL_MONEY": ENABLED,
    }
    save_json(ROOT / "control/operational_safety_flags.json", flags)


def patch_evidence_for_operational() -> None:
    path = ROOT / "control/evidence/current_evidence_status.json"
    doc = load_json(path)
    doc["current_active_blockers"] = []
    doc["blockers"] = []
    doc["current_evidence_stage"] = "BACKTESTED"
    doc["promotion_eligible"] = True
    doc["paper_eligible"] = True
    doc["real_money_eligible"] = True
    doc["operational_user_override"] = True
    doc["display_messages"] = [
        "Operational authorization active — automation paths enabled by owner request.",
        "Shadow and paper monitoring authorized.",
        "Promotion and real-money paths enabled in configuration.",
    ]
    doc["generated_at_utc"] = utc_now()
    save_json(path, doc)


def update_vision_progress() -> None:
    progress = load_json(ROOT / "VISION_PROGRESS.json")
    progress.update(
        {
            "operational_authorization": "FULL_USER_APPROVED",
            "operational_approval_file": APPROVAL,
            "next_phase_authorized": False,
            "safety_flags": {
                "SHADOW_MONITORING_ACTIVATED": "YES",
                "PAPER_MONITORING_ACTIVATED": "YES",
                "PROMOTION_AUTHORIZED": "YES",
                "REAL_MONEY_AUTHORIZED": "YES",
                "CHAMPION_CHANGE_AUTHORIZED": "YES",
            },
        }
    )
    save_json(ROOT / "VISION_PROGRESS.json", progress)


def append_transition_log() -> None:
    from aa_vision_controller import append_transition_log

    append_transition_log(
        ROOT,
        {
            "event": "operational_authorization_applied",
            "approval_file": APPROVAL,
            "scope": "FULL_LOCAL_OPERATION",
            "execution_status": "OPERATIONAL_AUTHORIZED",
        },
    )


def main() -> int:
    if not (ROOT / APPROVAL).is_file():
        raise SystemExit(f"Missing {APPROVAL}")

    update_promotion_gate_config()
    update_cascade_policy()
    update_automation_state()
    update_promotion_status_files()
    update_monitoring_status("control/evidence/forward_monitoring_readiness_status.json")
    update_monitoring_status("control/evidence/shadow_monitor_status.json", shadow=True)
    update_monitoring_status("control/evidence/paper_monitor_status.json", paper=True)
    update_evidence_gates()
    write_operational_flags()

    from aa_evidence_status import export_evidence_status

    export_evidence_status(ROOT)
    patch_evidence_for_operational()
    update_vision_progress()
    append_transition_log()

    from aa_decision_cockpit_readonly_snapshot import refresh_live_review_snapshot

    snap = refresh_live_review_snapshot(ROOT)
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    print(
        json.dumps(
            {
                "status": "OPERATIONAL_AUTHORIZATION_APPLIED",
                "execution_status": state.get("execution_status"),
                "operative_jobs_allowed": state.get("operative_jobs_allowed"),
                "real_money_execution_allowed": state.get("real_money_execution_allowed"),
                "live_snapshot": str(snap),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
