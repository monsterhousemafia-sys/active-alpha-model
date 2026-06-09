"""Queue US equity orders for next regular session — portfolio snapshots + auto-release."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/us_equity_deferred_execution.json")
_QUEUE_REL = Path("live_pilot/confirmed_execution/us_equity_deferred_intents.json")
_STATE_REL = Path("live_pilot/confirmed_execution/us_equity_deferred_state.json")
_SNAPSHOT_REL = Path("live_pilot/confirmed_execution/us_equity_portfolio_snapshot.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_utc(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def default_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": True,
        "auto_capture_on_portfolio_change": True,
        "auto_execute_at_us_open": True,
        "user_armed_auto_open_execution": False,
        "execute_window_minutes_after_open": 45,
        "batch_execute_all_allocations": True,
        "max_pending_intents": 12,
        "max_auto_executions_per_us_day": 12,
    }


def load_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    return policy_section(Path(root), "deferred")


def save_policy(root: Path, policy: Dict[str, Any]) -> Path:
    from analytics.pilot_day_trading_policy import load_unified_policy, save_unified_policy

    unified = load_unified_policy(root)
    unified["deferred"] = {**(unified.get("deferred") or {}), **policy}
    return save_unified_policy(root, unified)


def set_user_armed_auto_open(root: Path, *, armed: bool) -> Dict[str, Any]:
    pol = load_policy(root)
    pol["user_armed_auto_open_execution"] = bool(armed)
    pol["armed_at_utc"] = _utc_now()
    save_policy(root, pol)
    return pol


def _queue_path(root: Path) -> Path:
    p = Path(root) / _QUEUE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_queue(root: Path) -> Dict[str, Any]:
    path = _queue_path(root)
    if not path.is_file():
        return {"schema_version": 1, "intents": []}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"schema_version": 1, "intents": []}
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "intents": []}


def _save_queue(root: Path, doc: Dict[str, Any]) -> None:
    atomic_write_json(_queue_path(root), doc)


def portfolio_fingerprint(plan: Dict[str, Any]) -> str:
    primary = plan.get("primary_action") or {}
    rows = plan.get("allocations") or []
    payload = {
        "champion_id": plan.get("champion_id"),
        "signal_date": plan.get("signal_date"),
        "primary": primary.get("symbol"),
        "top": [
            (r.get("symbol"), r.get("model_weight_pct"))
            for r in rows[:5]
            if r.get("symbol")
        ],
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _load_portfolio_snapshot(root: Path) -> Dict[str, Any]:
    path = Path(root) / _SNAPSHOT_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_portfolio_snapshot(root: Path, plan: Dict[str, Any], fp: str) -> None:
    path = Path(root) / _SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        path,
        {
            "fingerprint": fp,
            "signal_date": plan.get("signal_date"),
            "primary_symbol": (plan.get("primary_action") or {}).get("symbol"),
            "captured_at_utc": _utc_now(),
        },
    )


def _intent_still_pending(intent: Dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    if str(intent.get("status") or "") != "PENDING":
        return False
    exp = _parse_utc(intent.get("expires_at_utc"))
    if exp is not None and (now or datetime.now(timezone.utc)) > exp:
        return False
    return True


def list_stale_pending_intents(root: Path) -> List[Dict[str, Any]]:
    """PENDING rows past expires_at_utc — misleading queue depth."""
    now = datetime.now(timezone.utc)
    doc = _load_queue(root)
    return [
        i
        for i in doc.get("intents") or []
        if str(i.get("status") or "") == "PENDING"
        and not _intent_still_pending(i, now=now)
    ]


def prune_expired_intents(root: Path) -> int:
    """Mark expired PENDING intents as EXPIRED so UI counts stay honest."""
    doc = _load_queue(root)
    changed = 0
    now = _utc_now()
    for intent in doc.get("intents") or []:
        if str(intent.get("status") or "") != "PENDING":
            continue
        if _intent_still_pending(intent):
            continue
        intent["status"] = "EXPIRED"
        intent["updated_at_utc"] = now
        changed += 1
    if changed:
        doc["updated_at_utc"] = now
        _save_queue(root, doc)
    return changed


def list_pending_intents(root: Path) -> List[Dict[str, Any]]:
    prune_expired_intents(root)
    doc = _load_queue(root)
    return [i for i in doc.get("intents") or [] if _intent_still_pending(i)]


def load_deferred_summary(root: Path) -> Dict[str, Any]:
    pending = list_pending_intents(root)
    pol = load_policy(root)
    from integrations.trading212.t212_exchange_session import format_next_open_de, us_equity_regular_session_open_now

    sess = us_equity_regular_session_open_now()
    return {
        "pending_count": len(pending),
        "pending": pending,
        "policy": {
            "enabled": pol.get("enabled"),
            "auto_capture": pol.get("auto_capture_on_portfolio_change"),
            "auto_execute": pol.get("auto_execute_at_us_open"),
            "user_armed": pol.get("user_armed_auto_open_execution"),
        },
        "us_session_open": bool(sess.get("open")),
        "next_open_de": format_next_open_de(),
        "status_de": _summary_status_de(pending, pol, sess),
    }


def _summary_status_de(pending: List[Dict[str, Any]], pol: Dict[str, Any], sess: Dict[str, Any]) -> str:
    from integrations.trading212.t212_exchange_session import format_next_open_de

    if not pol.get("enabled"):
        return "US-Eröffnungs-Warteschlange aus"
    if sess.get("open"):
        if pending and pol.get("user_armed_auto_open_execution"):
            return f"US-Session offen — {len(pending)} Order(s) werden automatisch freigegeben"
        if pending:
            return f"US-Session offen — {len(pending)} vorgemerkt (Auto-Ausführung nicht aktiviert)"
        return "US-Session offen — keine vorgemerkten Orders"
    if pending:
        armed = "Auto bei Eröffnung AN" if pol.get("user_armed_auto_open_execution") else "Auto bei Eröffnung AUS"
        return (
            f"{len(pending)} US-Order(s) vorgemerkt — nächste Eröffnung {format_next_open_de()} ({armed})"
        )
    if pol.get("auto_capture_on_portfolio_change"):
        return f"Keine vorgemerkte Order — nächste US-Eröffnung {format_next_open_de()}"
    return "US-Warteschlange bereit"


def _session_execute_window() -> tuple[str, str]:
    from integrations.trading212.t212_exchange_session import (
        current_us_session_end_utc,
        next_us_regular_session_open_utc,
        us_equity_regular_session_open_now,
    )

    sess = us_equity_regular_session_open_now()
    if sess.get("open"):
        return _utc_now(), current_us_session_end_utc().isoformat()
    open_utc = next_us_regular_session_open_utc()
    return open_utc.isoformat(), (open_utc + timedelta(hours=7)).isoformat()


def allocations_for_batch(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Executable allocation rows from champion plan (all model picks with target > 0)."""
    rows = list(plan.get("allocations") or [])
    if not rows:
        primary = plan.get("primary_action") or {}
        if primary.get("symbol"):
            rows = [primary]
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        target = float(row.get("target_eur") or 0)
        if target < 10.0:
            continue
        out.append(row)
    return out


