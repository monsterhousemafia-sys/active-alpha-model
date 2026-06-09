"""R3 Exec Mirror — State aus Evidence (read-only, keine UI).

Datenfluss:
  evidence/*.json  →  build_exec_mirror_state(root)  →  dict
  dict             →  GET /api/r3/mirror (Hub) oder HTML-Render
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics.r3_crash_guard import empty_mirror_state, safe_float, safe_int

_LOG = logging.getLogger(__name__)

# --- Evidence-Pfade (einzige Quellen für den Spiegel) ---
EVIDENCE_ORDERS = Path("evidence/r3_stock_orders_latest.json")
EVIDENCE_PREP = Path("evidence/r3_freigabe_latest.json")
EVIDENCE_BATCH = Path("evidence/r3_order_batch_latest.json")
EVIDENCE_BOND = Path("evidence/r3_t212_api_bond_latest.json")
EVIDENCE_SNAP = Path("evidence/pilot_day_trading_snapshot_latest.json")
EVIDENCE_PLAN = Path("evidence/pilot_investment_plan_latest.json")
EVIDENCE_REEVAL = Path("evidence/pilot_portfolio_reevaluation_latest.json")
EVIDENCE_KING = Path("evidence/king_trading_assist_latest.json")
EVIDENCE_CYCLE = Path("evidence/r3_trading_cycle_latest.json")
EVIDENCE_LOOP = Path("evidence/r3_closed_loop_latest.json")
EVIDENCE_ENGINE = Path("evidence/alpha_model_background_engine_latest.json")
EVIDENCE_SCORE = Path("evidence/closed_loop_score_latest.json")
EVIDENCE_REFRESH = Path("evidence/pilot_integrated_refresh_latest.json")
EVIDENCE_STACK = Path("evidence/stack_integrity_latest.json")
EVIDENCE_POSTMORTEM = Path("evidence/r3_daily_postmortem_latest.json")
EVIDENCE_QUOTES = Path("evidence/r3_quote_keepalive_latest.json")

_PREP_LABELS = {"t212_bond": "T212", "live_quotes": "Kurse", "order_surface": "Orders"}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _resolve_updated_at_utc(*sources: Dict[str, Any]) -> Optional[str]:
    best: Optional[datetime] = None
    best_raw: Optional[str] = None
    for doc in sources:
        raw = str(doc.get("updated_at_utc") or "").strip()
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            if best is None:
                best_raw = raw
            continue
        if best is None or ts > best:
            best = ts
            best_raw = raw
    return best_raw


def resolve_submission_mode(root: Path) -> Dict[str, Any]:
    """Order-Policy: Live nur wenn alle Gates explizit grün — sonst Dry-Run."""
    root = Path(root)
    reasons: List[str] = []
    live = False
    gates_checked = False
    try:
        from execution.linux_security_boundary import live_order_submission_blocked

        gates_checked = True
        if live_order_submission_blocked():
            reasons.append("Linux-Compute ohne Native-Freigabe")
        elif os.environ.get("AA_EXECUTION_DRY_RUN", "").strip() == "1":
            reasons.append("AA_EXECUTION_DRY_RUN")
        else:
            from execution.confirmed_live.p17_review_mode_guard import review_mode_active
            from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed

            if review_mode_active() and not live_submission_allowed(root):
                reasons.append("Review-Modus")
            else:
                live = True
    except Exception:
        reasons.append("Policy-Check fehlgeschlagen")
    if not gates_checked and not reasons:
        reasons.append("Policy unverifiziert")
    mode_de = (
        "Live-Submit nach Bestätigung"
        if live
        else "Dry-Run — " + (", ".join(reasons) if reasons else "keine Live-Orders")
    )
    return {"live_submit": live, "mode_de": mode_de, "reasons_de": reasons}


def display_headline(headline: str) -> str:
    text = str(headline or "—").strip()
    if " · " in text and "Zeilen" in text:
        return text.split(" · ", 1)[0].strip() or text
    return text or "—"


def _plan_integration_status_de(plan: Dict[str, Any]) -> str:
    parts: List[str] = []
    live = plan.get("t212_live") or {}
    basis = str(plan.get("plan_capital_basis") or live.get("plan_capital_basis") or "")
    if basis == "t212_total_account_live":
        parts.append("Live-Depot gesamt")
    elif basis == "r3_cash_investable_live":
        parts.append("Live-Cash")
    if plan.get("king_plan_merged"):
        n = int(plan.get("king_boost_applied") or 0)
        parts.append(f"König +{n}" if n else "König eingearbeitet")
    if plan.get("rebalanced_to_t212"):
        npos = int(plan.get("t212_positions_count") or live.get("positions_count") or 0)
        parts.append(f"T212-Umschichtung ({npos} Pos.)")
    sync = str(plan.get("t212_last_sync_utc") or live.get("last_sync_utc") or "")[:19].replace("T", " ")
    if sync:
        parts.append(f"Sync {sync}")
    return " · ".join(parts) if parts else "Champion-Basis"


def _collect_model_allocations(plan: Dict[str, Any], reeval: Dict[str, Any]) -> tuple[float, List[Dict[str, Any]]]:
    raw_inv = plan.get("investable_eur")
    if raw_inv is None:
        raw_inv = reeval.get("deployable_eur")
    if raw_inv is None:
        return 0.0, []
    plan_total = max(0.0, round(float(raw_inv), 2))
    rows: List[Dict[str, Any]] = []
    for alloc in plan.get("allocations") or []:
        if not isinstance(alloc, dict):
            continue
        tgt = round(safe_float(alloc.get("target_eur")), 2)
        if tgt <= 0:
            continue
        pct = round((tgt / plan_total * 100.0), 1) if plan_total > 0 else 0.0
        rows.append(
            {
                "symbol": str(alloc.get("symbol") or "—")[:32],
                "notional_eur": tgt,
                "pct": pct,
            }
        )
    rows.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    return plan_total, rows


def _collect_deferred_package_status(root: Path, buy_symbols: set[str]) -> Dict[str, Any]:
    if not buy_symbols:
        return {"active": False, "pending_count": 0, "want_count": 0, "complete": False}
    try:
        from execution.confirmed_live.us_equity_deferred_intents import (
            list_pending_r3_intents,
            r3_package_pending_status,
        )

        pending = list_pending_r3_intents(root)
        if not pending:
            return {"active": False, "pending_count": 0, "want_count": 0, "complete": False}
        pkg = r3_package_pending_status(root, buy_symbols)
        want = int(pkg.get("want_count") or 0)
        have = int(pkg.get("pending_count") or 0)
        return {
            "active": True,
            "pending_count": have,
            "want_count": want,
            "complete": bool(pkg.get("complete")),
            "missing_symbols": list(pkg.get("missing_symbols") or [])[:8],
            "headline_de": (
                f"Vorbestellt {have}/{want}"
                if want
                else f"Vorbestellt ({len(pending)})"
            ),
            "source_de": "live_pilot/confirmed_execution/us_equity_deferred_intents.json",
        }
    except Exception:
        return {"active": False, "pending_count": 0, "want_count": 0, "complete": False}


def _collect_execution_package(orders: Dict[str, Any]) -> Dict[str, Any]:
    initial_pkg = orders.get("initial_package") or {}
    buy_lines: List[Dict[str, Any]] = []
    sell_lines: List[Dict[str, Any]] = []
    for row in orders.get("stocks") or []:
        if not isinstance(row, dict):
            continue
        side = str(row.get("side") or "").upper()
        if side not in ("BUY", "SELL"):
            continue
        raw = row.get("notional_eur")
        if raw is None:
            continue
        notional = round(float(raw), 2)
        if notional <= 0:
            continue
        entry = {"symbol": str(row.get("symbol") or "—")[:32], "notional_eur": notional, "side": side}
        if side == "SELL":
            sell_lines.append(entry)
        else:
            buy_lines.append(entry)
    buy_lines.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    sell_lines.sort(key=lambda r: (-float(r.get("notional_eur") or 0), str(r.get("symbol") or "")))
    lines = buy_lines
    exec_total = round(sum(float(r.get("notional_eur") or 0) for r in buy_lines), 2)
    sell_total = round(sum(float(r.get("notional_eur") or 0) for r in sell_lines), 2)
    pkg_notional = initial_pkg.get("notional_eur")
    if pkg_notional is not None:
        notional = round(float(pkg_notional), 2)
    elif lines:
        notional = exec_total
    else:
        notional = 0.0
    return {
        "active": bool(initial_pkg.get("active")),
        "source_de": str(EVIDENCE_ORDERS),
        "notional_eur": notional,
        "sell_notional_eur": sell_total if sell_lines else None,
        "buy_count": len(buy_lines),
        "sell_count": len(sell_lines),
        "lines": lines,
        "sell_lines": sell_lines,
    }


def _resolve_trading_cycle(root: Path, cycle: Dict[str, Any]) -> Dict[str, Any]:
    """Kreislauf aus persistierter Evidence oder evaluate_trading_cycle (read-only)."""
    if cycle.get("stages"):
        return cycle
    try:
        from analytics.r3_trading_cycle import evaluate_trading_cycle

        return evaluate_trading_cycle(root)
    except Exception:
        return cycle


def _collect_system_metrics(
    root: Path,
    *,
    broker_summary: Dict[str, Any],
    quote_count: int,
    flow_doc: Dict[str, Any],
) -> List[Dict[str, Any]]:
    from analytics.r3_evidence_metrics import (
        pipeline_broker_metric,
        system_channels_metric,
        system_flow_metric,
        system_quotes_metric,
    )

    metrics: List[Dict[str, Any]] = []
    flow_ref = "evidence/r3_flow_latest.json"
    if flow_doc:
        pct = flow_doc.get("fluidity_pct")
        stable_min = int(flow_doc.get("stable_min_pct") or 75)
        metrics.append(
            {
                "id": "fluidity",
                "key_de": "Fluss",
                "ok": int(pct) >= stable_min if pct is not None else False,
                **system_flow_metric(flow_doc, evidence_ref=flow_ref),
            }
        )
        channels = list(flow_doc.get("channels") or [])
        if channels:
            ok_n = sum(1 for c in channels if c.get("ok"))
            metrics.append(
                {
                    "id": "channels",
                    "key_de": "Kanäle",
                    "ok": ok_n == len(channels),
                    **system_channels_metric(channels, evidence_ref=flow_ref),
                }
            )
    cash = broker_summary.get("cash_eur")
    inv = broker_summary.get("investable_eur")
    if cash is not None or inv is not None:
        bond = {"cash_eur": cash, "investable_eur": inv}
        m = pipeline_broker_metric(bond, {}, evidence_ref=str(EVIDENCE_BOND))
        metrics.append(
            {
                "id": "account",
                "key_de": "Konto",
                "ok": cash is not None and float(cash) > 0,
                **m,
            }
        )
    qm = system_quotes_metric(
        quote_count if quote_count > 0 else None,
        evidence_ref=str(EVIDENCE_SNAP),
        field="quote_snapshot.executable_prices_eur",
    )
    metrics.append(
        {
            "id": "quotes",
            "key_de": "Kurse",
            "ok": quote_count > 0,
            **qm,
        }
    )
    return metrics


def _collect_pipeline_layers(
    *,
    plan: Dict[str, Any],
    bond: Dict[str, Any],
    king: Dict[str, Any],
    cycle: Dict[str, Any],
    loop: Dict[str, Any],
    engine: Dict[str, Any],
    snap: Dict[str, Any],
    refresh: Dict[str, Any],
    stack: Dict[str, Any],
    score: Dict[str, Any],
    pkg_ready: bool,
    pkg_headline: str,
    pkg_notional_eur: Optional[float] = None,
    deferred_status: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    from analytics.r3_evidence_metrics import (
        layer_from_metric,
        pipeline_broker_metric,
        pipeline_cycle_metric,
        pipeline_engine_metric,
        pipeline_fees_metric,
        pipeline_freigabe_metric,
        pipeline_health_metric,
        pipeline_king_metric,
        pipeline_kreis_metric,
        pipeline_loop_metric,
        pipeline_plan_metric,
        pipeline_refresh_metric,
        pipeline_stack_metric,
    )

    live = plan.get("t212_live") if isinstance(plan.get("t212_live"), dict) else {}
    cash_raw = _first_json(bond.get("cash_eur"), live.get("cash_eur"))
    health = (snap.get("health") or {}) if isinstance(snap.get("health"), dict) else {}
    cost = refresh.get("cost_risk") or snap.get("cost_risk") or {}
    follow_n = len(king.get("follow_on_suggestions") or [])

    layers = [
        layer_from_metric(
            "broker",
            "T212 Konto",
            pipeline_broker_metric(bond, live, evidence_ref=str(EVIDENCE_BOND)),
            ok=bool(bond.get("connected")) and cash_raw is not None and float(cash_raw) > 0,
        ),
        layer_from_metric(
            "plan",
            "Modell-Plan",
            pipeline_plan_metric(plan, evidence_ref=str(EVIDENCE_PLAN)),
            ok=bool(plan.get("pipeline_synced")) and bool(live) and bool(plan.get("allocations")),
        ),
        layer_from_metric(
            "king",
            "König 32B",
            pipeline_king_metric(king, evidence_ref=str(EVIDENCE_KING)),
            ok=bool(plan.get("king_plan_merged")) or follow_n > 0,
            partial=not bool(plan.get("king_plan_merged")) and follow_n > 0,
        ),
        layer_from_metric(
            "cycle",
            "Trading-Kreislauf",
            pipeline_cycle_metric(cycle, evidence_ref=str(EVIDENCE_CYCLE)),
            ok=bool(cycle.get("closed")),
        ),
        layer_from_metric(
            "loop",
            "Closed Loop",
            pipeline_loop_metric(loop, evidence_ref=str(EVIDENCE_LOOP)),
            ok=bool(loop.get("loop_ok")),
        ),
        layer_from_metric(
            "engine",
            "Background-Engine",
            pipeline_engine_metric(engine, evidence_ref=str(EVIDENCE_ENGINE)),
            ok=bool(engine.get("ok")),
        ),
        layer_from_metric(
            "freigabe",
            "Freigabe / Paket",
            pipeline_freigabe_metric(
                pkg_ready=pkg_ready,
                notional_eur=pkg_notional_eur,
                evidence_ref=str(EVIDENCE_PREP),
                deferred_headline=(
                    str((deferred_status or {}).get("headline_de") or "")
                    if (deferred_status or {}).get("active")
                    else None
                ),
            ),
            ok=pkg_ready or bool((deferred_status or {}).get("complete")),
            partial=bool((deferred_status or {}).get("active"))
            and not bool((deferred_status or {}).get("complete")),
        ),
        layer_from_metric(
            "health",
            "Snapshot Health",
            pipeline_health_metric(health, evidence_ref=str(EVIDENCE_SNAP)),
            ok=bool(health.get("ok")),
        ),
        layer_from_metric(
            "fees",
            "Gebühren-Gate",
            pipeline_fees_metric(cost if isinstance(cost, dict) else {}, evidence_ref=str(EVIDENCE_REFRESH)),
            ok=bool(cost.get("trade_allowed", True)) if cost else False,
        ),
        layer_from_metric(
            "kreis",
            "Kreis-Score",
            pipeline_kreis_metric(score, evidence_ref=str(EVIDENCE_SCORE)),
            ok=(
                int(score.get("green") or 0) >= int(score["total"]) // 2
                if score.get("total") is not None
                else False
            ),
            partial=int(score.get("green") or 0) > 0,
        ),
        layer_from_metric(
            "stack",
            "Hub / Stack",
            pipeline_stack_metric(stack, evidence_ref=str(EVIDENCE_STACK)),
            ok=bool(stack.get("stack_ok")),
        ),
    ]
    rs = refresh.get("refresh_status") or {}
    if rs.get("rows"):
        rows = [r for r in rs["rows"] if isinstance(r, dict)]
        fails = [r for r in rows if r.get("status") == "FAIL"]
        warns = [r for r in rows if r.get("status") == "WARN"]
        if fails or warns:
            layers.append(
                layer_from_metric(
                    "refresh",
                    "Integrated Refresh",
                    pipeline_refresh_metric(rows, evidence_ref=str(EVIDENCE_REFRESH)),
                    ok=not fails and bool(rs.get("all_ok", not fails)),
                    partial=bool(warns) and not fails,
                )
            )
    return layers


def _first_json(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _as_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _collect_prognosis_mirror(root: Path, prognosis: Dict[str, Any]) -> Dict[str, Any]:
    picks = list(prognosis.get("top_picks") or [])
    rows = [
        {
            "symbol": str(p.get("ticker") or "—"),
            "pct": float(p.get("target_weight_pct") or 0),
            "king_boost_pct": p.get("king_boost_pct"),
        }
        for p in picks[:12]
    ]
    ww_buys = list(prognosis.get("worthwhile_buys") or [])[:12]
    if not ww_buys:
        ww_file = _load_json(root / Path("evidence/r3_worthwhile_positions_latest.json"))
        ww_buys = list(ww_file.get("worthwhile_buys") or [])[:12]
    return {
        "ok": bool(prognosis.get("ok")),
        "signal_date": prognosis.get("signal_date"),
        "capital_basis_de": str(prognosis.get("capital_basis_de") or "")[:120],
        "summary_de": str(prognosis.get("summary_de") or "")[:200],
        "investable_eur": _as_optional_float(prognosis.get("investable_eur")),
        "positions": int(prognosis.get("positions") or 0),
        "t212_trusted": prognosis.get("t212_trusted"),
        "worthwhile_buy_count": int(prognosis.get("worthwhile_buy_count") or len(ww_buys)),
        "top_picks": rows,
        "worthwhile_buys": ww_buys,
        "source_de": "evidence/r3_t212_prognosis_latest.json",
    }


def _collect_king_follow_on(king: Dict[str, Any]) -> Dict[str, Any]:
    suggestions = [
        {
            "symbol": str(s.get("symbol") or "—")[:32],
            "reason_de": str(s.get("reason_de") or "")[:120],
            "hint_eur": safe_float(s.get("hint_eur")) if s.get("hint_eur") else None,
        }
        for s in (king.get("follow_on_suggestions") or [])
        if isinstance(s, dict) and s.get("worth_follow_on", True)
    ]
    return {
        "advisory_only": bool(king.get("advisory_only", True)),
        "headline_de": str(king.get("headline_de") or king.get("summary_de") or "")[:160],
        "summary_de": str(king.get("summary_de") or "")[:240],
        "operator_hint_de": str(king.get("operator_hint_de") or "")[:120],
        "suggestion_count": len(suggestions),
        "suggestions": suggestions[:8],
        "source_de": str(EVIDENCE_KING),
    }


def build_exec_mirror_state(root: Path, *, refresh_scans: bool = False) -> Dict[str, Any]:
    """Read-only Spiegel — alle Felder aus Evidence, kein erfundener Wert."""
    root = Path(root)
    try:
        return _build_exec_mirror_state_impl(root, refresh_scans=bool(refresh_scans))
    except Exception as exc:
        _LOG.exception("build_exec_mirror_state failed: %s", exc)
        return empty_mirror_state(detail_de=str(exc)[:200])


def _build_exec_mirror_state_impl(root: Path, *, refresh_scans: bool = False) -> Dict[str, Any]:
    from analytics.r3_freigabe import freigabe_governance_note_de, package_ready

    pkg = package_ready(root)
    orders = _load_json(root / EVIDENCE_ORDERS)
    prep = _load_json(root / EVIDENCE_PREP)
    batch = _load_json(root / EVIDENCE_BATCH)
    bond = _load_json(root / EVIDENCE_BOND)
    snap = _load_json(root / EVIDENCE_SNAP)
    plan = _load_json(root / EVIDENCE_PLAN)
    reeval = _load_json(root / EVIDENCE_REEVAL)
    king = _load_json(root / EVIDENCE_KING)
    cycle = _load_json(root / EVIDENCE_CYCLE)
    loop = _load_json(root / EVIDENCE_LOOP)
    engine = _load_json(root / EVIDENCE_ENGINE)
    score = _load_json(root / EVIDENCE_SCORE)
    refresh = _load_json(root / EVIDENCE_REFRESH)
    stack = _load_json(root / EVIDENCE_STACK)

    quote_snap = snap.get("quote_snapshot") or {}
    health = snap.get("health") if isinstance(snap.get("health"), dict) else {}
    exec_prices = quote_snap.get("executable_prices_eur") or {}
    plan_total, model_allocations = _collect_model_allocations(plan, reeval)

    prep_rows: List[Dict[str, Any]] = []
    for step in prep.get("prep_steps") or []:
        if not isinstance(step, dict):
            continue
        sid = str(step.get("step") or "")
        prep_rows.append({"label_de": _PREP_LABELS.get(sid, sid), "ok": bool(step.get("ok"))})

    headline = display_headline(str(pkg.get("headline_de") or "Kein aktives Paket"))
    cost = refresh.get("cost_risk") or snap.get("cost_risk") or {}
    functions_doc = _load_json(root / Path("evidence/r3_trading_functions_latest.json"))
    if not functions_doc.get("functions"):
        try:
            from analytics.r3_trading_functions import build_r3_trading_functions

            functions_doc = build_r3_trading_functions(root, persist=False)
        except Exception:
            functions_doc = functions_doc or {}
    try:
        from analytics.r3_runtime_upgrade import (
            build_upgrade_status,
            load_runtime_profile,
            load_upgrade_evidence,
            scan_runtime_upgrades,
        )

        runtime_profile = load_runtime_profile(root)
        if refresh_scans:
            upgrade_doc = scan_runtime_upgrades(root, persist=True, force=True)
        else:
            upgrade_doc = load_upgrade_evidence(root)
        runtime_upgrade = build_upgrade_status(root)
        runtime_upgrade["pending"] = upgrade_doc.get("pending")
        runtime_upgrade["has_pending"] = bool(
            upgrade_doc.get("pending") and (upgrade_doc.get("pending") or {}).get("status") == "awaiting_confirmation"
        )
    except Exception:
        runtime_profile = {}
        runtime_upgrade = {}
    try:
        from analytics.r3_local_growth import local_confirmation_de, scan_local_growth

        if refresh_scans:
            stack_ok = bool(_load_json(root / Path("evidence/stack_integrity_latest.json")).get("stack_ok"))
            local_growth = scan_local_growth(root, persist=True, force=True, fast=stack_ok)
        else:
            local_growth = _load_json(root / Path("evidence/r3_local_growth_latest.json"))
        local_confirm = local_confirmation_de(root)
    except Exception:
        local_growth = {}
        local_confirm = ""
    try:
        from analytics.series_readiness import scan_series_readiness

        if refresh_scans:
            series_readiness = scan_series_readiness(root, persist=True, force=True, fast=True)
        else:
            series_readiness = _load_json(root / Path("evidence/series_readiness_latest.json"))
    except Exception:
        series_readiness = {}
    operator_readiness: Dict[str, Any] = {}
    try:
        from analytics.r3_operator_readiness import sync_r3_operator_readiness

        if refresh_scans:
            operator_readiness = sync_r3_operator_readiness(root, persist=True)
        else:
            operator_readiness = _load_json(root / Path("evidence/r3_operator_readiness_latest.json"))
            if not operator_readiness:
                operator_readiness = sync_r3_operator_readiness(root, persist=True)
    except Exception:
        operator_readiness = _load_json(root / Path("evidence/r3_operator_readiness_latest.json"))
    local_runtime = _load_json(root / Path("control/alpha_model_local_runtime.json"))
    local_first = _load_json(root / Path("evidence/r3_local_first_latest.json"))
    quotes_keep = _load_json(root / EVIDENCE_QUOTES)
    ingest = _load_json(root / Path("evidence/r3_browser_ingest_latest.json"))
    postmortem = _load_json(root / EVIDENCE_POSTMORTEM)
    if not postmortem.get("as_of_date"):
        try:
            from analytics.r3_daily_postmortem import run_daily_postmortem

            postmortem = run_daily_postmortem(root, persist=True)
        except Exception:
            postmortem = postmortem or {}
    alerts_de: List[str] = []
    voice_warning_de = str(postmortem.get("voice_warning_de") or "").strip() or None
    if postmortem.get("stale_sync_warning_de"):
        alerts_de.append(str(postmortem["stale_sync_warning_de"])[:160])
    if postmortem.get("bad_day") and postmortem.get("headline_de"):
        alerts_de.append(str(postmortem["headline_de"])[:160])
    if not voice_warning_de and alerts_de:
        voice_warning_de = alerts_de[0]

    cycle_resolved = _resolve_trading_cycle(root, cycle)
    pkg_notional_raw = pkg.get("notional_eur")
    pkg_notional_eur = _as_optional_float(pkg_notional_raw) if pkg_notional_raw is not None else None
    exec_pkg = _collect_execution_package(orders)
    buy_syms = {
        str(r.get("symbol") or "").upper()
        for r in (exec_pkg.get("lines") or [])
        if isinstance(r, dict) and r.get("symbol")
    }
    deferred_status = _collect_deferred_package_status(root, buy_syms)
    layers = _collect_pipeline_layers(
        plan=plan,
        bond=bond,
        king=king,
        cycle=cycle_resolved,
        loop=loop,
        engine=engine,
        snap=snap,
        refresh=refresh,
        stack=stack,
        score=score,
        pkg_ready=bool(pkg.get("ready")),
        pkg_headline=headline,
        pkg_notional_eur=pkg_notional_eur,
        deferred_status=deferred_status,
    )
    flow_doc: Dict[str, Any] = {}
    try:
        from analytics.r3_flow_orchestrator import build_r3_flow_status

        flow_doc = build_r3_flow_status(root, persist=False, read_only=True)
    except Exception:
        flow_doc = _load_json(root / Path("evidence/r3_flow_latest.json"))
    broker_summary = {
        "cash_eur": _as_optional_float(bond.get("cash_eur")),
        "investable_eur": _as_optional_float(
            _first_json(bond.get("investable_eur"), plan.get("investable_eur"))
        ),
        "positions_count": bond.get("positions_count"),
    }
    quote_count = len(exec_prices)
    system_metrics = _collect_system_metrics(
        root,
        broker_summary=broker_summary,
        quote_count=quote_count,
        flow_doc=flow_doc,
    )

    return {
        "schema_version": 2,
        "mirror_de": "Spiegel der technischen Exekutive — nur Anzeige",
        "updated_at_utc": _resolve_updated_at_utc(prep, batch, orders, plan, loop, snap),
        "package_ready": bool(pkg.get("ready")),
        "headline_de": headline,
        "governance_note_de": str(
            prep.get("governance_note_de") or pkg.get("governance_note_de") or freigabe_governance_note_de()
        ),
        "notional_eur": round(safe_float(pkg.get("notional_eur")), 2),
        "buy_count": safe_int(pkg.get("buy_count")),
        "model_output": {
            "title_de": "R3",
            "source_de": str(EVIDENCE_PLAN),
            "investable_eur": plan_total,
            "allocations": model_allocations,
            "plan_integration_de": _plan_integration_status_de(plan),
        },
        "execution_package": {**exec_pkg, "deferred_status": deferred_status},
        "deferred_package": deferred_status,
        "king_follow_on": _collect_king_follow_on(king),
        "prognosis": _collect_prognosis_mirror(root, _load_json(root / Path("evidence/r3_t212_prognosis_latest.json"))),
        "quote_keepalive": {
            "ok": bool(quotes_keep.get("ok")),
            "skipped": quotes_keep.get("skipped"),
            "price_latest": quotes_keep.get("price_latest") or ingest.get("price_latest"),
            "quote_status": (quotes_keep.get("assess_after") or {}).get("quote_status"),
            "headline_de": str(quotes_keep.get("headline_de") or ingest.get("message_de") or "")[:160],
            "updated_at_utc": quotes_keep.get("updated_at_utc") or ingest.get("updated_at_utc"),
            "source_de": str(EVIDENCE_QUOTES),
        },
        "daily_postmortem": {
            "ok": bool(postmortem.get("ok")),
            "bad_day": bool(postmortem.get("bad_day")),
            "as_of_date": postmortem.get("as_of_date"),
            "signal_date": postmortem.get("signal_date"),
            "summary_de": str(postmortem.get("summary_de") or "")[:200],
            "headline_de": str(postmortem.get("headline_de") or "")[:160],
            "portfolio_return_pct": postmortem.get("portfolio_return_pct"),
            "benchmark_return_pct": postmortem.get("benchmark_return_pct"),
            "delta_vs_benchmark_pct": postmortem.get("delta_vs_benchmark_pct"),
            "worst": postmortem.get("worst"),
            "best": postmortem.get("best"),
            "picks": list(postmortem.get("picks") or [])[:12],
            "source_de": str(EVIDENCE_POSTMORTEM),
        },
        "alerts_de": alerts_de,
        "voice_warning_de": voice_warning_de,
        "submission_mode": resolve_submission_mode(root),
        "t212_connected": bool(bond.get("bonded")) and bool(bond.get("connected")),
        "t212_detail_de": str(bond.get("confirmation_de") or "")[:100],
        "quote_count": len(exec_prices),
        "us_session_open": bool(quote_snap.get("_us_session_open")),
        "prep_rows": prep_rows,
        "pipeline_layers": layers,
        "broker_summary": {
            "cash_eur": round(safe_float(bond.get("cash_eur")), 2),
            "investable_eur": round(
                safe_float(bond.get("investable_eur") or plan.get("investable_eur")), 2
            ),
            "positions_count": safe_int(bond.get("positions_count")),
        },
        "snapshot_health": {
            "ok": bool(health.get("ok")),
            "blocks_execute": bool(health.get("blocks_execute")),
            "plan_pipeline_synced": health.get("plan_pipeline_synced"),
            "playbook_action": str(health.get("playbook_action") or ""),
            "errors_de": list(health.get("errors_de") or [])[:3],
        },
        "cost_risk": cost,
        "system_metrics": system_metrics,
        "trading_cycle": {
            "closed": bool(cycle_resolved.get("closed")),
            "cycle_pct": cycle_resolved.get("cycle_pct"),
            "stages_ok": cycle_resolved.get("stages_ok"),
            "stages_total": cycle_resolved.get("stages_total"),
            "stages": list(cycle_resolved.get("stages") or []),
        },
        "closed_loop": {
            "loop_ok": bool(loop.get("loop_ok")),
            "pipeline_synced": bool(loop.get("pipeline_synced")),
            "message_de": str(loop.get("message_de") or "")[:120],
        },
        "kreis_score": {
            "headline_de": str(score.get("headline_de") or ""),
            "green": int(score.get("green") or 0),
            "total": int(score.get("total") or 6),
            "pct": int(score.get("pct") or 0),
        },
        "local_runtime": {
            "hub_url": str(local_runtime.get("hub_url") or local_first.get("local_hub") or "http://127.0.0.1:17890"),
            "surface_url": str(local_growth.get("local_primary_url") or "http://127.0.0.1:17890/r3"),
            "local_only": bool(local_runtime.get("local_only", True)),
            "headline_de": str(local_growth.get("headline_de") or local_first.get("headline_de") or "R3 lokal"),
            "confirmation_de": str(local_confirm or local_first.get("confirmation_de") or "")[:160],
            "growth_pct": int(local_growth.get("growth_pct") or 0),
        },
        "local_growth": local_growth,
        "trading_functions": {
            "functions": list(functions_doc.get("functions") or []),
            "primary_function_id": functions_doc.get("primary_function_id"),
            "functions_active": int(functions_doc.get("functions_active") or 0),
            "context": functions_doc.get("context") or {},
        },
        "runtime_profile": runtime_profile,
        "runtime_upgrade": runtime_upgrade,
        "series_readiness": series_readiness,
        "operator_readiness": operator_readiness,
        "operator_readiness_ref": "evidence/r3_operator_readiness_latest.json",
        "last_batch": {
            "ok": batch.get("ok"),
            "partial": batch.get("partial"),
            "message_de": str(batch.get("message_de") or "")[:160],
            "orders_submitted": batch.get("orders_submitted"),
            "orders_total": batch.get("orders_total"),
            "notional_eur": batch.get("notional_eur"),
            "mode": batch.get("mode"),
        }
        if batch
        else None,
        "orders_ref": str(EVIDENCE_ORDERS),
    }
