"""V1 unified read-only evidence status aggregator."""
from __future__ import annotations

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_evidence_schema import (
    P9_UNREVIEWED_CLASSIFICATION,
    compute_evidence_stage,
    validate_source_classification,
)
from aa_experiment_registry import INITIAL_EXPERIMENT_ID, load_manifest, verify_manifest_provenance
from aa_safe_io import atomic_write_json

EVIDENCE_EXPORT = Path("control") / "evidence" / "current_evidence_status.json"
CANDIDATE_VARIANT = "MOM_63_TOP12"
CONTROL_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"

CONFIG_FLAG_MAP = {
    "AUTO_RESEARCH": "auto_research_enabled",
    "AUTO_PROMOTE_PAPER": "auto_promote_paper_enabled",
    "AUTO_PROMOTE_SIGNAL": "auto_promote_signal_enabled",
    "AUTO_EXECUTE_REAL_MONEY": "auto_execute_real_money_enabled",
}


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


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _gate_pass(gates: Dict[str, Any], name: str) -> Optional[bool]:
    gate = gates.get(name) or {}
    if not isinstance(gate, dict):
        return None
    val = gate.get("pass")
    if val is True:
        return True
    if val is False:
        return False
    return None


def _parse_p9_classification(md_text: str) -> str:
    if P9_UNREVIEWED_CLASSIFICATION in md_text:
        return P9_UNREVIEWED_CLASSIFICATION
    if "EXTERNALLY_REVIEWED" in md_text:
        return "EXTERNALLY_REVIEWED"
    return "UNKNOWN"


