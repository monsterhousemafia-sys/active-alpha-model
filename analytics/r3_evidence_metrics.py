"""R3-Anzeigemetriken — nur aus Evidence-Feldern berechnet, nie erfunden.

Jede Metrik liefert display_de + fields_de (JSON-Pfade) + evidence_ref.
Fehlende Felder → MISSING (—), kein or-0 für die Anzeige.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

MISSING = "—"


def _first_present(*values: Any) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
        if v != v:
            return None
        return v
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fmt_eur(value: Optional[float]) -> str:
    if value is None:
        return MISSING
    return f"{value:,.0f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _join_parts(parts: Sequence[str]) -> str:
    present = [p for p in parts if p and p != MISSING]
    return " · ".join(present) if present else MISSING


def _metric(display_de: str, *, evidence_ref: str, fields_de: Sequence[str]) -> Dict[str, Any]:
    return {
        "display_de": str(display_de or MISSING)[:48],
        "evidence_ref": str(evidence_ref or ""),
        "fields_de": list(fields_de),
    }


def trading_cycle_stage_metric(stage_id: str, doc: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    """Wert pro Kreislauf-Stufe — nur dokumentierte Evidence-Felder."""
    if not doc:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())

    if stage_id == "internet":
        lat = _as_int(doc.get("latency_ms"))
        if lat is not None:
            return _metric(f"{lat} ms", evidence_ref=evidence_ref, fields_de=("latency_ms",))
        if doc.get("internet_ok") is True:
            return _metric("1", evidence_ref=evidence_ref, fields_de=("internet_ok",))
        if doc.get("internet_ok") is False:
            return _metric("0", evidence_ref=evidence_ref, fields_de=("internet_ok",))
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())

    if stage_id == "account":
        cash = _as_float(doc.get("cash_eur"))
        inv = _as_float(doc.get("investable_eur"))
        if cash is None and inv is None:
            return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
        parts: List[str] = []
        if cash is not None:
            parts.append(f"{cash:,.0f}")
        if inv is not None:
            parts.append(_fmt_eur(inv))
        return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("cash_eur", "investable_eur"))

    if stage_id == "ingest":
        n = _as_int(doc.get("quote_count"))
        if n is not None:
            return _metric(str(n), evidence_ref=evidence_ref, fields_de=("quote_count",))
        if isinstance(doc.get("symbols"), list):
            return _metric(str(len(doc["symbols"])), evidence_ref=evidence_ref, fields_de=("symbols",))
        latest = doc.get("price_latest")
        if latest is not None:
            return _metric(str(latest)[:10], evidence_ref=evidence_ref, fields_de=("price_latest",))
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())

    if stage_id == "engine":
        reb = doc.get("rebalance") if isinstance(doc.get("rebalance"), dict) else {}
        cash = _as_float(reb.get("planning_cash_eur"))
        if cash is not None:
            return _metric(_fmt_eur(cash), evidence_ref=evidence_ref, fields_de=("rebalance.planning_cash_eur",))
        predict = doc.get("predict") if isinstance(doc.get("predict"), dict) else {}
        r3d = doc.get("r3_display") if isinstance(doc.get("r3_display"), dict) else {}
        sig = _first_present(predict.get("signal_date"), r3d.get("signal_date"))
        if sig is not None:
            return _metric(str(sig)[:10], evidence_ref=evidence_ref, fields_de=("predict.signal_date", "r3_display.signal_date"))
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())

    if stage_id == "plan":
        inv = _as_float(_first_present(doc.get("plan_capital_eur"), doc.get("investable_eur")))
        n_alloc = len(doc.get("allocations") or [])
        live = doc.get("t212_live") if isinstance(doc.get("t212_live"), dict) else {}
        pos_n = _as_int(_first_present(live.get("positions_count"), doc.get("t212_positions_count")))
        parts = []
        if n_alloc:
            parts.append(str(n_alloc))
        if pos_n is not None:
            parts.append(str(pos_n))
        if inv is not None:
            parts.append(_fmt_eur(inv))
        return _metric(
            _join_parts(parts),
            evidence_ref=evidence_ref,
            fields_de=("allocations", "t212_live.positions_count", "investable_eur"),
        )

    if stage_id == "display":
        pos = _as_int(doc.get("positions"))
        if pos is not None:
            return _metric(str(pos), evidence_ref=evidence_ref, fields_de=("positions",))
        sig = doc.get("signal_date")
        if sig is not None:
            return _metric(str(sig)[:10], evidence_ref=evidence_ref, fields_de=("signal_date",))
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())

    if stage_id == "orders":
        status = doc.get("status")
        if status is None:
            return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
        return _metric(str(status)[:16], evidence_ref=evidence_ref, fields_de=("status",))

    return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())


def pipeline_broker_metric(bond: Dict[str, Any], live: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    cash = _as_float(_first_present(bond.get("cash_eur"), live.get("cash_eur")))
    inv = _as_float(
        _first_present(bond.get("investable_eur"), live.get("cash_investable_eur"))
    )
    pos = _as_int(_first_present(bond.get("positions_count"), live.get("positions_count")))
    parts: List[str] = []
    if cash is not None:
        parts.append(f"{cash:,.0f}")
    if inv is not None:
        parts.append(_fmt_eur(inv))
    if pos is not None:
        parts.append(str(pos))
    return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("cash_eur", "investable_eur", "positions_count"))


def pipeline_plan_metric(plan: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    if not plan:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    n_alloc = len(plan.get("allocations") or [])
    boost = plan.get("king_boost_applied")
    run_id = plan.get("pipeline_run_id")
    parts: List[str] = []
    if n_alloc:
        parts.append(str(n_alloc))
    if boost is not None:
        parts.append(f"+{int(boost)}")
    if run_id:
        parts.append(str(run_id)[:12])
    return _metric(
        _join_parts(parts),
        evidence_ref=evidence_ref,
        fields_de=("allocations", "king_boost_applied", "pipeline_run_id"),
    )


def pipeline_king_metric(king: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    follow_n = len(king.get("follow_on_suggestions") or [])
    buy = king.get("buy_count")
    parts: List[str] = []
    if follow_n:
        parts.append(str(follow_n))
    if buy is not None:
        parts.append(str(int(buy)))
    if not parts:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("follow_on_suggestions", "buy_count"))


def pipeline_cycle_metric(cycle: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    ok_n = cycle.get("stages_ok")
    total = cycle.get("stages_total")
    pct = cycle.get("cycle_pct")
    if ok_n is None and total is None and pct is None:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    parts: List[str] = []
    if ok_n is not None and total is not None:
        parts.append(f"{int(ok_n)}/{int(total)}")
    elif ok_n is not None:
        parts.append(str(int(ok_n)))
    if pct is not None:
        parts.append(f"{int(pct)}%")
    return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("stages_ok", "stages_total", "cycle_pct"))


def pipeline_loop_metric(loop: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    inv = _as_float(_first_present(loop.get("investable_eur"), loop.get("plan_capital_eur")))
    pos = _as_int(loop.get("positions_count"))
    if inv is None and pos is None:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    parts: List[str] = []
    if inv is not None:
        parts.append(_fmt_eur(inv))
    if pos is not None:
        parts.append(str(pos))
    return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("investable_eur", "positions_count"))


def pipeline_engine_metric(engine: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    reb = engine.get("rebalance") if isinstance(engine.get("rebalance"), dict) else {}
    cash = _as_float(reb.get("planning_cash_eur"))
    if cash is not None:
        return _metric(_fmt_eur(cash), evidence_ref=evidence_ref, fields_de=("rebalance.planning_cash_eur",))
    predict = engine.get("predict") if isinstance(engine.get("predict"), dict) else {}
    sig = predict.get("signal_date")
    if sig is not None:
        return _metric(str(sig)[:10], evidence_ref=evidence_ref, fields_de=("predict.signal_date",))
    return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())


def pipeline_freigabe_metric(
    *,
    pkg_ready: bool,
    notional_eur: Optional[float],
    evidence_ref: str,
    deferred_headline: Optional[str] = None,
) -> Dict[str, Any]:
    if deferred_headline:
        return _metric(str(deferred_headline)[:32], evidence_ref=evidence_ref, fields_de=("deferred_package",))
    if notional_eur is not None and notional_eur > 0:
        return _metric(_fmt_eur(notional_eur), evidence_ref=evidence_ref, fields_de=("notional_eur",))
    if pkg_ready:
        return _metric("1", evidence_ref=evidence_ref, fields_de=("package_ready",))
    return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())


def pipeline_health_metric(health: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    errs = health.get("errors_de")
    if not isinstance(errs, list):
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    return _metric(str(len(errs)), evidence_ref=evidence_ref, fields_de=("errors_de",))


def pipeline_fees_metric(cost: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    if not cost:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    eur = _as_float(cost.get("base_round_trip_eur"))
    pct = _as_float(cost.get("base_round_trip_pct"))
    parts: List[str] = []
    if eur is not None:
        parts.append(f"{eur:.2f} €")
    if pct is not None:
        parts.append(f"{pct:.2f} %")
    return _metric(_join_parts(parts), evidence_ref=evidence_ref, fields_de=("base_round_trip_eur", "base_round_trip_pct"))


def pipeline_kreis_metric(score: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    green = score.get("green")
    total = score.get("total")
    if green is None or total is None:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    return _metric(f"{int(green)}/{int(total)}", evidence_ref=evidence_ref, fields_de=("green", "total"))


def pipeline_stack_metric(stack: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    checks = stack.get("checks")
    if isinstance(checks, list) and checks:
        ok_n = sum(1 for c in checks if isinstance(c, dict) and c.get("ok"))
        return _metric(f"{ok_n}/{len(checks)}", evidence_ref=evidence_ref, fields_de=("checks",))
    if stack.get("stack_ok") is True:
        return _metric("1", evidence_ref=evidence_ref, fields_de=("stack_ok",))
    if stack.get("stack_ok") is False:
        return _metric("0", evidence_ref=evidence_ref, fields_de=("stack_ok",))
    return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())


def pipeline_refresh_metric(rows: List[Dict[str, Any]], *, evidence_ref: str) -> Dict[str, Any]:
    if not rows:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    fails = sum(1 for r in rows if r.get("status") == "FAIL")
    warns = sum(1 for r in rows if r.get("status") == "WARN")
    return _metric(f"{fails} · {warns}", evidence_ref=evidence_ref, fields_de=("refresh_status.rows",))


def system_flow_metric(flow: Dict[str, Any], *, evidence_ref: str) -> Dict[str, Any]:
    pct = flow.get("fluidity_pct")
    if pct is None:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    return _metric(f"{int(pct)}%", evidence_ref=evidence_ref, fields_de=("fluidity_pct",))


def system_channels_metric(channels: List[Dict[str, Any]], *, evidence_ref: str) -> Dict[str, Any]:
    if not channels:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    ok_n = sum(1 for c in channels if c.get("ok"))
    return _metric(f"{ok_n}/{len(channels)}", evidence_ref=evidence_ref, fields_de=("channels",))


def system_quotes_metric(quote_count: Optional[int], *, evidence_ref: str, field: str) -> Dict[str, Any]:
    if quote_count is None:
        return _metric(MISSING, evidence_ref=evidence_ref, fields_de=())
    return _metric(str(int(quote_count)), evidence_ref=evidence_ref, fields_de=(field,))


def layer_from_metric(layer_id: str, label_de: str, metric: Dict[str, Any], *, ok: bool, partial: bool = False) -> Dict[str, Any]:
    return {
        "id": layer_id,
        "label_de": label_de,
        "ok": bool(ok),
        "partial": bool(partial) and not ok,
        "value_de": metric.get("display_de") or MISSING,
        "evidence_ref": metric.get("evidence_ref") or "",
        "fields_de": list(metric.get("fields_de") or []),
    }
