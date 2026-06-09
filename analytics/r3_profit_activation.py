"""Nach Gewinn/Liquidation: T212-Sync, neue Aktien, Funktionen + Lern-Analyse."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_profit_activation_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _profit_from_broker(broker: Dict[str, Any]) -> Dict[str, Any]:
    summary = broker.get("account_summary") if isinstance(broker.get("account_summary"), dict) else {}
    if not summary:
        try:
            sync_path = Path("live_pilot/manual_execution/readonly_real_account_state/latest_sync.json")
            if sync_path.is_file():
                summary = _load_json(sync_path).get("summary") or {}
        except Exception:
            summary = {}
    inv = summary.get("investments") if isinstance(summary.get("investments"), dict) else {}
    realized = inv.get("realizedProfitLoss")
    unrealized = inv.get("unrealizedProfitLoss")
    total_cost = inv.get("totalCost")
    current_val = inv.get("currentValue")
    return {
        "realized_profit_loss_eur": realized,
        "unrealized_profit_loss_eur": unrealized,
        "invested_cost_eur": total_cost,
        "invested_value_eur": current_val,
        "liquidation_complete": int(broker.get("positions_count") or 0) == 0,
    }


def _analysis_recommendations(
    *,
    profit: Dict[str, Any],
    functions: Dict[str, Any],
    reeval: Dict[str, Any],
    learn: Dict[str, Any],
    audit: Dict[str, Any],
    t212: Dict[str, Any],
) -> List[str]:
    recs: List[str] = []
    if profit.get("realized_profit_loss_eur") is not None:
        recs.append(
            f"Realisierter Gewinn/Verlust T212: {float(profit['realized_profit_loss_eur']):+.2f} € "
            "— in Learning-Ledger für Outcome-Reconciliation nutzen."
        )
    if t212.get("stale_cache"):
        recs.append("T212 API-Key erneuern und «Aktualisieren» — Kontostand sonst aus Cache.")
    if not reeval.get("quote_fresh"):
        recs.append("Live-Kurse aktualisieren (Internet) — Reevaluation nutzt sonst Modell-Stand.")
    exp = reeval.get("exposure_check") or {}
    if exp.get("under_invested"):
        recs.append(
            f"Unterinvestiert ({float(exp.get('cash_weight_pct') or 0):.0f}% Cash) — "
            "Initial Bestellung (Gesamtpaket) ist die aktive Funktion."
        )
    active_fn = functions.get("primary_function_id")
    if active_fn == "initial_order":
        pkg = functions.get("initial_package") or {}
        recs.append(
            f"Neue Aktien aktiv: {int(pkg.get('order_count') or 0)} Käufe auf "
            f"{float(pkg.get('budget_eur') or 0):.0f} € — Freigabe-Button auf /desktop."
        )
    live_n = int((learn.get("live_metrics") or {}).get("n_mature") or 0)
    if live_n < 3:
        recs.append("Live-Feedback dünn — nach Neukäufen Outcomes syncen (observe-only, kein Auto-Training).")
    for b in (audit.get("blockers") or [])[:4]:
        recs.append(f"Wallstreet-Blocker: {b}")
    if not recs:
        recs.append("Pipeline bereit — Freigabe und Einzel-Käufe auf R3 prüfen.")
    return recs


def activate_after_profit(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """
    1) T212+Lernen  2) Plan+Reeval  3) Trading-Funktionen+Orders
    4) Prognose+Gas/Sell  5) Freigabe  6) Wallstreet/Learning-Audit
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    broker: Dict[str, Any] = {}
    t212_doc: Dict[str, Any] = {}

    pipeline_doc: Dict[str, Any] = {}
    try:
        from analytics.r3_prognosis_pipeline import run_prognosis_automation

        pipeline_doc = run_prognosis_automation(root, persist=True)
        steps.append(
            {
                "step": "prognosis_pipeline",
                "ok": bool(pipeline_doc.get("ok")),
                "buys": pipeline_doc.get("worthwhile_buys"),
                "package_ready": pipeline_doc.get("package_ready"),
            }
        )
    except Exception as exc:
        steps.append({"step": "prognosis_pipeline", "ok": False, "error": str(exc)[:120]})

    try:
        from analytics.t212_learning_sync import sync_t212_with_learning

        t212_doc = sync_t212_with_learning(root, force=True, capture_learning=True)
        broker = {
            "cash_eur": t212_doc.get("cash_eur"),
            "positions_count": t212_doc.get("positions_count"),
            "last_successful_sync_utc": t212_doc.get("last_sync_utc"),
            "credentials_configured": True,
        }
        steps.append({"step": "t212_learning", "ok": bool(t212_doc.get("ok")), "headline": t212_doc.get("headline_de")})
    except Exception as exc:
        steps.append({"step": "t212_learning", "ok": False, "error": str(exc)[:120]})

    plan_doc: Dict[str, Any] = {}
    try:
        from analytics.king_plan_integration import rebuild_investment_plan_with_king

        plan_doc = rebuild_investment_plan_with_king(root, force_t212_sync=True)
        steps.append({"step": "investment_plan", "ok": bool(plan_doc.get("ok", True)), "investable_eur": plan_doc.get("investable_eur")})
    except Exception as exc:
        steps.append({"step": "investment_plan", "ok": False, "error": str(exc)[:120]})

    reeval: Dict[str, Any] = {}
    try:
        from analytics.pilot_portfolio_reevaluation import run_periodic_reevaluation

        reeval = run_periodic_reevaluation(root, broker=broker, plan=plan_doc, force=True)
        steps.append(
            {
                "step": "reevaluation",
                "ok": reeval.get("status") != "SKIPPED",
                "under_invested": (reeval.get("exposure_check") or {}).get("under_invested"),
                "actions": len(reeval.get("recommended_actions") or []),
            }
        )
    except Exception as exc:
        steps.append({"step": "reevaluation", "ok": False, "error": str(exc)[:120]})

    functions: Dict[str, Any] = {}
    try:
        from analytics.r3_trading_functions import build_r3_trading_functions

        functions = build_r3_trading_functions(root, persist=True)
        steps.append(
            {
                "step": "trading_functions",
                "ok": int(functions.get("functions_active") or 0) > 0,
                "primary": functions.get("primary_function_id"),
                "new_buys": len((functions.get("stock_groups") or {}).get("new_buys") or []),
            }
        )
    except Exception as exc:
        steps.append({"step": "trading_functions", "ok": False, "error": str(exc)[:120]})

    prognosis: Dict[str, Any] = {}
    try:
        from analytics.r3_t212_prognosis import build_r3_t212_daily_prognosis

        prognosis = build_r3_t212_daily_prognosis(root, persist=True)
        steps.append({"step": "prognosis", "ok": bool(prognosis.get("ok")), "positions": prognosis.get("positions")})
    except Exception as exc:
        steps.append({"step": "prognosis", "ok": False, "error": str(exc)[:120]})

    gas_doc: Dict[str, Any] = {}
    try:
        from analytics.gas_sell_steering import apply_gas_sell_steering, load_gas_sell_steering
        from analytics.r3_stock_orders import build_optimal_stock_actions

        buys = [r for r in build_optimal_stock_actions(root) if str(r.get("side") or "").upper() == "BUY"]
        apply_gas_sell_steering(root, buys)
        gas_doc = load_gas_sell_steering(root)
        steps.append(
            {
                "step": "gas_sell_steering",
                "ok": bool(gas_doc.get("on_course")),
                "gas_count": gas_doc.get("gas_count"),
                "headline": gas_doc.get("headline_de"),
            }
        )
    except Exception as exc:
        steps.append({"step": "gas_sell_steering", "ok": False, "error": str(exc)[:120]})

    freigabe: Dict[str, Any] = {}
    try:
        from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

        freigabe = auto_prepare_freigabe_for_desktop(root)
        steps.append(
            {
                "step": "freigabe",
                "ok": bool(freigabe.get("package_ready")),
                "package_ready": freigabe.get("package_ready"),
            }
        )
    except Exception as exc:
        steps.append({"step": "freigabe", "ok": False, "error": str(exc)[:120]})

    learn_audit: Dict[str, Any] = {}
    try:
        from analytics.learning_cycle_audit import run_learning_cycle_audit

        learn_audit = run_learning_cycle_audit(root)
        steps.append({"step": "learning_audit", "ok": bool(learn_audit.get("ok", True))})
    except Exception as exc:
        steps.append({"step": "learning_audit", "ok": False, "error": str(exc)[:120]})

    wallstreet: Dict[str, Any] = {}
    try:
        from analytics.wallstreet_performance_audit import run_wallstreet_audit

        wallstreet = run_wallstreet_audit(root)
        steps.append({"step": "wallstreet_audit", "ok": bool(wallstreet.get("ok", True))})
    except Exception as exc:
        steps.append({"step": "wallstreet_audit", "ok": False, "error": str(exc)[:120]})

    profit = _profit_from_broker(broker)
    recommendations = _analysis_recommendations(
        profit=profit,
        functions=functions,
        reeval=reeval,
        learn=learn_audit,
        audit=wallstreet,
        t212=t212_doc,
    )

    core_ok = all(
        s.get("ok")
        for s in steps
        if s.get("step") in ("trading_functions", "prognosis", "investment_plan")
    )
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": core_ok,
        "headline_de": (
            f"✓ Gewinn-Phase aktiv — {int(functions.get('functions_active') or 0)} Funktion(en), "
            f"{len((functions.get('stock_groups') or {}).get('new_buys') or [])} neue Aktien"
            if core_ok
            else "Gewinn-Aktivierung — siehe steps"
        ),
        "profit_de": profit,
        "realized_pl_eur": profit.get("realized_profit_loss_eur"),
        "cash_eur": broker.get("cash_eur") or plan_doc.get("available_cash_eur"),
        "investable_eur": plan_doc.get("investable_eur") or (functions.get("context") or {}).get("investable_eur"),
        "positions_count": broker.get("positions_count"),
        "primary_function": functions.get("primary_function_id"),
        "new_stocks": (functions.get("stock_groups") or {}).get("new_buys") or [],
        "package_ready": freigabe.get("package_ready"),
        "recommendations_de": recommendations,
        "steps": steps,
        "refs": {
            "trading_functions": "evidence/r3_trading_functions_latest.json",
            "prognosis": "evidence/r3_t212_prognosis_latest.json",
            "freigabe": "evidence/r3_freigabe_latest.json",
            "wallstreet": "evidence/wallstreet_audit_latest.json",
            "learning": "evidence/learning_cycle_audit_latest.json",
            "gas_sell": "evidence/gas_sell_steering_latest.json",
        },
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
