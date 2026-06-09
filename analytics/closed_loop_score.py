"""Closed-loop score — one number for Superprogramm health (6 stages)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_EVIDENCE_REL = Path("evidence/closed_loop_score_latest.json")

_STAGE_IDS = ("observe", "decide", "act", "learn", "evolve", "seal")


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


def _stage(
    stage_id: str,
    label_de: str,
    *,
    ok: bool,
    detail_de: str,
    partial: bool = False,
) -> Dict[str, Any]:
    if ok:
        status = "gruen"
    elif partial:
        status = "gelb"
    else:
        status = "rot"
    return {
        "id": stage_id,
        "label_de": label_de,
        "ok": ok,
        "partial": partial,
        "status": status,
        "detail_de": detail_de[:200],
    }


def build_closed_loop_score(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
    warnings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Six stages: observe → decide → act → learn → evolve → seal."""
    root = Path(root)
    snap = dict(snap or {})
    warnings = dict(warnings or {})

    learn_report = _load_json(root / "evidence/public_learning_report_latest.json")
    capture = learn_report.get("capture") or {}
    metrics = learn_report.get("metrics") or {}
    live = metrics.get("live") or {}
    evo = learn_report.get("evolution") or {}
    mature = int(live.get("n_mature") or 0)
    quality = learn_report.get("quality_score") or {}

    try:
        from analytics.h1_governance_status import load_h1_governance_status

        h1 = load_h1_governance_status(root)
    except Exception:
        h1 = {}

    try:
        from execution.confirmed_live.trading_mode_policy import execution_credentials_ready, get_trading_mode

        exec_ready = execution_credentials_ready(root)
        mode = get_trading_mode(root)
    except Exception:
        exec_ready = False
        mode = "manual"

    try:
        from integrations.trading212.t212_order_readiness import load_stock_buy_gate

        gate = load_stock_buy_gate(root)
        scope_proven = bool(gate.get("api_execute_scope_proven"))
    except Exception:
        scope_proven = False

    broker = snap.get("broker") or {}
    qc = snap.get("quote_coverage") or {}
    rebalance = snap.get("rebalance_status") or {}
    crit = int(warnings.get("critical_count") or 0)
    crit_raw = int(warnings.get("critical_count_raw") or crit)
    dampened = list(warnings.get("dampened_off_hours") or [])
    learning_ok = bool(capture.get("learning_healthy", True))
    broker_ok = broker.get("cash_eur") is not None and not broker.get("error")
    qc_ok = bool(qc.get("ok")) or int(qc.get("n_ok") or 0) >= int(qc.get("n_total") or 12) * 0.8

    try:
        from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

        us_open = bool(us_equity_regular_session_open_now().get("open"))
    except Exception:
        us_open = False

    if not us_open and not qc_ok:
        qc_note = "Wochenende/US zu — Kurse später"
        qc_partial = True
    else:
        qc_note = str(qc.get("quote_coverage_label_de") or "—")
        qc_partial = not qc_ok

    observe_ok = learning_ok and broker_ok
    observe = _stage(
        "observe",
        "Beobachten",
        ok=observe_ok and (qc_ok or not us_open),
        partial=observe_ok and qc_partial,
        detail_de=f"Lernen {'OK' if learning_ok else '—'} · Konto {'OK' if broker_ok else '—'} · Kurse {qc_note}",
    )

    signal_ok = bool((snap.get("prediction_gate") or {}).get("ok")) or not warnings.get(
        "must_resolve_before_trading"
    )
    decide_ok = signal_ok and crit == 0
    if crit:
        decide_detail = f"Warnungen {crit}× kritisch"
    elif dampened and crit_raw > 0:
        decide_detail = f"US zu — {len(dampened)} Hinweis(e) für Session (nicht blockierend)"
    else:
        decide_detail = "Signal/Warnings bereit"
    decide = _stage(
        "decide",
        "Entscheiden",
        ok=decide_ok,
        partial=signal_ok and crit > 0,
        detail_de=decide_detail,
    )

    freigabe = _load_json(root / "evidence/r3_freigabe_latest.json")
    cycle = _load_json(root / "evidence/r3_trading_cycle_latest.json")
    package_ready = bool(freigabe.get("freigabe_ready")) and bool(cycle.get("closed"))
    act_ok = mature >= 3 or (mature >= 1 and scope_proven)
    act_partial = (
        (exec_ready and mode == "ai_assisted" and rebalance.get("is_due"))
        or scope_proven
        or package_ready
    )
    if package_ready and not act_ok:
        plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
        plan_lines = sum(
            1
            for a in (plan.get("allocations") or [])
            if str(a.get("side") or "").upper() == "BUY"
        )
        order_lines = int(freigabe.get("buy_count") or 0)
        line_note = (
            f"{order_lines} Order-Zeilen"
            if order_lines and order_lines != plan_lines
            else f"{plan_lines} Zeilen"
        )
        act_detail = (
            f"Paket bereit ({line_note}) · "
            f"Live-Fills reif: {mature}/3 · API-Scope {'bewiesen' if scope_proven else 'offen'}"
        )
    else:
        act_detail = (
            f"Live-Fills reif: {mature}/3 · API-Scope {'bewiesen' if scope_proven else 'offen'}"
        )
    act = _stage(
        "act",
        "Handeln",
        ok=act_ok,
        partial=act_partial and not act_ok,
        detail_de=act_detail,
    )

    learn_score = int(quality.get("score") or 0)
    learn_ok = mature >= 1 and learn_score >= 50
    learn_stage = _stage(
        "learn",
        "Lernen",
        ok=learn_ok,
        partial=mature >= 1 or learn_score >= 40,
        detail_de=learn_report.get("message_de") or f"Note {quality.get('grade') or '—'} · reif {mature}",
    )

    stage_id = str(evo.get("stage_id") or "sportwagen")
    auto_doc = _load_json(root / "evidence/evolution_auto_apply_latest.json")
    auto_applied = len(auto_doc.get("applied") or [])
    evolve_ok = stage_id != "sportwagen" or auto_applied > 0 or mature >= 3
    evolve = _stage(
        "evolve",
        "Evolieren",
        ok=evolve_ok,
        partial=mature >= 1,
        detail_de=f"{stage_id} → {evo.get('next_stage_id') or 'sport_plus'} · Auto-Apply {auto_applied}",
    )

    seal_ok = bool(h1.get("sealed"))
    seal = _stage(
        "seal",
        "H1/Seal",
        ok=seal_ok,
        partial=str(h1.get("status")) == "COMPLETE",
        detail_de=h1.get("banner_de") or "H1 —",
    )

    stages = [observe, decide, act, learn_stage, evolve, seal]
    green = sum(1 for s in stages if s["ok"])
    yellow = sum(1 for s in stages if s.get("partial") and not s["ok"])
    total = len(stages)
    pct = int(round(100 * green / total))

    headline = f"Kreis-Score {green}/{total} grün ({pct}%)"
    if green == total:
        tag = "SUPERPROGRAMM_GESCHLOSSEN"
        summary = "Kreis geschlossen — alle Stufen grün."
    elif green >= 4:
        tag = "AUFBLUHEN"
        summary = f"Noch {total - green} Stufe(n) bis voll geschlossen."
    elif green >= 2:
        tag = "AUFBAU"
        summary = "Kern läuft — Live-Fills und H1-Seal sind die Hebel."
    else:
        tag = "START"
        summary = "Beobachten/Entscheiden zuerst — Montag Orders schließen den Kreis."

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "green": green,
        "yellow": yellow,
        "total": total,
        "pct": pct,
        "headline_de": headline,
        "tag": tag,
        "summary_de": summary,
        "stages": stages,
        "bottleneck_de": _bottleneck(stages),
    }
    return doc


