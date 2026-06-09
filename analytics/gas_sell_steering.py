"""Gas (Kaufen) + Sell — Modellsteuerung mit Gewinn-Hürde und Kurs-Halte-Checks."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/gas_sell_steering_policy.json")
_EVIDENCE_REL = Path("evidence/gas_sell_steering_latest.json")


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


def load_steering_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "require_prediction_ok": True,
            "require_fee_hurdle": True,
            "enforce_sell_before_gas": True,
            "gas_budget_buffer_pct": 2.0,
        }
    return doc


def steer_label(side: str, *, is_new: bool = False) -> str:
    side_u = str(side or "").upper()
    if side_u == "SELL":
        return "Sell"
    return "Gas" if is_new else "Gas+"


def _profit_gate(root: Path, row: Dict[str, Any], *, policy: Dict[str, Any]) -> Dict[str, Any]:
    if not policy.get("require_fee_hurdle", True):
        return {"ok": True, "profit_ok": True}
    notional = float(row.get("notional_eur") or 0)
    if notional <= 0:
        return {"ok": False, "profit_ok": False, "reason_de": "Notional ≤ 0"}
    limit = float(row.get("limit_price_eur") or 0)
    try:
        from analytics.pilot_integrated_refresh import estimate_cost_risk

        risk = estimate_cost_risk(root, notional_eur=notional, limit_price_eur=limit)
        if risk.get("trade_allowed"):
            return {
                "ok": True,
                "profit_ok": True,
                "hurdle_eur": risk.get("hurdle_eur"),
                "stress_pct": risk.get("stress_round_trip_pct"),
            }
        reason = risk.get("block_reason_stress") or risk.get("block_reason_base") or "Gebühren-Hürde"
        return {"ok": False, "profit_ok": False, "reason_de": str(reason)[:120]}
    except Exception as exc:
        return {"ok": True, "profit_ok": True, "reason_de": f"Gate-Skip: {exc}"[:80]}


def _gas_budget_cap(root: Path, gas_rows: List[Dict[str, Any]], *, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    fn_ctx = _load_json(root / "evidence/r3_trading_functions_latest.json").get("context") or {}
    investable = float(plan.get("investable_eur") or fn_ctx.get("investable_eur") or 0)
    if investable <= 0:
        return gas_rows
    buffer_pct = float(policy.get("gas_budget_buffer_pct") or 2.0)
    cap = investable * (1.0 - buffer_pct / 100.0)
    total = 0.0
    out: List[Dict[str, Any]] = []
    for row in sorted(gas_rows, key=lambda x: -float(x.get("priority_score") or 0)):
        n = float(row.get("notional_eur") or 0)
        if total + n <= cap + 0.01:
            out.append(row)
            total += n
        else:
            trimmed = dict(row)
            trimmed["sanctioned"] = False
            trimmed["clickable"] = False
            trimmed["profit_blocked"] = True
            trimmed["reason_de"] = f"Gas-Budget {cap:.0f} € erreicht — Rest später"
            out.append(trimmed)
    return out


def order_sell_then_gas(decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sell zuerst, dann Gas — Cash für profitable Rotation."""
    sells = sorted(
        [d for d in decisions if d.get("side") == "SELL"],
        key=lambda x: -float(x.get("priority_score") or 0),
    )
    gas = sorted(
        [d for d in decisions if d.get("side") == "BUY"],
        key=lambda x: -float(x.get("priority_score") or 0),
    )
    return sells + gas