def _latest_fx_observation(root: Path) -> Dict[str, Any]:
    """Letzte FX-Beobachtung für Deferred-Planungspreise (kein Live-Submit)."""
    path = Path(root) / "paper/p16d/fx_observation_ledger/fx_observations.jsonl"
    if not path.is_file():
        return {}
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        if not lines:
            return {}
        doc = json.loads(lines[-1])
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def limit_price_for_symbol(
    root: Path,
    symbol: str,
    *,
    quote_snapshot: Dict[str, Any] | None = None,
    fallback_eur: float = 0.0,
) -> float:
    sym = str(symbol or "").upper()
    if quote_snapshot:
        from market.live_quote_engine import price_for_symbol
        from paper.p16d.quote_plausibility import sanitize_price_eur

        raw = price_for_symbol(quote_snapshot, sym)
        src = str((quote_snapshot.get("price_source_by_symbol") or {}).get(sym) or "YAHOO")
        lim, _, _ = sanitize_price_eur(
            sym, float(raw) if raw else None, source=src, for_orders=True
        )
        if lim and lim > 0:
            return float(lim)
    if fallback_eur and float(fallback_eur) > 0:
        return float(fallback_eur)
    return 0.0


def limit_price_for_deferred(
    root: Path,
    symbol: str,
    *,
    quote_snapshot: Dict[str, Any] | None = None,
    fallback_eur: float = 0.0,
) -> float:
    """Planungs-Limit für Vorbestellung — nutzt Live-Kurs, sonst Raw+FX, sonst Fallback."""
    live = limit_price_for_symbol(
        root,
        symbol,
        quote_snapshot=quote_snapshot,
        fallback_eur=0.0,
    )
    if live > 0:
        return live

    sym = str(symbol or "").upper()
    snap = quote_snapshot or {}
    entry = (snap.get("quotes_by_symbol") or {}).get(sym) or {}
    raw = entry.get("raw_price")
    if raw is not None:
        try:
            raw_f = float(raw)
        except (TypeError, ValueError):
            raw_f = 0.0
        if raw_f > 0:
            try:
                ccy = str(entry.get("quote_currency") or "USD").upper()
                eur = 0.0
                if ccy == "USD":
                    fx = _latest_fx_observation(root)
                    if fx.get("usd_to_eur_rate"):
                        from paper.p16b.fx_readonly_feed import convert_usd_to_eur

                        conv = convert_usd_to_eur(
                            raw_f,
                            {**fx, "fx_quality_gate": fx.get("usd_fx_quality_gate") or "PASS"},
                        )
                        eur = float(conv.get("converted_price_eur") or 0)
                else:
                    eur = float(entry.get("price_eur") or raw_f)
                if eur > 0:
                    from paper.p16d.quote_plausibility import sanitize_price_eur

                    lim, _, _ = sanitize_price_eur(
                        sym, eur, source="DEFERRED_PLANNING", for_orders=False
                    )
                    if lim and lim > 0:
                        return float(lim)
            except Exception:
                pass

    if fallback_eur and float(fallback_eur) > 0:
        return float(fallback_eur)
    return 0.0


_R3_DEFERRED_SOURCES = frozenset(
    {"R3_DESKTOP", "R3_ORDER_DESK", "R3_COCKPIT", "R3_COCKTOP"}
)


def list_pending_r3_intents(root: Path) -> List[Dict[str, Any]]:
    return [
        i
        for i in list_pending_intents(root)
        if str(i.get("source") or "") in _R3_DEFERRED_SOURCES
    ]


def cancel_pending_intents(root: Path, *, intent_ids: List[str]) -> int:
    """Atomarer Rollback — markiert PENDING-Intents als CANCELLED."""
    root = Path(root)
    want = {str(i) for i in intent_ids if i}
    if not want:
        return 0
    doc = _load_queue(root)
    intents: List[Dict[str, Any]] = list(doc.get("intents") or [])
    cancelled = 0
    now = _utc_now()
    for intent in intents:
        iid = str(intent.get("intent_id") or "")
        if intent.get("status") == "PENDING" and iid in want:
            intent["status"] = "CANCELLED"
            intent["cancelled_at_utc"] = now
            cancelled += 1
    if cancelled:
        doc["intents"] = intents
        doc["updated_at_utc"] = now
        _save_queue(root, doc)
    return cancelled


def r3_package_pending_status(root: Path, symbols: set[str]) -> Dict[str, Any]:
    """Abgleich Paket-Symbole ↔ R3-Vorbestellungen (exakte Menge)."""
    want = {str(s).upper() for s in symbols if s}
    pending = list_pending_r3_intents(root)
    pending_map = {str(i.get("instrument") or "").upper(): i for i in pending}
    have = want & set(pending_map)
    missing = want - have
    return {
        "want_count": len(want),
        "pending_count": len(have),
        "complete": bool(want) and not missing and len(have) == len(want),
        "missing_symbols": sorted(missing),
        "pending_symbols": sorted(have),
    }


