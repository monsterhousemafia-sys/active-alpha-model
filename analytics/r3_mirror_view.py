"""R3 Exec Mirror — HTML/CSS/JS (View-Schicht, keine Evidence-Logik).

Prozent/Kanäle/Score nur im Operator-Status (/desktop, evidence/r3_operator_readiness_latest.json),
nicht auf /r3.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from analytics.r3_crash_guard import render_mirror_fallback_page
from analytics.r3_mirror_state import build_exec_mirror_state, display_headline
from analytics.r3_shell_brand import (
    R3_APP_NAME,
    R3_BRAND_GRADIENT,
    R3_ORANGE_TEXT,
    brand_mark_svg_inline,
    design_tokens_css,
    head_link_tags,
)

_LOG = logging.getLogger(__name__)
_BERLIN = ZoneInfo("Europe/Berlin")

# Defaults — zur Laufzeit überschreibbar via control/r3_runtime_profile.json
MIRROR_POLL_MS = 45_000
MIRROR_PREP_EVERY_N_POLLS = 4


def _mirror_timing(root: Path, state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    profile = (state or {}).get("runtime_profile") or {}
    if not profile:
        try:
            from analytics.r3_runtime_upgrade import load_runtime_profile

            profile = load_runtime_profile(root)
        except Exception:
            profile = {}
    poll = int(profile.get("mirror_poll_ms") or MIRROR_POLL_MS)
    prep = int(profile.get("mirror_prep_every_n_polls") or MIRROR_PREP_EVERY_N_POLLS)
    return {
        "mirror_poll_ms": max(15_000, min(120_000, poll)),
        "mirror_prep_every_n_polls": max(1, min(12, prep)),
        "mirror_reload_on_evidence_change": bool(profile.get("mirror_reload_on_evidence_change", True)),
        "mirror_soft_update": bool(profile.get("mirror_soft_update", False)),
    }


def format_stand_de(iso_utc: str) -> str:
    raw = str(iso_utc or "").strip()
    if not raw:
        return ""
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        local = ts.astimezone(_BERLIN)
        return local.strftime(f"%d.%m.%Y, %H:%M Uhr ({local.strftime('%Z')})")
    except (TypeError, ValueError):
        return raw[:19].replace("T", " ")


def _fmt_eur(n: Any) -> str:
    try:
        v = float(n)
        return f"{v:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _portfolio_table(
    rows: List[Dict[str, Any]],
    *,
    col3_label: str,
    col3_key: str = "pct",
    col3_suffix: str = " %",
    col3_fixed: Optional[str] = None,
) -> str:
    if not rows:
        return ""
    parts = [
        '<div class="r3-portfolio-row r3-portfolio-head">'
        '<span class="r3-portfolio-sym">Aktie</span>'
        '<span class="r3-portfolio-eur">Betrag</span>'
        f'<span class="r3-portfolio-pct">{html.escape(col3_label)}</span>'
        "</div>"
    ]
    for row in rows:
        sym = html.escape(str(row.get("symbol") or "—"))
        eur = _fmt_eur(row.get("notional_eur"))
        if col3_fixed is not None:
            col3 = html.escape(col3_fixed)
        elif col3_key == "notional_eur":
            col3 = html.escape(_fmt_eur(row.get(col3_key)))
        else:
            col3 = f"{float(row.get(col3_key) or 0):.1f}{col3_suffix}"
        parts.append(
            f'<div class="r3-portfolio-row">'
            f'<span class="r3-portfolio-sym">{sym}</span>'
            f'<span class="r3-portfolio-eur">{eur}</span>'
            f'<span class="r3-portfolio-pct">{col3}</span>'
            f"</div>"
        )
    return "".join(parts)


def _render_model_section(doc: Dict[str, Any]) -> str:
    mo = doc.get("model_output") or {}
    lines = list(mo.get("allocations") or [])
    total = float(mo.get("investable_eur") or 0)
    if not lines or total <= 0:
        return (
            '<section class="r3-panel r3-mirror-model" id="r3-mirror-model">'
            '<p class="r3-mirror-empty">—</p>'
            "</section>"
        )
    title = html.escape(str(mo.get("title_de") or R3_APP_NAME))
    return (
        f'<section class="r3-panel r3-mirror-model" id="r3-mirror-model" aria-label="{title}">'
        f'<p class="r3-portfolio-total"><span class="r3-label">Plan</span>'
        f'<strong class="r3-hero-amount">{html.escape(_fmt_eur(total))}</strong></p>'
        f'<div class="r3-portfolio-list r3-portfolio-scroll">'
        f'{_portfolio_table(lines, col3_label="%", col3_key="pct")}'
        f"</div></section>"
    )


def _render_king_follow_on_section(doc: Dict[str, Any]) -> str:
    king = doc.get("king_follow_on") or {}
    suggestions = list(king.get("suggestions") or [])
    if not suggestions and not king.get("summary_de"):
        return (
            '<section class="r3-panel r3-mirror-king" id="r3-mirror-king">'
            '<p class="r3-mirror-empty">—</p>'
            "</section>"
        )
    rows = []
    for s in suggestions:
        sym = html.escape(str(s.get("symbol") or "—"))
        hint = s.get("hint_eur")
        amt = html.escape(_fmt_eur(hint) if hint else "—")
        rows.append(
            f'<div class="r3-king-row">'
            f'<span class="r3-king-sym">{sym}</span>'
            f'<span class="r3-king-amt">{amt}</span>'
            f"</div>"
        )
    body = "".join(rows) if rows else ""
    return (
        '<section class="r3-panel r3-mirror-king" id="r3-mirror-king" aria-label="Follow-on">'
        f'<p class="r3-portfolio-total"><span class="r3-label">+</span></p>'
        f'<div class="r3-king-list">{body}</div>'
        "</section>"
    )


def _render_upgrade_banner(doc: Dict[str, Any]) -> str:
    up = doc.get("runtime_upgrade") or {}
    pending = up.get("pending") or {}
    if not up.get("has_pending") or pending.get("status") != "awaiting_confirmation":
        return ""
    title = html.escape(str(pending.get("label_de") or "Update"))
    pid = html.escape(str(pending.get("proposal_id") or ""), quote=True)
    return (
        '<section class="r3-upgrade-banner" id="r3-upgrade-banner" '
        f'data-proposal-id="{pid}" aria-label="Update">'
        f'<h2 class="r3-upgrade-title">{title}</h2>'
        '<div class="r3-upgrade-actions">'
        '<button type="button" class="r3-upgrade-btn r3-upgrade-apply" '
        'id="r3-upgrade-apply">Ja</button>'
        '<button type="button" class="r3-upgrade-btn r3-upgrade-dismiss" '
        'id="r3-upgrade-dismiss">Nein</button>'
        "</div>"
        '<p class="r3-upgrade-toast" id="r3-upgrade-toast" aria-live="polite"></p>'
        "</section>"
    )


def _render_local_banner(doc: Dict[str, Any]) -> str:
    return ""


def _render_growth_section(doc: Dict[str, Any]) -> str:
    return ""


def _render_trading_functions_section(doc: Dict[str, Any]) -> str:
    return ""


_PIPELINE_ORDER = (
    "broker",
    "plan",
    "king",
    "cycle",
    "loop",
    "engine",
    "freigabe",
    "health",
    "fees",
    "kreis",
    "stack",
    "refresh",
)

_PIPELINE_SHORT = {
    "broker": "T212",
    "plan": "Plan",
    "king": "32B",
    "cycle": "Kreis",
    "loop": "Loop",
    "engine": "Engine",
    "freigabe": "Paket",
    "health": "Health",
    "fees": "Gebühr",
    "kreis": "Score",
    "stack": "Stack",
    "refresh": "Refresh",
}

_CYCLE_SHORT = {
    "internet": "Net",
    "account": "Konto",
    "ingest": "Kurse",
    "engine": "Modell",
    "plan": "Plan",
    "display": "R3",
    "orders": "Order",
}

_FACT_SCROLL_TARGETS = {
    "broker": "r3-mirror-exec-pkg",
    "plan": "r3-mirror-model",
    "king": "r3-mirror-king",
    "freigabe": "r3-trading-functions",
    "internet": "r3-cycle-facts",
    "account": "r3-mirror-exec-pkg",
    "ingest": "r3-cycle-facts",
    "engine": "r3-mirror-model",
    "display": "r3-mirror-results",
    "orders": "r3-trading-functions",
}


def _fact_state(*, ok: bool = False, partial: bool = False) -> str:
    if ok:
        return "ok"
    if partial:
        return "warn"
    return "fail"


def _fact_row(
    key: str,
    value: str,
    *,
    ok: bool = False,
    partial: bool = False,
    node_id: str = "",
) -> str:
    state = _fact_state(ok=ok, partial=partial)
    scroll = _FACT_SCROLL_TARGETS.get(node_id, "")
    scroll_attr = f' data-scroll="{html.escape(scroll)}"' if scroll else ""
    node_attr = f' data-node="{html.escape(node_id)}"' if node_id else ""
    tag = "button" if scroll else "div"
    extra = ' type="button"' if scroll else ""
    return (
        f'<{tag} class="r3-fact-row r3-fact-{state}"{node_attr}{scroll_attr}{extra}>'
        f'<span class="r3-fact-k">{html.escape(key)}</span>'
        f'<span class="r3-fact-v">{html.escape(str(value or "—"))}</span>'
        f"</{tag}>"
    )


def _render_facts_stack(
    rows: List[str],
    *,
    section_id: str,
    closed: bool = False,
) -> str:
    if not rows:
        return ""
    cls = " r3-facts-closed" if closed else ""
    inner: List[str] = []
    for i, row in enumerate(rows):
        if i:
            inner.append('<div class="r3-fact-link" aria-hidden="true"></div>')
        inner.append(row)
    return (
        f'<section class="r3-facts{cls}" id="{html.escape(section_id)}">'
        f'<div class="r3-facts-list">{"".join(inner)}</div>'
        "</section>"
    )


def _render_system_facts(doc: Dict[str, Any]) -> str:
    return ""


def _render_cycle_facts(doc: Dict[str, Any]) -> str:
    return ""


def _render_pipeline_facts(doc: Dict[str, Any]) -> str:
    by_id = {str(l.get("id") or ""): l for l in (doc.get("pipeline_layers") or [])}
    rows: List[str] = []
    for lid in _PIPELINE_ORDER:
        layer = by_id.get(lid)
        if not layer:
            continue
        key = _PIPELINE_SHORT.get(lid) or lid[:6]
        val = str(layer.get("value_de") or "—")[:32]
        rows.append(
            _fact_row(
                key,
                val,
                ok=bool(layer.get("ok")),
                partial=bool(layer.get("partial")),
                node_id=lid,
            )
        )
    return _render_facts_stack(rows, section_id="r3-pipeline-facts")


def _render_layers_section(doc: Dict[str, Any]) -> str:
    return ""


def _render_prognosis_section(doc: Dict[str, Any]) -> str:
    prog = doc.get("prognosis") or {}
    buys = list(prog.get("worthwhile_buys") or [])
    picks = list(prog.get("top_picks") or [])
    inv = prog.get("investable_eur")
    if not buys and not picks and inv is None:
        return (
            '<section class="r3-panel r3-mirror-prognosis" id="r3-mirror-prognosis">'
            '<p class="r3-mirror-empty">—</p></section>'
        )
    rows = []
    if buys:
        for b in buys[:12]:
            sym = html.escape(str(b.get("symbol") or "—"))
            eur = float(b.get("target_eur") or b.get("gap_eur") or 0)
            pct = b.get("model_weight_pct")
            pct_s = f" · {float(pct):.1f}%" if pct is not None else ""
            rows.append(
                f'<div class="r3-portfolio-row r3-buy-row"><span class="r3-portfolio-sym">{sym}</span>'
                f'<span class="r3-portfolio-pct">{html.escape(_fmt_eur(eur))}{pct_s}</span></div>'
            )
    else:
        for p in picks:
            sym = html.escape(str(p.get("symbol") or "—"))
            pct = f"{float(p.get('pct') or 0):.1f}%"
            boost = p.get("king_boost_pct")
            boost_s = f' <span class="r3-king-boost">+{float(boost):.1f}%</span>' if boost else ""
            rows.append(
                f'<div class="r3-portfolio-row"><span class="r3-portfolio-sym">{sym}</span>'
                f'<span class="r3-portfolio-pct">{pct}{boost_s}</span></div>'
            )
    cap = html.escape(str(prog.get("capital_basis_de") or ""))
    signal = html.escape(str(prog.get("signal_date") or "—"))
    qk = doc.get("quote_keepalive") or {}
    price_day = html.escape(str(qk.get("price_latest") or "—"))
    qstat = html.escape(str(qk.get("quote_status") or "—"))
    trust = "ok" if prog.get("t212_trusted") else "warn"
    inv_s = html.escape(_fmt_eur(float(inv))) if inv is not None else "—"
    buy_n = int(prog.get("worthwhile_buy_count") or len(buys) or len(picks) or 0)
    buy_label = f" · {buy_n} Käufe" if buy_n else ""
    return (
        f'<section class="r3-panel r3-mirror-prognosis" id="r3-mirror-prognosis" aria-label="Tagesprognose">'
        f'<p class="r3-portfolio-total"><span class="r3-label">Prognose · {signal}{buy_label}</span>'
        f'<strong class="r3-hero-amount r3-hero-amount-sm">{inv_s}</strong></p>'
        f'<p class="r3-prognosis-meta r3-trust-{trust}">{cap}</p>'
        f'<p class="r3-prognosis-meta">Kurse {price_day} · {qstat}</p>'
        f'<div class="r3-portfolio-list r3-portfolio-scroll">{"".join(rows)}</div>'
        f"</section>"
    )


def _render_alerts_banner(doc: Dict[str, Any]) -> str:
    alerts = list(doc.get("alerts_de") or [])
    pm = doc.get("daily_postmortem") or {}
    if not alerts and pm.get("headline_de"):
        alerts = [str(pm["headline_de"])]
    if not alerts:
        voice = str(doc.get("voice_warning_de") or "").strip()
        if voice:
            alerts = [voice]
    if not alerts:
        return ""
    parts: List[str] = []
    for alert in alerts[:2]:
        text = html.escape(str(alert)[:200])
        cls = "r3-alert-bad" if pm.get("bad_day") or "veraltet" in text.lower() else "r3-alert-warn"
        parts.append(f'<p class="r3-alert-banner {cls}" role="alert">{text}</p>')
    voice = str(doc.get("voice_warning_de") or "").strip()
    voice_attr = html.escape(voice[:400], quote=True) if voice else ""
    data_voice = f' data-voice-warning="{voice_attr}"' if voice_attr else ""
    return (
        f'<section class="r3-alerts" id="r3-alerts" aria-live="polite"{data_voice}>'
        f"{''.join(parts)}</section>"
    )


def _render_postmortem_section(doc: Dict[str, Any]) -> str:
    pm = doc.get("daily_postmortem") or {}
    if not pm.get("ok") and not pm.get("summary_de"):
        return ""
    summary = html.escape(str(pm.get("summary_de") or pm.get("headline_de") or "—"))
    worst = pm.get("worst") or {}
    worst_s = ""
    if worst.get("symbol"):
        worst_s = (
            f' · schwächste: {html.escape(str(worst["symbol"]))} '
            f'{float(worst.get("daily_return_pct") or 0):+.2f} %'
        )
    cmd = "/erklär-heute"
    return (
        '<section class="r3-panel r3-mirror-postmortem" id="r3-mirror-postmortem" '
        'aria-label="Tagesbilanz">'
        f'<p class="r3-postmortem-lead"><span class="r3-label">Tagesbilanz</span> {summary}{worst_s}</p>'
        f'<p class="r3-postmortem-hint">Details: {html.escape(cmd)} im KI-Chat</p>'
        "</section>"
    )


def _render_start_hero(doc: Dict[str, Any]) -> str:
    pkg_ready = bool(doc.get("package_ready"))
    if pkg_ready:
        return ""
    inv = doc.get("investable_eur") or (doc.get("prognosis") or {}).get("investable_eur")
    inv_hint = f" · {float(inv):.0f} €" if inv else ""
    return (
        '<section class="r3-start-hero" id="r3-start-hero" aria-label="Start">'
        '<p class="r3-start-lead">T212 verknüpfen · Zielportfolio laden · Gewinn starten</p>'
        f'<button type="button" class="r3-start-btn" id="r3-start-btn" onclick="r3OneClickStart()">'
        f"Jetzt starten{html.escape(inv_hint)}</button>"
        '<p class="r3-start-hint" id="r3-start-hint">'
        "System bereitet 24/7 vor — unten Paket einmal bestätigen, Kreislauf läuft weiter</p>"
        "</section>"
    )


def _render_panels_stack(doc: Dict[str, Any]) -> str:
    model = _render_model_section(doc)
    postmortem = _render_postmortem_section(doc)
    prognosis = _render_prognosis_section(doc)
    exec_pkg = _render_execution_section(doc)
    king = _render_king_follow_on_section(doc)
    return (
        '<section class="r3-panels-stack" id="r3-panels-stack" aria-label="Plan T212 Plus">'
        f"{model}{postmortem}{prognosis}{exec_pkg}{king}"
        "</section>"
    )


def _render_execution_section(doc: Dict[str, Any]) -> str:
    pkg = doc.get("execution_package") or {}
    deferred = pkg.get("deferred_status") or doc.get("deferred_package") or {}
    buy_lines = list(pkg.get("lines") or [])
    sell_lines = list(pkg.get("sell_lines") or [])
    buy_total = pkg.get("notional_eur")
    sell_total = pkg.get("sell_notional_eur")
    def _block(label: str, rows: List[Dict[str, Any]], total_raw: Any, *, css: str) -> str:
        total_s = _fmt_eur(float(total_raw)) if total_raw is not None and float(total_raw) > 0 else "—"
        table = _portfolio_table(rows, col3_label="€", col3_key="notional_eur", col3_suffix="") if rows else ""
        empty = '<p class="r3-mirror-empty">—</p>' if not rows else ""
        return (
            f'<div class="r3-exec-block {css}">'
            f'<p class="r3-portfolio-total"><span class="r3-label">{html.escape(label)}</span>'
            f'<strong class="r3-hero-amount r3-hero-amount-sm">{html.escape(total_s)}</strong></p>'
            f'<div class="r3-portfolio-list r3-portfolio-scroll r3-exec-pkg-list">{table}{empty}</div>'
            f"</div>"
        )

    deferred_banner = ""
    if deferred.get("active"):
        state = "ok" if deferred.get("complete") else "warn"
        headline = html.escape(str(deferred.get("headline_de") or "Vorbestellt"))
        deferred_banner = (
            f'<p class="r3-deferred-banner r3-deferred-{state}" '
            f'aria-label="Vorbestellung">{headline}</p>'
        )
    body = deferred_banner + _block("Verkauf", sell_lines, sell_total, css="r3-exec-sell") + _block(
        "Kauf", buy_lines, buy_total, css="r3-exec-buy"
    )
    if not buy_lines and buy_total is None and not sell_lines and sell_total is None:
        return (
            '<section class="r3-panel r3-mirror-exec-pkg" id="r3-mirror-exec-pkg">'
            f"{body}</section>"
        )
    return (
        '<section class="r3-panel r3-mirror-exec-pkg" id="r3-mirror-exec-pkg" aria-label="T212">'
        f"{body}</section>"
    )


def render_results_panel(root: Path, state: Optional[Dict[str, Any]] = None) -> str:
    doc = state or build_exec_mirror_state(root)
    rows_html: List[str] = []

    def row(label: str, value: str, *, ok: Optional[bool] = None) -> None:
        vcls = "r3-mirror-v" + (" ok" if ok is True else " fail" if ok is False else "")
        rows_html.append(
            f'<div class="r3-mirror-row"><span class="r3-mirror-k">{html.escape(label)}</span>'
            f'<span class="{vcls}">{html.escape(value)}</span></div>'
        )

    row("T212", "✓" if doc.get("t212_connected") else "·", ok=doc.get("t212_connected"))
    deferred = doc.get("deferred_package") or {}
    pkg_label = display_headline(str(doc.get("headline_de") or "—"))
    if deferred.get("active"):
        pkg_label = str(deferred.get("headline_de") or pkg_label)
    row(
        "Paket",
        pkg_label,
        ok=doc.get("package_ready") or deferred.get("complete"),
    )

    qc = int(doc.get("quote_count") or 0)
    row("Kurse", str(qc) if qc else "·", ok=qc > 0)

    ts = format_stand_de(str(doc.get("updated_at_utc") or ""))
    utc_raw = html.escape(str(doc.get("updated_at_utc") or ""), quote=True)
    foot = (
        f'<p class="r3-mirror-foot">{html.escape(ts)}'
        f'<span class="r3-mirror-live" id="r3-mirror-live"></span></p>'
        if ts
        else '<p class="r3-mirror-foot"><span class="r3-mirror-live" id="r3-mirror-live"></span></p>'
    )

    status_html = "".join(rows_html)
    panels_stack = _render_panels_stack(doc)

    return (
        f'<section class="r3-mirror-results" id="r3-mirror-results" aria-label="R3"'
        f' data-updated-at-utc="{utc_raw}">'
        f'<div class="r3-mirror-brand"><div class="r3-mirror-mark" aria-hidden="true">'
        f'{brand_mark_svg_inline(size=48)}</div>'
        f'<h1 class="r3-mirror-title">{html.escape(R3_APP_NAME)}</h1>'
        f"</div>"
        f'<div class="r3-stack">'
        f"{_render_upgrade_banner(doc)}"
        f"{_render_alerts_banner(doc)}"
        f"{_render_start_hero(doc)}"
        f"{panels_stack}"
        f'<div class="r3-status-list r3-status-compact" id="r3-status-list">{status_html}</div>'
        f"</div>"
        f"{foot}</section>"
    )


def _mirror_css() -> str:
    return f"""
{design_tokens_css()}
.r3-viewport-fit {{
  flex: 1; min-height: 0; width: 100%; overflow-x: hidden; overflow-y: auto;
  display: flex; flex-direction: column; -webkit-overflow-scrolling: touch;
}}
.r3-exec-mirror {{
  flex: 0 0 auto; display: flex; flex-direction: column; margin: 0; width: 100%;
  transform: none;
}}
.r3-mirror-results {{
  display: flex; flex-direction: column; margin: 0;
  padding: var(--r3-pad-lg) var(--r3-pad-x);
  background: var(--r3-surface);
}}
.r3-mirror-brand {{
  display: flex; align-items: center; gap: var(--r3-gap);
  margin: 0 0 var(--r3-pad-lg); padding-bottom: var(--r3-pad);
  border-bottom: 1px solid var(--r3-border); flex-shrink: 0;
  flex-wrap: wrap;
}}
.r3-mirror-brand .r3-mirror-title {{ flex: 1; min-width: 0; }}
.r3-mirror-brand .r3-local-banner {{
  margin: 0; padding: 0; border: none; background: transparent;
}}
.r3-mirror-mark {{
  width: 48px; height: 48px; flex-shrink: 0;
  filter: drop-shadow(0 4px 12px rgba(233,84,32,.22));
}}
.r3-mirror-mark svg {{ display: block; width: 100%; height: 100%; shape-rendering: geometricPrecision; }}
.r3-mirror-title {{
  margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -.04em;
  color: var(--r3-orange); line-height: 1.1;
}}
.r3-status-compact {{
  border-radius: var(--r3-radius-sm); overflow: hidden;
  background: var(--r3-bg); border: 1px solid var(--r3-border);
}}
.r3-stack {{
  display: flex; flex-direction: column; gap: var(--r3-gap); flex-shrink: 0;
}}
.r3-section {{
  background: var(--r3-bg); border: 1px solid var(--r3-border);
  border-radius: var(--r3-radius); padding: var(--r3-pad);
}}
.r3-section-title {{
  margin: 0 0 var(--r3-gap); font-size: 11px; font-weight: 700;
  letter-spacing: .06em; text-transform: uppercase; color: var(--r3-muted);
}}
.r3-panel {{
  background: var(--r3-bg); border: 1px solid var(--r3-border);
  border-radius: var(--r3-radius-sm); padding: var(--r3-pad);
  display: flex; flex-direction: column; min-height: 0; margin: 0;
}}
.r3-facts {{
  background: var(--r3-bg); border: 1px solid var(--r3-border);
  border-radius: var(--r3-radius-sm); padding: var(--r3-pad);
}}
.r3-facts-list {{
  display: flex; flex-direction: column; align-items: stretch;
}}
.r3-fact-row {{
  display: grid; grid-template-columns: 52px 1fr; gap: 8px; align-items: center;
  padding: 6px 8px; border-radius: 6px; background: var(--r3-surface);
  border: 1px solid var(--r3-border); font-family: inherit; text-align: left;
  width: 100%;
}}
button.r3-fact-row {{ cursor: pointer; }}
button.r3-fact-row:focus-visible {{
  outline: 2px solid var(--r3-orange); outline-offset: 1px;
}}
.r3-fact-k {{
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  text-transform: uppercase; color: var(--r3-muted);
}}
.r3-fact-v {{
  font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums;
  color: var(--r3-text); text-align: right;
}}
.r3-fact-ok .r3-fact-v {{ color: var(--r3-ok); }}
.r3-fact-warn .r3-fact-v {{ color: var(--r3-orange); }}
.r3-fact-fail .r3-fact-v {{ color: var(--r3-fail); opacity: .9; }}
.r3-fact-link {{
  width: 2px; height: 6px; margin: 0 auto; background: var(--r3-border);
  border-radius: 1px;
}}
.r3-facts-closed .r3-fact-row.r3-fact-ok:first-child {{
  border-color: rgba(36,138,61,.45);
}}
.r3-panels-stack {{
  display: flex; flex-direction: column; gap: var(--r3-gap);
}}
.r3-panels-stack .r3-panel {{ margin: 0; }}
.r3-exec-block {{ margin-bottom: var(--r3-gap); }}
.r3-exec-block:last-child {{ margin-bottom: 0; }}
.r3-exec-sell .r3-label {{ color: var(--r3-fail); }}
.r3-exec-buy .r3-label {{ color: var(--r3-ok); }}
.r3-king-amt {{
  font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums;
  color: var(--r3-text); text-align: right; flex: 1;
}}
.r3-king-row {{ display: flex; align-items: center; gap: 8px; padding: 6px 10px; }}
.r3-label {{
  display: block; font-size: 11px; font-weight: 600; color: var(--r3-muted); margin-bottom: 4px;
}}
.r3-hero-amount {{
  display: block; font-size: 26px; font-weight: 700; letter-spacing: -.03em;
  color: var(--r3-text); line-height: 1.1;
}}
.r3-hero-amount-sm {{ font-size: 22px; }}
.r3-portfolio-source, .r3-portfolio-meta {{
  margin: 4px 0; font-size: 11px; color: var(--r3-muted);
}}
.r3-portfolio-list, .r3-status-list, .r3-king-list {{
  border-radius: var(--r3-radius-sm); overflow: hidden;
  background: var(--r3-surface); border: 1px solid var(--r3-border);
}}
.r3-exec-pkg-list, .r3-portfolio-scroll, .r3-king-list {{
  max-height: 160px; overflow-y: auto; -webkit-overflow-scrolling: touch;
}}
.r3-portfolio-row, .r3-king-row, .r3-mirror-row {{
  display: grid; align-items: center; gap: var(--r3-gap);
  padding: var(--r3-pad); background: var(--r3-surface);
  border-bottom: 1px solid var(--r3-border);
}}
.r3-portfolio-row {{ grid-template-columns: 1.1fr 1fr 0.65fr; }}
.r3-king-row {{ grid-template-columns: 0.45fr 1fr; }}
.r3-mirror-row {{
  display: flex; justify-content: space-between;
}}
.r3-portfolio-row:last-child, .r3-king-row:last-child, .r3-mirror-row:last-child {{
  border-bottom: none;
}}
.r3-portfolio-head {{ background: var(--r3-bg) !important; }}
.r3-portfolio-head span {{
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--r3-muted);
}}
.r3-portfolio-sym, .r3-king-sym {{ font-size: 13px; font-weight: 700; color: var(--r3-text); }}
.r3-portfolio-eur {{ font-size: 12px; font-weight: 600; text-align: right; color: var(--r3-text); }}
.r3-portfolio-pct, .r3-king-reason {{ font-size: 12px; color: var(--r3-muted); text-align: right; }}
.r3-king-reason {{ text-align: left; line-height: 1.35; }}
.r3-king-hint, .r3-king-summary {{
  margin: 0; padding: var(--r3-pad); font-size: 11px; color: var(--r3-muted);
}}
.r3-mirror-k {{ font-size: 12px; color: var(--r3-text); }}
.r3-mirror-v {{ font-size: 12px; font-weight: 500; text-align: right; color: var(--r3-muted); }}
.r3-mirror-v.ok {{ color: var(--r3-text); font-weight: 700; }}
.r3-mirror-v.fail {{ color: var(--r3-fail); }}
.r3-mirror-empty {{ margin: 0; font-size: 12px; color: var(--r3-muted); }}
.r3-mirror-foot {{
  margin: var(--r3-pad-lg) 0 0; padding-top: var(--r3-pad);
  border-top: 1px solid var(--r3-border);
  font-size: 11px; color: var(--r3-muted); text-align: center;
}}
.r3-mirror-live {{ color: var(--r3-muted); }}
.r3-submission-banner {{
  padding: var(--r3-pad); border-radius: var(--r3-radius-sm);
  font-size: 12px; background: var(--r3-warn-bg); color: var(--r3-warn);
  border: 1px solid rgba(154,123,0,.25);
}}
.r3-submission-banner.live {{
  background: var(--r3-ok-bg); color: var(--r3-ok); border-color: rgba(36,138,61,.25);
}}
.r3-local-banner {{
  display: flex; flex-wrap: wrap; align-items: center; gap: var(--r3-gap);
  padding: var(--r3-pad); border-radius: var(--r3-radius-sm);
  background: var(--r3-orange-bg); border: 1px solid var(--r3-orange-border);
  font-size: 11px; color: var(--r3-text);
}}
.r3-local-pill {{
  font-weight: 800; text-transform: uppercase; letter-spacing: .06em;
  padding: 3px 8px; border-radius: 6px;
  background: {R3_BRAND_GRADIENT}; color: #fff; font-size: 9px;
}}
.r3-local-hub {{ font-weight: 700; font-family: ui-monospace, monospace; }}
.r3-local-growth {{ font-size: 11px; font-weight: 700; color: var(--r3-ok); }}
.r3-local-detail {{ color: var(--r3-muted); flex: 1 1 100%; }}
.r3-growth-milestones {{
  margin: 0 0 var(--r3-gap); padding: 0 0 0 18px;
  font-size: 12px; color: var(--r3-text); line-height: 1.5;
}}
.r3-growth-ms.r3-growth-ok {{ color: var(--r3-ok); }}
.r3-growth-ms.r3-growth-open {{ color: var(--r3-muted); }}
.r3-growth-next {{ margin: 0; font-size: 12px; color: var(--r3-text); }}
.r3-start-hero {{
  padding: var(--r3-pad-lg); text-align: center;
  background: var(--r3-orange-bg); border: 1px solid var(--r3-orange-border);
  border-radius: var(--r3-radius);
}}
.r3-start-lead {{
  margin: 0 0 var(--r3-gap); font-size: 13px; font-weight: 600; color: var(--r3-text);
}}
.r3-start-btn {{
  display: block; width: 100%; padding: var(--r3-pad-lg);
  border: none; border-radius: var(--r3-radius);
  background: linear-gradient(145deg, var(--r3-orange-top) 0%, var(--r3-orange-bottom) 100%);
  color: #fff; font-size: 16px; font-weight: 800; cursor: pointer; font-family: inherit;
  box-shadow: 0 4px 14px rgba(233,84,32,.28);
}}
.r3-start-btn:disabled {{ opacity: .6; cursor: wait; }}
.r3-start-hint {{ margin: var(--r3-gap) 0 0; font-size: 11px; color: var(--r3-muted); }}
.r3-alerts {{ margin: 0 0 10px; }}
.r3-alert-banner {{
  margin: 0 0 6px; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 600;
  border: 1px solid rgba(255,214,10,.35); background: rgba(255,214,10,.08); color: var(--warn, #ffd60a);
}}
.r3-alert-banner.r3-alert-bad {{
  border-color: rgba(255,69,58,.4); background: rgba(255,69,58,.1); color: var(--fail, #ff453a);
}}
.r3-mirror-postmortem .r3-postmortem-lead {{ font-size: 13px; margin: 0 0 4px; }}
.r3-mirror-postmortem .r3-postmortem-hint {{ font-size: 11px; color: var(--muted); margin: 0; }}
.r3-upgrade-banner {{
  padding: var(--r3-pad); border-radius: var(--r3-radius);
  background: var(--r3-orange-bg); border: 1px solid var(--r3-orange-border);
}}
.r3-upgrade-kicker {{
  margin: 0 0 4px; font-size: 10px; font-weight: 700;
  text-transform: uppercase; color: var(--r3-orange);
}}
.r3-upgrade-title {{ margin: 0 0 var(--r3-gap); font-size: 14px; font-weight: 700; color: var(--r3-text); }}
.r3-upgrade-summary {{ margin: 0 0 var(--r3-gap); font-size: 12px; color: var(--r3-text); line-height: 1.4; }}
.r3-upgrade-changes {{ margin: 0 0 var(--r3-gap) 18px; padding: 0; font-size: 11px; line-height: 1.45; }}
.r3-upgrade-confirm {{ margin: 0 0 var(--r3-gap); font-size: 11px; color: var(--r3-muted); }}
.r3-upgrade-actions {{ display: flex; gap: var(--r3-gap); flex-wrap: wrap; }}
.r3-upgrade-btn {{
  padding: var(--r3-pad) 14px; border-radius: var(--r3-radius-sm); border: none;
  font-size: 12px; font-weight: 700; cursor: pointer; font-family: inherit;
}}
.r3-upgrade-apply {{ background: {R3_BRAND_GRADIENT}; color: #fff; }}
.r3-upgrade-dismiss {{ background: var(--r3-bg); color: var(--r3-text); border: 1px solid var(--r3-border); }}
.r3-upgrade-toast {{ min-height: 1em; margin: var(--r3-gap) 0 0; font-size: 11px; color: var(--r3-ok); }}
.r3-layers-broker, .r3-layers-kreis {{
  margin: 0 0 var(--r3-gap); font-size: 12px; color: var(--r3-text);
}}
.r3-layer-grid {{
  display: grid; grid-template-columns: repeat(auto-fill, minmax(148px, 1fr));
  gap: var(--r3-gap);
}}
.r3-layer-card {{
  background: var(--r3-surface); border-radius: var(--r3-radius-sm);
  border: 1px solid var(--r3-border); padding: var(--r3-pad);
}}
.r3-layer-head {{
  display: flex; justify-content: space-between; align-items: center;
  gap: var(--r3-gap); margin-bottom: 6px;
}}
.r3-layer-label {{ font-size: 11px; font-weight: 700; color: var(--r3-text); }}
.r3-layer-st {{
  font-size: 9px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; padding: 2px 6px; border-radius: 6px;
}}
.r3-layer-st-ok {{ background: var(--r3-ok-bg); color: var(--r3-ok); }}
.r3-layer-st-warn {{ background: var(--r3-warn-bg); color: var(--r3-warn); }}
.r3-layer-st-fail {{ background: var(--r3-fail-bg); color: var(--r3-fail); }}
.r3-layer-detail {{ margin: 0; font-size: 10px; color: var(--r3-muted); line-height: 1.4; }}
.r3-fn-grid {{
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--r3-gap);
}}
@media (max-width: 820px) {{ .r3-fn-grid {{ grid-template-columns: 1fr; }} }}
.r3-fn-card {{
  background: var(--r3-surface); border-radius: var(--r3-radius-sm);
  border: 1px solid var(--r3-border); padding: var(--r3-pad);
  display: flex; flex-direction: column; gap: 6px;
}}
.r3-fn-card.r3-fn-ok {{ border-color: rgba(36,138,61,.3); }}
.r3-fn-card.r3-fn-warn {{ border-color: var(--r3-orange-border); }}
.r3-fn-label {{ font-size: 12px; font-weight: 700; color: var(--r3-text); }}
.r3-fn-st {{ font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--r3-muted); }}
.r3-fn-meta {{ font-size: 11px; color: var(--r3-muted); }}
.r3-fn-ctx {{ margin: 0 0 var(--r3-gap); font-size: 12px; color: var(--r3-text); }}
"""


def _mirror_refresh_js(timing: Dict[str, Any]) -> str:
    poll = int(timing.get("mirror_poll_ms") or MIRROR_POLL_MS)
    prep = int(timing.get("mirror_prep_every_n_polls") or MIRROR_PREP_EVERY_N_POLLS)
    hard_reload = "true" if timing.get("mirror_reload_on_evidence_change", True) else "false"
    soft_update = "true" if timing.get("mirror_soft_update") else "false"
    return f"""
const R3_MIRROR_POLL_MS = {poll};
const R3_MIRROR_PREP_EVERY = {prep};
const R3_MIRROR_HARD_RELOAD = {hard_reload};
const R3_MIRROR_SOFT_UPDATE = {soft_update};
let r3MirrorPollN = 0;
let r3LastUtc = (document.getElementById('r3-mirror-results') || {{}}).dataset?.updatedAtUtc || '';

function r3GraphState(ok, partial) {{
  if (ok) return 'ok';
  if (partial) return 'warn';
  return 'fail';
}}

function r3SetFactRow(nodeId, value, ok, partial) {{
  if (!nodeId) return;
  const el = document.querySelector('.r3-fact-row[data-node=\"' + nodeId + '\"]');
  if (!el) return;
  const v = el.querySelector('.r3-fact-v');
  if (v && value != null && value !== '') v.textContent = String(value);
  const st = r3GraphState(!!ok, !!partial);
  el.classList.remove('r3-fact-ok', 'r3-fact-warn', 'r3-fact-fail');
  el.classList.add('r3-fact-' + st);
}}

function r3PatchStatusRow(label, value, ok) {{
  const rows = document.querySelectorAll('#r3-status-list .r3-mirror-row');
  for (const row of rows) {{
    const k = row.querySelector('.r3-mirror-k');
    const v = row.querySelector('.r3-mirror-v');
    if (!k || !v || k.textContent !== label) continue;
    v.textContent = value;
    v.className = 'r3-mirror-v' + (ok === true ? ' ok' : ok === false ? ' fail' : '');
    return;
  }}
}}

let r3LastVoiceWarning = '';

function r3SpeakWarning(text) {{
  const msg = String(text || '').trim();
  if (!msg || !window.speechSynthesis) return;
  try {{
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(msg);
    u.lang = 'de-DE';
    u.rate = 0.95;
    window.speechSynthesis.speak(u);
  }} catch (e) {{ /* fail-closed */ }}
}}

function r3PatchMirrorDisplays(j) {{
  if (!j) return;
  const vw = String(j.voice_warning_de || '').trim();
  if (vw && vw !== r3LastVoiceWarning) {{
    r3LastVoiceWarning = vw;
    r3SpeakWarning(vw);
  }}
  r3PatchStatusRow('T212', j.t212_connected ? '✓' : '·', !!j.t212_connected);
  const pkg = String(j.headline_de || '—').split(' · ')[0].trim() || '—';
  r3PatchStatusRow('Paket', pkg, !!j.package_ready);
  const qc = parseInt(j.quote_count || 0, 10);
  r3PatchStatusRow('Kurse', qc > 0 ? String(qc) : '·', qc > 0);
  const results = document.getElementById('r3-mirror-results');
  if (results && j.updated_at_utc) results.dataset.updatedAtUtc = String(j.updated_at_utc);
}}

function r3ScrollToTarget(id) {{
  if (!id) return;
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  document.querySelectorAll('.r3-fact-row.r3-fact-active').forEach((n) => n.classList.remove('r3-fact-active'));
}}

function r3BindGraphNavigation() {{
  document.querySelectorAll('.r3-fact-row[data-scroll]').forEach((btn) => {{
    if (btn.dataset.r3Bound === '1') return;
    btn.dataset.r3Bound = '1';
    btn.addEventListener('click', () => {{
      r3ScrollToTarget(btn.getAttribute('data-scroll'));
      btn.classList.add('r3-fact-active');
    }});
  }});
}}

function r3ReinitMirrorUi() {{
  r3BindUpgradeActions();
  r3BindGraphNavigation();
  const btn = document.getElementById('r3-freigabe-btn');
  if (btn && btn.classList.contains('blocked') && typeof r3RefreshOrderSurface === 'function') {{
    r3RefreshOrderSurface();
  }}
}}

async function r3SoftMirrorRefresh() {{
  const r = await fetch('/api/r3/mirror/panel', {{ cache: 'no-store' }});
  if (!r.ok) return false;
  const j = await r.json();
  const shell = document.getElementById('r3-desktop');
  if (!shell || !j || !j.body_html) return false;
  const wrap = document.createElement('div');
  wrap.innerHTML = j.body_html;
  if (!wrap.firstElementChild) return false;
  shell.innerHTML = wrap.innerHTML;
  if (j.updated_at_utc) r3LastUtc = String(j.updated_at_utc);
  if (typeof r3EnsureNativeViewport === 'function') r3EnsureNativeViewport();
  r3ReinitMirrorUi();
  return true;
}}

async function r3PollMirror() {{
  try {{
    r3MirrorPollN += 1;
    let freigabeDoc = null;
    if (r3MirrorPollN % (R3_MIRROR_PREP_EVERY * 2) === 0) {{
      const fr = await fetch('/api/r3/freigabe?prepare=0', {{ cache: 'no-store' }});
      if (fr.ok) freigabeDoc = await fr.json();
    }}
    const doScan = false;
    const doQuoteRefresh = (r3MirrorPollN % R3_MIRROR_PREP_EVERY) === 0;
    const q = doQuoteRefresh ? '?refresh=1' : (doScan ? '?scan=1' : '');
    const r = await fetch('/api/r3/mirror' + q, {{ cache: 'no-store' }});
    if (!r.ok) return;
    const j = await r.json();
    const utc = (j && j.updated_at_utc) ? String(j.updated_at_utc) : '';
    if (utc && r3LastUtc && utc !== r3LastUtc) {{
      if (R3_MIRROR_SOFT_UPDATE && await r3SoftMirrorRefresh()) {{
        r3PatchMirrorDisplays(j);
        return;
      }}
      if (R3_MIRROR_HARD_RELOAD) {{ location.reload(); return; }}
    }}
    if (utc) r3LastUtc = utc;
    r3PatchMirrorDisplays(j);
    if (freigabeDoc && freigabeDoc.package_ready) {{
      const btn = document.getElementById('r3-freigabe-btn');
      if (btn && btn.classList.contains('blocked')) location.reload();
    }}
    const liveEl = document.getElementById('r3-mirror-live');
    if (liveEl) {{
      const t = new Date().toLocaleTimeString('de-DE', {{ hour: '2-digit', minute: '2-digit' }});
      liveEl.textContent = ' · ' + t;
    }}
  }} catch (e) {{ /* fail-closed */ }}
}}

function r3BindUpgradeActions() {{
  const banner = document.getElementById('r3-upgrade-banner');
  const toast = document.getElementById('r3-upgrade-toast');
  const applyBtn = document.getElementById('r3-upgrade-apply');
  const dismissBtn = document.getElementById('r3-upgrade-dismiss');
  if (!banner || !applyBtn || !dismissBtn) return;
  const pid = banner.dataset.proposalId || '';
  const postUpgrade = async (action) => {{
    try {{
      const r = await fetch('/api/r3/upgrade?action=' + encodeURIComponent(action) + '&proposal_id=' + encodeURIComponent(pid), {{
        method: 'POST', cache: 'no-store'
      }});
      const j = await r.json();
      if (toast) toast.textContent = (j && j.message_de) ? j.message_de : '';
      if (j && j.ok) setTimeout(() => location.reload(), 600);
    }} catch (e) {{
      if (toast) toast.textContent = 'Update fehlgeschlagen — bitte erneut versuchen.';
    }}
  }};
  applyBtn.onclick = () => postUpgrade('confirm');
  dismissBtn.onclick = () => postUpgrade('dismiss');
}}

async function r3OneClickStart() {{
  const btn = document.getElementById('r3-start-btn');
  const hint = document.getElementById('r3-start-hint');
  if (btn) {{ btn.disabled = true; btn.textContent = 'Starte…'; }}
  if (hint) hint.textContent = 'T212 · Prognose · Paket…';
  try {{
    const r = await fetch('/api/r3/start', {{ method: 'POST', cache: 'no-store' }});
    const j = await r.json();
    if (hint) hint.textContent = j.headline_de || j.next_de || '';
    if (j.package_ready) {{
      setTimeout(() => location.reload(), 800);
      return;
    }}
    if (btn) {{ btn.disabled = false; btn.textContent = j.cta_de || 'Erneut starten'; }}
  }} catch (e) {{
    if (hint) hint.textContent = 'Start fehlgeschlagen — erneut versuchen';
    if (btn) {{ btn.disabled = false; btn.textContent = 'Jetzt starten'; }}
  }}
}}

document.addEventListener('DOMContentLoaded', () => {{
  r3ReinitMirrorUi();
  r3PollMirror();
  setInterval(r3PollMirror, R3_MIRROR_POLL_MS);
}});
"""


def _mirror_viewport_fit_js() -> str:
    """Native 1:1-Auflösung — kein CSS-Scale (vermeidet Unschärfe auf HiDPI)."""
    return """
function r3EnsureNativeViewport() {
  const inner = document.getElementById('r3-desktop');
  if (!inner) return;
  inner.style.transform = 'none';
  inner.style.width = '100%';
  inner.style.marginBottom = '0';
  inner.style.zoom = '1';
}

document.addEventListener('DOMContentLoaded', () => {
  r3EnsureNativeViewport();
  window.addEventListener('resize', r3EnsureNativeViewport);
});
"""


def render_mirror_body_html(root: Path, state: Optional[Dict[str, Any]] = None) -> str:
    """Spiegel-Inhalt für sanftes Panel-Update (ohne Voll-Reload)."""
    root = Path(root)
    state = state or build_exec_mirror_state(root)
    results_html = render_results_panel(root, state)
    sub = state.get("submission_mode") or {}
    sub_banner = ""
    if sub.get("live_submit"):
        sub_banner = '<p class="r3-submission-banner live" id="r3-submission-banner">Live</p>'
    try:
        from analytics.r3_trading_functions import render_r3_trading_functions_html

        exec_html = render_r3_trading_functions_html(root, exec_only=False)
    except Exception as exc:
        _LOG.warning("Auftrag-Oberfläche nicht geladen: %s", exc)
        exec_html = '<p class="r3-mirror-foot">Auftrag-Oberfläche nicht geladen</p>'
    return f"{results_html}{sub_banner}{exec_html}"


def build_mirror_panel_payload(root: Path) -> Dict[str, Any]:
    state = build_exec_mirror_state(root, refresh_scans=False)
    return {
        "schema_version": 1,
        "updated_at_utc": state.get("updated_at_utc"),
        "body_html": render_mirror_body_html(root, state),
    }


def render_r3_exec_mirror_page(root: Path, *, port: int = 17890) -> bytes:
    root = Path(root)
    try:
        port = max(1, min(65535, int(port)))
    except (TypeError, ValueError):
        port = 17890
    try:
        return _render_page_impl(root, port=port)
    except Exception as exc:
        _LOG.exception("render_r3_exec_mirror_page failed: %s", exc)
        return render_mirror_fallback_page(str(exc), port=port)


def _render_page_impl(root: Path, *, port: int) -> bytes:
    from analytics.r3_trading_functions import render_r3_trading_functions_html

    state = build_exec_mirror_state(root, refresh_scans=False)
    body_html = render_mirror_body_html(root, state)
    timing = _mirror_timing(root, state)

    from analytics.r3_trading_functions import R3_TRADING_FUNCTIONS_CSS, R3_TRADING_FUNCTIONS_JS

    css = _mirror_css()
    js = _mirror_refresh_js(timing)
    fit_js = _mirror_viewport_fit_js()
    trading_js = R3_TRADING_FUNCTIONS_JS
    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <meta name="color-scheme" content="light"/>
  {head_link_tags()}
  <title>{R3_APP_NAME}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ width: 100%; height: 100%; margin: 0; overflow: hidden;
      -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility; }}
    body {{
      height: 100dvh; max-height: 100dvh; display: flex; flex-direction: column;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", system-ui, sans-serif;
      background: var(--r3-bg); color: var(--r3-text);
    }}
    .page {{
      flex: 1; min-height: 0; display: flex; flex-direction: column;
      padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
    }}
    {css}
    {R3_TRADING_FUNCTIONS_CSS}
  </style>
</head>
<body>
    <div class="page">
    <div class="r3-viewport-fit">
      <div class="r3-exec-mirror" id="r3-desktop">
        {body_html}
      </div>
    </div>
  </div>
  <script>window.R3_HUB_PORT = {port};</script>
  <script>{trading_js}</script>
  <script>{fit_js}</script>
  <script>{js}</script>
</body>
</html>"""
    return page.encode("utf-8")
