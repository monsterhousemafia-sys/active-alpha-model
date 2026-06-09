"""Kernel — König 32B Beratung; Ausführung nur pilot_investment_plan (Modell-Plan)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_KING_EVIDENCE = Path("evidence/king_trading_assist_latest.json")


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


def _quant_rows(root: Path) -> List[Dict[str, Any]]:
    from analytics.r3_stock_orders import _build_plan_stock_actions, _build_quant_stock_actions

    plan_rows = list(_build_plan_stock_actions(root))
    if plan_rows:
        return plan_rows
    return list(_build_quant_stock_actions(root))


def _row_key(row: Dict[str, Any]) -> Tuple[str, str]:
    return (str(row.get("symbol") or "").upper(), str(row.get("side") or "BUY").upper())


def pass_through_decisions(
    quant_rows: List[Dict[str, Any]],
    *,
    source: str = "quant_pass_through",
    reason_de: str = "",
) -> List[Dict[str, Any]]:
    """Quant-Optimum direkt ausführbar — reibungslos wenn König offline."""
    out: List[Dict[str, Any]] = []
    for row in quant_rows:
        sym, side = _row_key(row)
        if not sym:
            continue
        out.append(
            {
                "symbol": sym,
                "side": side,
                "side_de": row.get("side_de"),
                "notional_eur": float(row.get("notional_eur") or 0),
                "is_new_position": bool(row.get("is_new_position")),
                "action_code": row.get("action_code"),
                "action_de": row.get("action_de"),
                "priority_score": row.get("priority_score"),
                "limit_price_eur": row.get("limit_price_eur"),
                "sanctioned": True,
                "decision_source": source,
                "reason_de": reason_de or str(row.get("action_de") or "")[:120],
                "clickable": True,
            }
        )
    return out


def merge_king_decisions(
    quant_rows: List[Dict[str, Any]],
    king_rows: List[Dict[str, Any]],
    *,
    agrees_with_model: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """König 32B bestätigt/filtert — nur bekannte Quant-Zeilen, kein neues Symbol."""
    quant_map = {_row_key(r): r for r in quant_rows}
    king_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for kr in king_rows:
        key = _row_key(kr)
        if key[0] and key in quant_map:
            king_map[key] = kr

    default_sanction = agrees_with_model is not False
    out: List[Dict[str, Any]] = []
    king_active = bool(king_rows)
    for key, row in quant_map.items():
        sym, side = key
        kd = king_map.get(key)
        if king_active:
            if kd is None:
                continue
            sanctioned = bool(kd.get("sanctioned", default_sanction))
            reason = str(kd.get("reason_de") or row.get("action_de") or "")[:120]
            source = "king_32b"
        else:
            sanctioned = True
            reason = str(row.get("action_de") or "")[:120]
            source = "quant_pass_through"
        if not sanctioned:
            continue
        out.append(
            {
                "symbol": sym,
                "side": side,
                "side_de": row.get("side_de"),
                "notional_eur": float(row.get("notional_eur") or 0),
                "is_new_position": bool(row.get("is_new_position")),
                "action_code": row.get("action_code"),
                "action_de": row.get("action_de"),
                "priority_score": row.get("priority_score"),
                "limit_price_eur": row.get("limit_price_eur"),
                "sanctioned": True,
                "decision_source": source,
                "reason_de": reason,
                "clickable": True,
            }
        )
    return out


def _plan_buy_counts(root: Path) -> Tuple[int, int]:
    """(plan_buy_lines, executable_buy_lines) — aligned with freigabe / r3_stock_orders."""
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    buys = [
        a
        for a in (plan.get("allocations") or [])
        if str(a.get("side") or "").upper() == "BUY"
    ]
    executable = [a for a in buys if float(a.get("target_eur") or 0) > 0]
    return len(buys), len(executable)


def write_king_advisory_evidence(
    root: Path,
    *,
    follow_on_suggestions: List[Dict[str, Any]],
    decision_mode: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """König 32B — nur Follow-on-Vorschläge; keine ausführbaren trade_decisions."""
    root = Path(root)
    plan_buys, plan_executable = _plan_buy_counts(root)
    doc = _load_json(root / _KING_EVIDENCE)
    doc.setdefault("schema_version", 2)
    doc["updated_at_utc"] = _utc_now()
    doc["advisory_only"] = True
    doc["execution_source_de"] = "pilot_investment_plan"
    doc["decision_layer_de"] = "Modell-Plan (1. Takt) → R3 · König 32B nur Follow-on"
    doc["trade_decisions"] = []
    doc["follow_on_suggestions"] = list(follow_on_suggestions)
    doc["decision_mode"] = decision_mode
    doc["executable_count"] = plan_executable
    doc["buy_count"] = plan_buys
    doc["plan_buy_count"] = plan_buys
    doc["plan_executable_buy_count"] = plan_executable
    doc["sell_count"] = 0
    doc["follow_on_count"] = len(follow_on_suggestions)
    if patch:
        doc.update(patch)
    # Plan-Zähler bleiben autoritativ — Patch darf buy_count nicht auf Kernel-Fallback setzen.
    doc["advisory_only"] = True
    doc["buy_count"] = plan_buys
    doc["plan_buy_count"] = plan_buys
    doc["plan_executable_buy_count"] = plan_executable
    doc["executable_count"] = plan_executable
    atomic_write_json(root / _KING_EVIDENCE, doc)
    return doc


def write_trade_decisions_to_king_evidence(
    root: Path,
    decisions: List[Dict[str, Any]],
    *,
    decision_mode: str,
    patch: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    if patch and patch.get("advisory_only"):
        return write_king_advisory_evidence(
            root,
            follow_on_suggestions=list(patch.get("follow_on_suggestions") or []),
            decision_mode=decision_mode,
            patch=patch,
        )
    try:
        from analytics.gas_sell_steering import apply_gas_sell_steering

        decisions = apply_gas_sell_steering(root, list(decisions))
    except Exception:
        pass
    doc = _load_json(root / _KING_EVIDENCE)
    doc.setdefault("schema_version", 2)
    doc["updated_at_utc"] = _utc_now()
    doc["trade_decisions"] = decisions
    doc["decision_mode"] = decision_mode
    doc["executable_count"] = len(decisions)
    doc["buy_count"] = sum(1 for d in decisions if d.get("side") == "BUY")
    doc["sell_count"] = sum(1 for d in decisions if d.get("side") == "SELL")
    if patch:
        doc.update(patch)
    atomic_write_json(root / _KING_EVIDENCE, doc)
    return doc


def ensure_kernel_trade_decisions(root: Path) -> Dict[str, Any]:
    """König-Evidence vorhanden halten — Ausführung bleibt Modell-Plan, König nur Beratung."""
    root = Path(root)
    doc = _load_json(root / _KING_EVIDENCE)
    if doc.get("follow_on_suggestions") is not None or doc.get("advisory_only"):
        return doc
    if doc.get("trade_decisions"):
        plan = _load_json(root / Path("evidence/pilot_investment_plan_latest.json"))
        plan_syms = {
            str(a.get("symbol") or "").upper()
            for a in (plan.get("allocations") or [])
            if a.get("symbol")
        }
        follow_on = [
            {
                "symbol": sym,
                "worth_follow_on": bool(d.get("sanctioned", True)),
                "reason_de": str(d.get("reason_de") or "")[:120],
                "hint_eur": float(d.get("notional_eur") or 0) or None,
            }
            for d in doc["trade_decisions"]
            if (sym := str(d.get("symbol") or "").upper())
            and (not plan_syms or sym in plan_syms)
        ]
        return write_king_advisory_evidence(
            root,
            follow_on_suggestions=follow_on,
            decision_mode="legacy_trade_to_advisory",
            patch={
                "ok": True,
                "skipped": True,
                "summary_de": "Legacy trade_decisions → Follow-on-Vorschläge migriert",
            },
        )

    from analytics.r3_stock_orders import _build_plan_stock_actions

    if _build_plan_stock_actions(root):
        summary = "Modell-Plan ist Ausführung — König 32B liefert Follow-on-Vorschläge"
        return write_king_advisory_evidence(
            root,
            follow_on_suggestions=[],
            decision_mode="plan_execution_advisory_pending",
            patch={
                "ok": True,
                "skipped": True,
                "summary_de": summary,
                "headline_de": summary[:120],
            },
        )

    quant = _quant_rows(root)
    decisions = pass_through_decisions(quant)
    summary = f"Kernel — {len(decisions)} Zeilen (kein Modell-Plan, Quant-Fallback)"
    return write_trade_decisions_to_king_evidence(
        root,
        decisions,
        decision_mode="quant_bootstrap",
        patch={
            "ok": True,
            "skipped": True,
            "summary_de": summary,
            "headline_de": summary[:120],
            "advisory_only": False,
            "decision_layer_de": "Quant-Fallback (kein Plan)",
        },
    )


def resolve_executable_trade_decisions(root: Path) -> List[Dict[str, Any]]:
    """Ausführung — nur Modell-Plan (König filtert nicht)."""
    from analytics.r3_stock_orders import _build_plan_stock_actions

    plan_rows = _build_plan_stock_actions(root)
    if plan_rows:
        return plan_rows
    return pass_through_decisions(_quant_rows(root))


def sync_kernel_trade_decisions(root: Path, *, force_king: bool = False) -> Dict[str, Any]:
    """Kernel-Sync: Quant → König 32B (wenn online) → trade_decisions Evidence."""
    root = Path(root)
    quant = _quant_rows(root)

    try:
        from analytics.king_trading_assist import run_king_trading_assist

        out = run_king_trading_assist(root, force=force_king)
    except Exception as exc:
        doc = write_king_advisory_evidence(
            root,
            follow_on_suggestions=[],
            decision_mode="king_error_advisory",
            patch={
                "ok": False,
                "reason_de": str(exc)[:120],
                "headline_de": "König-Fehler — Modell-Plan bleibt Ausführung",
            },
        )
        return {"ok": True, "decision_mode": doc.get("decision_mode"), "executable_count": 0}

    doc = _load_json(root / _KING_EVIDENCE)
    if not doc.get("follow_on_suggestions") and not doc.get("trade_decisions"):
        write_king_advisory_evidence(
            root,
            follow_on_suggestions=[],
            decision_mode="king_skip_advisory",
            patch={"headline_de": "Modell-Plan bleibt Ausführung — keine Follow-on-Vorschläge"},
        )
    return {
        "ok": True,
        "king_skipped": out.get("skipped"),
        "decision_mode": doc.get("decision_mode"),
        "executable_count": doc.get("executable_count") or len(doc.get("trade_decisions") or []),
        "detail_de": out.get("detail_de"),
    }
