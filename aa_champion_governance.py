"""Champion governance panel for Decision Cockpit (Phase D)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_evidence_schema import resolve_locked_champion

STRATEGIC_DECISION_PATH = Path("control") / "champion_strategic_decision.json"

CHARTER_PATH = Path("control") / "champion_decision_charter.md"
CRITERIA_PATH = Path("control") / "champion_change_criteria.yaml"
CANONICAL_PATH = Path("evidence") / "canonical_model_comparison.json"
COST_STRESS_PATH = Path("control") / "evidence" / "cost_stress_status.json"


def _read_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "MISSING"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def load_champion_change_criteria(root: Path) -> Tuple[Dict[str, Any], str]:
    path = Path(root) / CRITERIA_PATH
    if not path.is_file():
        return {}, "MISSING"
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}, "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def _metric_for_variant(canonical: Dict[str, Any], variant_id: str) -> Dict[str, float]:
    for row in canonical.get("variants") or []:
        if str(row.get("variant_id")) == variant_id:
            return dict(row.get("metrics") or {})
    return {}


def _rank_entry(rankings: Dict[str, Any], variant_id: str) -> Optional[Dict[str, Any]]:
    for key in ("sharpe_matrix_embedded", "sharpe_aligned_intersection"):
        for row in rankings.get(key) or []:
            if row.get("variant_id") == variant_id:
                return row
    return None


def build_champion_governance_de(root: Path) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)
    criteria, crit_st = load_champion_change_criteria(root)
    canonical, can_st = _read_json(root / CANONICAL_PATH)
    cost_stress, cs_st = _read_json(root / COST_STRESS_PATH)

    headline = canonical.get("headline") or {}
    rankings = canonical.get("rankings") or {}
    matrix_rank = rankings.get("sharpe_matrix_embedded") or []
    n_matrix = len(matrix_rank)

    champ_metrics = _metric_for_variant(canonical, locked)
    m1_metrics = _metric_for_variant(canonical, "M1_MOM_BLEND_MATCHED_CONTROLS")
    r0_metrics = _metric_for_variant(canonical, "R0_LEGACY_ENSEMBLE")

    champ_sharpe = float(champ_metrics.get("sharpe_0rf") or 0)
    m1_sharpe = float(m1_metrics.get("sharpe_0rf") or 0)
    r0_sharpe = float(r0_metrics.get("sharpe_0rf") or 0)
    m1_delta = m1_sharpe - champ_sharpe if champ_sharpe and m1_sharpe else None
    r0_delta = r0_sharpe - champ_sharpe if champ_sharpe and r0_sharpe else None

    champ_rank_row = _rank_entry(rankings, locked)
    champ_rank = champ_rank_row.get("rank") if champ_rank_row else headline.get("champion_sharpe_rank_matrix")
    leader = headline.get("matrix_embedded_sharpe_leader")
    is_sharpe_leader = bool(headline.get("champion_is_sharpe_leader"))

    cost_gate = cost_stress.get("COST_STRESS_GATE") or {} if cs_st == "OK" else {}
    cost_status = str(cost_gate.get("evaluation_status") or "UNKNOWN")
    cost_pass = cost_gate.get("pass")

    blockers = list(canonical.get("governance_blockers") or [])
    if cs_st == "OK":
        blockers.extend(cost_gate.get("blockers") or [])

    strategic, strat_st = _read_json(root / STRATEGIC_DECISION_PATH)
    strat_summary = strategic.get("decision_summary_de") if strat_st == "OK" else None
    strat_option = strategic.get("selected_option") if strat_st == "OK" else None

    lines = [
        f"Freigabe: Produktiv freigegeben — {locked}",
        f"Backtest-Sharpe (Matrix ~1860d): Rang {champ_rank} von {n_matrix}"
        + (" — nicht höchster Sharpe" if not is_sharpe_leader else ""),
    ]
    if leader and leader != locked:
        lines.append(f"Matrix-Sharpe-Führer: {leader}")
    if m1_delta is not None:
        lines.append(f"M1-Delta Sharpe (M1 − Champion): {m1_delta:+.4f}")
    if r0_delta is not None:
        lines.append(f"R0-Delta Sharpe (R0 − Champion): {r0_delta:+.4f}")
    lines.append(f"Cost-Stress (+25 bps): {cost_status} (pass={cost_pass})")
    lines.append("Auto-Promotion: DISABLED — manuelle Freigabe erforderlich")
    if blockers:
        lines.append("Aktive Blocker: " + ", ".join(sorted(set(str(b) for b in blockers))))
    lines.append("Quarantäne: R5_rank_only_train5 (kein operativer Champion)")
    if strat_summary:
        lines.append(f"Phase-E-Entscheidung: {strat_option or 'n/a'} — {strat_summary}")
    if headline.get("do_not_cross_compare_frames"):
        lines.append("Hinweis: Matrix-embedded ≠ MOM-Intersection-Sharpe vermischen.")

    charter_ok = (root / CHARTER_PATH).is_file()
    canonical_ok = can_st == "OK"

    return {
        "schema_version": 1,
        "authoritative_champion": locked,
        "approval_status_de": "Freigegeben",
        "is_highest_backtest_sharpe": is_sharpe_leader,
        "matrix_sharpe_rank": champ_rank,
        "matrix_variants_compared": n_matrix,
        "matrix_sharpe_leader": leader,
        "m1_sharpe_delta": m1_delta,
        "r0_sharpe_delta": r0_delta,
        "champion_sharpe_0rf": champ_sharpe or None,
        "m1_sharpe_0rf": m1_sharpe or None,
        "cost_stress_status": cost_status,
        "cost_stress_pass": cost_pass,
        "auto_promotion": "DISABLED",
        "change_criteria_status": crit_st,
        "canonical_comparison_status": can_st,
        "charter_present": charter_ok,
        "lines_de": lines,
        "summary_de": lines[1] if len(lines) > 1 else lines[0],
        "blockers": sorted(set(str(b) for b in blockers)),
        "criteria_ref": str(CRITERIA_PATH).replace("\\", "/"),
        "charter_ref": str(CHARTER_PATH).replace("\\", "/"),
        "canonical_ref": str(CANONICAL_PATH).replace("\\", "/"),
        "ready_for_external_review": charter_ok and canonical_ok and crit_st == "OK",
        "strategic_decision_option": strat_option,
        "strategic_decision_summary_de": strat_summary,
        "strategic_decision_status": strat_st,
    }
