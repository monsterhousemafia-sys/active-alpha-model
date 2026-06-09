"""Pre-session warnings — surface blockers before a bad trading day repeats."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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


def _add(
    out: List[Dict[str, Any]],
    *,
    code: str,
    severity: str,
    title_de: str,
    detail_de: str,
    action_de: str = "",
) -> None:
    out.append(
        {
            "code": code,
            "severity": severity,
            "title_de": title_de,
            "detail_de": detail_de,
            "action_de": action_de,
        }
    )


def _load_authorization(root: Path) -> Dict[str, Any]:
    path = root / "control/authorization/current_authorization_status.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _load_adaptive_runtime(root: Path) -> Dict[str, Any]:
    path = root / "control/adaptive_runtime_state.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def infrastructure_open_points(root: Path) -> List[Dict[str, Any]]:
    """Static setup gaps independent of today's market snapshot."""
    points: List[Dict[str, Any]] = []
    from aa_paths import venv_python_ok

    if not venv_python_ok(root):
        points.append(
            {
                "id": "venv_pip",
                "severity": "critical",
                "detail_de": ".venv fehlt oder pip defekt — bash tools/setup_linux_native.sh",
            }
        )
    if not (root / ".env").is_file():
        points.append(
            {
                "id": "env_file",
                "severity": "warn",
                "detail_de": ".env fehlt — T212-Keys ggf. nicht geladen",
            }
        )
    ready_path = root / "evidence/ai_kernel_ready_latest.json"
    if ready_path.is_file():
        try:
            ready = json.loads(ready_path.read_text(encoding="utf-8"))
            for b in ready.get("blockers") or []:
                points.append(
                    {
                        "id": f"ready_{b}",
                        "severity": "critical" if b in ("venv", "tests", "snapshot") else "warn",
                        "detail_de": f"ai_kernel ready: Blocker «{b}»",
                    }
                )
        except (json.JSONDecodeError, OSError):
            pass
    return points


