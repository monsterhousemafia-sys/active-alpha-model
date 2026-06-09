"""König 32B — Trading-Beratung für Active Alpha Model (read-only, fail-closed)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/king_trading_assist_policy.json")
_EVIDENCE_REL = Path("evidence/king_trading_assist_latest.json")
_STATE_REL = Path("control/king_trading_assist_state.json")

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


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


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def load_king_trading_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {"enabled": True, "cooldown_min": 30, "timeout_s": 120, "temperature": 0.15}
    return doc


def _cooldown_ok(root: Path, *, minutes: int) -> bool:
    state = _load_json(root / _STATE_REL)
    stamp = _parse_utc(str(state.get("last_run_utc") or ""))
    if not stamp:
        return True
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - stamp).total_seconds() / 60.0
    return age >= float(minutes)


def _plan_fingerprint(plan: Dict[str, Any]) -> str:
    parts = [
        str(plan.get("updated_at_utc") or ""),
        str(plan.get("investable_eur") or ""),
        str(plan.get("pipeline_run_id") or ""),
        str(plan.get("signal_date") or ""),
    ]
    for row in plan.get("allocations") or []:
        if not isinstance(row, dict):
            continue
        parts.append(
            f"{row.get('symbol')}:{row.get('target_eur')}:{row.get('model_weight_pct')}:{row.get('side')}"
        )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _mark_run(root: Path, *, plan_fp: str = "", worthwhile_buy_count: int = 0) -> None:
    predict = _load_json(root / "control/prediction_readiness.json")
    atomic_write_json(
        root / _STATE_REL,
        {
            "last_run_utc": _utc_now(),
            "updated_at_utc": _utc_now(),
            "last_plan_fingerprint": plan_fp,
            "last_worthwhile_buy_count": worthwhile_buy_count,
            "last_signal_at_utc": predict.get("generated_at_utc"),
        },
    )


def _king_trigger_reason(root: Path, policy: Dict[str, Any], *, force: bool = False) -> Optional[str]:
    """Event-basiert: nur bei Plan-/Kauf-Änderung, Rebalance oder force."""
    if force:
        return "force"
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    state = _load_json(root / _STATE_REL)
    fp = _plan_fingerprint(plan)
    if fp and fp != str(state.get("last_plan_fingerprint") or ""):
        return "plan_changed"
    ww = _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
    buy_n = int(ww.get("worthwhile_buy_count") or 0)
    if buy_n != int(state.get("last_worthwhile_buy_count") or -1):
        return "worthwhile_changed"
    reeval = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
    if reeval.get("trade_required"):
        return "trade_required"
    try:
        from analytics.live_trading_operations import rebalance_status

        if rebalance_status(root).get("is_due"):
            return "rebalance_due"
    except Exception:
        pass
    predict = _load_json(root / "control/prediction_readiness.json")
    if str(predict.get("generated_at_utc") or "") != str(state.get("last_signal_at_utc") or ""):
        if predict.get("generated_at_utc"):
            return "signal_changed"
    return None


def build_trading_context(root: Path) -> Dict[str, Any]:
    """Kompakter Evidence-Snapshot für König-32B — keine Rohdaten-Flut."""
    root = Path(root)
    readiness = _load_json(root / "control/prediction_readiness.json")
    engine = _load_json(root / "evidence/alpha_model_background_engine_latest.json")
    cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")
    functions = _load_json(root / "evidence/r3_trading_functions_latest.json")
    reeval = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")

    stocks: List[Dict[str, Any]] = []
    groups: Dict[str, Any] = {}
    try:
        from analytics.r3_stock_orders import build_stock_groups

        groups = build_stock_groups(root)
        stocks = list(groups.get("all") or [])[:12]
    except Exception:
        pass

    fn_list = list(functions.get("functions") or [])
    active_fns = [f for f in fn_list if f.get("active")]
    primary_id = functions.get("primary_function_id")

    plan_allocations = [
        {
            "symbol": str(a.get("symbol") or "").upper(),
            "target_eur": float(a.get("target_eur") or 0),
            "model_weight_pct": a.get("model_weight_pct"),
            "side": str(a.get("side") or "BUY").upper(),
        }
        for a in (plan.get("allocations") or [])[:16]
        if str(a.get("symbol") or "").upper()
    ]

    return {
        "signal_date": readiness.get("signal_date"),
        "prediction_ok": bool(readiness.get("ok")),
        "blockers": list(readiness.get("blockers") or [])[:6],
        "investable_eur": plan.get("investable_eur") or functions.get("context", {}).get("investable_eur"),
        "positions_count": functions.get("context", {}).get("positions_count") or plan.get("positions"),
        "model_plan": {
            "role_de": "Erster Takt — autoritative R3/T212-Ausführung",
            "source_de": "evidence/pilot_investment_plan_latest.json",
            "investable_eur": plan.get("investable_eur"),
            "allocation_count": len(plan_allocations),
            "allocations": plan_allocations,
        },
        "primary_function": primary_id,
        "active_functions": [
            {
                "id": f.get("id"),
                "label_de": f.get("label_de"),
                "orders": f.get("order_count"),
                "eur": f.get("notional_eur"),
            }
            for f in active_fns
        ],
        "stock_summary": {
            "sells": [
                {"symbol": s.get("symbol"), "eur": s.get("notional_eur")}
                for s in (groups.get("sells") or [])[:8]
            ],
            "new_buys": [
                {"symbol": s.get("symbol"), "eur": s.get("notional_eur")}
                for s in (groups.get("new_buys") or [])[:8]
            ],
            "rebuy": [
                {"symbol": s.get("symbol"), "eur": s.get("notional_eur")}
                for s in (groups.get("rebuy") or [])[:6]
            ],
        },
        "top_actions": [
            {
                "symbol": a.get("symbol"),
                "action_code": a.get("action_code"),
                "gap_eur": a.get("gap_eur"),
                "priority_score": a.get("priority_score"),
            }
            for a in sorted(
                list(reeval.get("recommended_actions") or []),
                key=lambda x: -float(x.get("priority_score") or 0),
            )[:10]
        ],
        "engine_ok": bool(engine.get("ok")),
        "rebalance_due": bool((engine.get("rebalance") or {}).get("is_due")),
        "h1_status": (engine.get("h1_backtest") or {}).get("status"),
        "cycle_closed": bool(cycle.get("closed")),
        "cycle_stages_ok": cycle.get("stages_ok"),
        "order_surface_de": functions.get("order_surface_de"),
    }


def _parse_advice_json(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        doc = json.loads(raw)
        return doc if isinstance(doc, dict) else {}
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        try:
            doc = json.loads(match.group(0))
            return doc if isinstance(doc, dict) else {}
        except json.JSONDecodeError:
            pass
    return {
        "summary_de": raw[:500],
        "primary_action_de": "",
        "agrees_with_model": None,
    }


def _allowed_follow_on_symbols(root: Path) -> set[str]:
    allowed: set[str] = set()
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    for alloc in plan.get("allocations") or []:
        sym = str(alloc.get("symbol") or "").upper().strip()
        if sym:
            allowed.add(sym)
    reeval = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
    for action in reeval.get("recommended_actions") or []:
        sym = str(action.get("symbol") or "").upper().strip()
        if sym:
            allowed.add(sym)
    return allowed


def _normalize_follow_on_suggestions(
    root: Path,
    raw: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    allowed = _allowed_follow_on_symbols(root)
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw:
        sym = str(item.get("symbol") or "").upper().strip()
        if not sym or sym in seen or (allowed and sym not in allowed):
            continue
        worth = bool(item.get("worth_follow_on", item.get("sanctioned", True)))
        if not worth:
            continue
        hint = item.get("hint_eur", item.get("notional_eur"))
        try:
            hint_f = round(float(hint), 2) if hint is not None else None
        except (TypeError, ValueError):
            hint_f = None
        out.append(
            {
                "symbol": sym,
                "worth_follow_on": True,
                "reason_de": str(item.get("reason_de") or item.get("action_de") or "")[:160],
                "hint_eur": hint_f if hint_f and hint_f > 0 else None,
                "priority": float(item.get("priority_score") or item.get("priority") or 0),
            }
        )
        seen.add(sym)
    out.sort(key=lambda x: -float(x.get("priority") or 0))
    return out[:8]


def _legacy_trades_to_follow_on(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "symbol": str(t.get("symbol") or "").upper(),
            "worth_follow_on": bool(t.get("sanctioned", True)),
            "reason_de": str(t.get("reason_de") or "")[:160],
            "hint_eur": t.get("notional_eur"),
            "priority_score": t.get("priority_score"),
        }
        for t in trades
        if str(t.get("symbol") or "").upper()
    ]


def _system_prompt(policy: Dict[str, Any], root: Optional[Path] = None) -> str:
    forschung = ""
    if root is not None:
        try:
            from analytics.king_32b_forschung import forschung_context_for_prompt

            forschung = forschung_context_for_prompt(root) + "\n"
        except Exception:
            pass
    return (
        forschung
        + "Du bist König 32B (qwen2.5-coder:32b) — Berater für Active Alpha Model in R3.\n"
        "Du hast bereits alle Evidence-Daten im Kontext (model_plan, stock_summary, top_actions).\n"
        "Der Modell-Plan (pilot_investment_plan) gibt den ERSTEN TAKT vor — R3 führt ihn aus.\n"
        "Deine Aufgabe: NUR Vorschläge, wo sich WEITERFÜHRENDES Investieren (Nachkauf/Top-up) lohnt.\n"
        "Deine follow_on_suggestions werden im Hintergrund in den Modell-Plan eingerechnet;\n"
        "der Plan reagiert danach mit Umschichtung gegen das T212-Live-Depot.\n"
        "Regeln: Keine neuen Symbole. Keine Orders. Kein Champion-Wechsel. Ersten Takt nicht löschen.\n"
        "Nur Symbole aus model_plan.allocations oder top_actions.\n"
        "Antworte NUR als JSON:\n"
        '{"summary_de":"…","primary_action_de":"…","risks_de":["…"],'
        '"agrees_with_model":true,"focus_symbols":["SYM"],"operator_hint_de":"…",'
        '"follow_on_suggestions":[{"symbol":"STX","worth_follow_on":true,'
        '"reason_de":"…","hint_eur":25.0,"priority":9.0}]}'
    )


def run_king_trading_assist(root: Path, *, force: bool = False) -> Dict[str, Any]:
    """Ein König-32B-Tick — Beratung für Trading, optional im Engine-Tick."""
    root = Path(root)
    policy = load_king_trading_policy(root)
    if not policy.get("enabled", True):
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": True,
            "reason_de": "deaktiviert",
        }

    cd = int(policy.get("cooldown_min") or 60)
    trigger = _king_trigger_reason(root, policy, force=force)
    if not trigger:
        if not _cooldown_ok(root, minutes=cd):
            cached = _load_json(root / _EVIDENCE_REL)
            return {
                "step": "king_trading",
                "ok": True,
                "skipped": True,
                "reason_de": "cooldown_no_event",
                "advice_de": cached.get("summary_de"),
            }
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": True,
            "reason_de": "no_plan_change",
        }
    if not force and trigger != "force" and not _cooldown_ok(root, minutes=cd):
        cached = _load_json(root / _EVIDENCE_REL)
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": True,
            "reason_de": f"cooldown_after_{trigger}",
            "advice_de": cached.get("summary_de"),
        }

    from analytics.local_llm_bridge import load_llm_config, ollama_available

    cfg = load_llm_config(root)
    base = str(cfg.get("base_url") or "http://127.0.0.1:11434")
    from analytics.kernel_trade_decisions import write_king_advisory_evidence

    if not ollama_available(base, timeout_s=3.0):
        model = str((cfg.get("role_models") or {}).get("trading_local") or cfg.get("default_model"))
        headline = "Modell-Plan bleibt Ausführung — König 32B offline"
        prior = _load_json(root / _EVIDENCE_REL)
        prior_follow_on = [
            s
            for s in (prior.get("follow_on_suggestions") or [])
            if isinstance(s, dict)
        ]
        out = write_king_advisory_evidence(
            root,
            follow_on_suggestions=prior_follow_on,
            decision_mode="king_offline_advisory",
            patch={
                "schema_version": 2,
                "ok": True,
                "skipped": True,
                "reason_de": "Ollama offline — vorherige Follow-on-Vorschläge beibehalten",
                "model": model,
                "summary_de": headline,
                "headline_de": headline,
                "follow_on_preserved": bool(prior_follow_on),
            },
        )
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": True,
            "reason_de": out.get("reason_de"),
            "detail_de": out.get("headline_de"),
            "executable_count": 0,
            "follow_on_count": 0,
        }

    ctx = build_trading_context(root)
    try:
        from analytics.king_evidence_rag import build_evidence_rag

        rag = build_evidence_rag(root, persist=False)
        ctx["evidence_rag"] = json.loads(str(rag.get("rag_text") or "[]"))
    except Exception:
        pass
    ctx_text = json.dumps(ctx, ensure_ascii=False, indent=0)
    max_chars = int(policy.get("max_context_chars") or 6000)
    ctx_text = ctx_text[:max_chars]

    try:
        from analytics.r3_model_synergy import resolve_ollama_role
        from analytics.local_llm_bridge import chat_completion

        pick = resolve_ollama_role(root, "trading portfolio aktien rebalance signal", mode="trading")
        model = str(pick.get("model") or "")
        messages = [
            {"role": "system", "content": _system_prompt(policy, root)},
            {
                "role": "user",
                "content": (
                    "Evidence (Active Alpha hat bereits gerechnet — model_plan = erster Takt):\n"
                    f"{ctx_text}\n\n"
                    "Gib Follow-on-Vorschläge: Wo lohnt sich weiterführendes Investieren "
                    "(Nachkauf/Top-up) NACH dem Modell-Plan? Ersetze den Plan nicht."
                ),
            },
        ]
        content, _raw = chat_completion(
            root,
            messages,
            model=model or None,
            temperature=float(policy.get("temperature") or 0.15),
            timeout_s=float(policy.get("timeout_s") or 120),
            num_ctx=int(pick.get("num_ctx") or 8192),
        )
        advice = _parse_advice_json(content)
        raw_follow_on = list(advice.get("follow_on_suggestions") or [])
        if not raw_follow_on and advice.get("trade_decisions"):
            raw_follow_on = _legacy_trades_to_follow_on(list(advice["trade_decisions"]))
        follow_on = _normalize_follow_on_suggestions(root, raw_follow_on)
        plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
        ww = _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
        _mark_run(
            root,
            plan_fp=_plan_fingerprint(plan),
            worthwhile_buy_count=int(ww.get("worthwhile_buy_count") or 0),
        )
        doc = write_king_advisory_evidence(
            root,
            follow_on_suggestions=follow_on,
            decision_mode="king_32b_follow_on",
            patch={
                "schema_version": 2,
                "ok": True,
                "skipped": False,
                "model": model,
                "role_de": str(pick.get("role_de") or "trading_local"),
                "king_model_de": "König 32B — Follow-on-Beratung",
                "context_snapshot": ctx,
                "summary_de": str(advice.get("summary_de") or content[:400]),
                "primary_action_de": str(advice.get("primary_action_de") or ""),
                "risks_de": list(advice.get("risks_de") or [])[:5],
                "agrees_with_model": advice.get("agrees_with_model"),
                "focus_symbols": list(advice.get("focus_symbols") or [])[:8],
                "operator_hint_de": str(advice.get("operator_hint_de") or ""),
                "headline_de": str(advice.get("summary_de") or "König 32B — Follow-on-Vorschläge")[:120],
                "policy_ref": str(_POLICY_REL).replace("\\", "/"),
            },
        )
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": False,
            "trigger_de": trigger,
            "model": model,
            "agrees_with_model": doc.get("agrees_with_model"),
            "detail_de": doc.get("headline_de"),
            "follow_on_count": len(follow_on),
            "executable_count": 0,
        }
    except Exception as exc:
        err = str(exc)[:160]
        doc = write_king_advisory_evidence(
            root,
            follow_on_suggestions=[],
            decision_mode="king_error_advisory",
            patch={
                "schema_version": 2,
                "ok": False,
                "skipped": True,
                "reason_de": err,
                "headline_de": f"König-Fehler — Modell-Plan bleibt Ausführung ({err[:40]})",
            },
        )
        return {
            "step": "king_trading",
            "ok": True,
            "skipped": True,
            "reason_de": err,
            "detail_de": doc["headline_de"],
            "executable_count": 0,
        }


def load_king_trading_assist(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)
