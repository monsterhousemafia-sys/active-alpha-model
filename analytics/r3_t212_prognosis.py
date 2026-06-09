"""R3 — finale Tagesprognose für das Trading212-Portfolio (Active Alpha = Engine dahinter)."""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json
from analytics.pilot_today_pick import BLOCKED_SYMBOLS

_ROLES_REL = Path("control/r3_product_roles.json")
_READINESS_REL = Path("control/prediction_readiness.json")
_PLAN_REL = Path("evidence/pilot_investment_plan_latest.json")
_EVIDENCE_REL = Path("evidence/r3_t212_prognosis_latest.json")


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


def load_product_roles(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _ROLES_REL)


def _executable_picks(readiness: Dict[str, Any], plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ausführbare Ticker — Plan-Allokationen haben Vorrang (gleiche Basis wie Desktop/Orders)."""
    picks: List[Dict[str, Any]] = []
    for row in list(plan.get("allocations") or []):
        sym = str(row.get("symbol") or "").upper().strip()
        if not sym or sym in BLOCKED_SYMBOLS:
            continue
        w_pct = float(row.get("model_weight_pct") or 0.0)
        picks.append(
            {
                "ticker": sym,
                "target_weight": w_pct / 100.0,
                "target_weight_pct": round(w_pct, 2),
            }
        )
    if picks:
        return picks

    for row in list(readiness.get("top_picks") or []):
        sym = str(row.get("ticker") or "").upper().strip()
        if not sym or sym in BLOCKED_SYMBOLS:
            continue
        picks.append(
            {
                "ticker": sym,
                "target_weight": float(row.get("target_weight") or 0.0),
                "target_weight_pct": round(float(row.get("target_weight") or 0.0) * 100, 2),
            }
        )
        if len(picks) >= 12:
            break
    return picks


def _king_operator_message_de(root: Path, base: str) -> str:
    """König 32B — read-only Operator-Zusammenfassung für Prognose-message_de."""
    king = _load_json(root / "evidence/king_trading_assist_latest.json")
    if not king:
        return base
    parts = [str(base or "Prognose bereit.").rstrip(".")]
    summary = str(king.get("summary_de") or king.get("headline_de") or "").strip()
    hint = str(king.get("operator_hint_de") or king.get("primary_action_de") or "").strip()
    if summary:
        parts.append(f"König: {summary[:160]}")
    if hint and hint not in summary:
        parts.append(hint[:100])
    return " · ".join(parts)[:320]


def _apply_king_boost(root: Path, picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """König Follow-on — Prioritäts-Boost auf ausführbare Ticker (Anzeige, kein Champion-Wechsel)."""
    king = _load_json(root / "evidence/king_trading_assist_latest.json")
    boost_by_sym: Dict[str, float] = {}
    for row in king.get("follow_on_suggestions") or []:
        if not isinstance(row, dict) or not row.get("worth_follow_on", True):
            continue
        sym = str(row.get("symbol") or "").upper().strip()
        if sym:
            boost_by_sym[sym] = float(row.get("weight_boost_pct") or row.get("priority_boost_pct") or 0.15)
    if not boost_by_sym:
        return picks
    out: List[Dict[str, Any]] = []
    for p in picks:
        sym = str(p.get("ticker") or "").upper()
        boost = boost_by_sym.get(sym)
        if boost:
            w = float(p.get("target_weight_pct") or 0)
            p = {
                **p,
                "king_boost_pct": round(boost, 2),
                "target_weight_pct": round(w + boost, 2),
                "target_weight": round(float(p.get("target_weight") or 0) + boost / 100.0, 4),
            }
        out.append(p)
    out.sort(key=lambda r: float(r.get("target_weight_pct") or 0), reverse=True)
    return out


def _enrich_from_live_capital(
    root: Path,
    doc: Dict[str, Any],
    *,
    live_capital: Optional[Dict[str, Any]],
    worthwhile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cap = live_capital or {}
    basis = cap.get("capital_basis") or cap
    if cap.get("ok") or basis.get("investable_eur") is not None:
        if basis.get("investable_eur") is not None:
            doc["investable_eur"] = basis.get("investable_eur")
        if basis.get("planning_cash_eur") is not None:
            doc["available_cash_eur"] = basis.get("planning_cash_eur")
        elif basis.get("cash_eur") is not None:
            doc["available_cash_eur"] = basis.get("cash_eur")
        doc["capital_basis_de"] = (
            f"Live T212 · {float(doc.get('available_cash_eur') or 0):.0f} € · "
            f"{float(doc.get('investable_eur') or 0):.0f} € investierbar"
        )
        doc["last_sync_utc"] = basis.get("last_sync_utc") or cap.get("last_sync_utc")
    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=False)
    except Exception:
        trust = {}
    if cap.get("trusted") is not None:
        trust = {**trust, "trusted": cap.get("trusted")}
    doc["t212_trusted"] = bool(trust.get("trusted"))
    doc["t212_orders_blocked"] = not bool(trust.get("orders_allowed", trust.get("trusted")))
    doc["t212_trust_reason"] = trust.get("reason_code")
    if not doc.get("t212_trusted"):
        doc["ok"] = False
        doc["order_gate_ok"] = False
        if trust.get("message_de"):
            doc.setdefault("blockers", [])
            if trust.get("message_de") not in doc["blockers"]:
                doc["blockers"] = list(doc["blockers"]) + [str(trust["message_de"])[:120]]

    ww = worthwhile or {}
    buys = list(ww.get("worthwhile_buys") or cap.get("worthwhile_buys") or [])
    sells = list(ww.get("worthwhile_sells") or cap.get("worthwhile_sells") or [])
    if not buys and not sells:
        ww_file = _load_json(root / "evidence/r3_worthwhile_positions_latest.json")
        buys = list(ww_file.get("worthwhile_buys") or [])
        sells = list(ww_file.get("worthwhile_sells") or [])
    doc["worthwhile_buys"] = buys[:12]
    doc["worthwhile_sells"] = sells[:12]
    doc["worthwhile_buy_count"] = len(buys)
    doc["worthwhile_sell_count"] = len(sells)
    return doc


def build_r3_t212_daily_prognosis(
    root: Path,
    *,
    persist: bool = True,
    live_capital: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """R3-Lieferobjekt: finale Tagesprognose für T212 (Algorithmus nur als engine_de)."""
    root = Path(root)
    roles = load_product_roles(root)
    readiness = _load_json(root / _READINESS_REL)
    plan = _load_json(root / _PLAN_REL)

    if live_capital is None:
        live_capital = _load_json(root / "evidence/r3_live_capital_latest.json") or _load_json(
            root / "evidence/r3_worthwhile_positions_latest.json"
        )

    picks = _apply_king_boost(root, _executable_picks(readiness, plan))

    signal_date = readiness.get("signal_date") or plan.get("signal_date")
    ok = bool(readiness.get("ok")) and bool(picks)
    blockers = list(readiness.get("blockers") or [])
    if not picks and not blockers:
        blockers = ["Keine Zielgewichte — Predict ausstehend"]

    engine_profile = str(readiness.get("profile_used") or plan.get("signal_profile") or "daily_alpha_h1")
    summary = str(
        plan.get("summary_de")
        or plan.get("strategy_de")
        or readiness.get("message_de")
        or ""
    )[:320]

    ingest: Dict[str, Any] = {}
    try:
        from analytics.r3_browser_data import load_ingest_status

        ingest = load_ingest_status(root)
    except Exception:
        pass

    alpha = roles.get("active_alpha_model_de") or {}
    r3_role = roles.get("r3_de") or {}
    result_at = readiness.get("generated_at_utc")

    h1_evidence: Dict[str, Any] = {}
    try:
        from analytics.live_profile_governance import h1_model_evidence

        h1_evidence = h1_model_evidence(root)
    except Exception:
        pass

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "product_de": "R3",
        "platform_de": "Zentrale Handelsplattform",
        "headline_de": "R3 Handelsergebnis · Trading212",
        "presentation_only_de": str(r3_role.get("presentation_only_de") or "Nur Ergebnisse — kein Training"),
        "browser_mode_de": str(ingest.get("mode_de") or "Lokaler Browser — Daten aus Internet"),
        "data_source_de": str(ingest.get("price_source") or "internet"),
        "internet_ok": ingest.get("internet_ok"),
        "price_current": ingest.get("price_current", readiness.get("price_current")),
        "ingest_updated_at_utc": ingest.get("updated_at_utc"),
        "delivery_de": str(
            r3_role.get("delivers_de")
            or "Handelsergebnis für das Trading212-Portfolio"
        ),
        "engine_de": "Active Alpha Model",
        "engine_note_de": str(
            alpha.get("schedule_de") or "Täglich trainiert — Ergebnis nur hier auf R3"
        ),
        "model_result_at_utc": result_at,
        "broker_de": "Trading212",
        "signal_date": signal_date,
        "profile_used": engine_profile,
        "h1_evidence": h1_evidence or None,
        "ok": ok,
        "blockers": blockers,
        "message_de": readiness.get("message_de")
        or ("Prognose bereit." if ok else (blockers[0] if blockers else "Prognose blockiert")),
        "price_latest": readiness.get("price_latest"),
        "portfolio_path": str(
            readiness.get("portfolio_path")
            or roles.get("portfolio_artifact")
            or "model_output_sp500_pit_t212/latest_target_portfolio.csv"
        ),
        "positions": len(picks),
        "top_picks": picks,
        "investable_eur": plan.get("investable_eur"),
        "available_cash_eur": plan.get("available_cash_eur"),
        "summary_de": summary,
        "eod_local_time_cet": (
            (plan.get("prediction_meta") or {}).get("eod_local_time_cet") or "22:15"
        ),
        "order_gate_ok": bool(readiness.get("order_gate_ok")),
        "disclaimer_de": str(
            readiness.get("disclaimer")
            or "Research signal only — Orders ausschließlich über R3 (GUI-Bestätigung)."
        ),
    }
    try:
        from analytics.r3_trading_functions import build_r3_trading_functions

        fn_doc = build_r3_trading_functions(root, persist=True)
        doc["trading_functions"] = {
            "primary_function_id": fn_doc.get("primary_function_id"),
            "functions_active": fn_doc.get("functions_active"),
            "functions": fn_doc.get("functions"),
            "evidence_ref": "evidence/r3_trading_functions_latest.json",
        }
    except Exception:
        pass

    doc = _enrich_from_live_capital(root, doc, live_capital=live_capital, worthwhile=live_capital)
    base_msg = str(doc.get("message_de") or "")
    doc["message_de"] = _king_operator_message_de(root, base_msg)
    if doc.get("capital_basis_de") and doc.get("summary_de"):
        inv = float(doc.get("investable_eur") or 0)
        n = int(doc.get("positions") or 0)
        if inv > 0 and "investierbar" not in str(doc.get("summary_de") or ""):
            doc["summary_de"] = (
                f"{doc.get('profile_used') or 'daily_alpha_h1'}: {n} Positionen auf {inv:.0f} € "
                f"investierbar (Live T212)."
            )[:320]

    try:
        from analytics.r3_daily_postmortem import run_daily_postmortem

        pm = run_daily_postmortem(root, persist=True)
        doc["daily_postmortem"] = {
            "ok": bool(pm.get("ok")),
            "bad_day": bool(pm.get("bad_day")),
            "summary_de": str(pm.get("summary_de") or "")[:200],
            "headline_de": str(pm.get("headline_de") or "")[:160],
            "as_of_date": pm.get("as_of_date"),
            "portfolio_return_pct": pm.get("portfolio_return_pct"),
            "benchmark_return_pct": pm.get("benchmark_return_pct"),
        }
        if pm.get("voice_warning_de"):
            doc["voice_warning_de"] = pm["voice_warning_de"]
        if pm.get("stale_sync_warning_de"):
            doc.setdefault("blockers", [])
            stale = str(pm["stale_sync_warning_de"])[:120]
            if stale not in doc["blockers"]:
                doc["blockers"] = list(doc["blockers"]) + [stale]
        if pm.get("bad_day") and pm.get("headline_de"):
            doc.setdefault("warnings_de", [])
            warn = str(pm["headline_de"])[:120]
            if warn not in doc["warnings_de"]:
                doc["warnings_de"] = list(doc["warnings_de"]) + [warn]
    except Exception:
        pass

    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def refresh_r3_daily_prognosis(
    root: Path,
    *,
    persist: bool = True,
    live_capital: Optional[Dict[str, Any]] = None,
    force_capital_sync: bool = False,
) -> Dict[str, Any]:
    """Live-Cash optional syncen, dann Prognose bauen."""
    root = Path(root)
    cap = live_capital
    if cap is None or force_capital_sync:
        try:
            from analytics.r3_live_capital import sync_live_capital_basis

            cap = sync_live_capital_basis(root, force=force_capital_sync)
        except Exception:
            cap = cap or {}
    return build_r3_t212_daily_prognosis(root, persist=persist, live_capital=cap)


def render_r3_t212_prognosis_section(
    root: Path,
    prognosis: Optional[Dict[str, Any]] = None,
    *,
    desktop_only: bool = False,
) -> str:
    if prognosis is not None:
        doc = prognosis
    else:
        doc = _load_json(root / _EVIDENCE_REL)
        if not doc:
            doc = build_r3_t212_daily_prognosis(root, persist=False)
    picks = list(doc.get("top_picks") or [])
    if not picks and not doc.get("blockers"):
        return ""

    ok = bool(doc.get("ok"))
    rows = []
    for row in picks[:12]:
        ticker = str(row.get("ticker") or "—")
        pct = float(row.get("target_weight_pct") or 0.0)
        rows.append(f"<tr><td>{html.escape(ticker)}</td><td>{pct:.2f}%</td></tr>")

    warn = ""
    if not ok:
        blockers = doc.get("blockers") or []
        warn = (
            f'<p class="pred-signal-warn">'
            f'{html.escape(str(blockers[0] if blockers else doc.get("message_de") or "nicht bereit"))}'
            f"</p>"
        )

    table = ""
    if rows:
        table = (
            "<table><thead><tr><th>Ticker</th><th>Zielgewicht</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    summary = html.escape(str(doc.get("summary_de") or ""))
    cash = doc.get("investable_eur")
    cash_line = f" · {float(cash):.0f} € investierbar" if cash is not None else ""
    signal = html.escape(str(doc.get("signal_date") or "—"))

    if desktop_only:
        functions_html = ""
        try:
            from analytics.r3_trading_functions import render_r3_trading_functions_html

            functions_html = render_r3_trading_functions_html(root, exec_only=True)
        except Exception:
            pass
        return f"""
<section class="pred-signal r3-only" id="r3-desktop" aria-label="R3">
  {functions_html}
</section>"""

    data_src = html.escape(str(doc.get("data_source_de") or "internet"))
    browser = html.escape(str(doc.get("browser_mode_de") or "Lokaler Browser"))
    model_note = html.escape(str(doc.get("engine_note_de") or ""))
    return f"""
<section class="pred-signal r3-t212-prognosis" id="r3-t212-prognosis" aria-label="R3 Handelsergebnis T212">
  <h2>R3 Handelsergebnis · Trading212 · {signal}</h2>
  <p class="r3-platform-role">Zentrale Handelsplattform — präsentiert nur Modell-Ergebnisse</p>
  <p class="r3-browser-data ok">{browser} · Datenquelle {data_src}</p>
  <p class="pred-signal-meta">
    {int(doc.get('positions') or 0)} Positionen{cash_line}
    · {'bereit' if ok else 'ausstehend'}
    · Preise {html.escape(str(doc.get('price_latest') or '—'))}
  </p>
  {f'<p class="pred-signal-summary">{summary}</p>' if summary else ''}
  {table}
  {warn}
  {f'<p class="pred-signal-engine">{model_note}</p>' if model_note else ''}
</section>"""
