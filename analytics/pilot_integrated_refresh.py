"""One linked refresh pass: broker, quotes, FX, champion, plan, reeval, costs, trade gate."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/pilot_integrated_refresh_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _row(
    key: str,
    label_de: str,
    *,
    status: str,
    value_de: str,
    detail_de: str = "",
    updated_utc: str = "",
) -> Dict[str, Any]:
    return {
        "key": key,
        "label_de": label_de,
        "status": status,
        "value_de": value_de,
        "detail_de": detail_de,
        "updated_utc": updated_utc or _utc_now(),
    }


def estimate_cost_risk(
    root: Path,
    *,
    notional_eur: float,
    limit_price_eur: float = 0.0,
) -> Dict[str, Any]:
    """Base + stress costs; linked to fee policy (same module as order gate)."""
    from integrations.trading212.t212_fee_economics import (
        estimate_round_trip_cost_eur,
        estimate_stress_round_trip_cost_eur,
        is_notional_worth_trading,
        is_notional_worth_trading_stress,
        load_fee_economics_policy,
        trade_fee_hurdle_eur,
    )

    pol = load_fee_economics_policy(root)
    base = estimate_round_trip_cost_eur(notional_eur, price_eur=limit_price_eur, policy=pol)
    stress = estimate_stress_round_trip_cost_eur(
        notional_eur, price_eur=limit_price_eur, policy=pol
    )
    worth_b, reason_b = is_notional_worth_trading(
        notional_eur, root, price_eur=limit_price_eur
    )
    worth_s, reason_s = is_notional_worth_trading_stress(
        notional_eur, root, price_eur=limit_price_eur
    )
    return {
        "notional_eur": round(float(notional_eur), 2),
        "base_round_trip_eur": base["round_trip_cost_eur"],
        "base_round_trip_pct": base["round_trip_pct"],
        "stress_round_trip_eur": stress["round_trip_cost_eur"],
        "stress_round_trip_pct": stress["round_trip_pct"],
        "stress_add_bps": stress.get("stress_add_bps"),
        "hurdle_eur": trade_fee_hurdle_eur(root, notional_eur=notional_eur, price_eur=limit_price_eur),
        "worth_trading_base": worth_b,
        "worth_trading_stress": worth_s,
        "block_reason_base": reason_b,
        "block_reason_stress": reason_s,
        "trade_allowed": worth_b and worth_s,
    }


def build_refresh_status(
    root: Path,
    *,
    broker: Dict[str, Any],
    market_prices: Dict[str, Any],
    champion_guard: Dict[str, Any],
    investment_plan: Dict[str, Any],
    reevaluation: Dict[str, Any],
    fx: Dict[str, Any],
    session: Dict[str, Any],
    cost_risk: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dashboard rows for cockpit — updated every integrated refresh."""
    rows: List[Dict[str, Any]] = []
    sync_utc = str(broker.get("last_sync_utc") or "")[:19]
    cash = broker.get("cash_eur")
    rows.append(
        _row(
            "broker",
            "T212 Konto (frei handelbar)",
            status="OK" if cash is not None else "FAIL",
            value_de=f"{float(cash):,.2f} €" if cash is not None else "—",
            detail_de=str(broker.get("status") or ""),
            updated_utc=sync_utc,
        )
    )

    fresh = (market_prices or {}).get("freshness") or {}
    q_st = str(fresh.get("status") or "—")
    us_open = bool(session.get("open"))
    q_status = "OK" if q_st == "FRESH" else ("WARN" if not us_open else "FAIL")
    rows.append(
        _row(
            "quotes",
            "Live-Kurse (US-Aktien)",
            status=q_status,
            value_de=q_st,
            detail_de=str(fresh.get("reason") or market_prices.get("_quote_gate_reason") or "")[:100],
            updated_utc=str(
                market_prices.get("fetched_at_utc")
                or fresh.get("as_of_utc")
                or ""
            )[:19],
        )
    )

    if fx.get("ok"):
        rows.append(
            _row(
                "fx",
                "Wechselkurs EUR/USD",
                status="OK",
                value_de=f"1 EUR = {float(fx['usd_per_eur']):.4f} USD",
                detail_de=str(fx.get("source") or ""),
                updated_utc=str(fx.get("fx_event_time_utc") or "")[:19],
            )
        )
    else:
        rows.append(
            _row(
                "fx",
                "Wechselkurs EUR/USD",
                status="FAIL",
                value_de="nicht verfügbar",
                detail_de="Gebühren-/USD-Vergleich unsicher",
            )
        )

    cg = champion_guard or {}
    g_st = "OK" if cg.get("champion_ok") and cg.get("signals_ok") else "FAIL"
    rows.append(
        _row(
            "champion",
            "Champion & Signal",
            status=g_st,
            value_de=str(cg.get("status_de") or "—")[:80],
            detail_de=f"Signal {cg.get('signal_date') or '—'}",
            updated_utc=str(cg.get("checked_at_utc") or "")[:19],
        )
    )

    re_st = "OK" if reevaluation.get("status") == "OK" else "WARN"
    if us_open and not reevaluation.get("quote_fresh"):
        re_st = "FAIL"
    rows.append(
        _row(
            "reeval",
            "Portfolio-Abgleich (Ist vs Modell)",
            status=re_st,
            value_de=str(reevaluation.get("urgency") or "—"),
            detail_de=(reevaluation.get("summary_de") or "")[:120],
            updated_utc=str(reevaluation.get("generated_at_utc") or "")[:19],
        )
    )

    primary = (investment_plan or {}).get("primary_action") or {}
    sym = str(primary.get("symbol") or "—")
    if cost_risk:
        cr_st = "OK" if cost_risk.get("trade_allowed") else "FAIL"
        rows.append(
            _row(
                "cost_base",
                f"Gebühren Round-trip ({sym})",
                status="OK",
                value_de=(
                    f"~{cost_risk['base_round_trip_eur']:.2f} € "
                    f"({cost_risk['base_round_trip_pct']:.2f} %)"
                ),
                detail_de=f"Hürde ≥ {cost_risk['hurdle_eur']:.2f} €",
            )
        )
        rows.append(
            _row(
                "cost_stress",
                f"Gebühren Stress (+{cost_risk.get('stress_add_bps', '?')} bp)",
                status="OK" if cost_risk.get("worth_trading_stress") else "FAIL",
                value_de=(
                    f"~{cost_risk['stress_round_trip_eur']:.2f} € "
                    f"({cost_risk['stress_round_trip_pct']:.2f} %)"
                ),
                detail_de=str(cost_risk.get("block_reason_stress") or "")[:100],
            )
        )
        trade_ok = (
            reevaluation.get("trade_required")
            and cost_risk.get("trade_allowed")
            and g_st == "OK"
            and (q_status == "OK" or not us_open)
        )
        rows.append(
            _row(
                "trade_gate",
                "Handeln lohnt sich (verknüpft)",
                status="OK" if trade_ok else "FAIL",
                value_de="Ja" if trade_ok else "Nein",
                detail_de=(
                    "Modell-Abgleich + Gebühren Basis/Stress + Signale + Kurse"
                ),
            )
        )

    generated = _utc_now()
    doc = {
        "generated_at_utc": generated,
        "us_session_open": us_open,
        "rows": rows,
        "summary_de": _refresh_summary_de(rows),
        "all_ok": not any(r["status"] == "FAIL" for r in rows),
    }
    return doc


