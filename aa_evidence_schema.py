"""V1 evidence schema — stages, source classifications, fail-closed stage rules."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

EVIDENCE_STAGES: Tuple[str, ...] = (
    "IDEA",
    "BACKTESTED",
    "ROBUSTNESS_CHECKED",
    "SHADOW_RUNNING",
    "SHADOW_PASSED",
    "PAPER_RUNNING",
    "PAPER_CANDIDATE",
    "REJECTED",
)

SOURCE_CLASSIFICATIONS: Tuple[str, ...] = (
    "NOT_AVAILABLE",
    "HISTORICAL_EXISTING",
    "PREEXISTING_UNREVIEWED",
    "EXTERNALLY_REVIEWED",
    "FORWARD_EXTERNALLY_APPROVED",
    "STALE_OR_CONFLICTING",
)

STAGE_RANK: Dict[str, int] = {
    "IDEA": 0,
    "BACKTESTED": 1,
    "ROBUSTNESS_CHECKED": 2,
    "SHADOW_RUNNING": 3,
    "SHADOW_PASSED": 4,
    "PAPER_RUNNING": 5,
    "PAPER_CANDIDATE": 6,
    "REJECTED": -1,
}

P9_UNREVIEWED_CLASSIFICATION = "PREEXISTING_UNREVIEWED_PASS"
AUTHORITATIVE_CHAMPION = "R0_LEGACY_ENSEMBLE"
LOCKED_CHAMPION = AUTHORITATIVE_CHAMPION
PREVIOUS_CHAMPION = "R3_w075_q065_noexit"
LEGACY_V2_COST_STRESS_LABEL = PREVIOUS_CHAMPION
OPERATIONAL_CHAMPION_REL = "control/operational_champion.json"
CHAMPION_LINEAGE_POLICY_REL = "control/champion_lineage_policy.json"
CHAMPION_LINEAGE_STATUS_REL = "control/authorization/champion_lineage_status.json"
QUARANTINED_R5_CLAIM_REL = "control/quarantine/g0r_r5_unauthorized/operational_champion_r5_claim.json"


def _read_champion_lineage_status(root: Path) -> Dict[str, Any]:
    path = root / CHAMPION_LINEAGE_STATUS_REL
    if not path.is_file():
        return {}
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_locked_champion(root: Optional[Path] = None) -> str:
    """Authoritative sealed-baseline champion for governance and cockpit display."""
    if root is not None:
        try:
            from analytics.strategic_governance import resolve_governance_champion

            return resolve_governance_champion(Path(root))
        except Exception:
            pass
        root = Path(root)
        decision_path = root / "control" / "champion_strategic_decision.json"
        if decision_path.is_file():
            try:
                import json

                decision = json.loads(decision_path.read_text(encoding="utf-8"))
                if decision.get("champion_change_executed"):
                    active = str(decision.get("active_champion") or "").strip()
                    if active:
                        return active
            except Exception:
                pass
        status = _read_champion_lineage_status(root)
        auth = str(status.get("authoritative_champion") or "").strip()
        if auth:
            return auth
    return LOCKED_CHAMPION


def resolve_unsealed_operational_champion_claim(root: Optional[Path] = None) -> Optional[str]:
    """Return variant_id from an active (non-quarantined) operational champion pointer."""
    if root is None:
        return None
    root = Path(root)
    path = root / OPERATIONAL_CHAMPION_REL
    if not path.is_file():
        return None
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("quarantine_classification") or "").strip():
            return None
        variant_id = str(data.get("variant_id", "") or "").strip()
        return variant_id or None
    except Exception:
        return None


def validate_evidence_stage(stage: str) -> bool:
    return str(stage).upper() in EVIDENCE_STAGES


def validate_source_classification(classification: str) -> bool:
    return str(classification).upper() in SOURCE_CLASSIFICATIONS


def stage_rank(stage: str) -> int:
    return STAGE_RANK.get(str(stage).upper(), -999)


def min_stage(a: str, b: str) -> str:
    if a == "REJECTED" or b == "REJECTED":
        return "REJECTED"
    return a if stage_rank(a) <= stage_rank(b) else b


def cap_stage(stage: str, max_stage: str) -> str:
    if stage == "REJECTED" or max_stage == "REJECTED":
        return "REJECTED"
    return min_stage(stage, max_stage)


def eligibility_for_stage(stage: str) -> Dict[str, bool]:
    rank = stage_rank(stage)
    return {
        "promotion_eligible": False,
        "paper_eligible": rank >= stage_rank("PAPER_CANDIDATE"),
        "real_money_eligible": False,
    }


def compute_evidence_stage(
    *,
    proposed_stage: str = "BACKTESTED",
    source_classification: str = "PREEXISTING_UNREVIEWED",
    cost_stress_pass: Optional[bool] = None,
    economic_value_pass: Optional[bool] = None,
    risk_gate_pass: Optional[bool] = None,
    data_quality_pass: Optional[bool] = None,
    data_quality_evidence_missing: bool = False,
    robustness_pass: Optional[bool] = None,
    multiple_testing_pass: Optional[bool] = None,
    p9_unreviewed: bool = True,
    source_conflicts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fail-closed stage resolution; never elevates without explicit gate pass."""
    if not validate_evidence_stage(proposed_stage):
        proposed_stage = "IDEA"
    if not validate_source_classification(source_classification):
        source_classification = "NOT_AVAILABLE"

    stage = proposed_stage
    blockers: List[str] = list(source_conflicts or [])

    if source_classification in {"NOT_AVAILABLE", "STALE_OR_CONFLICTING"}:
        stage = cap_stage(stage, "IDEA")
        blockers.append("SOURCE_CLASSIFICATION_LIMITS_STAGE")

    if cost_stress_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append("COST_STRESS_NOT_EVALUATED" if cost_stress_pass is None else "COST_STRESS_NOT_PASSED")
    if economic_value_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append("ECONOMIC_VALUE_NOT_PASSED")
    if risk_gate_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append("RISK_GATE_NOT_PASSED")
    if data_quality_evidence_missing or data_quality_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        if data_quality_evidence_missing:
            blockers.append("DATA_QUALITY_EVIDENCE_MISSING")
        else:
            blockers.append("DATA_QUALITY_NOT_PASSED")

    if robustness_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append(
            "ROBUSTNESS_NOT_EVALUATED" if robustness_pass is None else "ROBUSTNESS_NOT_PASSED"
        )

    if multiple_testing_pass is not True:
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append(
            "MULTIPLE_TESTING_NOT_EVALUATED"
            if multiple_testing_pass is None
            else "MULTIPLE_TESTING_NOT_PASSED"
        )

    if p9_unreviewed or source_classification == "PREEXISTING_UNREVIEWED":
        stage = cap_stage(stage, "BACKTESTED")
        blockers.append("P9_NOT_EXTERNALLY_REVIEWED")

    if source_conflicts:
        stage = cap_stage(stage, "BACKTESTED")
        for item in source_conflicts:
            if item not in blockers:
                blockers.append(item)

    elig = eligibility_for_stage(stage)
    elig["promotion_eligible"] = False
    elig["real_money_eligible"] = False
    elig["paper_eligible"] = False

    return {
        "current_evidence_stage": stage,
        "source_classification": source_classification,
        "blockers": sorted(set(blockers)),
        **elig,
    }
