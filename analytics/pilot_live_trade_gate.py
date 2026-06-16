"""Fail-closed live preflight: fresh quotes, FX, fees, portfolio re-check before orders."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analytics.pilot_pick_rationale import explain_primary_pick, rationale_one_liner
from integrations.trading212.t212_fee_economics import (
    estimate_round_trip_cost_eur,
    estimate_stress_round_trip_cost_eur,
    is_notional_worth_trading,
    is_notional_worth_trading_stress,
    load_fee_economics_policy,
    trade_fee_hurdle_eur,
)


def _block(code: str, message_de: str) -> Dict[str, str]:
    return {"code": code, "message_de": message_de}


def fetch_live_quotes_fail_closed(root: Path, *, force: bool = True) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """US session: fresh quotes required. Outside US: best-effort with explicit stale flag."""
    from analytics.pilot_day_trading_facade import quote_fetch_timeout_s, us_session_open
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now
    from market.live_quote_engine import ensure_live_quotes_fresh_bounded

    blocks: List[Dict[str, str]] = []
    us_open = us_session_open()
    try:
        snap = ensure_live_quotes_fresh_bounded(
            Path(root),
            force=force or us_open,
            timeout_s=quote_fetch_timeout_s(root),
            owner="pilot_live_trade_gate",
        )
    except Exception as exc:
        snap = {"executable_prices_eur": {}, "freshness": {"status": "ERROR", "reason": str(exc)[:120]}}
        if us_open:
            blocks.append(_block("QUOTES_FETCH_FAILED", f"Live-Kurse nicht abrufbar: {exc}"[:160]))
    from analytics.pilot_portfolio_reevaluation import _check_quotes_for_session
    from analytics.pilot_portfolio_reevaluation import load_policy as load_reeval_policy

    ok, reason, _ = _check_quotes_for_session(snap, load_reeval_policy(root))
    snap["_quote_gate_ok"] = ok
    snap["_quote_gate_reason"] = reason
    if us_open and not ok:
        blocks.append(
            _block(
                "QUOTES_NOT_FRESH",
                reason or "Live-Kurse nicht frisch genug — kein Trade-Vergleich in der US-Session.",
            )
        )
    sess = us_equity_regular_session_open_now()
    snap["_us_session_open"] = bool(sess.get("open"))
    return snap, blocks


def fetch_live_fx_fail_closed(root: Path) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    from integrations.trading212.t212_cash_display import fetch_display_fx

    fx = fetch_display_fx(Path(root))
    blocks: List[Dict[str, str]] = []
    if not fx.get("ok"):
        blocks.append(
            _block(
                "FX_UNAVAILABLE",
                "USD/EUR-Spot nicht verfügbar — Gebühren- und USD-Anzeige unsicher.",
            )
        )
    return fx, blocks


def run_fresh_portfolio_reevaluation(
    root: Path,
    *,
    broker: Dict[str, Any],
    plan: Dict[str, Any],
    quote_snapshot: Dict[str, Any],
    champion_guard: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion

    return evaluate_live_portfolio_vs_champion(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
    )


def _symbol_reeval_row(report: Dict[str, Any], symbol: str) -> Optional[Dict[str, Any]]:
    sym = str(symbol).upper()
    for row in report.get("recommended_actions") or report.get("rows") or []:
        if str(row.get("symbol", "")).upper() == sym:
            return row
    return None


def build_live_order_preflight(
    root: Path,
    *,
    symbol: str,
    target_notional_eur: float,
    broker: Dict[str, Any],
    plan: Dict[str, Any],
    champion_guard: Optional[Dict[str, Any]] = None,
    limit_price_eur: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Single fail-closed gate before any live order.
    Returns ok, blocks[], confirmation_lines[], details for UI.
    """
    root = Path(root)
    sym = str(symbol).upper()
    blocks: List[Dict[str, str]] = []
    lines: List[str] = []

    if broker.get("cash_eur") is None:
        blocks.append(_block("BROKER_CASH_UNKNOWN", "Freies Guthaben unbekannt — zuerst T212 aktualisieren."))

    guard = champion_guard or {}
    if not guard.get("champion_ok", True):
        blocks.append(_block("CHAMPION_BLOCKED", "Champion-Guard blockiert — keine Order."))
    if not guard.get("signals_ok", True):
        blocks.append(_block("SIGNALS_STALE", "Modell-Signale veraltet — nur beobachten."))

    quote_snap, q_blocks = fetch_live_quotes_fail_closed(root, force=True)
    blocks.extend(q_blocks)

    fx, fx_blocks = fetch_live_fx_fail_closed(root)
    blocks.extend(fx_blocks)

    from market.live_quote_engine import price_for_symbol
    from paper.p16d.quote_plausibility import sanitize_price_eur

    raw_px = price_for_symbol(quote_snap, sym)
    src = str((quote_snap.get("price_source_by_symbol") or {}).get(sym) or "YAHOO")
    limit, _, px_reason = sanitize_price_eur(
        sym, float(raw_px) if raw_px else None, source=src, for_orders=True
    )
    if limit is None or limit <= 0:
        if limit_price_eur and limit_price_eur > 0:
            limit = round(float(limit_price_eur), 2)
        else:
            limit = round(max(1.0, float(target_notional_eur) / 2.0), 2)
            if quote_snap.get("_quote_gate_ok"):
                blocks.append(
                    _block(
                        "LIMIT_FALLBACK",
                        f"Kein belastbarer Live-Limitpreis für {sym} — Schätzung aus Zielvolumen.",
                    )
                )
            elif quote_snap.get("_us_session_open"):
                blocks.append(
                    _block("NO_LIVE_PRICE", f"Kein Live-Kurs für {sym} — Order in US-Session blockiert.")
                )
    else:
        limit = round(float(limit), 2)

    fresh = quote_snap.get("freshness") or {}
    lines.append(
        f"Live-Limit (EUR): {limit:.2f} €"
        + (f" — {px_reason}" if px_reason else "")
        + f" | Kurse: {fresh.get('status', '—')} ({fresh.get('reason', '')[:60]})"
    )

    if fx.get("ok"):
        lines.append(
            f"Wechselkurs: 1 EUR = {float(fx['usd_per_eur']):.4f} USD ({fx.get('source', '')})"
        )

    report = run_fresh_portfolio_reevaluation(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snap,
        champion_guard=guard,
    )
    from analytics.live_trading_operations import load_policy as load_lt_pol

    lt_pol = load_lt_pol(root)
    relaxed = bool(lt_pol.get("relaxed_order_preflight", True))

    row = _symbol_reeval_row(report, sym)
    if report.get("us_session_open") and not report.get("quote_fresh"):
        blocks.append(
            _block(
                "REEVAL_STALE_QUOTES",
                str(report.get("quote_reason") or "Portfolio-Vergleich ohne frische Live-Kurse."),
            )
        )

    if row:
        lines.append(
            f"Portfolio-Abgleich: {row.get('action_de', '—')} "
            f"(Gap {float(row.get('gap_eur') or 0):+.2f} €, Ist {row.get('current_eur')} / Soll {row.get('target_eur')})"
        )
        if row.get("fee_note_de"):
            lines.append(f"Gebühren: {row['fee_note_de']}")
        ac = str(row.get("action_code") or "")
        if not relaxed:
            if ac not in ("NACHKAUF", "LEICHT_UNTER") and report.get("quote_fresh") and report.get("trade_required"):
                blocks.append(
                    _block(
                        "NOT_WORTH_IT",
                        f"Portfolio-Abgleich: kein lohnender Nachkauf für {sym} ({ac}).",
                    )
                )
            elif ac not in ("NACHKAUF", "LEICHT_UNTER") and report.get("quote_fresh"):
                blocks.append(
                    _block(
                        "NOT_WORTH_IT",
                        f"Portfolio-Abgleich empfiehlt für {sym}: {ac} — nicht kaufen.",
                    )
                )
    elif not relaxed and report.get("quote_fresh") and sym != str((plan.get("primary_action") or {}).get("symbol") or "").upper():
        blocks.append(_block("SYMBOL_NOT_IN_REEVAL", f"{sym} nicht in aktuellem Portfolio-Check."))

    wave = plan.get("rebalance_wave") if isinstance(plan.get("rebalance_wave"), dict) else {}
    row_scaled = (plan.get("primary_action") or {}) if isinstance(plan.get("primary_action"), dict) else {}
    if row_scaled.get("scaled_notional_eur") is not None:
        notional = float(row_scaled.get("scaled_notional_eur") or target_notional_eur)
    elif row_scaled.get("wave_scale_factor") is not None and row_scaled.get("original_notional_eur") is not None:
        notional = round(
            float(row_scaled["original_notional_eur"]) * float(row_scaled["wave_scale_factor"]),
            2,
        )
    else:
        notional = float(target_notional_eur)
    if wave:
        from execution.confirmed_live.rebalance_wave_planner import wave_summary_de

        lines.append(f"Cash-Welle: {wave_summary_de(wave)}")
        if row_scaled.get("original_notional_eur") is not None and notional != float(
            row_scaled.get("original_notional_eur") or 0
        ):
            lines.append(
                f"Skaliertes Order-Volumen: {notional:.2f} € "
                f"(Modell-Gap {float(row_scaled.get('original_notional_eur') or 0):.2f} €)"
            )
    worth, fee_reason = is_notional_worth_trading(notional, root, price_eur=limit)
    pol = load_fee_economics_policy(root)
    rt = estimate_round_trip_cost_eur(notional, policy=pol)
    hurdle = trade_fee_hurdle_eur(root, notional_eur=notional, price_eur=limit)
    lines.append(
        f"Round-trip ~{rt['round_trip_cost_eur']:.2f} € ({rt['round_trip_pct']:.2f} %) · Hürde {hurdle:.2f} €"
    )
    if not worth and not relaxed:
        blocks.append(_block("FEE_HURDLE", fee_reason))
    elif not worth:
        lines.append(f"Hinweis Gebühren: {fee_reason}")

    st = estimate_stress_round_trip_cost_eur(notional, price_eur=limit, policy=pol)
    lines.append(
        f"Stress Round-trip ~{st['round_trip_cost_eur']:.2f} € ({st['round_trip_pct']:.2f} %)"
    )
    if not relaxed and load_fee_economics_policy(root).get("require_stress_pass_for_trade", True):
        worth_s, fee_s = is_notional_worth_trading_stress(notional, root, price_eur=limit)
        if not worth_s:
            blocks.append(_block("FEE_STRESS_HURDLE", fee_s))

    rat = explain_primary_pick(root, symbol=sym, plan_row=(plan.get("primary_action") or {}))
    lines.append("")
    lines.append("Modell-Begründung (CSV, eingefroren):")
    lines.append(rationale_one_liner(rat, max_len=200))
    for f in (rat.get("factors_de") or [])[:10]:
        lines.append(f"  • {f}")

    lines.append("")
    lines.append(f"Portfolio-Check: {report.get('summary_de', '—')[:280]}")

    ok = len(blocks) == 0
    return {
        "ok": ok,
        "symbol": sym,
        "limit_price_eur": limit,
        "target_notional_eur": notional,
        "blocks": blocks,
        "confirmation_lines": lines,
        "quote_snapshot": quote_snap,
        "fx": fx,
        "reevaluation": report,
        "pick_rationale": rat,
        "fee_round_trip_eur": rt.get("round_trip_cost_eur"),
    }


def format_confirmation_dialog_text(preflight: Dict[str, Any]) -> str:
    if not preflight.get("ok"):
        hdr = "Order blockiert (fail-closed):\n\n"
        bl = "\n".join(f"• {b['message_de']}" for b in preflight.get("blocks") or [])
        return hdr + bl
    body = "\n".join(preflight.get("confirmation_lines") or [])
    return (
        "Live-Prüfung bestanden — Order nur nach Ihrer Bestätigung.\n"
        "(Frische Kurse, FX, Gebühren, Portfolio-Abgleich)\n\n"
        + body
    )
