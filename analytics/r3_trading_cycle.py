"""In sich geschlossener Trading-Kreislauf — ein Einstieg, eine Evidence-Kette."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_trading_cycle_policy.json")
_EVIDENCE_REL = Path("evidence/r3_trading_cycle_latest.json")

def _plan_stage_ok(doc: Dict[str, Any]) -> bool:
    inv = float(doc.get("investable_eur") or doc.get("plan_capital_eur") or 0)
    if inv <= 0:
        return False
    live = doc.get("t212_live") or {}
    if not live and not doc.get("updated_at_utc"):
        return inv > 0
    allocs = doc.get("allocations") or []
    if allocs:
        return True
    pos_n = int(live.get("positions_count") or doc.get("t212_positions_count") or 0)
    if pos_n == 0:
        return bool(doc.get("plan_capital_eur") or inv)
    return bool(doc.get("rebalanced_to_t212")) or bool(doc.get("rebalance_mode_de"))


def _engine_stage_ok(doc: Dict[str, Any]) -> bool:
    if not bool(doc.get("ok")):
        return False
    reb = doc.get("rebalance") or {}
    if reb.get("skipped") and reb.get("stale_plan"):
        return False
    if reb.get("closed_loop") is False:
        return False
    return bool(doc.get("ok")) or bool((doc.get("r3_display") or {}).get("ok"))


_STAGE_SPECS: Tuple[Tuple[str, str, str, Callable[[Dict[str, Any]], bool]], ...] = (
    ("internet", "Internet", "evidence/r3_internet_latest.json", lambda d: bool(d.get("internet_ok"))),
    (
        "account",
        "Konto R3",
        "evidence/r3_t212_api_bond_latest.json",
        lambda d: bool(d.get("connected")) and d.get("cash_eur") is not None,
    ),
    (
        "ingest",
        "Kurse",
        "evidence/r3_browser_ingest_latest.json",
        lambda d: bool(d.get("internet_ok")) and bool(d.get("ok")),
    ),
    (
        "engine",
        "Modell",
        "evidence/alpha_model_background_engine_latest.json",
        _engine_stage_ok,
    ),
    (
        "plan",
        "Plan",
        "evidence/pilot_investment_plan_latest.json",
        _plan_stage_ok,
    ),
    (
        "display",
        "R3 Anzeige",
        "evidence/r3_t212_prognosis_latest.json",
        lambda d: bool(d.get("ok")) or int(d.get("positions") or 0) > 0,
    ),
    (
        "orders",
        "Orders R3",
        "control/r3_order_execution_policy.json",
        lambda d: str(d.get("status") or "") == "AUTHORITATIVE",
    ),
)


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


def load_trading_cycle_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def _stage_detail(stage_id: str, doc: Dict[str, Any]) -> str:
    if not doc:
        return "Evidence ausstehend"
    if stage_id == "internet":
        return str(doc.get("confirmation_de") or doc.get("message_de") or "—")[:120]
    if stage_id == "account":
        cash = doc.get("cash_eur")
        return f"T212 · {float(cash):.0f} €" if cash is not None else "Konto ausstehend"
    if stage_id == "ingest":
        return str(doc.get("price_latest") or doc.get("message_de") or "—")[:120]
    if stage_id == "engine":
        sig = (doc.get("predict") or {}).get("signal_date") or (doc.get("r3_display") or {}).get("signal_date")
        return f"Signal {sig or '—'}"
    if stage_id == "plan":
        inv = doc.get("plan_capital_eur") or doc.get("investable_eur")
        live = doc.get("t212_live") or {}
        pos_n = int(live.get("positions_count") or doc.get("t212_positions_count") or 0)
        n_alloc = len(doc.get("allocations") or [])
        sync = "live" if live else "—"
        return f"{n_alloc} Zeilen · {pos_n} Pos · {float(inv or 0):.0f} € · {sync}"
    if stage_id == "display":
        return str(doc.get("signal_date") or doc.get("message_de") or "—")[:120]
    if stage_id == "orders":
        return "Nur R3 — GUI-Bestätigung → T212"
    return "—"


def evaluate_trading_cycle(root: Path) -> Dict[str, Any]:
    """Read-only: alle Kreislauf-Stufen aus Evidence bewerten."""
    root = Path(root)
    policy = load_trading_cycle_policy(root)
    stages: List[Dict[str, Any]] = []
    from analytics.r3_evidence_metrics import trading_cycle_stage_metric

    for stage_id, label_de, rel, ok_fn in _STAGE_SPECS:
        doc = _load_json(root / rel)
        ok = bool(doc) and ok_fn(doc)
        metric = trading_cycle_stage_metric(stage_id, doc, evidence_ref=rel)
        stages.append(
            {
                "id": stage_id,
                "label_de": label_de,
                "ok": ok,
                "value_de": metric.get("display_de"),
                "detail_de": _stage_detail(stage_id, doc),
                "evidence_ref": rel,
                "fields_de": list(metric.get("fields_de") or []),
            }
        )
    ok_n = sum(1 for s in stages if s.get("ok"))
    total = len(stages)
    # Orders-Gate ist Architektur-OK wenn Policy da; Laufzeit-Kreislauf = erste 6 Stufen
    runtime_stages = [s for s in stages if s.get("id") != "orders"]
    runtime_ok = all(s.get("ok") for s in runtime_stages[:6])
    closed = runtime_ok and stages[-1].get("ok")
    pct = int(round(100 * ok_n / total)) if total else 0
    return {
        "schema_version": 1,
        "headline_de": str(policy.get("headline_de") or "Trading-Kreislauf"),
        "stages": stages,
        "stages_ok": ok_n,
        "stages_total": total,
        "cycle_pct": pct,
        "closed": closed,
        "runtime_closed": runtime_ok,
        "message_de": (
            f"Kreislauf geschlossen · {ok_n}/{total} Stufen"
            if closed
            else f"Kreislauf offen · {ok_n}/{total} Stufen"
        ),
        "confirmation_de": (
            "✓ Trading-Kreislauf geschlossen"
            if closed
            else f"Trading-Kreislauf · {pct}% — Hintergrund-Tick ausstehend"
        ),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }


def _run_cycle_steps(root: Path) -> Dict[str, Any]:
    """Prognose-first — ein Kanal, kein paralleler T212/Ingest-Hammer."""
    root = Path(root)
    results: Dict[str, Any] = {"ok": True, "steps": []}

    try:
        from analytics.r3_internet_requirement import probe_and_record_internet

        net = probe_and_record_internet(root, persist=True)
        results["steps"].append({"id": "internet", "ok": bool(net.get("internet_ok"))})
        if not net.get("internet_ok"):
            results["ok"] = False
            return results
    except Exception as exc:
        results["steps"].append({"id": "internet", "ok": False, "error": str(exc)[:80]})
        results["ok"] = False
        return results

    try:
        from analytics.r3_quote_keepalive import tick_quote_keepalive

        quotes = tick_quote_keepalive(root, force=False, owner="r3_cycle", persist=True)
        results["steps"].append(
            {
                "id": "quotes",
                "ok": bool(quotes.get("ok")),
                "skipped": bool(quotes.get("skipped")),
                "price_latest": quotes.get("price_latest"),
                "quote_status": (quotes.get("assess_after") or {}).get("quote_status"),
            }
        )
    except Exception as exc:
        results["steps"].append({"id": "quotes", "ok": False, "error": str(exc)[:80]})

    t212_force = False
    try:
        from analytics.r3_t212_api_bond import sync_r3_t212_api_bond

        bond = sync_r3_t212_api_bond(root, force=True, persist=True)
        results["steps"].append(
            {
                "id": "t212_sync",
                "ok": bool(bond.get("connected")) or bool(bond.get("bonded")),
                "cash_eur": bond.get("cash_eur"),
                "detail_de": str(bond.get("confirmation_de") or bond.get("message_de") or "")[:100],
            }
        )
        try:
            from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

            trust = assess_t212_trust_from_root(root, persist=True)
            t212_force = not bool(trust.get("trusted"))
            results["steps"].append(
                {
                    "id": "t212_trust",
                    "ok": bool(trust.get("trusted")),
                    "reason": trust.get("reason_code"),
                }
            )
        except Exception as exc:
            results["steps"].append({"id": "t212_trust", "ok": False, "error": str(exc)[:80]})
            t212_force = True
    except Exception as exc:
        results["steps"].append({"id": "t212_sync", "ok": False, "error": str(exc)[:80]})
        t212_force = True

    try:
        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

        prog = ensure_r3_prognosis_fresh(root, force=t212_force, persist=True)
        capital_step = next((s for s in (prog.get("steps") or []) if s.get("step") == "live_capital"), {})
        results["steps"].append(
            {
                "id": "prognosis",
                "ok": bool(prog.get("ok")),
                "trusted": prog.get("t212_trusted"),
                "buys": prog.get("worthwhile_buys"),
                "skipped": bool(prog.get("skipped")),
                "cash_eur": capital_step.get("investable_eur"),
                "positions_count": capital_step.get("positions"),
            }
        )
        if not prog.get("ok") and not prog.get("skipped"):
            results["ok"] = False
    except Exception as exc:
        results["steps"].append({"id": "prognosis", "ok": False, "error": str(exc)[:80]})
        results["ok"] = False

    try:
        from analytics.r3_trading_functions import build_r3_trading_functions

        fn = build_r3_trading_functions(root, persist=True)
        reb = next((f for f in (fn.get("functions") or []) if f.get("id") == "rebalance_notice"), {})
        results["steps"].append(
            {
                "id": "rebalance",
                "ok": True,
                "active": bool(reb.get("active")),
                "rebalance_due": reb.get("rebalance_due"),
                "functions_active": fn.get("functions_active"),
            }
        )
    except Exception as exc:
        results["steps"].append({"id": "rebalance", "ok": False, "error": str(exc)[:80]})

    try:
        from analytics.r3_daily_postmortem import run_daily_postmortem

        pm = run_daily_postmortem(root, persist=True)
        results["steps"].append(
            {
                "id": "postmortem",
                "ok": bool(pm.get("ok")),
                "bad_day": pm.get("bad_day"),
                "summary_de": str(pm.get("summary_de") or "")[:120],
                "voice_warning_de": pm.get("voice_warning_de"),
            }
        )
    except Exception as exc:
        results["steps"].append({"id": "postmortem", "ok": False, "error": str(exc)[:80]})

    try:
        from analytics.alpha_model_background_engine import tick_alpha_model_background

        eng = tick_alpha_model_background(root, force=False)
        results["steps"].append(
            {
                "id": "engine",
                "ok": bool(eng.get("ok")),
                "steps_ok": eng.get("steps_ok"),
                "signal_date": (eng.get("predict") or {}).get("signal_date"),
            }
        )
    except Exception as exc:
        results["steps"].append({"id": "engine", "ok": False, "error": str(exc)[:80]})

    return results


def run_trading_cycle(root: Path) -> Dict[str, Any]:
    """Ein Einstieg für den geschlossenen Trading-Kreislauf (ohne Order-Ausführung)."""
    root = Path(root)
    run_result = _run_cycle_steps(root)
    evaluation = evaluate_trading_cycle(root)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(run_result.get("ok")) and bool(evaluation.get("runtime_closed")),
        "run_ok": bool(run_result.get("ok")),
        "closed": bool(evaluation.get("closed")),
        "runtime_closed": bool(evaluation.get("runtime_closed")),
        "cycle_pct": evaluation.get("cycle_pct"),
        "stages": evaluation.get("stages") or [],
        "stages_ok": evaluation.get("stages_ok"),
        "stages_total": evaluation.get("stages_total"),
        "steps": run_result.get("steps") or [],
        "headline_de": evaluation.get("headline_de"),
        "message_de": evaluation.get("message_de"),
        "confirmation_de": evaluation.get("confirmation_de"),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "orders_de": "Schritt 7 nur über R3 mit GUI-Bestätigung",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_trading_cycle_status(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if doc:
        return doc
    return evaluate_trading_cycle(root)