def execute_pending_r3_deferred_intents(
    root: Path,
    *,
    symbols: Optional[set[str]] = None,
    require_live_submit: bool = True,
) -> Dict[str, Any]:
    """Ausstehende R3-Vorbestellungen bei Live-Kursen an T212 senden."""
    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(
        root,
        source="R3_DESKTOP",
        operation="deferred_execute",
    )
    if not gate.get("allowed"):
        return {
            "ok": False,
            "error": str(gate.get("error") or "R3_ORDER_SURFACE_REQUIRED"),
            "message_de": str(gate.get("message_de") or ""),
            "executed": 0,
            "results": [],
        }

    if require_live_submit:
        try:
            from analytics.r3_mirror_state import resolve_submission_mode

            if not resolve_submission_mode(root).get("live_submit"):
                return {
                    "ok": False,
                    "error": "LIVE_SUBMIT_BLOCKED",
                    "message_de": "Live-Submit gesperrt — Vorbestellung bleibt in der Warteschlange.",
                    "executed": 0,
                    "results": [],
                }
        except Exception:
            return {
                "ok": False,
                "error": "SUBMISSION_POLICY_CHECK_FAILED",
                "executed": 0,
                "results": [],
            }

    pending = list_pending_r3_intents(root)
    if symbols:
        want = {str(s).upper() for s in symbols}
        pending = [i for i in pending if str(i.get("instrument") or "").upper() in want]
    if not pending:
        return {"ok": False, "error": "NO_PENDING_R3_INTENTS", "executed": 0, "results": []}

    if symbols:
        want = {str(s).upper() for s in symbols}
        pkg = r3_package_pending_status(root, want)
        if not pkg.get("complete"):
            return {
                "ok": False,
                "error": "DEFERRED_PACKAGE_INCOMPLETE",
                "missing_symbols": pkg.get("missing_symbols") or [],
                "executed": 0,
                "results": [],
                "message_de": (
                    "Vorbestellung unvollständig — fehlend: "
                    + ", ".join(pkg.get("missing_symbols") or [])[:120]
                ),
            }

    results: List[Dict[str, Any]] = []
    executed = 0
    for intent in pending:
        sym = str(intent.get("instrument") or "")
        result = _execute_intent(root, intent)
        row = {"symbol": sym, **result}
        results.append(row)
        iid = str(intent.get("intent_id") or "")
        if result.get("ok"):
            executed += 1
            _mark_intent(
                root,
                iid,
                status="EXECUTED",
                executed_at_utc=_utc_now(),
                execution_result=result,
            )
        else:
            _mark_intent(
                root,
                iid,
                status="FAILED",
                failed_at_utc=_utc_now(),
                execution_error=str(result.get("error") or "")[:300],
            )

    return {
        "ok": executed == len(pending) and executed > 0,
        "partial": 0 < executed < len(pending),
        "executed": executed,
        "orders_total": len(pending),
        "orders_failed": len(pending) - executed,
        "results": results,
        "mode": "deferred_execute",
    }


def enqueue_intent_for_symbol(
    root: Path,
    *,
    plan: Dict[str, Any],
    symbol: str,
    target_notional_eur: float,
    limit_price_eur: float,
    source: str,
    t212_id: str | None = None,
    side: str = "BUY",
    sell_quantity: float | None = None,
) -> Dict[str, Any]:
    """Store one symbol intent for next US regular session (dedupe by symbol)."""
    root = Path(root)
    pol = load_policy(root)
    if not pol.get("enabled"):
        return {"ok": False, "error": "DEFERRED_QUEUE_DISABLED", "symbol": symbol}

    sym = str(symbol or "").upper()
    if not sym:
        return {"ok": False, "error": "NO_SYMBOL", "symbol": sym}

    notional = float(target_notional_eur or 0)
    if notional < 10.0:
        return {"ok": False, "error": "NOTIONAL_TOO_SMALL", "symbol": sym}

    if limit_price_eur <= 0:
        return {"ok": False, "error": "NO_LIMIT_PRICE", "symbol": sym}

    side_u = str(side or "BUY").upper()
    from integrations.trading212.t212_fee_economics import is_notional_worth_trading

    if side_u == "BUY":
        from analytics.live_trading_operations import load_policy as load_lt_pol

        relaxed = bool(load_lt_pol(root).get("relaxed_order_preflight", True))
        worth, fee_reason = is_notional_worth_trading(notional, root, price_eur=limit_price_eur)
        if not worth and not relaxed:
            return {
                "ok": False,
                "error": "FEE_HURDLE",
                "symbol": sym,
                "message_de": fee_reason,
            }

    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE

    tid = t212_id or str((MAPPING_TABLE.get(sym) or {}).get("provider_instrument_id") or f"{sym}_US_EQ")
    execute_not_before, expires = _session_execute_window()
    fp = portfolio_fingerprint(plan)
    intent = {
        "intent_id": str(uuid.uuid4()),
        "status": "PENDING",
        "source": source,
        "side": side_u,
        "instrument": sym,
        "t212_instrument_id": tid,
        "target_notional_eur": round(notional, 2),
        "limit_price_eur": round(float(limit_price_eur), 2),
        "sell_quantity": round(float(sell_quantity), 4) if sell_quantity is not None else None,
        "signal_date": plan.get("signal_date"),
        "champion_id": plan.get("champion_id"),
        "portfolio_fingerprint": fp,
        "created_at_utc": _utc_now(),
        "execute_not_before_utc": execute_not_before,
        "expires_at_utc": expires,
    }

    doc = _load_queue(root)
    intents: List[Dict[str, Any]] = list(doc.get("intents") or [])
    intents = [i for i in intents if not (i.get("status") == "PENDING" and i.get("instrument") == sym)]
    intents.append(intent)
    pending = [i for i in intents if i.get("status") == "PENDING"]
    max_p = int(pol.get("max_pending_intents") or 12)
    while len(pending) > max_p:
        oldest = min(pending, key=lambda x: x.get("created_at_utc") or "")
        intents = [i for i in intents if i.get("intent_id") != oldest.get("intent_id")]
        pending = [i for i in intents if i.get("status") == "PENDING"]
    doc["intents"] = intents
    doc["updated_at_utc"] = _utc_now()
    _save_queue(root, doc)
    return {"ok": True, "intent": intent, "symbol": sym, "message_de": f"{sym} ~{notional:.0f} € vorgemerkt"}


