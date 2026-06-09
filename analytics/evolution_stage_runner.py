"""Secure evolution stage orchestration — Sportwagen → Rennwagen with governance gates."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from aa_safe_io import atomic_write_json
from analytics.evolution_governance import GOVERNANCE_BLOCKED_ACTIONS, kernel_blocks_full_auto

EVIDENCE_REL = Path("evidence/evolution_cycle_latest.json")


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


def stage_criteria_progress(root: Path, audit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Gap analysis toward next evolution stage (for UI)."""
    from analytics.learning_cycle_audit import build_audit_context, load_evolution_track, resolve_stage

    root = Path(root)
    audit = audit or {}
    ctx = build_audit_context(root)
    stage = audit.get("stage") or ctx.get("resolved_stage") or resolve_stage(root, ctx)
    track = load_evolution_track(root)
    stages = sorted(track.get("stages") or [], key=lambda s: int(s.get("order") or 0))
    next_id = stage.get("next_stage_id")
    next_stage = next((s for s in stages if s.get("id") == next_id), None)
    if not next_stage:
        return {
            "current_stage_id": stage.get("stage_id"),
            "next_stage_id": None,
            "ready_for_next": False,
            "gaps_de": ["Maximale Stufe erreicht (unter Governance-Grenze)."],
        }

    criteria = next_stage.get("criteria") or {}
    live = ctx.get("live_metrics") or audit.get("live_metrics") or {}
    bt = ctx.get("backtest_metrics") or audit.get("backtest_metrics") or {}
    gaps: List[str] = []

    if "min_mature_live" in criteria:
        need = int(criteria["min_mature_live"])
        have = int(live.get("n_mature") or 0)
        if have < need:
            gaps.append(f"Live reif: {have}/{need} Fills")
    if "min_live_signed_hit_rate" in criteria:
        need = float(criteria["min_live_signed_hit_rate"])
        have = live.get("signed_hit_rate")
        if have is None or float(have) < need:
            gaps.append(f"Signed Hit-Rate: {have if have is not None else '—'} (Ziel ≥{need:.0%})")
    if criteria.get("live_mae_below_backtest"):
        live_mae = live.get("mae")
        bt_mae = bt.get("mae")
        if live_mae is None or bt_mae is None or float(live_mae) >= float(bt_mae):
            gaps.append("Live-MAE muss unter Backtest-MAE liegen")
    if criteria.get("daily_alpha_h1_backtest_sealed") and not ctx.get("backtest_sealed"):
        gaps.append("H1-Backtest sealed (offline PASS)")
    if criteria.get("min_weeks_improving"):
        need = int(criteria["min_weeks_improving"])
        have = int(ctx.get("weeks_improving_signed_hit") or 0)
        if have < need:
            gaps.append(f"Wochen mit steigender Hit-Rate: {have}/{need}")
    if criteria.get("shadow_pass") and not ctx.get("shadow_pass"):
        gaps.append("Shadow-Monitoring PASS")
    if criteria.get("m9_approved") and not ctx.get("m9_approved"):
        gaps.append("M9 Governance freigegeben")
    if criteria.get("evolution_allow_full_auto") and not ctx.get("evolution_allow_full_auto"):
        gaps.append("evolution_allow_full_auto in evolution_track.json (Rennwagen)")

    return {
        "current_stage_id": stage.get("stage_id"),
        "current_label_de": stage.get("stage_label_de"),
        "next_stage_id": next_id,
        "next_label_de": next_stage.get("label_de"),
        "ready_for_next": len(gaps) == 0,
        "gaps_de": gaps or [f"Bereit für Stufe «{next_stage.get('label_de')}»"],
        "auto_actions_next": list(next_stage.get("auto_actions") or []),
    }


def _weekly_audit_due(root: Path, *, days: int = 7) -> bool:
    path = root / "evidence/wallstreet_audit_latest.json"
    if not path.is_file():
        return True
    doc = _load_json(path)
    ts = str(doc.get("generated_at_utc") or "")
    try:
        last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - last).total_seconds()
        return age >= days * 86400
    except ValueError:
        return True


