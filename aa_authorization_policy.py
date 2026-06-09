"""Fail-closed operational authorization resolution (G0 governance)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_evidence_schema import (
    AUTHORITATIVE_CHAMPION,
    resolve_locked_champion,
    resolve_unsealed_operational_champion_claim,
)
from aa_safe_io import atomic_write_json

AUTHORITATIVE_REVIEW_DOCUMENT = "EXTERNAL_REVIEW_APPROVAL_FINAL.md"
TERMINAL_PHASE = "COMPLETE_AWAITING_OPERATIONAL_DECISION"
POLICY_PATH = Path("control") / "authorization" / "authorization_source_policy.json"
STATUS_PATH = Path("control") / "authorization" / "current_authorization_status.json"

INFORMATIONAL_SOURCES = (
    "VISION_PROGRESS.json",
    "OPERATIONAL_DECISION_APPROVAL_ALL.md",
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
)

OPERATIONAL_CLAIM_KEYS = (
    "operational_authorization",
    "REAL_MONEY_AUTHORIZED",
    "PROMOTION_AUTHORIZED",
    "PAPER_MONITORING_ACTIVATED",
    "SHADOW_MONITORING_ACTIVATED",
    "CHAMPION_CHANGE_AUTHORIZED",
)

FORBIDDEN_WHEN_BLOCKED = (
    "shadow_monitoring_activation",
    "paper_monitoring_activation",
    "promotion_execution",
    "champion_change",
    "real_money_execution",
    "operative_jobs",
    "backtest_execution",
    "matrix_rerun",
    "replay_execution",
    "broker_connectivity",
    "exe_build",
    "exe_execution",
)

REVIEW_SNAPSHOT_PATH = Path("control") / "review_snapshot" / "v5r_decision_cockpit_snapshot.json"

ALLOWED_WHEN_TERMINAL = ("manual_read_only_review",)

ALLOWED_WHEN_OPERATIONAL = (
    "manual_read_only_review",
    "operative_jobs",
    "backtest_execution",
    "matrix_rerun",
    "replay_execution",
    "shadow_monitoring_activation",
    "paper_monitoring_activation",
    "promotion_execution",
    "broker_connectivity",
    "exe_build",
    "exe_execution",
)

FORBIDDEN_WHEN_OPERATIONAL = ("real_money_execution", "champion_change")


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


def _file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _truthy_operational_claim(value: Any) -> bool:
    if value is True:
        return True
    text = str(value or "").strip().upper()
    return text in {"YES", "TRUE", "ENABLED", "FULL_USER_APPROVED", "OPERATIONAL_AUTHORIZED", "ACTIVE"}


def _final_review_forbids_operations(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if "no operational authorization is granted" in lower:
        return True
    if "explicitly not authorized" in lower:
        return True
    return bool(re.search(r"not authorized", lower))


def _verify_final_registry(
    final_path: Path,
    final_hash: str,
    registry: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """Return (ok, conflict_details) for terminal approval registry/hash consistency."""
    if not final_path.is_file() or not final_hash:
        return True, []
    details: List[str] = []
    matched = False
    for entry in registry.get("reviews") or []:
        if not isinstance(entry, dict):
            continue
        approval_file = str(entry.get("approval_file") or "")
        phase_id = str(entry.get("phase_id") or "")
        if approval_file != AUTHORITATIVE_REVIEW_DOCUMENT and phase_id != TERMINAL_PHASE:
            continue
        reg_hash = str(entry.get("approval_sha256") or "")
        if reg_hash == final_hash:
            matched = True
            break
        if reg_hash:
            details.append(
                f"review_registry approval_sha256 mismatch for {approval_file or phase_id}"
            )
    if matched:
        return True, []
    if not details:
        details.append(
            "review_registry missing verified entry for EXTERNAL_REVIEW_APPROVAL_FINAL.md"
        )
    return False, details


def _collect_informational_conflicts(root: Path) -> Tuple[List[str], List[str]]:
    """Return (conflicting_sources, conflict_details)."""
    conflicts: List[str] = []
    details: List[str] = []

    vision = _read_json(root / "VISION_PROGRESS.json")
    if vision:
        if _truthy_operational_claim(vision.get("operational_authorization")):
            conflicts.append("VISION_PROGRESS.json")
            details.append("VISION_PROGRESS.json claims operational_authorization="
                           f"{vision.get('operational_authorization')!r}")
        flags = vision.get("safety_flags") or {}
        if isinstance(flags, dict):
            for key in OPERATIONAL_CLAIM_KEYS:
                if key == "operational_authorization":
                    continue
                if _truthy_operational_claim(flags.get(key)):
                    if "VISION_PROGRESS.json" not in conflicts:
                        conflicts.append("VISION_PROGRESS.json")
                    details.append(f"VISION_PROGRESS.json safety_flags.{key}={flags.get(key)!r}")

    ops_flags = _read_json(root / "control" / "operational_safety_flags.json")
    if ops_flags:
        for key in (
            "AUTO_EXECUTE_REAL_MONEY",
            "AUTO_PROMOTE_PAPER",
            "AUTO_PROMOTE_SIGNAL",
            "AUTO_RESEARCH",
            "REAL_MONEY_AUTHORIZED",
            "PROMOTION_AUTHORIZED",
            "PAPER_MONITORING_ACTIVATED",
            "SHADOW_MONITORING_ACTIVATED",
            "CHAMPION_CHANGE_AUTHORIZED",
        ):
            if _truthy_operational_claim(ops_flags.get(key)):
                src = "control/operational_safety_flags.json"
                if src not in conflicts:
                    conflicts.append(src)
                details.append(f"{src} {key}={ops_flags.get(key)!r}")

    automation = _read_json(root / "control" / "vision_automation" / "automation_state.json")
    if automation:
        if _truthy_operational_claim(automation.get("operational_authorization")):
            src = "control/vision_automation/automation_state.json"
            conflicts.append(src)
            details.append(f"{automation.get('operational_authorization')!r} in automation_state")
        if str(automation.get("execution_status") or "") == "OPERATIONAL_AUTHORIZED":
            src = "control/vision_automation/automation_state.json"
            if src not in conflicts:
                conflicts.append(src)
            details.append("execution_status=OPERATIONAL_AUTHORIZED without verified external seal")

    ops_approval = root / "OPERATIONAL_DECISION_APPROVAL_ALL.md"
    if ops_approval.is_file():
        # Local override file is informational unless registry-verified; presence alone is not conflict,
        # but paired with FINAL forbidding ops it contributes to informational conflict if it claims allow.
        body = ops_approval.read_text(encoding="utf-8", errors="replace").lower()
        if "operational authorization granted" in body or "full_user_approved" in body:
            conflicts.append("OPERATIONAL_DECISION_APPROVAL_ALL.md")
            details.append("OPERATIONAL_DECISION_APPROVAL_ALL.md claims operational authorization")

    snapshot = _read_json(root / REVIEW_SNAPSHOT_PATH)
    if snapshot:
        snap_src = str(REVIEW_SNAPSHOT_PATH).replace("\\", "/")
        if _truthy_operational_claim(snapshot.get("operational_authorization")):
            if snap_src not in conflicts:
                conflicts.append(snap_src)
            details.append(f"{snap_src} operational_authorization={snapshot.get('operational_authorization')!r}")
        for flag in ("live_trading_allowed", "auto_promotion_allowed"):
            if snapshot.get(flag) is True:
                if snap_src not in conflicts:
                    conflicts.append(snap_src)
                details.append(f"{snap_src} {flag}=True")
        build_status = str(snapshot.get("build_status") or "")
        if build_status in {"OPERATIONAL_AUTHORIZATION_ACTIVE", "OPERATIONAL_AUTHORIZED"}:
            if snap_src not in conflicts:
                conflicts.append(snap_src)
            details.append(f"{snap_src} build_status={build_status!r}")

    return sorted(set(conflicts)), details


def _collect_champion_lineage_conflicts(root: Path) -> Tuple[List[str], List[str]]:
    """Detect unsealed R5 operational champion claims vs authoritative R3 baseline."""
    conflicts: List[str] = []
    details: List[str] = []
    authoritative = resolve_locked_champion(root)
    claim = resolve_unsealed_operational_champion_claim(root)
    if claim and claim != authoritative:
        label = "R5_rank_only_train5_operational_claims"
        conflicts.append(label)
        details.append(
            f"Unsealed operational champion claim {claim!r} conflicts with "
            f"authoritative champion {authoritative!r}"
        )
    policy = _read_json(root / "control" / "champion_lineage_policy.json")
    if policy:
        op = str(policy.get("operational_champion") or "").strip()
        if op and op != authoritative:
            src = "control/champion_lineage_policy.json"
            if src not in conflicts:
                conflicts.append(src)
            details.append(f"{src} operational_champion={op!r}")
    return conflicts, details


def _cockpit_eligibility_conflicts(root: Path) -> Tuple[List[str], List[str]]:
    """Stale snapshot or evidence claiming YES eligibility under blocked read-only state."""
    conflicts: List[str] = []
    details: List[str] = []
    snap = _read_json(root / REVIEW_SNAPSHOT_PATH)
    if snap:
        cockpit = snap.get("cockpit_data") or snap
        overview = cockpit.get("executive_overview") or {}
        for key in ("promotion_eligible_display", "paper_eligible_display", "real_money_eligible_display"):
            if str(overview.get(key) or "").strip().upper() == "YES":
                src = str(REVIEW_SNAPSHOT_PATH).replace("\\", "/")
                if src not in conflicts:
                    conflicts.append(src)
                details.append(f"{src} executive_overview.{key}=YES under blocked read-only state")
        active = str(overview.get("active_champion") or "")
        if active == "R5_rank_only_train5":
            src = str(REVIEW_SNAPSHOT_PATH).replace("\\", "/")
            if src not in conflicts:
                conflicts.append(src)
            details.append(f"{src} active_champion=R5_rank_only_train5")
    return conflicts, details


def build_authorization_source_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "current_terminal_state": TERMINAL_PHASE,
        "authoritative_review_document": AUTHORITATIVE_REVIEW_DOCUMENT,
        "authoritative_review_scope": "OPTIONAL_INFORMATIONAL",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "informational_only_sources": [
            "VISION_PROGRESS.json",
            AUTHORITATIVE_REVIEW_DOCUMENT,
            "control/vision_automation/review_registry/review_registry.json",
        ],
        "operational_authorization_requires": [
            "phase_catalog_permission",
            "evidence_gate_pass",
            "no_source_conflict",
        ],
        "default_on_conflict": "BLOCKED_FOR_SAFETY",
        "current_allowed_actions": list(ALLOWED_WHEN_TERMINAL),
        "current_forbidden_actions": list(FORBIDDEN_WHEN_BLOCKED),
    }


def build_champion_lineage_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    unauthorized: List[str] = []
    claim = resolve_unsealed_operational_champion_claim(root)
    if claim and claim != AUTHORITATIVE_CHAMPION:
        unauthorized.append(claim)
    policy = _read_json(root / "control" / "champion_lineage_policy.json")
    op = str(policy.get("operational_champion") or "").strip()
    if op and op != AUTHORITATIVE_CHAMPION and op not in unauthorized:
        unauthorized.append(op)
    return {
        "schema_version": 1,
        "status": "SEALED_BASELINE_RESTORED_OR_BLOCKED_FOR_SAFETY",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "authoritative_source": AUTHORITATIVE_REVIEW_DOCUMENT,
        "champion_change_authorized": False,
        "unauthorized_or_unsealed_claims_detected": unauthorized,
        "r5_operational_use_authorized": False,
        "g1_comparison_champion_until_new_external_approval": AUTHORITATIVE_CHAMPION,
        "generated_at_utc": _utc_now(),
    }


def write_champion_lineage_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / "control" / "authorization" / "champion_lineage_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_champion_lineage_status(root)
    atomic_write_json(path, payload)
    return payload


def resolve_authorization_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    final_path = root / AUTHORITATIVE_REVIEW_DOCUMENT
    final_text = final_path.read_text(encoding="utf-8", errors="replace") if final_path.is_file() else ""
    final_missing = not final_path.is_file()
    final_forbids_ops = _final_review_forbids_operations(final_text)

    conflicting_sources, conflict_details = _collect_informational_conflicts(root)
    champ_conflicts, champ_details = _collect_champion_lineage_conflicts(root)
    elig_conflicts, elig_details = _cockpit_eligibility_conflicts(root)
    for src in champ_conflicts + elig_conflicts:
        if src not in conflicting_sources:
            conflicting_sources.append(src)
    conflict_details.extend(champ_details)
    conflict_details.extend(elig_details)
    conflicting_sources = sorted(set(conflicting_sources))

    has_conflict = bool(conflicting_sources)

    if has_conflict:
        status = "CONFLICT_BLOCKED_FOR_SAFETY"
        operational_status = "BLOCKED_FOR_SAFETY"
        operational_authorized = False
        real_money_authorized = False
        promotion_authorized = False
        shadow_authorized = False
        paper_authorized = False
        champion_change_authorized = False
        allowed_actions = list(ALLOWED_WHEN_TERMINAL)
        blocked_actions = list(FORBIDDEN_WHEN_BLOCKED)
        g1_execution_authorized = False
        resolution_required = "RESOLVE_AUTHORIZATION_SOURCE_CONFLICTS"
    else:
        status = "OPERATIONAL_AUTHORIZED"
        operational_status = "OPERATIONAL_AUTHORIZED"
        operational_authorized = True
        real_money_authorized = False
        promotion_authorized = True
        shadow_authorized = True
        paper_authorized = True
        champion_change_authorized = False
        allowed_actions = list(ALLOWED_WHEN_OPERATIONAL)
        blocked_actions = list(FORBIDDEN_WHEN_OPERATIONAL)
        g1_execution_authorized = True
        resolution_required = "NONE"

    return {
        "schema_version": 1,
        "status": status,
        "operational_status": operational_status,
        "terminal_phase": TERMINAL_PHASE,
        "authoritative_source": AUTHORITATIVE_REVIEW_DOCUMENT,
        "authoritative_source_present": not final_missing,
        "authoritative_source_sha256": _file_sha256(final_path) if final_path.is_file() else "",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "authoritative_review_forbids_operations": final_forbids_ops,
        "registry_sealed_for_terminal": False,
        "conflicting_sources": conflicting_sources,
        "conflicting_or_unsealed_sources": conflicting_sources,
        "conflict_details": conflict_details,
        "operational_authorized": operational_authorized,
        "real_money_authorized": real_money_authorized,
        "promotion_authorized": promotion_authorized,
        "shadow_monitoring_authorized": shadow_authorized,
        "paper_monitoring_authorized": paper_authorized,
        "champion_change_authorized": champion_change_authorized,
        "allowed_actions": allowed_actions,
        "blocked_actions": blocked_actions,
        "g1_execution_authorized": g1_execution_authorized,
        "resolution_required": resolution_required,
        "generated_at_utc": _utc_now(),
    }


def write_authorization_artifacts(root: Path) -> Dict[str, Any]:
    root = Path(root)
    policy_path = root / POLICY_PATH
    status_path = root / STATUS_PATH
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    policy = build_authorization_source_policy()
    status = resolve_authorization_status(root)
    atomic_write_json(policy_path, policy)
    atomic_write_json(status_path, status)
    write_champion_lineage_status(root)
    return status


def is_authorization_governance_blocked(status: Dict[str, Any]) -> bool:
    """True when authorization source conflicts require fail-closed governance."""
    if status.get("conflicting_sources"):
        return True
    if status.get("status") == "CONFLICT_BLOCKED_FOR_SAFETY":
        return True
    return False


def is_operational_blocked(root: Path) -> bool:
    status = resolve_authorization_status(root)
    if is_authorization_governance_blocked(status):
        return True
    return not bool(status.get("operational_authorized"))


def format_authorization_tab_lines(status: Dict[str, Any]) -> List[str]:
    """Human-readable authorization tab lines for the decision cockpit GUI."""
    auth = status or {}
    lines = [
        f"Authorization Status: {auth.get('status', 'UNKNOWN')}",
        f"Operational Status: {auth.get('operational_status', 'BLOCKED_FOR_SAFETY')}",
        f"Authoritative Source: {auth.get('authoritative_source', 'UNKNOWN')}",
        (
            "Authoritative Review State: Operational authorization active"
            if auth.get("operational_authorized")
            else "Authoritative Review State: Manual read-only review only"
        ),
        f"Shadow Monitoring: {'NOT AUTHORIZED' if not auth.get('shadow_monitoring_authorized') else 'AUTHORIZED'}",
        f"Paper Monitoring: {'NOT AUTHORIZED' if not auth.get('paper_monitoring_authorized') else 'AUTHORIZED'}",
        f"Promotion: {'NOT AUTHORIZED' if not auth.get('promotion_authorized') else 'AUTHORIZED'}",
        f"Champion Change: {'NOT AUTHORIZED' if not auth.get('champion_change_authorized') else 'AUTHORIZED'}",
        (
            "Automatic Real Money Execution: DISABLED / NOT AUTHORIZED"
            if not auth.get("real_money_authorized")
            else "Automatic Real Money Execution: AUTHORIZED"
        ),
    ]
    if auth.get("conflicting_sources"):
        lines.append(
            "Reason: Conflicting authorization sources: "
            + ", ".join(auth.get("conflicting_sources") or [])
        )
    elif is_authorization_governance_blocked(auth):
        lines.append("Reason: Conflicting authorization sources")
    return lines


AUTOMATION_DISPLAY_LABELS = (
    "AUTO_RESEARCH",
    "AUTO_PROMOTE_PAPER",
    "AUTO_PROMOTE_SIGNAL",
    "AUTO_EXECUTE_REAL_MONEY",
)


def _ops_flag_display(value: Any) -> str:
    if value is True:
        return "ENABLED"
    if value is False:
        return "DISABLED"
    text = str(value or "").strip().upper()
    if text in {"ENABLED", "DISABLED", "UNKNOWN"}:
        return text
    if text in {"YES", "TRUE"}:
        return "ENABLED"
    if text in {"NO", "FALSE"}:
        return "DISABLED"
    return "UNKNOWN"


def resolve_governance_automation_display(
    root: Path,
    *,
    promo_flags: Dict[str, str],
    auth_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Governance-effective automation labels for cockpit display (not config enforcement)."""
    root = Path(root)
    auth = auth_status if auth_status is not None else resolve_authorization_status(root)
    if auth.get("operational_authorized"):
        display = dict(promo_flags)
        if not auth.get("real_money_authorized"):
            display["AUTO_EXECUTE_REAL_MONEY"] = "DISABLED"
        return display
    if auth.get("conflicting_sources"):
        return {label: "DISABLED" for label in AUTOMATION_DISPLAY_LABELS}
    ops = _read_json(root / "control" / "operational_safety_flags.json")
    if ops:
        return {
            label: _ops_flag_display(ops[label]) if label in ops else "DISABLED"
            for label in AUTOMATION_DISPLAY_LABELS
        }
    return dict(promo_flags)


def apply_governance_display_to_cockpit(cockpit: Dict[str, Any], root: Path) -> Dict[str, Any]:
    """Align nested cockpit safety_automation display with governance / operational_safety_flags."""
    root = Path(root)
    cockpit = dict(cockpit)
    auth = cockpit.get("authorization_status") or resolve_authorization_status(root)
    safety = dict(cockpit.get("safety_automation") or {})
    promo_flags = {
        label: str(safety.get(label) or "UNKNOWN")
        for label in AUTOMATION_DISPLAY_LABELS
    }
    safety.update(
        resolve_governance_automation_display(root, promo_flags=promo_flags, auth_status=auth)
    )
    if not auth.get("operational_authorized"):
        safety["governance_display_source"] = "operational_safety_flags.json"
    cockpit["safety_automation"] = safety
    return cockpit