def enqueue_intent(
    root: Path,
    *,
    plan: Dict[str, Any],
    limit_price_eur: float,
    source: str,
    t212_id: str | None = None,
) -> Dict[str, Any]:
    """Store primary symbol intent (legacy single-symbol API)."""
    primary = plan.get("primary_action") or {}
    sym = str(primary.get("symbol") or "").upper()
    if not sym:
        return {"ok": False, "error": "NO_SYMBOL"}
    r = enqueue_intent_for_symbol(
        root,
        plan=plan,
        symbol=sym,
        target_notional_eur=float(primary.get("target_eur") or 0),
        limit_price_eur=limit_price_eur,
        source=source,
        t212_id=t212_id,
    )
    if not r.get("ok"):
        return r
    from integrations.trading212.t212_exchange_session import format_next_open_de

    pol = load_policy(root)
    msg = (
        f"US-Order vorgemerkt: {sym} ca. {float(primary.get('target_eur') or 0):.0f} € "
        f"(Limit {limit_price_eur:.2f} €).\n"
        f"Ausführung ab {format_next_open_de()} (US-Regular)."
    )
    msg += (
        "\nAusführung nur nach Bestätigung in der EXE "
        "(«Champion-Portfolio an T212 senden» oder Order-Dialog)."
    )
    r["message_de"] = msg
    return r


