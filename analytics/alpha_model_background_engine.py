"""Active Alpha Model — Hintergrund-Engine (Prognose, Rebalance-Plan, H1-Monitor). R3 = Anzeige."""
from __future__ import annotations

import html
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/alpha_model_background_engine_policy.json")
_EVIDENCE_REL = Path("evidence/alpha_model_background_engine_latest.json")
_STATE_REL = Path("control/alpha_model_background_engine_state.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_engine_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _cooldown_ok(root: Path, step: str, *, minutes: int) -> bool:
    state = _load_json(root / _STATE_REL)
    stamp = _parse_utc(str((state.get("last_step_utc") or {}).get(step) or ""))
    if not stamp:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60.0
    return age >= float(minutes)


def _mark_step(root: Path, step: str) -> None:
    state = _load_json(root / _STATE_REL)
    last = dict(state.get("last_step_utc") or {})
    last[step] = _utc_now()
    state["last_step_utc"] = last
    state["updated_at_utc"] = _utc_now()
    atomic_write_json(root / _STATE_REL, state)


def _step_predict(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.r3_internet_requirement import internet_step_blocked, require_internet_for

    net = require_internet_for(root, consumer="alpha_engine")
    if not net.get("allowed"):
        return internet_step_blocked("predict", net)
    cd = int((policy.get("cooldown_min") or {}).get("predict") or 90)
    if not _cooldown_ok(root, "predict", minutes=cd):
        return {"step": "predict", "ok": True, "skipped": True, "reason_de": "cooldown"}
    readiness = _load_json(root / "control/prediction_readiness.json")
    gen = _parse_utc(str(readiness.get("generated_at_utc") or ""))
    if readiness.get("ok") and gen:
        if gen.tzinfo is None:
            gen = gen.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - gen).total_seconds() < cd * 60:
            return {
                "step": "predict",
                "ok": True,
                "skipped": True,
                "reason_de": "prognose_frisch",
                "signal_date": readiness.get("signal_date"),
            }
    try:
        from analytics.prediction_operations import maybe_run_eod_prediction_switch

        out = maybe_run_eod_prediction_switch(root, force=False)
        if out.get("skipped") and readiness.get("ok"):
            return {
                "step": "predict",
                "ok": True,
                "skipped": True,
                "reason_de": "prognose_bereit",
                "signal_date": readiness.get("signal_date"),
            }
        if out.get("skipped") and not readiness.get("ok"):
            from tools.run_tomorrow_prediction import run_prediction

            out = run_prediction(root, force_prices=False, allow_fallback=True)
        _mark_step(root, "predict")
        return {
            "step": "predict",
            "ok": bool(out.get("ok")),
            "skipped": bool(out.get("skipped")),
            "signal_date": out.get("signal_date"),
            "detail_de": str(out.get("message_de") or out.get("last_error") or "")[:120],
        }
    except Exception as exc:
        return {"step": "predict", "ok": False, "error_de": str(exc)[:120]}


def _step_rebalance_plan(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.r3_internet_requirement import internet_step_blocked, require_internet_for

    net = require_internet_for(root, consumer="alpha_engine")
    if not net.get("allowed"):
        return internet_step_blocked("rebalance_plan", net)
    cd = int((policy.get("cooldown_min") or {}).get("rebalance_plan") or 45)
    from analytics.r3_closed_loop import (
        load_r3_account_for_engine,
        rebalance_plan_inputs_stale,
        record_closed_loop_tick,
    )

    stale, stale_reasons = rebalance_plan_inputs_stale(root)
    cooldown_elapsed = _cooldown_ok(root, "rebalance_plan", minutes=cd)
    if not cooldown_elapsed and not stale:
        account = load_r3_account_for_engine(root)
        plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
        record_closed_loop_tick(
            root,
            account=account,
            plan=plan,
            step="rebalance_plan",
            loop_ok=bool(plan.get("pipeline_synced", True)) and bool(account.get("ok")),
            stale_reason_de="cooldown — Eingaben unverändert",
        )
        return {
            "step": "rebalance_plan",
            "ok": True,
            "skipped": True,
            "reason_de": "cooldown",
            "stale_plan": False,
            "closed_loop": bool(plan.get("pipeline_synced", True)),
            "pipeline_synced": bool(plan.get("pipeline_synced", True)),
        }
    try:
        from analytics.king_plan_integration import rebuild_investment_plan_with_king
        from analytics.live_trading_operations import rebalance_status

        out = rebuild_investment_plan_with_king(root, force_t212_sync=False)
        account = load_r3_account_for_engine(root)
        status = rebalance_status(root)
        if not out.get("ok"):
            record_closed_loop_tick(
                root,
                account=account,
                plan=None,
                step="rebalance_plan",
                loop_ok=False,
                stale_reason_de=str(out.get("error_de") or "Plan-Rebuild fehlgeschlagen")[:120],
            )
            return {
                "step": "rebalance_plan",
                "ok": False,
                "error_de": out.get("error_de") or "Plan-Rebuild fehlgeschlagen",
                "closed_loop": False,
                "cash_source": account.get("cash_source"),
                "forced_stale_rebuild": stale and not cooldown_elapsed,
                "stale_reasons": stale_reasons,
            }

        plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
        pipeline_synced = bool(out.get("pipeline_synced"))
        loop_doc = record_closed_loop_tick(
            root,
            account=account,
            plan=plan if plan else None,
            step="rebalance_plan",
            loop_ok=pipeline_synced,
            pipeline_partial=bool(out.get("partial")),
        )
        _mark_step(root, "rebalance_plan")
        investable = float(out.get("investable_eur") or account.get("investable_eur") or 0)
        return {
            "step": "rebalance_plan",
            "ok": True,
            "skipped": False,
            "forced_stale_rebuild": stale and not cooldown_elapsed,
            "stale_reasons": stale_reasons if stale else [],
            "is_due": bool(status.get("is_due")),
            "positions": int(out.get("t212_positions_count") or 0),
            "investable_eur": investable,
            "r3_investable_eur": investable,
            "planning_cash_eur": account.get("planning_cash_eur"),
            "cash_eur": account.get("cash_eur"),
            "cash_source": account.get("cash_source"),
            "closed_loop": pipeline_synced,
            "pipeline_synced": pipeline_synced,
            "partial": bool(out.get("partial")),
            "closed_loop_ref": "evidence/r3_closed_loop_latest.json",
            "king_boost_applied": out.get("king_boost_applied"),
            "rebalanced_to_t212": out.get("rebalanced_to_t212"),
            "reeval_refreshed": out.get("reeval_refreshed"),
            "orders_refreshed": out.get("orders_refreshed"),
            "pipeline_run_id": out.get("pipeline_run_id"),
            "detail_de": str(
                loop_doc.get("message_de") or out.get("detail_de") or status.get("summary_de") or ""
            )[:120],
            "presentation_only": True,
            "orders_execution": False,
            "plan_only": True,
        }
    except Exception as exc:
        return {"step": "rebalance_plan", "ok": False, "error_de": str(exc)[:120]}


def _step_order_prep(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from analytics.r3_freigabe import refresh_freigabe_evidence

        doc = refresh_freigabe_evidence(root)
        return {
            "step": "order_prep",
            "ok": True,
            "package_ready": bool(doc.get("package_ready") or doc.get("freigabe_ready")),
            "freigabe_ready": bool(doc.get("package_ready") or doc.get("freigabe_ready")),
            "detail_de": str(doc.get("headline_de") or "")[:120],
        }
    except Exception as exc:
        return {"step": "order_prep", "ok": False, "error_de": str(exc)[:120]}


def _step_stufe_a(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    stufe_pol = _load_json(root / "control/king_stufe_a_policy.json")
    if not stufe_pol.get("enabled", True):
        return {"step": "stufe_a", "ok": True, "skipped": True, "reason_de": "deaktiviert"}
    cd = int(stufe_pol.get("tick_cooldown_min") or 45)
    if not _cooldown_ok(root, "stufe_a", minutes=cd):
        return {"step": "stufe_a", "ok": True, "skipped": True, "reason_de": "cooldown"}
    try:
        from analytics.king_stufe_a import run_stufe_a_tick

        out = run_stufe_a_tick(root, force=False, persist=True)
        if not out.get("skipped"):
            _mark_step(root, "stufe_a")
        return {**out, "step": "stufe_a"}
    except Exception as exc:
        return {"step": "stufe_a", "ok": False, "error_de": str(exc)[:120]}


def _step_king_trading_assist(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    assist_pol = _load_json(root / "control/king_trading_assist_policy.json")
    if not assist_pol.get("enabled", True):
        return {"step": "king_trading", "ok": True, "skipped": True, "reason_de": "deaktiviert"}
    try:
        from analytics.king_trading_assist import run_king_trading_assist

        out = run_king_trading_assist(root, force=False)
        if not out.get("skipped"):
            _mark_step(root, "king_trading")
        return out
    except Exception as exc:
        return {"step": "king_trading", "ok": True, "skipped": True, "error_de": str(exc)[:120]}


def _step_h1_monitor(root: Path, policy: Dict[str, Any]) -> Dict[str, Any]:
    cd = int((policy.get("cooldown_min") or {}).get("h1_monitor") or 5)
    if not _cooldown_ok(root, "h1_monitor", minutes=cd):
        return {"step": "h1_monitor", "ok": True, "skipped": True, "reason_de": "cooldown"}
    try:
        from analytics.live_profile_governance import h1_backtest_status, h1_model_evidence

        h1 = h1_backtest_status(root)
        h1_ev = h1_model_evidence(root)
        status = str(h1.get("status") or "MISSING")
        eval_doc: Dict[str, Any] = {}
        if status == "COMPLETE":
            try:
                from tools.run_daily_alpha_h1_pipeline import _evaluate

                eval_doc = _evaluate(root, seal=False)
            except Exception:
                eval_doc = _load_json(root / "evidence/daily_alpha_h1_evaluation_latest.json")
        pipeline = {
            "ok": status in ("RUNNING", "COMPLETE"),
            "phase": status.lower(),
            "h1_status": status,
            "h1_backtest_status": {"status": status, "run_dir": h1_ev.get("run_dir")},
            "progress_pct": h1.get("progress_pct"),
            "run_dir": h1_ev.get("run_dir"),
            "pass_full_seal": h1_ev.get("pass_full_seal"),
            "operational_ok": h1_ev.get("operational_ok"),
            "metrics_strategy": h1_ev.get("metrics_strategy"),
            "updated_at_utc": _utc_now(),
            "engine_de": "Active Alpha Model",
            "presentation_de": "Monitor only — kein Neustart aus R3",
        }
        if eval_doc.get("evaluated_at_utc") or eval_doc.get("message_de"):
            pipeline["evaluation_de"] = str(eval_doc.get("message_de") or "")[:160]
        atomic_write_json(root / "evidence/daily_alpha_h1_pipeline_latest.json", pipeline)
        _mark_step(root, "h1_monitor")
        return {
            "step": "h1_monitor",
            "ok": True,
            "h1_status": status,
            "run_dir": h1_ev.get("run_dir"),
            "operational_ok": h1_ev.get("operational_ok"),
            "pass_full_seal": h1_ev.get("pass_full_seal"),
            "progress_pct": h1.get("progress_pct"),
            "evaluated": bool(eval_doc.get("evaluated_at_utc") or h1_ev.get("evaluated_at_utc")),
            "detail_de": f"H1 {status}" + (
                f" · Sharpe {float((h1_ev.get('metrics_strategy') or {}).get('sharpe_0rf') or 0):.2f}"
                if (h1_ev.get("metrics_strategy") or {}).get("sharpe_0rf") is not None
                else ""
            ) + (
                f" · {int(h1.get('progress_pct') or 0)}%" if h1.get("progress_pct") is not None else ""
            ),
        }
    except Exception as exc:
        return {"step": "h1_monitor", "ok": False, "error_de": str(exc)[:120]}


def _step_r3_refresh(
    root: Path,
    policy: Dict[str, Any],
    *,
    rebalance_step: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Nach Rebalance: kanonische Prognose-Pipeline (T212 coalesced)."""
    reb = rebalance_step or {}
    rebalance_ran = bool(reb.get("ok")) and not reb.get("skipped")
    try:
        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

        out = ensure_r3_prognosis_fresh(root, force=rebalance_ran, persist=True)
        doc = out.get("prognosis") or {}
        if not doc:
            doc = _load_json(root / "evidence/r3_t212_prognosis_latest.json")
        return {
            "step": "r3_refresh",
            "ok": bool(doc.get("ok")),
            "skipped": bool(out.get("skipped")),
            "refreshed": not bool(out.get("skipped")),
            "reason_de": "nach_rebalance" if rebalance_ran else str(out.get("reason_de") or "coalesced"),
            "signal_date": doc.get("signal_date"),
            "positions": doc.get("positions"),
            "worthwhile_buys": doc.get("worthwhile_buy_count"),
            "pipeline_ok": bool(out.get("ok")),
            "detail_de": str(doc.get("message_de") or doc.get("headline_de") or "")[:120],
        }
    except Exception as exc:
        doc = _load_json(root / "evidence/r3_t212_prognosis_latest.json")
        return {
            "step": "r3_refresh",
            "ok": bool(doc.get("ok")),
            "skipped": True,
            "error_de": str(exc)[:120],
            "detail_de": str(doc.get("message_de") or "")[:120],
        }


def tick_alpha_model_background(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Ein Hintergrund-Tick — Engine rechnet, R3 liest nur Evidence."""
    root = Path(root)
    policy = load_engine_policy(root)
    if force:
        atomic_write_json(root / _STATE_REL, {"last_step_utc": {}, "updated_at_utc": _utc_now()})

    predict_step = _step_predict(root, policy)
    king_step = _step_king_trading_assist(root, policy)
    stufe_a_step = _step_stufe_a(root, policy)
    rebalance_step = _step_rebalance_plan(root, policy)
    steps = [
        predict_step,
        king_step,
        stufe_a_step,
        rebalance_step,
        _step_order_prep(root, policy),
        _step_h1_monitor(root, policy),
        _step_r3_refresh(root, policy, rebalance_step=rebalance_step),
    ]
    ok_n = sum(1 for s in steps if s.get("ok"))
    h1 = next((s for s in steps if s.get("step") == "h1_monitor"), {})
    h1_ev: Dict[str, Any] = {}
    try:
        from analytics.live_profile_governance import h1_model_evidence

        h1_ev = h1_model_evidence(root)
    except Exception:
        pass
    predict = next((s for s in steps if s.get("step") == "predict"), {})
    reb = next((s for s in steps if s.get("step") == "rebalance_plan"), {})
    king = next((s for s in steps if s.get("step") == "king_trading"), {})
    stufe_a = next((s for s in steps if s.get("step") == "stufe_a"), {})
    order_prep = next((s for s in steps if s.get("step") == "order_prep"), {})
    refresh = next((s for s in steps if s.get("step") == "r3_refresh"), {})

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "engine_de": str(policy.get("engine_de") or "Active Alpha Model"),
        "presentation_de": str(policy.get("presentation_de") or "R3 = Anzeige only"),
        "ok": ok_n == len(steps)
        and not (reb.get("skipped") and reb.get("stale_plan"))
        and reb.get("closed_loop") is not False,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "steps": steps,
        "predict": {
            "ok": bool(predict.get("ok")),
            "signal_date": predict.get("signal_date"),
            "skipped": predict.get("skipped"),
        },
        "rebalance": {
            "ok": bool(reb.get("ok")),
            "skipped": reb.get("skipped"),
            "stale_plan": reb.get("stale_plan"),
            "pipeline_synced": reb.get("pipeline_synced"),
            "partial": reb.get("partial"),
            "is_due": reb.get("is_due"),
            "investable_eur": reb.get("investable_eur"),
            "r3_investable_eur": reb.get("r3_investable_eur"),
            "planning_cash_eur": reb.get("planning_cash_eur"),
            "cash_source": reb.get("cash_source"),
            "closed_loop": reb.get("closed_loop"),
            "pipeline_run_id": reb.get("pipeline_run_id"),
        },
        "closed_loop_ref": "evidence/r3_closed_loop_latest.json",
        "king_trading": {
            "ok": bool(king.get("ok")),
            "skipped": king.get("skipped"),
            "model": king.get("model"),
            "agrees_with_model": king.get("agrees_with_model"),
            "detail_de": king.get("detail_de"),
            "evidence_ref": "evidence/king_trading_assist_latest.json",
        },
        "stufe_a": {
            "ok": bool(stufe_a.get("ok")),
            "skipped": stufe_a.get("skipped"),
            "growth_phase": stufe_a.get("growth_phase"),
            "detail_de": stufe_a.get("headline_de"),
            "evidence_ref": "evidence/king_stufe_a_latest.json",
        },
        "order_prep": {
            "ok": bool(order_prep.get("ok")),
            "package_ready": order_prep.get("package_ready"),
            "detail_de": order_prep.get("detail_de"),
            "evidence_ref": "evidence/r3_freigabe_latest.json",
        },
        "h1_backtest": {
            "status": h1.get("h1_status") or h1_ev.get("h1_status"),
            "run_dir": h1.get("run_dir") or h1_ev.get("run_dir"),
            "progress_pct": h1.get("progress_pct"),
            "sealed": h1_ev.get("sealed"),
            "pass_full_seal": h1_ev.get("pass_full_seal"),
            "operational_ok": h1.get("operational_ok") if h1.get("operational_ok") is not None else h1_ev.get("operational_ok"),
            "metrics_strategy": h1_ev.get("metrics_strategy"),
        },
        "r3_display": {
            "ok": bool(refresh.get("ok")),
            "signal_date": refresh.get("signal_date"),
            "positions": refresh.get("positions"),
        },
        "confirmation_de": _confirmation_de(predict, reb, h1, refresh),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "api_route_de": "GET /api/r3/engine",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_engine_status(root: Path, *, persist: bool = False) -> Dict[str, Any]:
    doc = _load_json(root / _EVIDENCE_REL)
    if doc:
        return doc
    if persist:
        return tick_alpha_model_background(root, force=False)
    return {
        "engine_de": "Active Alpha Model",
        "presentation_de": "R3 = Anzeige",
        "ok": False,
        "confirmation_de": "Engine — bash tools/king_ops.sh alpha-engine",
    }


def _confirmation_de(
    predict: Dict[str, Any],
    reb: Dict[str, Any],
    h1: Dict[str, Any],
    refresh: Dict[str, Any],
) -> str:
    sig = predict.get("signal_date") or refresh.get("signal_date") or "—"
    h1s = str(h1.get("h1_status") or "—")
    reb_bit = "Rebalance fällig" if reb.get("is_due") else "Rebalance OK"
    if predict.get("skipped") and refresh.get("ok"):
        return f"Active Alpha · Hintergrund · Anzeige R3 · {sig} · {reb_bit} · H1 {h1s}"
    if predict.get("ok") or refresh.get("ok"):
        return f"Active Alpha · Hintergrund · Prognose {sig} · {reb_bit} · H1 {h1s}"
    return f"Active Alpha · Hintergrund · H1 {h1s} · Engine tick ausstehend"


R3_ENGINE_CSS = """
.r3-engine-status {
  text-align: center; font-size: 11px; color: var(--muted); margin: 0 0 8px;
  padding: 7px 12px; border-radius: 10px;
  border: 1px solid var(--line); background: rgba(127,127,127,.05);
}
.r3-engine-status.ok { color: var(--accent); border-color: rgba(94,92,230,.25); }
"""


def render_r3_engine_status_line(root: Path, status: Optional[Dict[str, Any]] = None) -> str:
    doc = status or _load_json(root / _EVIDENCE_REL)
    if not doc:
        doc = {"confirmation_de": "Active Alpha — Hintergrund", "ok": False}
    text = html.escape(str(doc.get("confirmation_de") or doc.get("presentation_de") or "Active Alpha"))
    cls = "ok" if doc.get("ok") or doc.get("r3_display", {}).get("ok") else ""
    return (
        f'<p class="r3-engine-status {cls}" id="r3-engine-status" '
        f'aria-label="Active Alpha Hintergrund">{text}</p>'
    )