def _observed_status_modes(auto_status: Dict[str, Any], promotion_status: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    return {
        "auto_promotion_status": dict(auto_status.get("automation_modes") or {}),
        "promotion_status": dict(promotion_status.get("automation_modes") or {}),
    }


def _parse_automation_config(root: Path) -> Tuple[Dict[str, str], List[str], List[str]]:
    """Return (modes, blockers, unsafe_flags). Missing/incomplete => UNKNOWN modes."""
    root = Path(root)
    cfg_path = root / "promotion_gate_config.yaml"
    unknown = {key: "UNKNOWN" for key in CONFIG_FLAG_MAP}
    if not cfg_path.is_file():
        return unknown, ["AUTOMATION_CONFIG_MISSING_OR_INCOMPLETE"], []

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return unknown, ["AUTOMATION_CONFIG_MISSING_OR_INCOMPLETE"], []

    if not isinstance(raw, dict):
        return unknown, ["AUTOMATION_CONFIG_MISSING_OR_INCOMPLETE"], []

    if raw.get("operational_user_override") is True:
        modes: Dict[str, str] = {}
        for key, flag in CONFIG_FLAG_MAP.items():
            modes[key] = "ENABLED" if raw.get(flag) is True else "DISABLED"
        return modes, [], []

    blockers: List[str] = []
    unsafe: List[str] = []
    modes: Dict[str, str] = {}
    incomplete = False
    for key, flag in CONFIG_FLAG_MAP.items():
        if flag not in raw:
            incomplete = True
            modes[key] = "UNKNOWN"
        elif raw[flag] is True:
            modes[key] = "ENABLED"
            unsafe.append(f"UNSAFE_AUTOMATION_CONFIGURATION:{key}")
        else:
            modes[key] = "DISABLED"
    if incomplete:
        blockers.append("AUTOMATION_CONFIG_MISSING_OR_INCOMPLETE")
    return modes, blockers, unsafe


def _display_messages(*, manifest_present: bool, provenance_ok: bool) -> List[str]:
    if not manifest_present or not provenance_ok:
        return [
            "Evidence is missing or not verified.",
            "No externally reviewed Shadow or Paper readiness is established.",
            "Promotion and real-money execution remain blocked.",
        ]
    return [
        "Historical and preparation evidence exists.",
        "No externally reviewed Shadow or Paper readiness is established.",
        "Promotion and real-money execution remain blocked.",
    ]


def _automation_mode_conflicts(
    config_modes: Dict[str, str],
    auto_status: Dict[str, Any],
    promotion_status: Dict[str, Any],
) -> List[str]:
    conflicts: List[str] = []
    if any(v == "UNKNOWN" for v in config_modes.values()):
        return conflicts
    for source_name, observed in _observed_status_modes(auto_status, promotion_status).items():
        for mode_key, config_val in config_modes.items():
            obs_val = str(observed.get(mode_key, "")).upper()
            if not obs_val:
                continue
            if config_val == "ENABLED" and obs_val == "DISABLED":
                conflicts.append(
                    f"automation_mode:{mode_key}: config=ENABLED {source_name}=DISABLED"
                )
            elif config_val == "DISABLED" and obs_val == "ENABLED":
                conflicts.append(
                    f"automation_mode:{mode_key}: config=DISABLED {source_name}=ENABLED"
                )
    return conflicts


def _resolve_champion_evidence(
    auto_status: Dict[str, Any],
    lkg: Dict[str, Any],
) -> Tuple[Optional[str], List[str]]:
    auto_champ = auto_status.get("champion_variant_id") or (
        (auto_status.get("gate_evaluation") or {}).get("champion_variant_id")
    )
    lkg_champ = (
        lkg.get("validated_variant_id")
        or lkg.get("variant_id")
        or (lkg.get("pointer") or {}).get("variant_id")
    )
    if not auto_champ or not lkg_champ:
        return None, ["CHAMPION_EVIDENCE_MISSING"]
    if str(auto_champ) != str(lkg_champ):
        return None, ["CHAMPION_EVIDENCE_CONFLICT"]
    return str(auto_champ), []


def _system_health_ok(system_health: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if not system_health:
        return False, ["SYSTEM_HEALTH_NOT_CONFIRMED"]
    operational = str(system_health.get("operational_health", "")).upper()
    critical = system_health.get("critical_errors")
    if operational == "OK" and isinstance(critical, list) and len(critical) == 0:
        return True, []
    return False, ["SYSTEM_HEALTH_NOT_CONFIRMED"]


def _detect_gate_conflicts(
    auto_status: Dict[str, Any],
    promotion_status: Dict[str, Any],
) -> Tuple[List[str], Dict[str, Any]]:
    conflicts: List[str] = []
    auto_gates = ((auto_status.get("gate_evaluation") or {}).get("gates") or {})
    promo_gates = promotion_status.get("gates") or {}

    for gate_name in sorted(set(auto_gates) | set(promo_gates)):
        a = auto_gates.get(gate_name) or {}
        p = promo_gates.get(gate_name) or {}
        if not a or not p:
            continue
        ap, pp = a.get("pass"), p.get("pass")
        if ap is not None and pp is not None and ap != pp:
            conflicts.append(f"{gate_name}: auto_promotion={ap} promotion_status={pp}")

    auto_allowed = bool((auto_status.get("gate_evaluation") or {}).get("promotion_allowed", False))
    promo_allowed = bool(promotion_status.get("all_gates_pass", False))
    if auto_allowed != promo_allowed:
        conflicts.append(f"promotion_allowed: auto={auto_allowed} promotion_status={promo_allowed}")

    return conflicts, {"auto_promotion_gates": auto_gates, "promotion_status_gates": promo_gates}


def build_evidence_status(root: Path) -> Dict[str, Any]:
    """Strictly read-only — no manifest creation, no directory creation, no writes."""
    root = Path(root)

    config_modes, config_blockers, unsafe_flags = _parse_automation_config(root)
    auto_status = _read_json(root / "control" / "auto_promotion_status.json")
    promotion_status = _read_json(root / "control" / "promotion_status.json")
    system_health = _read_json(root / "control" / "system_health.json")
    lkg = _read_json(root / "control" / "last_known_good_state.json")
    p9_md = _read_text(root / doc_rel("P9_EXTERNAL_REVIEW_STATUS.md"))
    manifest = load_manifest(root, INITIAL_EXPERIMENT_ID)

    champion, champion_blockers = _resolve_champion_evidence(auto_status, lkg)
    health_ok, health_blockers = _system_health_ok(system_health)
    gate_conflicts, gate_views = _detect_gate_conflicts(auto_status, promotion_status)
    mode_conflicts = _automation_mode_conflicts(config_modes, auto_status, promotion_status)
    conflicts = gate_conflicts + mode_conflicts

    blockers: List[str] = list(champion_blockers) + list(health_blockers) + list(config_blockers) + list(unsafe_flags)
    provenance_ok = False
    provenance_blockers: List[str] = []

    if not manifest:
        blockers.append("EVIDENCE_PROVENANCE_MISSING")
        proposed_stage = "IDEA"
        source_class = "NOT_AVAILABLE"
    else:
        provenance_ok, provenance_blockers = verify_manifest_provenance(root, manifest)
        blockers.extend(provenance_blockers)
        source_class = str(manifest.get("source_classification") or "NOT_AVAILABLE")
        if not validate_source_classification(source_class):
            source_class = "NOT_AVAILABLE"
        if provenance_ok:
            proposed_stage = str(manifest.get("current_evidence_stage") or "IDEA")
        else:
            proposed_stage = "IDEA"
            source_class = "NOT_AVAILABLE"

    auto_gates = gate_views["auto_promotion_gates"]
    cost_pass = _gate_pass(auto_gates, "COST_STRESS_GATE")
    econ_pass = _gate_pass(auto_gates, "ECONOMIC_VALUE_GATE")
    risk_pass = _gate_pass(auto_gates, "RISK_GATE")
    dq_pass = _gate_pass(auto_gates, "DATA_QUALITY_GATE")
    dq_missing = "DATA_QUALITY_GATE" not in auto_gates

    v2_cost = _read_json(root / "control" / "evidence" / "cost_stress_status.json")
    v2_robust = _read_json(root / "control" / "evidence" / "robustness_status.json")
    v2_mt = _read_json(root / "control" / "evidence" / "multiple_testing_status.json")
    v2_inventory = _read_json(root / "control" / "evidence" / "v2_source_inventory.json")
    v3_forward = _read_json(root / "control" / "evidence" / "forward_monitoring_readiness_status.json")
    v3_shadow = _read_json(root / "control" / "evidence" / "shadow_monitor_status.json")
    v3_paper = _read_json(root / "control" / "evidence" / "paper_monitor_status.json")
    v3_requirements = _read_json(root / "control" / "evidence" / "forward_monitoring_data_requirements.json")

    monitoring_blockers = (
        "FORWARD_MONITORING_NOT_EXTERNALLY_APPROVED",
        "SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED",
        "PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED",
    )

    if v2_cost:
        gate = v2_cost.get("COST_STRESS_GATE") or {}
        ev_status = gate.get("evaluation_status")
        if ev_status == "NOT_EVALUABLE":
            cost_pass = False
        elif ev_status in {"PASS", "FAIL"}:
            cost_pass = bool(gate.get("pass"))
    robust_pass: Optional[bool] = None
    if v2_robust:
        re = v2_robust.get("ROBUSTNESS_EVIDENCE") or {}
        st = re.get("status")
        if st in {"NOT_EVALUABLE", "PARTIAL_ONLY"}:
            robust_pass = False if st == "PARTIAL_ONLY" else None
        elif "pass" in re:
            robust_pass = bool(re.get("pass"))
    mt_pass: Optional[bool] = None
    if v2_mt:
        mte = v2_mt.get("MULTIPLE_TESTING_EVIDENCE") or {}
        if mte.get("status") == "NOT_EVALUABLE":
            mt_pass = False
        elif mte.get("status") in {"PASS", "FAIL"}:
            mt_pass = bool(mte.get("pass"))

    p9_class = _parse_p9_classification(p9_md)
    p9_unreviewed = p9_class == P9_UNREVIEWED_CLASSIFICATION

    if not provenance_ok or not manifest:
        resolved = {
            "current_evidence_stage": "IDEA",
            "source_classification": "NOT_AVAILABLE",
            "blockers": blockers,
            "promotion_eligible": False,
            "paper_eligible": False,
            "real_money_eligible": False,
        }
        historical_manifest_blockers: List[str] = []
        current_active = sorted(set(blockers))
        resolved_or_superseded: List[str] = []
    else:
        resolved = compute_evidence_stage(
            proposed_stage=proposed_stage,
            source_classification=source_class,
            cost_stress_pass=cost_pass,
            economic_value_pass=econ_pass,
            risk_gate_pass=risk_pass,
            data_quality_pass=dq_pass,
            data_quality_evidence_missing=dq_missing,
            robustness_pass=robust_pass,
            multiple_testing_pass=mt_pass,
            p9_unreviewed=p9_unreviewed,
            source_conflicts=conflicts,
        )
        historical_manifest_blockers = sorted(set(manifest.get("blockers") or []))
        current_active = sorted(
            set(champion_blockers)
            | set(health_blockers)
            | set(config_blockers)
            | set(unsafe_flags)
            | set(resolved.get("blockers") or [])
            | set((v2_cost.get("COST_STRESS_GATE") or {}).get("blockers") or [])
            | set((v2_robust.get("ROBUSTNESS_EVIDENCE") or {}).get("blockers") or [])
        )
        if (v2_mt.get("MULTIPLE_TESTING_EVIDENCE") or {}).get("blocker"):
            b = str((v2_mt.get("MULTIPLE_TESTING_EVIDENCE") or {}).get("blocker"))
            if b:
                current_active.append(b)

        resolved_or_superseded = []
        for hb in historical_manifest_blockers:
            if hb == "COST_STRESS_NOT_EVALUATED" and v2_cost:
                resolved_or_superseded.append(hb)
            elif hb == "COST_STRESS_NOT_PASSED" and cost_pass is True:
                resolved_or_superseded.append(hb)

        current_active = sorted(set(b for b in current_active if b not in resolved_or_superseded))
        if cost_pass is True and "COST_STRESS_NOT_EVALUATED" in current_active:
            resolved_or_superseded.append("COST_STRESS_NOT_EVALUATED")
            current_active = [b for b in current_active if b != "COST_STRESS_NOT_EVALUATED"]

        for mb in monitoring_blockers:
            current_active.append(mb)
        for artifact in (v3_forward, v3_shadow, v3_paper):
            for b in artifact.get("active_blockers") or []:
                current_active.append(str(b))
        current_active = sorted(set(current_active))

        blockers = current_active

    source_artifacts = [
        {"path": "promotion_gate_config.yaml", "role": "automation_config_primary"},
        {"path": "control/auto_promotion_status.json", "role": "auto_promotion_safety_source"},
        {"path": "control/promotion_status.json", "role": "informative_promotion_view"},
        {"path": "control/system_health.json", "role": "system_health"},
        {"path": "control/last_known_good_state.json", "role": "lkg_reference"},
    ]
    manifest_rel = f"control/experiments/{INITIAL_EXPERIMENT_ID}.yaml"
    if (root / manifest_rel).is_file():
        source_artifacts.append({"path": manifest_rel, "role": "experiment_manifest"})
    if (root / "control" / "p9_shadow_paper_prep_status.json").is_file():
        source_artifacts.append(
            {"path": "control/p9_shadow_paper_prep_status.json", "role": "p9_preparation_status"}
        )
    if (root / doc_rel("P9_EXTERNAL_REVIEW_STATUS.md")).is_file():
        source_artifacts.append({"path": doc_rel("P9_EXTERNAL_REVIEW_STATUS.md"), "role": "p9_review_classification"})

    if (root / "control" / "evidence" / "forward_monitoring_readiness_status.json").is_file():
        source_artifacts.append(
            {"path": "control/evidence/forward_monitoring_readiness_status.json", "role": "forward_monitoring_readiness"}
        )
    if (root / "control" / "evidence" / "shadow_monitor_status.json").is_file():
        source_artifacts.append({"path": "control/evidence/shadow_monitor_status.json", "role": "shadow_monitor_status"})
    if (root / "control" / "evidence" / "paper_monitor_status.json").is_file():
        source_artifacts.append({"path": "control/evidence/paper_monitor_status.json", "role": "paper_monitor_status"})
    if (root / "control" / "evidence" / "forward_monitoring_data_requirements.json").is_file():
        source_artifacts.append(
            {"path": "control/evidence/forward_monitoring_data_requirements.json", "role": "monitoring_data_requirements"}
        )

    observed_modes = _observed_status_modes(auto_status, promotion_status)

    return {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_EVIDENCE",
        "champion_variant_id": champion,
        "candidate_variant_id": CANDIDATE_VARIANT,
        "control_variant_id": CONTROL_VARIANT,
        "automation_modes": config_modes,
        "observed_automation_modes": observed_modes,
        "current_evidence_stage": resolved["current_evidence_stage"],
        "source_classification": resolved.get("source_classification", source_class),
        "promotion_eligible": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "historical_manifest_blockers": historical_manifest_blockers,
        "current_active_blockers": current_active,
        "resolved_or_superseded_blockers": sorted(set(resolved_or_superseded)),
        "gate_summary": {
            "COST_STRESS_GATE": {
                "pass": cost_pass,
                "source": "control/evidence/cost_stress_status.json" if v2_cost else "auto_promotion_status",
            },
            "ECONOMIC_VALUE_GATE": {"pass": econ_pass, "source": "auto_promotion_status"},
            "RISK_GATE": {"pass": risk_pass, "source": "auto_promotion_status"},
            "DATA_QUALITY_GATE": {"pass": dq_pass, "source": "auto_promotion_status", "missing": dq_missing},
            "ROBUSTNESS_EVIDENCE": {
                "pass": robust_pass,
                "source": "control/evidence/robustness_status.json" if v2_robust else None,
            },
            "MULTIPLE_TESTING_EVIDENCE": {
                "pass": mt_pass,
                "source": "control/evidence/multiple_testing_status.json" if v2_mt else None,
            },
            "promotion_allowed_auto": bool((auto_status.get("gate_evaluation") or {}).get("promotion_allowed", False)),
            "all_gates_pass_promotion_status": bool(promotion_status.get("all_gates_pass", False)),
            "system_health_ok": health_ok,
        },
        "v2_evidence_artifacts": {
            "v2_source_inventory.json": bool(v2_inventory),
            "cost_stress_status.json": bool(v2_cost),
            "robustness_status.json": bool(v2_robust),
            "multiple_testing_status.json": bool(v2_mt),
        },
        "monitoring_artifacts": {
            "forward_monitoring_readiness_status.json": bool(v3_forward),
            "shadow_monitor_status.json": bool(v3_shadow),
            "paper_monitor_status.json": bool(v3_paper),
            "forward_monitoring_data_requirements.json": bool(v3_requirements),
        },
        "monitoring_summary": {
            "forward_activation_status": v3_forward.get("activation_status"),
            "shadow_activation_status": v3_shadow.get("activation_status"),
            "paper_activation_status": v3_paper.get("activation_status"),
            "shadow_collection_started": v3_shadow.get("shadow_collection_started", False),
            "paper_simulation_started": v3_paper.get("paper_simulation_started", False),
        },
        "source_artifacts": source_artifacts,
        "source_conflicts": conflicts,
        "blockers": sorted(set(current_active)),
        "display_messages": _display_messages(manifest_present=bool(manifest), provenance_ok=provenance_ok),
        "p9_classification": p9_class,
    }


def export_evidence_status(root: Path) -> Path:
    root = Path(root)
    payload = build_evidence_status(root)
    out = root / EVIDENCE_EXPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out, payload)
    return out


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()
