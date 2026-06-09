"""Safe auto-improvements (Zone A/B) driven by evolution stage — never champion/auto-execute."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json
from analytics.evolution_governance import GOVERNANCE_BLOCKED_ACTIONS, kernel_blocks_full_auto
from analytics.learning_cycle_audit import load_evolution_track, resolve_stage
from analytics.pilot_day_trading_policy import load_unified_policy, save_unified_policy

EVIDENCE_REL = Path("evidence/evolution_auto_apply_latest.json")
SHADOW_METRICS_REL = Path("evidence/evolution_shadow_metrics_latest.json")
CHALLENGER_QUEUE_REL = Path("evidence/challenger_offline_queue_latest.json")


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _estimate_live_slippage_bps(root: Path) -> float | None:
    from execution.live_learning.live_execution_outcome_bridge import (
        _filled_from_payload,
        _history_orders_by_id,
        _load_submitted_records,
    )

    gaps: List[float] = []
    history = _history_orders_by_id(root)
    for rec in _load_submitted_records(root):
        rec_id = str((rec.get("response") or {}).get("id") or "")
        resp = history.get(rec_id, rec.get("response") or {})
        filled, _, entry = _filled_from_payload(resp, rec.get("draft") or {})
        if not filled:
            continue
        limit = float((rec.get("draft") or {}).get("limit_price") or resp.get("limitPrice") or 0)
        if limit > 0 and entry > 0:
            gaps.append(abs(entry - limit) / limit * 10000.0)
    if not gaps:
        return None
    gaps.sort()
    return float(gaps[len(gaps) // 2])


def apply_safe_evolution_improvements(root: Path, *, audit: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Apply only actions allowed for current evolution stage."""
    root = Path(root)
    track = load_evolution_track(root)
    limits = track.get("safe_auto_limits") or {}
    stage = resolve_stage(root)
    allowed = set(stage.get("auto_actions_allowed") or [])
    applied: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    pol = load_unified_policy(root)
    changed = False

    if "slippage_calibrate" in allowed:
        est = _estimate_live_slippage_bps(root)
        costs = dict(pol.get("costs") or {})
        current = float(costs.get("slippage_bps") or 5.0)
        cap = float(limits.get("slippage_bps_max") or 25.0)
        step = float(limits.get("slippage_bps_step") or 1.0)
        if est is not None and est > current + 0.5:
            new_val = min(cap, round(max(current + step, est * 0.8), 1))
            if new_val > current:
                costs["slippage_bps"] = new_val
                costs["evolution_slippage_calibrated_at_utc"] = _utc_now_iso()
                pol["costs"] = costs
                changed = True
                applied.append({"action": "slippage_calibrate", "from": current, "to": new_val, "observed_bps": est})
            else:
                skipped.append({"action": "slippage_calibrate", "reason": "at_cap"})
        else:
            skipped.append({"action": "slippage_calibrate", "reason": "insufficient_fill_data_or_already_ok"})
    else:
        skipped.append({"action": "slippage_calibrate", "reason": "stage_not_allowed"})

    if "quote_refresh_tune" in allowed:
        refresh = dict(pol.get("refresh") or {})
        open_s = int(refresh.get("quote_refresh_seconds_open") or 60)
        floor = int(limits.get("quote_refresh_seconds_open_min") or 45)
        if open_s > floor:
            refresh["quote_refresh_seconds_open"] = max(floor, open_s - 5)
            refresh["evolution_tuned_at_utc"] = _utc_now_iso()
            pol["refresh"] = refresh
            changed = True
            applied.append({"action": "quote_refresh_tune", "quote_refresh_seconds_open": refresh["quote_refresh_seconds_open"]})
    else:
        skipped.append({"action": "quote_refresh_tune", "reason": "stage_not_allowed"})

    if "cash_buffer_tune" in allowed and audit:
        live = audit.get("live_metrics") or {}
        hit = live.get("signed_hit_rate")
        try:
            from analytics.prediction_operations import load_prediction_operations

            ops = load_prediction_operations(root)
            budget = dict(ops.get("budget") or {})
            buf = float(budget.get("cash_buffer_pct") or 5.0)
            buf_min = float(limits.get("cash_buffer_pct_min") or 3.0)
            buf_max = float(limits.get("cash_buffer_pct_max") or 10.0)
            if hit is not None and float(hit) >= 0.48 and buf > buf_min:
                budget["cash_buffer_pct"] = max(buf_min, min(buf_max, round(buf - 0.5, 1)))
                ops["budget"] = budget
                ops_path = root / "control/prediction_operations.json"
                ops_path.write_text(json.dumps(ops, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                applied.append({"action": "cash_buffer_tune", "cash_buffer_pct": budget["cash_buffer_pct"]})
            else:
                skipped.append({"action": "cash_buffer_tune", "reason": "hit_rate_or_buffer_not_ready"})
        except Exception as exc:
            skipped.append({"action": "cash_buffer_tune", "reason": str(exc)[:80]})
    else:
        skipped.append({"action": "cash_buffer_tune", "reason": "stage_not_allowed"})

    if "min_trade_tune" in allowed:
        lt = dict(pol.get("live_trading") or {})
        current = float(lt.get("min_trade_eur") or 5.0)
        floor = float((pol.get("costs") or {}).get("min_trade_eur_floor") or 5.0)
        live = (audit or {}).get("live_metrics") or {}
        hit = live.get("signed_hit_rate")
        if hit is not None and float(hit) >= 0.48 and current > floor:
            new_val = max(floor, round(current - 1.0, 2))
            if new_val < current:
                lt["min_trade_eur"] = new_val
                lt["evolution_min_trade_tuned_at_utc"] = _utc_now_iso()
                pol["live_trading"] = lt
                changed = True
                applied.append({"action": "min_trade_tune", "from": current, "to": new_val})
            else:
                skipped.append({"action": "min_trade_tune", "reason": "at_floor"})
        else:
            skipped.append({"action": "min_trade_tune", "reason": "insufficient_live_hit_rate"})
    else:
        skipped.append({"action": "min_trade_tune", "reason": "stage_not_allowed"})

    if "shadow_metrics_log" in allowed and audit:
        payload = {
            "schema_version": 1,
            "generated_at_utc": _utc_now_iso(),
            "stage_id": stage.get("stage_id"),
            "live_metrics": audit.get("live_metrics") or {},
            "backtest_metrics": audit.get("backtest_metrics") or {},
            "delta_vs_previous": audit.get("delta_vs_previous") or {},
        }
        atomic_write_json(root / SHADOW_METRICS_REL, payload)
        applied.append({"action": "shadow_metrics_log", "path": str(SHADOW_METRICS_REL)})
    else:
        skipped.append({"action": "shadow_metrics_log", "reason": "stage_not_allowed"})

    if "challenger_offline_queue" in allowed:
        queue = {
            "schema_version": 1,
            "generated_at_utc": _utc_now_iso(),
            "status": "QUEUED_OFFLINE_ONLY",
            "champion_unchanged": True,
            "note_de": (
                "Challenger-Backtest nur offline — kein Live-Champion-Wechsel ohne Seal und Freigabe."
            ),
            "suggested_command": "python3 tools/run_tomorrow_prediction.py --profile daily_alpha_h1",
        }
        atomic_write_json(root / CHALLENGER_QUEUE_REL, queue)
        applied.append({"action": "challenger_offline_queue", "queued": True, "live_promotion": False})
    else:
        skipped.append({"action": "challenger_offline_queue", "reason": "stage_not_allowed"})

    if "execution_style_optimize" in allowed:
        lt = dict(pol.get("live_trading") or {})
        if str(lt.get("order_execution_type") or "limit") == "limit":
            lt["evolution_execution_note_utc"] = _utc_now_iso()
            lt["evolution_execution_recommendation_de"] = (
                "Rennsport: Limit DAY beibehalten bis ≥30 Live-Fills mit Slippage-Daten."
            )
            pol["live_trading"] = lt
            changed = True
            applied.append({"action": "execution_style_optimize", "mode": "limit_day_unchanged"})
        else:
            skipped.append({"action": "execution_style_optimize", "reason": "already_market"})
    else:
        skipped.append({"action": "execution_style_optimize", "reason": "stage_not_allowed"})

    track_gov = (track.get("governance") or {})
    full_auto_flag = bool(track_gov.get("evolution_allow_full_auto"))
    for forbidden in GOVERNANCE_BLOCKED_ACTIONS:
        if forbidden not in allowed:
            continue
        reason = "stage_not_allowed"
        if forbidden in allowed:
            if kernel_blocks_full_auto(root) or not full_auto_flag:
                reason = "governance_blocked — AI_KERNEL.gui_confirm + evolution_allow_full_auto"
            else:
                reason = "governance_blocked — m9/shadow criteria not met"
        skipped.append({"action": forbidden, "reason": reason, "blocked": True})

    if changed:
        save_unified_policy(root, pol)

    out = {
        "schema_version": 1,
        "generated_at_utc": _utc_now_iso(),
        "ok": True,
        "stage_id": stage.get("stage_id"),
        "applied": applied,
        "skipped": skipped,
        "message_de": (
            f"Evolution Auto-Apply ({stage.get('stage_label_de')}): "
            f"{len(applied)} angewendet, {len(skipped)} uebersprungen."
        ),
    }
    atomic_write_json(root / EVIDENCE_REL, out)
    return out