def run_passive_stage_actions(
    root: Path,
    *,
    allowed: Set[str],
    audit: Dict[str, Any],
    skip: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Stage-gated observe/learn actions — no champion or live orders."""
    root = Path(root)
    skip = skip or set()
    results: List[Dict[str, Any]] = []

    if "outcome_sync" in allowed and "outcome_sync" not in skip:
        try:
            from execution.live_learning.live_execution_outcome_bridge import sync_live_execution_outcomes

            r = sync_live_execution_outcomes(root, refresh_history=False)
            results.append({"action": "outcome_sync", "ok": bool(r.get("ok")), "detail": r})
        except Exception as exc:
            results.append({"action": "outcome_sync", "ok": False, "error": str(exc)[:120]})

    if "learning_capture" in allowed and "learning_capture" not in skip:
        try:
            from analytics.public_learning_kernel import run_capture_only

            r = run_capture_only(root)
            ok = bool((r.get("readiness") or {}).get("learning_healthy", True))
            results.append({"action": "learning_capture", "ok": ok})
        except Exception as exc:
            results.append({"action": "learning_capture", "ok": False, "error": str(exc)[:120]})

    if "feedback_update" in allowed:
        try:
            from aa_prediction_outcomes import write_feedback_report

            out = root / "model_output_sp500_pit_t212"
            if out.is_dir():
                write_feedback_report(out)
                results.append({"action": "feedback_update", "ok": True})
            else:
                results.append({"action": "feedback_update", "ok": False, "reason": "no_out_dir"})
        except Exception as exc:
            results.append({"action": "feedback_update", "ok": False, "error": str(exc)[:120]})

    if "price_refresh_on_predict" in allowed:
        hint_path = root / "control/evolution_runtime_hints.json"
        hints = _load_json(hint_path)
        hints["prefer_quote_refresh_on_predict"] = True
        hints["updated_at_utc"] = _utc_now()
        atomic_write_json(hint_path, hints)
        results.append({"action": "price_refresh_on_predict", "ok": True})

    if "weekly_audit" in allowed and _weekly_audit_due(root):
        try:
            from analytics.wallstreet_performance_audit import run_wallstreet_audit

            r = run_wallstreet_audit(root)
            results.append({"action": "weekly_audit", "ok": True, "verdict": r.get("verdict")})
        except Exception as exc:
            results.append({"action": "weekly_audit", "ok": False, "error": str(exc)[:120]})
    elif "weekly_audit" in allowed:
        results.append({"action": "weekly_audit", "ok": True, "skipped": True, "reason": "not_due"})

    for blocked in GOVERNANCE_BLOCKED_ACTIONS:
        if blocked in allowed:
            results.append(
                {
                    "action": blocked,
                    "ok": False,
                    "blocked": True,
                    "reason_de": "Governance — AI_KERNEL + evolution_track verbieten Vollauto",
                }
            )

    return results


def run_evolution_cycle(
    root: Path,
    *,
    audit: Optional[Dict[str, Any]] = None,
    apply_improvements: bool = True,
    skip_passive: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Full secure evolution pass: audit → passive actions → safe auto-apply."""
    from analytics.evolution_auto_apply import apply_safe_evolution_improvements
    from analytics.learning_cycle_audit import run_learning_cycle_audit

    root = Path(root)
    if audit is None:
        audit = run_learning_cycle_audit(root)

    stage = audit.get("stage") or {}
    allowed = set(stage.get("auto_actions_allowed") or [])
    passive = run_passive_stage_actions(root, allowed=allowed, audit=audit, skip=skip_passive)
    auto_apply: Dict[str, Any] = {"skipped": True}
    if apply_improvements:
        auto_apply = apply_safe_evolution_improvements(root, audit=audit)

    progress = stage_criteria_progress(root, audit)
    kernel_block = kernel_blocks_full_auto(root)

    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "ok": True,
        "stage": stage,
        "evolution_state": audit.get("evolution_state") or {},
        "progress": progress,
        "passive_actions": passive,
        "auto_apply": auto_apply,
        "governance": {
            "kernel_blocks_full_auto": kernel_block,
            "blocked_actions": sorted(GOVERNANCE_BLOCKED_ACTIONS),
            "evolution_allow_full_auto": bool(
                _load_json(root / "control/evolution_track.json").get("governance", {}).get(
                    "evolution_allow_full_auto"
                )
            ),
        },
        "message_de": (
            f"Evolution {stage.get('stage_label_de', 'Sportwagen')}: "
            f"{len([p for p in passive if p.get('ok')])} passive OK, "
            f"{len(auto_apply.get('applied') or [])} Tuning angewendet."
        ),
    }
    atomic_write_json(root / EVIDENCE_REL, report)
    return report