def collect_trading_day_warnings(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build warning list from dashboard snapshot + account/policy state."""
    root = Path(root)
    warnings: List[Dict[str, Any]] = []

    try:
        from aa_adaptive_runtime import refresh_price_feed_state

        refresh_price_feed_state(root, write=True)
    except Exception:
        pass

    broker = (snap or {}).get("broker") or {}
    reeval = (snap or {}).get("reevaluation") or {}
    status = (snap or {}).get("rebalance_status") or {}
    deferred = (snap or {}).get("deferred") or {}
    guard = (snap or {}).get("guard") or (snap or {}).get("champion_guard") or {}
    if not guard:
        try:
            from analytics.champion_runtime_guard import verify_champion_runtime

            guard = verify_champion_runtime(root).as_dict()
        except Exception:
            guard = {}
    quote_gate = (snap or {}).get("quote_coverage") or {}
    readiness = (snap or {}).get("trading_readiness") or {}
    n_positions = int((snap or {}).get("n_positions") or 0)

    # --- Quotes ---
    urgency = str(reeval.get("urgency") or "")
    if urgency == "STALE_QUOTES":
        _add(
            warnings,
            code="STALE_QUOTES",
            severity="critical",
            title_de="Live-Kurse unvollständig",
            detail_de=str(reeval.get("quote_reason") or reeval.get("summary_de") or "STALE_QUOTES"),
            action_de="«Aktualisieren» — alle Champion-Symbole brauchen Kurse vor Rebalance",
        )
    elif quote_gate and not quote_gate.get("ok"):
        cov = quote_gate.get("coverage_ratio")
        _add(
            warnings,
            code="PARTIAL_QUOTE_COVERAGE",
            severity="critical",
            title_de="Kurs-Abdeckung zu niedrig",
            detail_de=str(quote_gate.get("quote_coverage_label_de") or f"Abdeckung {cov}"),
            action_de="Internet prüfen, dann «Aktualisieren»",
        )

    # --- Cash vs model ---
    exposure = reeval.get("exposure_check") or {}
    cash_weight = float(exposure.get("cash_weight_pct") or 0)
    if exposure.get("under_invested") and cash_weight >= 85.0:
        gap = float(exposure.get("exposure_gap_pct") or 0)
        _add(
            warnings,
            code="UNDER_INVESTED_CASH",
            severity="critical",
            title_de="Fast alles Cash — Modell will investiert sein",
            detail_de=f"Cash {cash_weight:.0f} % · Exposure-Lücke {gap:.0f} % · Regime {reeval.get('regime', '—')}",
            action_de="Rebalance ② oder Champion-Portfolio senden — nicht manuell in iOS stückeln",
        )

    # --- Rebalance due but flat ---
    if status.get("is_due") and n_positions == 0 and float(broker.get("cash_eur") or 0) > 50:
        _add(
            warnings,
            code="REBALANCE_DUE_NO_POSITIONS",
            severity="critical",
            title_de="Rebalance fällig — Depot leer",
            detail_de=str(status.get("summary_de") or "REBALANCE_DUE"),
            action_de="Schritt ② Rebalance — sonst verpasst du den Handelstag",
        )

    # --- Broker API buy gate ---
    try:
        from integrations.trading212.t212_order_readiness import (
            assess_order_readiness,
            broker_stock_buy_likely_blocked,
        )

        if broker_stock_buy_likely_blocked(root):
            _add(
                warnings,
                code="BROKER_STOCK_BUY_BLOCKED",
                severity="critical",
                title_de="T212 blockiert API-Aktienkäufe",
                detail_de="Mehrere Käufe von T212 abgelehnt (Insufficient/Blocked-Streak)",
                action_de="Einmal INTC in T212-App testen → «T212-Kaufblock zurücksetzen»",
            )
        else:
            rd = assess_order_readiness(root, cash_eur=broker.get("cash_eur"))
            for b in rd.blockers or []:
                if b == "BROKER_STOCK_BUY_BLOCKED_STREAK":
                    _add(
                        warnings,
                        code="BROKER_STOCK_BUY_BLOCKED",
                        severity="critical",
                        title_de="T212 blockiert API-Aktienkäufe",
                        detail_de=rd.status_de[:300],
                        action_de="Testkauf in T212-App, dann Kaufblock zurücksetzen",
                    )
    except Exception:
        pass

    # --- Expired / stale deferred queue ---
    try:
        from execution.confirmed_live.us_equity_deferred_intents import (
            list_pending_intents,
            list_stale_pending_intents,
            prune_expired_intents,
        )

        stale = list_stale_pending_intents(root)
        if stale:
            prune_expired_intents(root)
            _add(
                warnings,
                code="EXPIRED_DEFERRED_QUEUE",
                severity="warn",
                title_de="Abgelaufene US-Orders in Warteschlange",
                detail_de=f"{len(stale)} vorgemerkte Order(s) waren abgelaufen — bitte neu vormerken",
                action_de="Rebalance ② erneut — alte Queue wurde bereinigt",
            )
        pending = list_pending_intents(root)
        pol = deferred.get("policy") or {}
        if pending and not pol.get("user_armed"):
            _add(
                warnings,
                code="PENDING_NOT_ARMED",
                severity="warn",
                title_de=f"{len(pending)} Order(s) vorgemerkt — Auto-Ausführung aus",
                detail_de=str(deferred.get("status_de") or ""),
                action_de="Champion-Portfolio per GUI bestätigen senden (kein Auto-Execute)",
            )
    except Exception:
        pass

    # --- Authorization ---
    auth = _load_authorization(root)
    if str(auth.get("status") or "").startswith("CONFLICT"):
        _add(
            warnings,
            code="AUTHORIZATION_CONFLICT",
            severity="warn",
            title_de="Governance: BLOCKED FOR SAFETY",
            detail_de="; ".join(str(x) for x in (auth.get("conflict_details") or [])[:2]),
            action_de="Kein Echtgeld bis Konflikt geklärt — manuelle GUI-Orders mit Vorsicht",
        )
    if auth.get("real_money_authorized") is False:
        _add(
            warnings,
            code="REAL_MONEY_NOT_AUTHORIZED",
            severity="info",
            title_de="Echtgeld-Gate: noch nicht freigegeben",
            detail_de=str(auth.get("real_money_note_de") or "")[:200],
            action_de=f"Go-Live-Ziel: {auth.get('generated_at_utc', '—')[:10]}",
        )

    # --- Price feed / internet (live probe — stale state file must not false-alarm) ---
    try:
        from aa_adaptive_runtime import probe_internet_prices

        internet_live = probe_internet_prices()
    except Exception:
        internet_live = False
    adaptive = _load_adaptive_runtime(root)
    ctx = adaptive.get("context") or {}
    price_source = str(adaptive.get("price_source") or "")
    if not internet_live and (ctx.get("internet_ok") is False or price_source == "fictive"):
        from analytics.alpha_model_local_runtime import dampen_warning_for_local, is_local_only

        sev = dampen_warning_for_local(root, "OFFLINE_OR_FICTIVE_PRICES", "critical")
        action = (
            "Lokal-only PRE_GO_LIVE — fictive Kurse OK bis Montag/Internet"
            if is_local_only(root) and sev != "critical"
            else "Netzwerk prüfen — ohne echte Kurse kein Rebalance"
        )
        title = (
            "Lokale/fictive Kurse (PRE_GO_LIVE — erwartet)"
            if is_local_only(root) and sev != "critical"
            else "Kein verlässlicher Internet-Preisfeed"
        )
        _add(
            warnings,
            code="OFFLINE_OR_FICTIVE_PRICES",
            severity=sev,
            title_de=title,
            detail_de="; ".join(adaptive.get("notes") or [])[:240] or "price_source=fictive",
            action_de=action,
        )

    # --- Champion / signal ---
    if guard.get("hard_block") or not guard.get("champion_ok") or not guard.get("signals_ok"):
        _add(
            warnings,
            code="CHAMPION_OR_SIGNAL",
            severity="critical",
            title_de="Champion oder Signal nicht OK",
            detail_de=str(guard.get("status_de") or guard.get("message_de") or "Guard FAIL"),
            action_de="③ Signal aktualisieren oder Champion-Guard prüfen",
        )
    elif guard.get("warnings"):
        seal_warns = [
            w
            for w in (guard.get("warnings") or [])
            if str(w).startswith(("EXPERIMENTAL_", "DAILY_ALPHA_H1_"))
        ]
        if seal_warns:
            _add(
                warnings,
                code="H1_NOT_SEALED_YET",
                severity="warn",
                title_de="H1-Profil noch nicht sealed — Lernphase",
                detail_de="; ".join(seal_warns)[:240],
                action_de="Vor Go-Live H1-Backtest sealed; Orders nur mit GUI-Bestätigung",
            )

    # --- Trading readiness ---
    if readiness and not readiness.get("ready"):
        checks = readiness.get("checks") or []
        failed = [c.get("label") for c in checks if not c.get("ok")]
        if failed:
            _add(
                warnings,
                code="TRADING_NOT_READY",
                severity="warn",
                title_de="Live-Orders noch nicht bereit",
                detail_de=" · ".join(str(x) for x in failed[:4]),
                action_de="API-Key speichern, KI-Modus, Go-Live-Panel",
            )

    # --- Broker connection ---
    if broker.get("error") and broker.get("cash_eur") is None:
        _add(
            warnings,
            code="BROKER_SYNC_FAIL",
            severity="critical",
            title_de="T212-Sync fehlgeschlagen",
            detail_de=str(broker.get("error"))[:200],
            action_de="«Verbindung zu T212 laden»",
        )

    infra = infrastructure_open_points(root)
    for pt in infra:
        _add(
            warnings,
            code=f"INFRA_{pt['id']}",
            severity=str(pt.get("severity") or "warn"),
            title_de="Setup offen",
            detail_de=str(pt.get("detail_de") or ""),
            action_de="bash tools/setup_linux_native.sh",
        )

    from analytics.trading_warning_context import (
        dampen_off_hours_warnings,
        finalize_warning_counts,
        us_trading_action_window_open,
    )

    us_open = us_trading_action_window_open()
    warnings, dampened = dampen_off_hours_warnings(warnings, us_open=us_open)
    counts = finalize_warning_counts(warnings, dampened_codes=dampened, us_open=us_open)

    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now().replace(microsecond=0).isoformat(),
        "severity": counts["severity"],
        "count": len(warnings),
        "critical_count": counts["critical_count"],
        "critical_count_raw": counts["critical_count_raw"],
        "warn_count": counts["warn_count"],
        "headline_de": counts["headline_de"],
        "must_resolve_before_trading": counts["must_resolve_before_trading"],
        "dampened_off_hours": counts["dampened_off_hours"],
        "us_session_open": counts["us_session_open"],
        "warnings": warnings,
        "infrastructure_open_points": infra,
    }


def warnings_traffic_level(report: Dict[str, Any]) -> str:
    if int(report.get("critical_count") or 0) > 0:
        return "ROT"
    if int(report.get("warn_count") or 0) > 0:
        return "GELB"
    return "GRUEN"
