"""T212 Live-Bild — Cash + Positionen als einheitliche Berechnungsgrundlage."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/t212_live_portfolio_basis_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def enrich_broker_from_live_picture(root: Path, broker: Dict[str, Any]) -> Dict[str, Any]:
    """
    T212 Live-Bild (API-Bond + Cache) in Broker-Dict mergen — Positionen nie verwerfen.
    """
    root = Path(root)
    out = dict(broker or {})
    positions = list(out.get("positions") or [])
    if positions and out.get("cash_eur") is not None:
        out["live_picture_source"] = out.get("source") or "broker"
        out["positions_count"] = int(out.get("positions_count") or len(positions))
        return out

    if not positions or out.get("cash_eur") is None:
        pass  # fall through to bond/cache merge

    for rel in (
        "evidence/r3_t212_api_bond_latest.json",
        "live_pilot/manual_execution/readonly_real_account_state/latest_sync.json",
    ):
        snap = _load_json(root / rel)
        if not snap:
            continue
        if str(rel).endswith("latest_sync.json"):
            summary = snap.get("summary") if isinstance(snap.get("summary"), dict) else {}
            inv = summary.get("investments") if isinstance(summary.get("investments"), dict) else {}
            cash = summary.get("cash") if isinstance(summary.get("cash"), dict) else {}
            if out.get("cash_eur") is None:
                for key in ("availableToTrade", "available", "total"):
                    if cash.get(key) is not None:
                        try:
                            out["cash_eur"] = float(cash[key])
                            break
                        except (TypeError, ValueError):
                            pass
            if inv.get("currentValue") is not None and not positions:
                try:
                    out["invested_current_value_eur"] = float(inv["currentValue"])
                except (TypeError, ValueError):
                    pass
            out["live_picture_source"] = "readonly_account_state"
            continue

        if out.get("cash_eur") is None and snap.get("cash_eur") is not None:
            out["cash_eur"] = snap.get("cash_eur")
        if not positions and snap.get("positions"):
            out["positions"] = list(snap.get("positions") or [])
            out["positions_count"] = int(snap.get("positions_count") or len(out["positions"]))
        if snap.get("cash_breakdown"):
            out["cash_breakdown"] = snap.get("cash_breakdown")
        if snap.get("last_sync_utc"):
            out["last_sync_utc"] = snap.get("last_sync_utc")
        out["live_picture_source"] = out.get("live_picture_source") or "r3_t212_api_bond"
        if out.get("positions"):
            break

    out["positions_count"] = int(out.get("positions_count") or len(out.get("positions") or []))
    return out


def live_human_portfolio(broker: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.human_vs_base_comparison import human_portfolio_from_broker

    return human_portfolio_from_broker(
        {
            "cash_eur": broker.get("cash_eur"),
            "positions": broker.get("positions") or [],
            "credentials_configured": bool(broker.get("credentials_configured", True)),
        }
    )


def resolve_calculation_basis(
    root: Path,
    broker: Dict[str, Any],
    planning_cash_eur: float | None,
) -> Dict[str, Any]:
    """Gesamtdepot (Cash+Positionen) wenn Live-Bild Positionen hat, sonst investierbares Cash."""
    from analytics.r3_closed_loop import resolve_r3_plan_capital_eur
    from analytics.t212_broker_economics import build_broker_economics_context

    broker = enrich_broker_from_live_picture(root, broker)
    planning = float(planning_cash_eur or broker.get("r3_planning_cash_eur") or broker.get("cash_eur") or 0)
    capital = resolve_r3_plan_capital_eur(root, broker, planning)
    human = live_human_portfolio(broker)
    pos_n = int(capital.get("positions_count") or human.get("positions_count") or 0)
    basis = str(capital.get("basis") or "r3_cash_investable_live")
    plan_cap = float(capital.get("plan_capital_eur") or 0)
    economics = build_broker_economics_context(root, broker, plan_capital_eur=plan_cap)
    if pos_n > 0:
        basis_de = (
            f"T212 Live-Depot: {float(capital.get('total_account_value_eur') or 0):.0f} € gesamt "
            f"({float(capital.get('invested_eur') or 0):.0f} € in {pos_n} Aktien, ohne Puffer)"
        )
    else:
        basis_de = (
            f"T212 Live-Cash: {plan_cap:.0f} € gesamt investierbar (ohne Puffer)"
        )
    fee_de = (economics.get("fees") or {}).get("summary_de") or ""
    if fee_de:
        basis_de = f"{basis_de} · {fee_de}"
    return {
        **capital,
        "human": human,
        "holdings": list(human.get("holdings") or []),
        "basis_de": basis_de,
        "calculation_basis": basis,
        "live_picture_source": broker.get("live_picture_source"),
        "broker_economics": economics,
        "currency_context": economics.get("currency"),
        "fee_policy": economics.get("fees"),
    }


def _worthwhile_from_rebalanced_plan(plan: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    buys: List[Dict[str, Any]] = []
    sells: List[Dict[str, Any]] = []
    for row in plan.get("allocations") or []:
        side = str(row.get("side") or "BUY").upper()
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            continue
        gap = float(row.get("gap_eur") or row.get("target_eur") or 0)
        score = abs(gap) * (1.0 + float(row.get("model_weight_pct") or 0) / 100.0)
        item = {
            **row,
            "symbol": sym,
            "side": side,
            "gap_eur": gap,
            "priority_score": round(score, 2),
            "worthwhile": True,
            "source": "t212_live_rebalance",
            "action_de": row.get("side_de") or row.get("rationale_de") or f"{sym}: {gap:+.0f} €",
        }
        if side == "SELL":
            item["action_code"] = "REDUZIEREN"
            sells.append(item)
        else:
            item["action_code"] = "KAUFEN" if float(row.get("held_eur") or 0) <= 0 else "NACHKAUF"
            buys.append(item)
    buys.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    sells.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    return buys, sells


def build_plan_on_live_basis(
    root: Path,
    broker: Dict[str, Any],
    *,
    planning_cash_eur: float | None = None,
    rebalance_to_holdings: bool = True,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Investment-Plan auf T212 Live-Bild:
    1) Gesamtdepot/Cash als Skalierungsbasis
    2) t212_live mit Holdings
    3) optional Gap-Plan vs. Live-Positionen
    """
    root = Path(root)
    broker = enrich_broker_from_live_picture(root, broker)
    basis = resolve_calculation_basis(root, broker, planning_cash_eur)
    planning = float(
        planning_cash_eur
        or broker.get("r3_planning_cash_eur")
        or broker.get("cash_eur")
        or basis.get("cash_investable_eur")
        or 0
    )
    plan_capital = float(basis.get("plan_capital_eur") or basis.get("cash_investable_eur") or 0)

    from analytics.pilot_investment_plan import build_investment_plan

    plan = build_investment_plan(
        root,
        planning,
        investable_eur=plan_capital,
        budget_source=str(basis.get("calculation_basis") or "t212_live_sync"),
    )
    human = basis.get("human") or {}
    plan["t212_live"] = {
        "cash_eur": broker.get("cash_eur"),
        "planning_cash_eur": round(planning, 2),
        "cash_investable_eur": basis.get("cash_investable_eur"),
        "plan_capital_eur": plan_capital,
        "plan_capital_basis": basis.get("calculation_basis"),
        "total_account_value_eur": basis.get("total_account_value_eur"),
        "invested_eur": basis.get("invested_eur"),
        "positions_count": basis.get("positions_count"),
        "holdings": basis.get("holdings"),
        "last_sync_utc": broker.get("last_sync_utc"),
        "live_picture_source": basis.get("live_picture_source"),
        "calculation_basis_de": basis.get("basis_de"),
        "connected": bool(broker.get("connected")),
    }
    plan["plan_capital_eur"] = plan_capital
    plan["plan_capital_basis"] = basis.get("calculation_basis")
    plan["planning_basis"] = basis.get("calculation_basis")
    plan["calculation_basis_de"] = basis.get("basis_de")
    plan["broker_economics"] = basis.get("broker_economics")
    plan["currency_context"] = basis.get("currency_context")
    plan["fee_policy"] = basis.get("fee_policy")

    reb_meta: Dict[str, Any] = {"ok": True, "rebalanced": False}
    if rebalance_to_holdings and int(basis.get("positions_count") or 0) > 0:
        from analytics.king_plan_integration import rebalance_plan_to_t212_holdings

        plan, reb_meta = rebalance_plan_to_t212_holdings(plan, broker, root)
        reb_meta["rebalanced"] = bool(plan.get("rebalanced_to_t212"))

    meta = {
        "ok": True,
        "basis": basis,
        "rebalance": reb_meta,
        "updated_at_utc": _utc_now(),
    }
    return plan, meta


def persist_live_basis_evidence(root: Path, basis: Dict[str, Any], plan: Dict[str, Any]) -> None:
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "calculation_basis": basis.get("calculation_basis"),
        "basis_de": basis.get("basis_de"),
        "total_account_value_eur": basis.get("total_account_value_eur"),
        "invested_eur": basis.get("invested_eur"),
        "positions_count": basis.get("positions_count"),
        "holdings": basis.get("holdings"),
        "live_picture_source": basis.get("live_picture_source"),
        "plan_capital_eur": plan.get("plan_capital_eur"),
        "rebalanced_to_t212": plan.get("rebalanced_to_t212"),
        "rebalance_mode_de": plan.get("rebalance_mode_de"),
        "broker_economics": basis.get("broker_economics"),
        "currency_context": basis.get("currency_context"),
        "fee_policy": basis.get("fee_policy"),
    }
    atomic_write_json(Path(root) / _EVIDENCE_REL, doc)
