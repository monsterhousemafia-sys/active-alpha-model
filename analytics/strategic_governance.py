"""Single strategic governance model — sync derived control artifacts from SSoT."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

STRATEGIC_DECISION_REL = Path("control/champion_strategic_decision.json")
PREDICTION_OPS_REL = Path("control/prediction_operations.json")
MANIFEST_REL = Path("control/strategic_governance.json")
LINEAGE_STATUS_REL = Path("control/authorization/champion_lineage_status.json")
LEARNING_POLICY_REL = Path("control/learning_collection_policy.json")
LINEAGE_POLICY_REL = Path("control/champion_lineage_policy.json")
OPERATIONAL_STATUS_REL = Path("control/champion_operational_status.json")
AUTH_STATUS_REL = Path("control/authorization/current_authorization_status.json")
AUTH_SOURCE_REL = Path("control/authorization/authorization_source_policy.json")

PRIOR_CHAMPION = "R3_w075_q065_noexit"
DEFAULT_GOVERNANCE_CHAMPION = "R0_LEGACY_ENSEMBLE"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_governance_champion(root: Path) -> str:
    """M9-approved production identity (SSoT tier 1: strategic decision)."""
    root = Path(root)
    decision = _load_json(root / STRATEGIC_DECISION_REL)
    if decision.get("champion_change_executed"):
        active = str(decision.get("active_champion") or "").strip()
        if active:
            return active
    lineage = _load_json(root / LINEAGE_STATUS_REL)
    auth = str(lineage.get("authoritative_champion") or "").strip()
    if auth:
        return auth
    ops = _load_json(root / PREDICTION_OPS_REL)
    gov = str(ops.get("governance_champion") or "").strip()
    return gov or DEFAULT_GOVERNANCE_CHAMPION


def resolve_prior_champion(root: Path) -> str:
    decision = _load_json(Path(root) / STRATEGIC_DECISION_REL)
    prior = str(decision.get("prior_champion") or "").strip()
    return prior or PRIOR_CHAMPION


def resolve_production_fallback_variant(root: Path) -> str:
    ops = _load_json(Path(root) / PREDICTION_OPS_REL)
    fb = str(ops.get("production_fallback") or "").strip()
    if fb:
        return fb
    profiles = ops.get("profiles") or {}
    row = profiles.get(str(ops.get("fallback_profile") or "r3_w075_production")) or {}
    return str(row.get("variant_key") or PRIOR_CHAMPION)


def resolve_active_signal_profile(root: Path) -> str:
    from analytics.prediction_operations import active_profile

    return active_profile(root)


def resolve_active_signal_variant(root: Path) -> str:
    from analytics.prediction_operations import resolve_operational_signal_id

    return resolve_operational_signal_id(root)


def resolve_effective_orders_profile(root: Path) -> str:
    """Orders use validated fallback while experimental H1 is unsealed."""
    root = Path(root)
    ops = _load_json(root / PREDICTION_OPS_REL)
    active = str(ops.get("active_profile") or "daily_alpha_h1")
    fallback = str(ops.get("fallback_profile") or "r3_w075_production")
    experimental = set(ops.get("experimental_profiles") or ["daily_alpha_h1"])
    if active not in experimental:
        return active
    try:
        from analytics.live_profile_governance import is_h1_backtest_sealed

        if is_h1_backtest_sealed(root):
            return active
    except Exception:
        pass
    return fallback


def build_governance_manifest(root: Path) -> Dict[str, Any]:
    """Canonical two-tier model: governance champion vs live signal profile."""
    root = Path(root)
    ops = _load_json(root / PREDICTION_OPS_REL)
    decision = _load_json(root / STRATEGIC_DECISION_REL)
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    governance = resolve_governance_champion(root)
    signal_profile = resolve_active_signal_profile(root)
    signal_variant = resolve_active_signal_variant(root)
    fallback_variant = resolve_production_fallback_variant(root)
    effective_orders = resolve_effective_orders_profile(root)
    h1_sealed = is_h1_backtest_sealed(root)
    experimental = list(ops.get("experimental_profiles") or ["daily_alpha_h1"])

    issues: List[str] = []
    ops_gov = str(ops.get("governance_champion") or "").strip()
    if ops_gov and ops_gov != governance:
        issues.append(f"prediction_operations.governance_champion={ops_gov} != {governance}")

    learning = _load_json(root / LEARNING_POLICY_REL)
    locked = str(
        learning.get("governance_champion_locked")
        or learning.get("active_champion_locked")
        or ""
    ).strip()
    if locked and locked != governance:
        issues.append(f"learning_collection_policy lock={locked} != {governance}")

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "model": "two_tier_champion",
        "ssot": {
            "governance_champion": str(STRATEGIC_DECISION_REL).replace("\\", "/"),
            "operational_signal": str(PREDICTION_OPS_REL).replace("\\", "/"),
        },
        "governance_champion": governance,
        "prior_governance_champion": resolve_prior_champion(root),
        "m9_executed": bool(decision.get("champion_change_executed")),
        "m9_approval_ref": str(decision.get("approval_file") or ""),
        "active_signal_profile": signal_profile,
        "active_signal_variant": signal_variant,
        "production_fallback_variant": fallback_variant,
        "production_fallback_profile": str(ops.get("fallback_profile") or "r3_w075_production"),
        "effective_orders_profile": effective_orders,
        "experimental_profiles": experimental,
        "h1_backtest_sealed": h1_sealed,
        "h1_backtest_status": h1_backtest_status(root),
        "strategic_objective_ref": str(ops.get("objective_ref") or "control/r0_migration/alpha_objective.json"),
        "research_sharpe_leader": str(ops.get("research_sharpe_leader") or "MOM_63_TOP12"),
        "rules_de": (
            f"Governance-Champion {governance} (M9-freigegeben) ist die autorisierte Produktionsidentität. "
            f"Live-Signal {signal_variant} über Profil {signal_profile} ist experimentell bis H1-Seal. "
            f"Orders nutzen {effective_orders} solange H1 unsealed. "
            f"Validierter Fallback: {fallback_variant}."
        ),
        "coherence_ok": len(issues) == 0,
        "coherence_issues": issues,
    }


def sync_strategic_governance(root: Path) -> Dict[str, Any]:
    """Propagate SSoT to all derived control artifacts."""
    root = Path(root)
    manifest = build_governance_manifest(root)
    governance = manifest["governance_champion"]
    prior = manifest["prior_governance_champion"]
    signal_variant = manifest["active_signal_variant"]
    signal_profile = manifest["active_signal_profile"]
    fallback_variant = manifest["production_fallback_variant"]
    decision = _load_json(root / STRATEGIC_DECISION_REL)

    atomic_write_json(root / MANIFEST_REL, manifest)

    lineage_payload = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "authoritative_champion": governance,
        "authoritative_source": str(decision.get("approval_file") or "champion_strategic_decision.json"),
        "prior_champion": prior,
        "champion_change_authorized": bool(decision.get("champion_change_executed")),
        "g1_comparison_champion_until_new_external_approval": prior,
        "research_sharpe_leader": manifest["research_sharpe_leader"],
        "research_sharpe_leader_ref": "evidence/canonical_model_comparison.json",
        "status": "M9_ACTIVE_CHAMPION",
        "prediction_profile_ref": str(PREDICTION_OPS_REL).replace("\\", "/"),
        "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
        "active_signal_profile": signal_profile,
        "active_signal_variant": signal_variant,
    }
    (root / LINEAGE_STATUS_REL).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root / LINEAGE_STATUS_REL, lineage_payload)

    learning = _load_json(root / LEARNING_POLICY_REL)
    learning.update(
        {
            "updated_at_utc": _utc_now(),
            "governance_champion_locked": governance,
            "active_champion_locked": governance,
            "observation_signal_profile": signal_profile,
            "observation_signal_variant": signal_variant,
            "production_fallback_variant": fallback_variant,
            "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
            "purpose": (
                "Forward observation ledger; governance champion = M9 identity; "
                "observation tracks experimental live signal until H1 sealed."
            ),
        }
    )
    atomic_write_json(root / LEARNING_POLICY_REL, learning)

    lineage_policy = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "authoritative_champion": governance,
        "prior_champion": prior,
        "operational_champion": governance,
        "production_fallback_variant": fallback_variant,
        "active_signal_variant": signal_variant,
        "authoritative_runtime_resolver": "analytics.strategic_governance.resolve_governance_champion",
        "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
        "status": "M9_SYNCED",
        "note_de": "Abgeleitet aus champion_strategic_decision + prediction_operations — nicht manuell editieren.",
    }
    atomic_write_json(root / LINEAGE_POLICY_REL, lineage_policy)

    operational_status = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "operational_champion": governance,
        "production_fallback_variant": fallback_variant,
        "live_signal_variant": signal_variant,
        "live_signal_profile": signal_profile,
        "effective_orders_profile": manifest["effective_orders_profile"],
        "phase": "M9_LIVE_EXPERIMENTAL",
        "strategic_decision": "M9_R0_GOVERNANCE_WITH_H1_EXPERIMENTAL_SIGNAL",
        "auto_promotion": "DISABLED",
        "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
    }
    atomic_write_json(root / OPERATIONAL_STATUS_REL, operational_status)

    auth_status = _load_json(root / AUTH_STATUS_REL)
    auth_status.update(
        {
            "generated_at_utc": _utc_now(),
            "authoritative_champion": governance,
            "prior_champion": prior,
            "champion_change_authorized": bool(decision.get("champion_change_executed")),
            "authoritative_source": str(decision.get("approval_file") or decision.get("waiver_ref") or ""),
            "operational_status": "M9_ACTIVE_LIVE_EXPERIMENTAL",
            "live_experimental_profile": signal_profile,
            "production_fallback_variant": fallback_variant,
            "real_money_authorized": False,
            "real_money_note_de": (
                "Echtgeld nur nach H1-Seal (experimental gate); EXE-Bestätigung pro Order-Welle."
            ),
            "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
            "supersedes_g0_terminal_for": "champion_identity_only",
        }
    )
    atomic_write_json(root / AUTH_STATUS_REL, auth_status)

    auth_source = _load_json(root / AUTH_SOURCE_REL)
    auth_source.update(
        {
            "generated_at_utc": _utc_now(),
            "authoritative_champion": governance,
            "prior_champion": prior,
            "authoritative_source": str(decision.get("approval_file") or ""),
            "strategic_governance_ref": str(MANIFEST_REL).replace("\\", "/"),
        }
    )
    atomic_write_json(root / AUTH_SOURCE_REL, auth_source)

    ops = _load_json(root / PREDICTION_OPS_REL)
    if ops:
        ops["governance_champion"] = governance
        ops["updated_at_utc"] = _utc_now()
        ops["strategic_model"] = {
            "tier_1_governance_champion": governance,
            "tier_2_live_signal_profile": signal_profile,
            "tier_2_live_signal_variant": signal_variant,
            "production_fallback_variant": fallback_variant,
            "effective_orders_profile": manifest["effective_orders_profile"],
            "manifest_ref": str(MANIFEST_REL).replace("\\", "/"),
            "note_de": manifest["rules_de"],
        }
        atomic_write_json(root / PREDICTION_OPS_REL, ops)

    manifest = build_governance_manifest(root)
    atomic_write_json(root / MANIFEST_REL, manifest)

    return {
        "status": "OK",
        "manifest_path": str(MANIFEST_REL).replace("\\", "/"),
        "governance_champion": governance,
        "active_signal_variant": signal_variant,
        "effective_orders_profile": manifest["effective_orders_profile"],
        "coherence_ok": manifest["coherence_ok"],
        "coherence_issues": manifest["coherence_issues"],
    }