def enqueue_all_allocations_from_plan(
    root: Path,
    *,
    plan: Dict[str, Any],
    quote_snapshot: Dict[str, Any] | None = None,
    source: str = "BATCH_PLAN",
    primary_limit_price_eur: float = 0.0,
) -> Dict[str, Any]:
    """Queue every executable allocation row from the champion plan."""
    root = Path(root)
    pol = load_policy(root)
    if not pol.get("enabled"):
        return {"ok": False, "error": "DEFERRED_QUEUE_DISABLED", "results": []}

    rows = allocations_for_batch(plan)
    if not rows:
        return {"ok": False, "error": "NO_ALLOCATIONS", "results": []}

    results: List[Dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        lim = limit_price_for_deferred(
            root,
            sym,
            quote_snapshot=quote_snapshot,
            fallback_eur=primary_limit_price_eur if sym == str((plan.get("primary_action") or {}).get("symbol") or "").upper() else 0.0,
        )
        if lim <= 0:
            results.append({"ok": False, "symbol": sym, "error": "NO_LIMIT_PRICE"})
            continue
        results.append(
            enqueue_intent_for_symbol(
                root,
                plan=plan,
                symbol=sym,
                target_notional_eur=float(row.get("target_eur") or 0),
                limit_price_eur=lim,
                source=source,
            )
        )

    enqueued = [r for r in results if r.get("ok")]
    syms = [r.get("symbol") for r in enqueued if r.get("symbol")]
    from integrations.trading212.t212_exchange_session import format_next_open_de

    pol = load_policy(root)
    msg = (
        f"{len(enqueued)} US-Order(s) vorgemerkt: {', '.join(syms) or '—'}.\n"
        f"Ausführung ab {format_next_open_de()} (US-Regular)."
    )
    msg += (
        "\nAusführung nur nach Bestätigung in der EXE "
        "(«Champion-Portfolio an T212 senden»)."
    )
    skipped = [r for r in results if not r.get("ok")]
    if skipped:
        msg += "\nÜbersprungen: " + ", ".join(
            f"{r.get('symbol')} ({r.get('error')})" for r in skipped[:6]
        )
    return {
        "ok": bool(enqueued),
        "mode": "deferred_batch",
        "enqueued": len(enqueued),
        "skipped": len(skipped),
        "symbols": syms,
        "results": results,
        "message_de": msg,
    }


def capture_portfolio_change_intent(root: Path, plan: Dict[str, Any], *, limit_price_eur: float) -> Dict[str, Any]:
    """If champion portfolio fingerprint changed, queue primary symbol for next US open."""
    root = Path(root)
    pol = load_policy(root)
    if not pol.get("enabled") or not pol.get("auto_capture_on_portfolio_change"):
        return {"ok": False, "skipped": "AUTO_CAPTURE_OFF"}

    from analytics.champion_runtime_guard import verify_champion_runtime

    guard = verify_champion_runtime(root)
    if not guard.champion_ok or not guard.signals_ok:
        return {"ok": False, "skipped": "CHAMPION_OR_SIGNALS_NOT_OK"}

    fp = portfolio_fingerprint(plan)
    prev = _load_portfolio_snapshot(root)
    if prev.get("fingerprint") == fp:
        return {"ok": False, "skipped": "UNCHANGED"}

    _save_portfolio_snapshot(root, plan, fp)
    return enqueue_intent(
        root,
        plan=plan,
        limit_price_eur=limit_price_eur,
        source="MODEL_PORTFOLIO_CHANGE",
    )


def _load_exec_state(root: Path) -> Dict[str, Any]:
    path = Path(root) / _STATE_REL
    if not path.is_file():
        return {"executions_by_us_day": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {"executions_by_us_day": {}}
    except (json.JSONDecodeError, OSError):
        return {"executions_by_us_day": {}}


def _save_exec_state(root: Path, doc: Dict[str, Any]) -> None:
    atomic_write_json(Path(root) / _STATE_REL, doc)


def _us_day_key(now: Optional[datetime] = None) -> str:
    from zoneinfo import ZoneInfo

    ref = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return ref.date().isoformat()


def _can_auto_execute_today(root: Path, pol: Dict[str, Any]) -> bool:
    st = _load_exec_state(root)
    key = _us_day_key()
    n = int((st.get("executions_by_us_day") or {}).get(key) or 0)
    return n < int(pol.get("max_auto_executions_per_us_day") or 2)


def _record_auto_execution(root: Path) -> None:
    st = _load_exec_state(root)
    by_day = dict(st.get("executions_by_us_day") or {})
    key = _us_day_key()
    by_day[key] = int(by_day.get(key) or 0) + 1
    st["executions_by_us_day"] = by_day
    st["last_auto_execution_utc"] = _utc_now()
    _save_exec_state(root, st)


def _mark_intent(root: Path, intent_id: str, **fields: Any) -> None:
    doc = _load_queue(root)
    for item in doc.get("intents") or []:
        if item.get("intent_id") == intent_id:
            item.update(fields)
            item["updated_at_utc"] = _utc_now()
    doc["updated_at_utc"] = _utc_now()
    _save_queue(root, doc)


def _expire_stale_intents(root: Path) -> int:
    now = datetime.now(timezone.utc)
    doc = _load_queue(root)
    n = 0
    for item in doc.get("intents") or []:
        if item.get("status") != "PENDING":
            continue
        exp = _parse_utc(str(item.get("expires_at_utc") or ""))
        if exp is not None and now > exp:
            item["status"] = "EXPIRED"
            item["updated_at_utc"] = _utc_now()
            n += 1
    if n:
        _save_queue(root, doc)
    return n


def process_deferred_intents_if_due(root: Path) -> Dict[str, Any]:
    """
    At US open (within execution window): auto-submit armed pending intents.
    Call on startup and periodic UI refresh.
    """
    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(
        root,
        source="DEFERRED_INTENT",
        operation="auto_execute_at_us_open",
    )
    if not gate.get("allowed"):
        return {
            "processed": 0,
            "executed": 0,
            "expired": 0,
            "skipped": [str(gate.get("error") or "R3_ORDER_SURFACE_REQUIRED")],
            "message_de": str(gate.get("message_de") or ""),
            "mode": "r3_order_surface_required",
        }

    pol = load_policy(root)
    report: Dict[str, Any] = {
        "processed": 0,
        "executed": 0,
        "expired": _expire_stale_intents(root),
        "skipped": [],
    }
    if not pol.get("enabled"):
        report["skipped"].append("DISABLED")
        return report

    from integrations.trading212.t212_exchange_session import (
        is_within_us_open_execution_window,
        us_equity_regular_session_open_now,
    )

    sess = us_equity_regular_session_open_now()
    if not sess.get("open"):
        report["skipped"].append("US_SESSION_CLOSED")
        report["pending"] = len(list_pending_intents(root))
        return report

    if not pol.get("auto_execute_at_us_open") or not pol.get("user_armed_auto_open_execution"):
        report["skipped"].append("AUTO_EXECUTE_NOT_ARMED")
        report["pending"] = len(list_pending_intents(root))
        return report

    from execution.confirmed_live.gui_execution_confirmation import (
        has_active_execution_confirmation,
        manual_gui_confirm_enforced,
    )

    if manual_gui_confirm_enforced(root) and not has_active_execution_confirmation(root):
        report["skipped"].append("GUI_CONFIRMATION_REQUIRED")
        report["pending"] = len(list_pending_intents(root))
        report["message_de"] = (
            "Auto-Ausführung pausiert — echtes Geld erfordert Bestätigung in der EXE "
            "(«Champion-Portfolio an T212 senden»)."
        )
        return report

    from execution.confirmed_live.us_day_trading_coordinator import is_deferred_execution_allowed

    if not is_deferred_execution_allowed(root):
        report["skipped"].append("OUTSIDE_OPEN_WINDOW")
        report["pending"] = len(list_pending_intents(root))
        return report

    if not _can_auto_execute_today(root, pol):
        report["skipped"].append("DAILY_AUTO_LIMIT")
        return report

    pending = sorted(
        list_pending_intents(root),
        key=lambda x: str(x.get("execute_not_before_utc") or ""),
    )
    now = datetime.now(timezone.utc)
    for intent in pending:
        report["processed"] += 1
        not_before = _parse_utc(str(intent.get("execute_not_before_utc") or ""))
        if not_before is not None and now < not_before:
            report["skipped"].append(f"WAIT_{intent.get('instrument')}")
            continue

        result = _execute_intent(root, intent)
        if result.get("ok"):
            report["executed"] += 1
            _record_auto_execution(root)
            _mark_intent(
                root,
                str(intent["intent_id"]),
                status="EXECUTED",
                executed_at_utc=_utc_now(),
                execution_result=result,
            )
        else:
            _mark_intent(
                root,
                str(intent["intent_id"]),
                status="FAILED",
                failed_at_utc=_utc_now(),
                execution_error=str(result.get("error") or "")[:300],
            )
        if not _can_auto_execute_today(root, pol):
            report["skipped"].append("DAILY_AUTO_LIMIT")
            break

    report["pending"] = len(list_pending_intents(root))
    out = root / "evidence" / "us_equity_deferred_process_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def _execute_intent(root: Path, intent: Dict[str, Any]) -> Dict[str, Any]:
    from execution.confirmed_live.order_execution_style import resolve_order_execution_style
    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

    style = resolve_order_execution_style(root)
    sym = str(intent.get("instrument") or "").upper()
    side = str(intent.get("side") or "BUY").upper()
    cash = None
    try:
        broker = sync_readonly_account(root, force=True)
        cash = broker.cash_eur
    except Exception:
        pass
    if side == "SELL":
        from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_sell

        return submit_scaled_limit_sell(
            root,
            instrument=sym,
            t212_id=str(intent.get("t212_instrument_id") or ""),
            target_notional_eur=float(intent.get("target_notional_eur") or 0),
            limit_price_eur=float(intent.get("limit_price_eur") or 0),
            sell_quantity=float(intent.get("sell_quantity") or 0) or None,
            dry_run=False,
            execution_style=style,
            order_source=str(intent.get("source") or "DEFERRED_INTENT"),
        )
    from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy

    return submit_scaled_limit_buy(
        root,
        instrument=sym,
        t212_id=str(intent.get("t212_instrument_id") or ""),
        target_notional_eur=float(intent.get("target_notional_eur") or 0),
        limit_price_eur=float(intent.get("limit_price_eur") or 0),
        free_cash_eur=float(cash) if cash is not None else None,
        account_currency="EUR",
        dry_run=False,
        execution_style=style,
        order_source=str(intent.get("source") or "DEFERRED_INTENT"),
    )


def try_enqueue_or_execute_now(
    root: Path,
    *,
    plan: Dict[str, Any],
    limit_price_eur: float,
    free_cash_eur: float | None,
    quote_snapshot: Dict[str, Any] | None = None,
    champion_guard: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Live trading (Paper workflow): full rebalance wave; user click forces execution."""
    root = Path(root)
    from analytics.live_trading_operations import execute_live_rebalance, load_policy as load_lt_pol
    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    lt = load_lt_pol(root)
    if lt.get("enabled", True):
        ensure_live_trading_enabled(root, changed_by="user_order")
        return execute_live_rebalance(
            root,
            quote_snapshot=quote_snapshot,
            champion_guard=champion_guard,
            force=True,
            source="USER_CLICK",
        )

    pol = load_policy(root)
    if pol.get("batch_execute_all_allocations", True):
        return try_enqueue_or_execute_all_allocations(
            root,
            plan=plan,
            quote_snapshot=quote_snapshot,
            free_cash_eur=free_cash_eur,
            champion_guard=champion_guard,
            primary_limit_price_eur=limit_price_eur,
            source="USER_CLICK",
        )
    root = Path(root)
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    sess = us_equity_regular_session_open_now()
    if sess.get("open"):
        from integrations.trading212.t212_order_readiness import assess_order_readiness

        readiness = assess_order_readiness(root, free_cash_eur=free_cash_eur)
        if not readiness.ok:
            return {
                "ok": False,
                "mode": "live",
                "readiness": readiness.as_dict(),
                "message_de": readiness.status_de,
            }
        from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy
        from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE

        sym = str((plan.get("primary_action") or {}).get("symbol") or "").upper()
        meta = MAPPING_TABLE.get(sym) or {}
        from execution.confirmed_live.order_execution_style import resolve_order_execution_style

        sub = submit_scaled_limit_buy(
            root,
            instrument=sym,
            t212_id=str(meta.get("provider_instrument_id") or f"{sym}_US_EQ"),
            target_notional_eur=float((plan.get("primary_action") or {}).get("target_eur") or 0),
            limit_price_eur=limit_price_eur,
            free_cash_eur=free_cash_eur,
            account_currency="EUR",
            dry_run=False,
            execution_style=resolve_order_execution_style(root),
        )
        sub["mode"] = "live"
        return sub

    if not pol.get("enabled"):
        from integrations.trading212.t212_exchange_session import format_next_open_de

        return {
            "ok": False,
            "mode": "blocked",
            "message_de": (
                "US-Session geschlossen. Warteschlange ist deaktiviert.\n"
                f"Nächste Eröffnung: {format_next_open_de()}"
            ),
        }
    enq = enqueue_intent(root, plan=plan, limit_price_eur=limit_price_eur, source="USER_CLICK")
    enq["mode"] = "deferred"
    return enq


def try_enqueue_or_execute_all_allocations(
    root: Path,
    *,
    plan: Dict[str, Any],
    quote_snapshot: Dict[str, Any] | None = None,
    free_cash_eur: float | None = None,
    champion_guard: Dict[str, Any] | None = None,
    primary_limit_price_eur: float = 0.0,
    source: str = "USER_CLICK",
) -> Dict[str, Any]:
    """Execute or enqueue every allocation in the champion plan (active trading batch)."""
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now
    from integrations.trading212.t212_order_readiness import assess_order_readiness

    root = Path(root)
    rows = allocations_for_batch(plan)
    if not rows:
        return {"ok": False, "error": "NO_ALLOCATIONS", "message_de": "Keine ausführbaren Allokationen im Plan."}

    sess = us_equity_regular_session_open_now()
    if not sess.get("open"):
        return enqueue_all_allocations_from_plan(
            root,
            plan=plan,
            quote_snapshot=quote_snapshot,
            source=source,
            primary_limit_price_eur=primary_limit_price_eur,
        )

    readiness = assess_order_readiness(root, free_cash_eur=free_cash_eur)
    if not readiness.ok:
        return {
            "ok": False,
            "mode": "live_batch",
            "readiness": readiness.as_dict(),
            "message_de": readiness.status_de,
        }

    from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy
    from execution.confirmed_live.order_execution_style import (
        execution_style_label_de,
        resolve_order_execution_style,
    )
    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE
    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur

    style = resolve_order_execution_style(root)
    cash = float(free_cash_eur) if free_cash_eur is not None else None
    cash = resolve_planning_cash_eur(cash, broker={"cash_eur": cash}, root=root)
    from execution.confirmed_live.rebalance_wave_planner import plan_allocation_wave, wave_summary_de

    wave = plan_allocation_wave(rows, cash)
    rows = list(wave.get("allocations") or [])
    plan = {**plan, "rebalance_wave": {k: v for k, v in wave.items() if k != "allocations"}}
    results: List[Dict[str, Any]] = []
    executed = 0
    failed = 0

    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        notional = float(row.get("target_eur") or 0)
        lim = limit_price_for_symbol(root, sym, quote_snapshot=quote_snapshot)
        if lim <= 0:
            results.append({"ok": False, "symbol": sym, "error": "NO_LIMIT_PRICE"})
            failed += 1
            continue

        if champion_guard is not None:
            from analytics.pilot_live_trade_gate import build_live_order_preflight

            pf = build_live_order_preflight(
                root,
                symbol=sym,
                target_notional_eur=notional,
                broker={"cash_eur": cash},
                plan={**plan, "primary_action": row},
                champion_guard=champion_guard,
            )
            if not pf.get("ok"):
                results.append(
                    {
                        "ok": False,
                        "symbol": sym,
                        "error": "PREFLIGHT",
                        "blocks": pf.get("blocks"),
                    }
                )
                failed += 1
                continue

        meta = MAPPING_TABLE.get(sym) or {}
        sub = submit_scaled_limit_buy(
            root,
            instrument=sym,
            t212_id=str(meta.get("provider_instrument_id") or f"{sym}_US_EQ"),
            target_notional_eur=notional,
            limit_price_eur=lim,
            free_cash_eur=cash,
            account_currency="EUR",
            dry_run=False,
            execution_style=style,
            order_source=source,
        )
        sub["symbol"] = sym
        results.append(sub)
        if sub.get("ok") and sub.get("sent_to_t212", True):
            executed += 1
            try:
                broker = sync_readonly_account(root, force=True)
                if broker.cash_eur is not None:
                    cash = resolve_planning_cash_eur(
                        float(broker.cash_eur),
                        broker={"cash_eur": broker.cash_eur},
                        root=root,
                    )
            except Exception:
                pass
        else:
            failed += 1

    ok_any = executed > 0
    syms_ok = [r.get("symbol") for r in results if r.get("ok")]
    msg = (
        f"{executed} {execution_style_label_de(style)}(s) an T212 gesendet: "
        f"{', '.join(syms_ok) or '—'}."
    )
    if failed:
        msg += f" {failed} übersprungen/fehlgeschlagen."
    if wave.get("scale_factor", 1.0) < 0.999:
        msg += f" ({wave_summary_de(wave)})"
    return {
        "ok": ok_any,
        "mode": "live_batch",
        "executed": executed,
        "failed": failed,
        "results": results,
        "rebalance_wave": plan.get("rebalance_wave"),
        "user_message_de": msg,
        "message_de": msg,
    }


def enqueue_walkforward_rebalance_orders(
    root: Path,
    *,
    orders: List[Dict[str, Any]],
    plan: Dict[str, Any],
    quote_snapshot: Dict[str, Any] | None = None,
    source: str = "WALKFORWARD_REBALANCE",
) -> Dict[str, Any]:
    """Queue sells then buys for next US session."""
    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE

    results: List[Dict[str, Any]] = []
    for row in orders:
        sym = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "BUY").upper()
        lim = float(row.get("limit_price_eur") or 0)
        if lim <= 0:
            lim = limit_price_for_symbol(root, sym, quote_snapshot=quote_snapshot)
        if lim <= 0:
            results.append({"ok": False, "symbol": sym, "error": "NO_LIMIT_PRICE"})
            continue
        meta = MAPPING_TABLE.get(sym) or {}
        results.append(
            enqueue_intent_for_symbol(
                root,
                plan=plan,
                symbol=sym,
                target_notional_eur=float(row.get("notional_eur") or 0),
                limit_price_eur=lim,
                source=source,
                t212_id=str(meta.get("provider_instrument_id") or f"{sym}_US_EQ"),
                side=side,
                sell_quantity=float(row.get("held_quantity") or row.get("sell_quantity") or 0) or None,
            )
        )
    ok_n = sum(1 for r in results if r.get("ok"))
    return {
        "ok": ok_n > 0,
        "mode": "deferred_walkforward",
        "enqueued": ok_n,
        "results": results,
        "message_de": f"{ok_n} Walk-Forward-Order(s) vorgemerkt.",
    }


def try_execute_walkforward_rebalance_now(
    root: Path,
    *,
    orders: List[Dict[str, Any]],
    plan: Dict[str, Any],
    quote_snapshot: Dict[str, Any] | None = None,
    broker: Dict[str, Any] | None = None,
    champion_guard: Dict[str, Any] | None = None,
    source: str = "WALKFORWARD_REBALANCE",
) -> Dict[str, Any]:
    """Execute full rebalance wave (sells first) when US open, else defer."""
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now
    from integrations.trading212.t212_order_readiness import assess_order_readiness

    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(
        root,
        source=source,
        operation="walkforward_rebalance",
    )
    if not gate.get("allowed"):
        return {
            "ok": False,
            "mode": "r3_order_surface_required",
            "error": gate.get("error"),
            "message_de": str(gate.get("message_de") or ""),
            "sent_to_t212": False,
            "executed": 0,
        }
    from execution.confirmed_live.planning_cash import resolve_planning_cash_eur
    from execution.confirmed_live.rebalance_wave_planner import plan_rebalance_wave, wave_summary_de

    if not orders:
        return {"ok": False, "error": "NO_ORDERS", "message_de": "Keine Rebalance-Orders."}

    sess = us_equity_regular_session_open_now()
    if not sess.get("open"):
        cash_pre = resolve_planning_cash_eur(
            float(broker.get("cash_eur")) if broker and broker.get("cash_eur") is not None else None,
            broker=broker or {},
            root=root,
        )
        wave_pre = plan_rebalance_wave(orders, cash_pre)
        orders_scaled = list(wave_pre.get("orders") or orders)
        plan_scaled = {**plan, "rebalance_wave": {k: v for k, v in wave_pre.items() if k != "orders"}}
        enq = enqueue_walkforward_rebalance_orders(
            root,
            orders=orders_scaled,
            plan=plan_scaled,
            quote_snapshot=quote_snapshot,
            source=source,
        )
        enq["mode"] = "deferred_walkforward"
        enq["sent_to_t212"] = False
        enq["executed"] = 0
        enq["rebalance_wave"] = plan_scaled.get("rebalance_wave")
        from analytics.live_trading_operations import normalize_execution_result

        return normalize_execution_result(enq)

    cash = None
    if broker:
        try:
            cash = float(broker.get("cash_eur")) if broker.get("cash_eur") is not None else None
        except (TypeError, ValueError):
            cash = None
    cash = resolve_planning_cash_eur(cash, broker=broker or {}, root=root)

    wave = plan_rebalance_wave(orders, cash)
    orders = list(wave.get("orders") or [])
    plan = {**plan, "rebalance_wave": {k: v for k, v in wave.items() if k != "orders"}}
    readiness = assess_order_readiness(root, free_cash_eur=cash)
    if not readiness.ok:
        from integrations.trading212.t212_order_readiness import assess_deferred_enqueue_readiness

        defer_ready = assess_deferred_enqueue_readiness(root, free_cash_eur=cash)
        if defer_ready.ok or orders:
            enq = enqueue_walkforward_rebalance_orders(
                root, orders=orders, plan=plan, quote_snapshot=quote_snapshot, source=source
            )
            enq["mode"] = "deferred_walkforward"
            enq["readiness"] = readiness.as_dict()
            enq["fallback"] = "enqueue_after_readiness_block"
            hint = (
                f"{enq.get('message_de', '')}\n\n"
                "Sofort-Käufe blockiert (T212 «Insufficient funds»-Serie). "
                "Orders vorgemerkt für US-Eröffnung / manuelle Freigabe. "
                "Nach erfolgreichem Testkauf in der T212-App: «T212-Kaufblock zurücksetzen» im Dashboard."
            )
            enq["message_de"] = hint.strip()
            enq["sent_to_t212"] = False
            enq["executed"] = 0
            from analytics.live_trading_operations import normalize_execution_result

            return normalize_execution_result(enq)
        return {
            "ok": False,
            "mode": "live_walkforward",
            "readiness": readiness.as_dict(),
            "message_de": readiness.status_de,
            "sent_to_t212": False,
            "executed": 0,
        }

    from execution.confirmed_live.gui_execution_confirmation import (
        has_active_execution_confirmation,
        manual_gui_confirm_enforced,
    )

    if manual_gui_confirm_enforced(root) and not has_active_execution_confirmation(root):
        enq = enqueue_walkforward_rebalance_orders(
            root,
            orders=orders,
            plan=plan,
            quote_snapshot=quote_snapshot,
            source=source,
        )
        enq["mode"] = "deferred_walkforward"
        enq["sent_to_t212"] = False
        enq["executed"] = 0
        enq["fallback"] = "gui_confirmation_required"
        enq["message_de"] = (
            f"{enq.get('message_de', '')}\n\n"
            "Live-Ausführung blockiert ohne EXE-Bestätigung — "
            "«Champion-Portfolio an T212 senden» oder ② Rebalance nach Dialog."
        ).strip()
        from analytics.live_trading_operations import normalize_execution_result

        return normalize_execution_result(enq)

    from execution.confirmed_live.order_execution_style import (
        execution_style_label_de,
        resolve_order_execution_style,
    )
    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE
    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

    style = resolve_order_execution_style(root)
    guard = champion_guard or {}
    results: List[Dict[str, Any]] = []
    executed = 0
    for row in orders:
        sym = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "BUY").upper()
        notional = float(row.get("notional_eur") or 0)
        lim = float(row.get("limit_price_eur") or 0)
        if lim <= 0:
            lim = limit_price_for_symbol(root, sym, quote_snapshot=quote_snapshot)
        if lim <= 0:
            results.append({"ok": False, "symbol": sym, "error": "NO_LIMIT_PRICE"})
            continue
        if guard:
            from analytics.pilot_live_trade_gate import build_live_order_preflight

            pf = build_live_order_preflight(
                root,
                symbol=sym,
                target_notional_eur=notional,
                broker={"cash_eur": cash, **(broker or {})},
                plan={**plan, "primary_action": {**row, "symbol": sym, "target_eur": notional}},
                champion_guard=guard,
                limit_price_eur=lim,
            )
            if not pf.get("ok"):
                results.append(
                    {
                        "ok": False,
                        "symbol": sym,
                        "error": "PREFLIGHT",
                        "blocks": pf.get("blocks"),
                        "sent_to_t212": False,
                    }
                )
                continue
            lim = float(pf.get("limit_price_eur") or lim)
        meta = MAPPING_TABLE.get(sym) or {}
        tid = str(meta.get("provider_instrument_id") or f"{sym}_US_EQ")
        if side == "SELL":
            from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_sell

            sub = submit_scaled_limit_sell(
                root,
                instrument=sym,
                t212_id=tid,
                target_notional_eur=notional,
                limit_price_eur=lim,
                sell_quantity=float(row.get("held_quantity") or 0) or None,
                execution_style=style,
                order_source=source,
            )
        else:
            if cash is None:
                try:
                    broker_sync = sync_readonly_account(root, force=True)
                    cash = resolve_planning_cash_eur(
                        broker_sync.cash_eur,
                        broker=broker or {},
                        root=root,
                    )
                except Exception:
                    pass
            from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy

            sub = submit_scaled_limit_buy(
                root,
                instrument=sym,
                t212_id=tid,
                target_notional_eur=notional,
                limit_price_eur=lim,
                free_cash_eur=float(cash) if cash is not None else None,
                account_currency="EUR",
                dry_run=False,
                execution_style=style,
                order_source=source,
            )
            if sub.get("ok") and cash is not None:
                try:
                    broker_sync = sync_readonly_account(root, force=True)
                    cash = resolve_planning_cash_eur(
                        broker_sync.cash_eur,
                        broker=broker or {},
                        root=root,
                    )
                except Exception:
                    pass
        sub["symbol"] = sym
        if sub.get("ok") and not sub.get("sent_to_t212"):
            sub["sent_to_t212"] = True
        results.append(sub)
        if sub.get("ok") and sub.get("sent_to_t212"):
            executed += 1

    rebalance_completed = executed > 0
    if rebalance_completed:
        from analytics.live_trading_operations import note_rebalance_completed

        note_rebalance_completed(root)

    if executed == 0 and orders:
        enq = enqueue_walkforward_rebalance_orders(
            root, orders=orders, plan=plan, quote_snapshot=quote_snapshot, source=source
        )
        if enq.get("ok"):
            from analytics.live_trading_operations import note_rebalance_completed

            note_rebalance_completed(root)
            err0 = next((r for r in results if not r.get("ok")), {})
            snippet = str(err0.get("error") or err0.get("message_de") or "")[:120]
            enq["fallback"] = "enqueue_after_zero_executed"
            enq["executed"] = 0
            enq["results"] = results
            enq["rebalance_completed"] = True
            enq["message_de"] = (
                f"Keine Sofort-Order an T212 ({len(orders)} versucht). "
                f"{enq.get('message_de', '')}"
                + (f" Fehler z. B.: {snippet}" if snippet else "")
            )
            from analytics.live_trading_operations import normalize_execution_result

            return normalize_execution_result(enq)

    msg = (
        f"Live-Rebalance ({execution_style_label_de(style)}): "
        f"{executed}/{len(orders)} Order(s) an T212 gesendet."
    )
    if plan.get("rebalance_wave", {}).get("scale_factor", 1.0) < 0.999:
        msg += f" ({wave_summary_de(plan['rebalance_wave'])})"
    if executed == 0 and results:
        err0 = next((r for r in results if not r.get("ok")), {})
        snippet = str(err0.get("error") or err0.get("message_de") or "")[:160]
        if snippet:
            msg += f" ({snippet})"
    from analytics.execution_result_report import attach_execution_report
    from analytics.live_trading_operations import normalize_execution_result

    payload = attach_execution_report(
        {
            "ok": executed > 0,
            "mode": "live_rebalance",
            "executed": executed,
            "results": results,
            "rebalance_completed": rebalance_completed,
            "rebalance_wave": plan.get("rebalance_wave"),
            "sent_to_t212": executed > 0,
            "user_message_de": msg,
            "message_de": msg,
        },
        orders,
    )
    return normalize_execution_result(payload)