def _bottleneck(stages: List[Dict[str, Any]]) -> str:
    for s in stages:
        if not s.get("ok") and not s.get("partial"):
            return f"{s.get('label_de')}: {s.get('detail_de')}"
    for s in stages:
        if not s.get("ok"):
            return f"{s.get('label_de')}: {s.get('detail_de')}"
    return "Kein Engpass — Kreis grün."


def format_circle_lines_de(doc: Dict[str, Any]) -> List[str]:
    lines = [doc.get("headline_de") or "Kreis-Score —", doc.get("summary_de") or ""]
    for s in doc.get("stages") or []:
        icon = "✓" if s.get("ok") else ("~" if s.get("partial") else "✗")
        lines.append(f"  {icon} {s.get('label_de')}: {s.get('detail_de')}")
    bn = doc.get("bottleneck_de")
    if bn and doc.get("green", 0) < doc.get("total", 6):
        lines.append(f"→ Engpass: {bn}")
    return [ln for ln in lines if ln]


def write_closed_loop_score(root: Path, doc: Dict[str, Any]) -> Path:
    path = Path(root) / _EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_closed_loop_score(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    if doc:
        return doc
    return build_closed_loop_score(root)


def refresh_closed_loop_score(
    root: Path,
    *,
    snap: Optional[Dict[str, Any]] = None,
    warnings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    if snap is None or warnings is None:
        try:
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = snap or _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
        except Exception:
            snap = snap or {}
        if warnings is None:
            try:
                from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

                warnings = collect_trading_day_warnings(root, snap=snap)
            except Exception:
                warnings = {}
    doc = build_closed_loop_score(root, snap=snap, warnings=warnings)
    write_closed_loop_score(root, doc)
    return doc