def _refresh_summary_de(rows: List[Dict[str, Any]]) -> str:
    fails = [r for r in rows if r["status"] == "FAIL"]
    warns = [r for r in rows if r["status"] == "WARN"]
    if fails:
        return f"Refresh: {len(fails)} Blocker — {fails[0]['label_de']}"
    if warns:
        return f"Refresh: {len(warns)} Hinweis(e) — sonst aktuell"
    return "Refresh: alle Prüfungen OK"


@dataclass
class IntegratedRefreshResult:
    generated_at_utc: str
    broker: Dict[str, Any] = field(default_factory=dict)
    market_prices: Dict[str, Any] = field(default_factory=dict)
    champion_guard: Dict[str, Any] = field(default_factory=dict)
    investment_plan: Dict[str, Any] = field(default_factory=dict)
    reevaluation: Dict[str, Any] = field(default_factory=dict)
    trading_snapshot: Any = None
    refresh_status: Dict[str, Any] = field(default_factory=dict)
    fx: Dict[str, Any] = field(default_factory=dict)
    cost_risk: Dict[str, Any] = field(default_factory=dict)

    def as_state_patch(self) -> Dict[str, Any]:
        return {
            "broker": self.broker,
            "market_prices": self.market_prices,
            "champion_guard": self.champion_guard,
            "investment_plan": self.investment_plan,
            "portfolio_reevaluation": self.reevaluation,
            "refresh_status": self.refresh_status,
            "fx": self.fx,
            "cost_risk": self.cost_risk,
            "trading_snapshot": (
                self.trading_snapshot.as_dict()
                if hasattr(self.trading_snapshot, "as_dict")
                else self.trading_snapshot
            ),
        }


