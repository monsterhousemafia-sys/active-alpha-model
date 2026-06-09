"""Transparent DE breakdown for live rebalance / portfolio waves."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping


def _sym(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or "").upper()


def summarize_execution_breakdown(
    orders_planned: Iterable[Mapping[str, Any]],
    results: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Categorize per-symbol outcomes: executed, failed, skipped_no_price, skipped_preflight.
    """
    planned = list(orders_planned or [])
    res_list = list(results or [])
    n_planned = len(planned)

    executed: List[str] = []
    failed: List[str] = []
    skipped_no_price: List[str] = []
    skipped_preflight: List[str] = []
    skipped_other: List[str] = []

    by_sym: Dict[str, Dict[str, Any]] = {}
    for r in res_list:
        sym = _sym(r)
        if sym:
            by_sym[sym] = dict(r)

    for row in planned:
        sym = _sym(row)
        if not sym:
            continue
        r = by_sym.get(sym) or {}
        err = str(r.get("error") or "").upper()
        if r.get("ok") and r.get("sent_to_t212", r.get("ok")):
            executed.append(sym)
        elif err == "NO_LIMIT_PRICE":
            skipped_no_price.append(sym)
        elif err == "PREFLIGHT":
            skipped_preflight.append(sym)
        elif r.get("ok"):
            executed.append(sym)
        elif err:
            failed.append(sym)
        else:
            skipped_other.append(sym)

    n_exec = len(executed)
    parts = [f"{n_exec}/{n_planned} an T212 gesendet"]
    if skipped_no_price:
        parts.append(f"{len(skipped_no_price)} ohne Kurs ({', '.join(skipped_no_price)})")
    if skipped_preflight:
        parts.append(f"{len(skipped_preflight)} Preflight ({', '.join(skipped_preflight)})")
    if failed:
        parts.append(f"{len(failed)} fehlgeschlagen ({', '.join(failed)})")
    if skipped_other:
        parts.append(f"{len(skipped_other)} übersprungen")

    return {
        "orders_planned": n_planned,
        "executed": n_exec,
        "executed_symbols": executed,
        "failed": len(failed),
        "failed_symbols": failed,
        "skipped_no_price": len(skipped_no_price),
        "skipped_no_price_symbols": skipped_no_price,
        "skipped_preflight": len(skipped_preflight),
        "skipped_preflight_symbols": skipped_preflight,
        "skipped_other": len(skipped_other),
        "summary_de": " — ".join(parts),
    }


def attach_execution_report(exec_result: Dict[str, Any], orders_planned: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge breakdown into execution result dict."""
    out = dict(exec_result)
    breakdown = summarize_execution_breakdown(orders_planned, out.get("results") or [])
    out["execution_breakdown"] = breakdown
    out["executed"] = breakdown["executed"]
    out["failed"] = breakdown["failed"]
    out["skipped_no_price"] = breakdown["skipped_no_price"]
    out["skipped_preflight"] = breakdown["skipped_preflight"]
    base_msg = str(out.get("message_de") or "").strip()
    summary = breakdown["summary_de"]
    if summary and summary not in base_msg:
        out["message_de"] = f"{base_msg} | {summary}".strip(" |") if base_msg else summary
        out["user_message_de"] = out.get("user_message_de") or out["message_de"]
    return out