def build_on_course_status(root: Path, decisions: List[Dict[str, Any]]) -> Dict[str, Any]:
    root = Path(root)
    policy = load_steering_policy(root)
    readiness = _load_json(root / "control/prediction_readiness.json")
    cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")

    prediction_ok = bool(readiness.get("ok"))
    blockers = list(readiness.get("blockers") or [])
    cycle_closed = bool(cycle.get("closed"))

    executable = [d for d in decisions if d.get("sanctioned") and d.get("clickable", True)]
    gas_n = sum(1 for d in executable if d.get("side") == "BUY")
    sell_n = sum(1 for d in executable if d.get("side") == "SELL")
    blocked = sum(1 for d in decisions if d.get("profit_blocked"))

    checks = {
        "prediction_ok": prediction_ok,
        "cycle_closed": cycle_closed,
        "has_executable": len(executable) > 0,
        "profit_gates_applied": True,
    }
    if policy.get("require_prediction_ok", True):
        checks["prediction_required"] = prediction_ok
    on_course = all(
        [
            not blockers or prediction_ok,
            cycle_closed or gas_n > 0 or sell_n > 0,
            len(executable) > 0 or blocked == 0,
        ]
    )
    headline = (
        f"✓ Auf Kurs — {gas_n} Gas · {sell_n} Sell"
        if on_course and executable
        else (
            f"Gas/Sell bereit — {gas_n} Kauf · {sell_n} Verkauf"
            if executable
            else "Warten — keine profitable Gas/Sell-Zeile"
        )
    )
    return {
        "on_course": on_course,
        "headline_de": headline,
        "gas_count": gas_n,
        "sell_count": sell_n,
        "blocked_profit": blocked,
        "blockers": blockers[:5],
        "checks": checks,
        "profit_target_de": (
            "Gewinn-Ziel: Top-Signale + Gebühren-Hürde + Sell-vor-Gas — kein Garantieversprechen"
        ),
    }


def apply_gas_sell_steering(root: Path, decisions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Unterste Steuerung: Gas/Sell-Labels, Gewinn-Hürde, Sell-vor-Gas, Budget-Deckel.
    """
    root = Path(root)
    policy = load_steering_policy(root)
    readiness = _load_json(root / "control/prediction_readiness.json")

    if policy.get("require_prediction_ok", True) and not readiness.get("ok"):
        blockers = ", ".join(readiness.get("blockers") or []) or "prediction_readiness"
        for row in decisions:
            row["sanctioned"] = False
            row["clickable"] = False
            row["steering_mode"] = steer_label(str(row.get("side") or ""))
            row["profit_blocked"] = True
            row["reason_de"] = f"Nicht auf Kurs — {blockers}"[:120]
        _persist_steering(root, decisions, on_course={"on_course": False, "headline_de": f"Blockiert: {blockers}"})
        return decisions

    steered: List[Dict[str, Any]] = []
    for row in decisions:
        item = dict(row)
        side = str(item.get("side") or "BUY").upper()
        is_new = bool(item.get("is_new_position"))
        item["steering_mode"] = steer_label(side, is_new=is_new)
        item["side_de"] = item["steering_mode"]

        gate = _profit_gate(root, item, policy=policy)
        if not gate.get("profit_ok"):
            item["sanctioned"] = False
            item["clickable"] = False
            item["profit_blocked"] = True
            item["reason_de"] = gate.get("reason_de") or "Gewinn-Hürde nicht erfüllt"
        else:
            item.setdefault("sanctioned", True)
            item.setdefault("clickable", True)
            item["profit_ok"] = True
        steered.append(item)

    sells = [r for r in steered if r.get("side") == "SELL" and r.get("sanctioned")]
    gas_raw = [r for r in steered if r.get("side") == "BUY" and r.get("sanctioned")]
    gas_capped = _gas_budget_cap(root, gas_raw, policy=policy)
    blocked_gas = [r for r in steered if r.get("side") == "BUY" and not r.get("sanctioned")]
    blocked_sell = [r for r in steered if r.get("side") == "SELL" and not r.get("sanctioned")]

    if policy.get("enforce_sell_before_gas", True):
        ordered = order_sell_then_gas(sells + gas_capped) + blocked_sell + blocked_gas
    else:
        ordered = steered

    on_course = build_on_course_status(root, ordered)
    _persist_steering(root, ordered, on_course=on_course)
    return ordered


def _persist_steering(
    root: Path,
    decisions: List[Dict[str, Any]],
    *,
    on_course: Dict[str, Any],
) -> None:
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "steering_de": load_steering_policy(root).get("steering_de"),
        "on_course": on_course.get("on_course"),
        "headline_de": on_course.get("headline_de"),
        "gas_count": on_course.get("gas_count"),
        "sell_count": on_course.get("sell_count"),
        "blocked_profit": on_course.get("blocked_profit"),
        "profit_target_de": on_course.get("profit_target_de"),
        "checks": on_course.get("checks"),
        "decisions_preview": [
            {
                "symbol": d.get("symbol"),
                "steering_mode": d.get("steering_mode"),
                "notional_eur": d.get("notional_eur"),
                "sanctioned": d.get("sanctioned"),
            }
            for d in decisions[:16]
        ],
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)


def load_gas_sell_steering(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