def run_integrated_refresh(
    root: Path,
    *,
    force: bool = True,
    auto_enqueue: bool = False,
) -> IntegratedRefreshResult:
    """Full linked refresh used by cockpit «Aktualisieren» and timers."""
    root = Path(root)
    from analytics.champion_runtime_guard import verify_champion_runtime, write_guard_evidence
    from analytics.pilot_investment_plan import ensure_plan_symbols_in_scope
    from analytics.pilot_day_trading_facade import refresh_trading_snapshot
    from integrations.trading212.t212_cash_display import fetch_display_fx
    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

    broker_obj = sync_readonly_account(root, force=force)
    broker = {
        "cash_eur": broker_obj.cash_eur,
        "cash_breakdown": broker_obj.cash_breakdown or {},
        "status": broker_obj.status,
        "positions_count": broker_obj.positions_count,
        "positions": broker_obj.positions or [],
        "last_sync_utc": broker_obj.last_successful_sync_utc,
    }

    guard = verify_champion_runtime(root)
    write_guard_evidence(root, guard)
    champion_guard = guard.as_dict()

    from analytics.pilot_live_trade_gate import fetch_live_quotes_fail_closed

    market_prices, _ = fetch_live_quotes_fail_closed(root, force=True)
    fx = fetch_display_fx(root)

    plan: Dict[str, Any] = {}
    cost_risk: Dict[str, Any] = {}
    if broker.get("cash_eur") is not None:
        from analytics.king_plan_integration import rebuild_investment_plan_with_king

        rebuilt = rebuild_investment_plan_with_king(root, force_t212_sync=force)
        if rebuilt.get("ok"):
            plan_path = root / "evidence/pilot_investment_plan_latest.json"
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                plan = {}
        else:
            from analytics.pilot_investment_plan import build_investment_plan, write_plan_evidence

            plan = build_investment_plan(root, float(broker["cash_eur"]))
            ensure_plan_symbols_in_scope(root, plan)
            write_plan_evidence(root, plan)
        primary = plan.get("primary_action") or {}
        sym = str(primary.get("symbol") or "").upper()
        limit = 0.0
        if sym:
            from market.live_quote_engine import price_for_symbol
            from paper.p16d.quote_plausibility import sanitize_price_eur

            raw = price_for_symbol(market_prices, sym)
            lim, _, _ = sanitize_price_eur(sym, float(raw) if raw else None)
            if lim and lim > 0:
                limit = float(lim)
        notional = float(primary.get("target_eur") or 0)
        if notional > 0:
            cost_risk = estimate_cost_risk(
                root, notional_eur=notional, limit_price_eur=limit
            )
            plan["cost_risk"] = cost_risk

    limit_price = 0.0
    primary = plan.get("primary_action") or {}
    if primary.get("symbol"):
        from market.live_quote_engine import price_for_symbol
        from paper.p16d.quote_plausibility import sanitize_price_eur

        sym = str(primary["symbol"]).upper()
        raw = price_for_symbol(market_prices, sym)
        lim, _, _ = sanitize_price_eur(sym, float(raw) if raw else None)
        if lim and lim > 0:
            limit_price = float(lim)

    snap = refresh_trading_snapshot(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=market_prices,
        champion_guard=champion_guard,
        force_reevaluation=force,
        auto_enqueue=auto_enqueue,
        limit_price_eur=None,
    )

    if limit_price > 0 and plan:
        from analytics.pilot_day_trading_facade import capture_portfolio_change_if_needed

        capture_portfolio_change_if_needed(root, plan, limit_price_eur=limit_price)

    reevaluation = snap.reevaluation if hasattr(snap, "reevaluation") else {}
    if cost_risk:
        reevaluation = {**reevaluation, "cost_risk": cost_risk}

    session = snap.session if hasattr(snap, "session") else {}
    refresh_status = build_refresh_status(
        root,
        broker=broker,
        market_prices=market_prices,
        champion_guard=champion_guard,
        investment_plan=plan,
        reevaluation=reevaluation,
        fx=fx,
        session=session,
        cost_risk=cost_risk or None,
    )

    result = IntegratedRefreshResult(
        generated_at_utc=_utc_now(),
        broker=broker,
        market_prices=market_prices,
        champion_guard=champion_guard,
        investment_plan=plan,
        reevaluation=reevaluation,
        trading_snapshot=snap,
        refresh_status=refresh_status,
        fx=fx,
        cost_risk=cost_risk,
    )
    atomic_write_json(root / _EVIDENCE_REL, {
        "generated_at_utc": result.generated_at_utc,
        "refresh_status": refresh_status,
        "cost_risk": cost_risk,
        "reevaluation_urgency": reevaluation.get("urgency"),
    })
    return result
