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
from analytics.r3_operator_surface_text import OPERATOR_RETRY, OPERATOR_SYNC_WAIT, start_hint_de
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
    del state
    try:
        from analytics.r3_hw_software_bond import resolve_r3_runtime_tuning

        tuning = resolve_r3_runtime_tuning(root)
        mirror = tuning.get("mirror") or {}
        return {
            "mirror_poll_ms": int(mirror.get("mirror_poll_ms") or MIRROR_POLL_MS),
            "mirror_prep_every_n_polls": int(mirror.get("mirror_prep_every_n_polls") or MIRROR_PREP_EVERY_N_POLLS),
            "mirror_reload_on_evidence_change": bool(mirror.get("mirror_reload_on_evidence_change", False)),
            "mirror_soft_update": bool(mirror.get("mirror_soft_update", True)),
        }
    except Exception:
        pass
    profile = {}
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
        "mirror_reload_on_evidence_change": bool(profile.get("mirror_reload_on_evidence_change", False)),
        "mirror_soft_update": bool(profile.get("mirror_soft_update", True)),
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
        return ""
    title = html.escape(str(mo.get("title_de") or R3_APP_NAME))
    return (
        f'<section class="r3-panel r3-mirror-model" id="r3-mirror-model" aria-label="{title}">'
        f'<p class="r3-portfolio-total"><span class="r3-label">Plan</span>'
        f'<strong class="r3-hero-amount">{html.escape(_fmt_eur(total))}</strong></p>'
        f'<div class="r3-portfolio-list r3-portfolio-scroll">'
        f'{_portfolio_table(lines, col3_label="%", col3_key="pct")}'
        f"</div></section>"
    )


def _render_alerts_banner(doc: Dict[str, Any]) -> str:
    pm = doc.get("daily_postmortem") or {}
    fw = doc.get("fall_watch") or {}
    if not (pm.get("bad_day") or fw.get("fall_detected")):
        return ""
    alerts: List[str] = []
    if pm.get("bad_day") and pm.get("headline_de"):
        alerts.append(str(pm["headline_de"])[:160])
    if fw.get("fall_detected") and fw.get("headline_de"):
        alerts.insert(0, str(fw["headline_de"])[:160])
    if not alerts:
        return ""
    text = html.escape(alerts[0][:200])
    return (
        f'<section class="r3-alerts" id="r3-alerts" aria-live="polite">'
        f'<p class="r3-alert-banner r3-alert-bad" role="alert">{text}</p></section>'
    )


def _render_start_hero(doc: Dict[str, Any]) -> str:
    if bool(doc.get("package_ready")):
        return ""
    if bool(doc.get("needs_api_setup")):
        return ""
    if bool(doc.get("t212_trusted")) and float(doc.get("notional_eur") or 0) > 0:
        return ""
    if not doc.get("operator_api_ready"):
        return ""
    hint = start_hint_de(
        needs_api=False,
        trusted=bool(doc.get("t212_trusted")),
        reason_code=str(doc.get("t212_trust_reason") or "") or None,
    )
    hint_html = (
        f'<p class="r3-start-hint" id="r3-start-hint">{html.escape(hint)}</p>'
        if hint
        else ""
    )
    return (
        '<section class="r3-start-hero" id="r3-start-hero" aria-label="Start">'
        f'<button type="button" class="r3-start-btn" id="r3-start-btn" onclick="r3OneClickStart()">'
        f"Jetzt starten</button>"
        f"{hint_html}"
        "</section>"
    )


def _render_panels_stack(doc: Dict[str, Any]) -> str:
    sections = [
        _render_model_section(doc),
        _render_execution_section(doc),
    ]
    visible = [s for s in sections if s]
    if not visible:
        return ""
    return (
        '<section class="r3-panels-stack" id="r3-panels-stack" aria-label="Plan und Auftrag">'
        f"{''.join(visible)}"
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
        if not rows:
            return ""
        total_s = _fmt_eur(float(total_raw)) if total_raw is not None and float(total_raw) > 0 else "—"
        table = _portfolio_table(rows, col3_label="€", col3_key="notional_eur", col3_suffix="")
        return (
            f'<div class="r3-exec-block {css}">'
            f'<p class="r3-portfolio-total"><span class="r3-label">{html.escape(label)}</span>'
            f'<strong class="r3-hero-amount r3-hero-amount-sm">{html.escape(total_s)}</strong></p>'
            f'<div class="r3-portfolio-list r3-portfolio-scroll r3-exec-pkg-list">{table}</div>'
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
    if not buy_lines and not sell_lines and not deferred.get("active"):
        return ""
    body = deferred_banner + _block("Verkauf", sell_lines, sell_total, css="r3-exec-sell") + _block(
        "Kauf", buy_lines, buy_total, css="r3-exec-buy"
    )
    if not body.strip():
        return ""
    return (
        '<section class="r3-panel r3-mirror-exec-pkg" id="r3-mirror-exec-pkg" aria-label="T212">'
        f"{body}</section>"
    )


def _render_status_line(doc: Dict[str, Any]) -> str:
    if not doc.get("t212_trusted"):
        return ""
    if doc.get("package_ready"):
        return ""
    headline = str(doc.get("headline_de") or "").strip()
    if not headline:
        return ""
    return f'<p class="r3-status-msg">{html.escape(display_headline(headline)[:160])}</p>'


def render_results_panel(root: Path, state: Optional[Dict[str, Any]] = None) -> str:
    root = Path(root)
    doc = state or build_exec_mirror_state(root)
    from analytics.r3_t212_setup_ui import render_t212_setup_panel

    setup_html = render_t212_setup_panel(
        root,
        show=bool(doc.get("needs_api_setup")),
    )
    utc_raw = html.escape(str(doc.get("updated_at_utc") or ""), quote=True)
    panels_stack = _render_panels_stack(doc)
    status_html = _render_status_line(doc)
    brand = (
        f'<div class="r3-mirror-brand r3-mirror-brand-compact">'
        f'<h1 class="r3-mirror-title">{html.escape(R3_APP_NAME)}</h1>'
        f"</div>"
    )
    return (
        f'<section class="r3-mirror-results r3-mirror-functional" id="r3-mirror-results" '
        f'aria-label="R3" data-exec-mode="1" data-updated-at-utc="{utc_raw}">'
        f"{brand}"
        f'<div class="r3-stack">'
        f"{setup_html}"
        f"{_render_alerts_banner(doc)}"
        f"{_render_start_hero(doc)}"
        f"{panels_stack}"
        f"{status_html}"
        f"</div></section>"
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
.r3-mirror-brand-compact {{
  margin: 0 0 var(--r3-gap); padding-bottom: 0; border-bottom: none;
}}
.r3-mirror-functional .r3-mirror-title {{
  font-size: 22px;
}}
.r3-status-msg {{
  margin: 0; font-size: 13px; color: var(--r3-muted); line-height: 1.45;
}}
.r3-status-msg.fail {{
  color: var(--r3-warn);
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
.r3-fall-watch {{
  border: 1px solid var(--r3-border); border-radius: var(--r3-radius-sm);
  background: linear-gradient(180deg, rgba(28,28,30,.92) 0%, rgba(22,22,24,.98) 100%);
}}
.r3-fall-head {{ display: flex; flex-direction: column; gap: 4px; margin-bottom: var(--r3-gap); }}
.r3-fall-title {{ margin: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
.r3-fall-badge {{
  font-size: 10px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase;
  padding: 3px 8px; border-radius: 999px;
}}
.r3-fall-badge.r3-fall-confirmed {{ background: rgba(255,69,58,.18); color: #ff453a; border: 1px solid rgba(255,69,58,.35); }}
.r3-fall-badge.r3-fall-weak {{ background: rgba(255,214,10,.12); color: #ffd60a; border: 1px solid rgba(255,214,10,.3); }}
.r3-fall-badge.r3-fall-ok {{ background: var(--r3-ok-bg); color: var(--r3-ok); border: 1px solid rgba(48,209,88,.25); }}
.r3-fall-badge.r3-fall-wait {{ background: var(--r3-bg); color: var(--r3-muted); border: 1px solid var(--r3-border); }}
.r3-fall-sub {{ margin: 0; font-size: 11px; color: var(--r3-muted); }}
.r3-fall-metrics {{
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--r3-gap);
  margin-bottom: var(--r3-gap);
}}
.r3-fall-metric {{
  background: var(--r3-surface); border: 1px solid var(--r3-border); border-radius: 8px;
  padding: 8px 10px; text-align: center;
}}
.r3-fall-metric-lbl {{ display: block; font-size: 10px; color: var(--r3-muted); margin-bottom: 2px; }}
.r3-fall-metric-val {{ font-size: 15px; font-weight: 800; }}
.r3-fall-metric.r3-fall-confirmed .r3-fall-metric-val {{ color: #ff453a; }}
.r3-fall-metric.r3-fall-weak .r3-fall-metric-val {{ color: #ffd60a; }}
.r3-fall-progress {{
  position: relative; height: 8px; border-radius: 999px; background: rgba(255,255,255,.06);
  margin-bottom: var(--r3-gap); overflow: hidden;
}}
.r3-fall-progress-bar {{
  height: 100%; border-radius: 999px;
  background: linear-gradient(90deg, #ffd60a 0%, #ff453a 100%);
  transition: width .4s ease;
}}
.r3-fall-progress-lbl {{
  position: absolute; right: 0; top: 12px; font-size: 9px; color: var(--r3-muted);
}}
.r3-fall-ticker-head span:last-child, .r3-fall-ret {{ text-align: right; }}
.r3-fall-ticker-row .r3-fall-ret {{ font-weight: 700; font-variant-numeric: tabular-nums; }}
.r3-fall-row-down .r3-fall-ret {{ color: #ff453a; }}
.r3-fall-row-up .r3-fall-ret {{ color: var(--r3-ok); }}
.r3-fall-reasons {{
  margin: var(--r3-gap) 0 0; padding-left: 18px; font-size: 11px; color: var(--r3-text); line-height: 1.45;
}}
.r3-fall-hint {{ margin: 6px 0 0; font-size: 10px; color: var(--r3-muted); }}
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
    soft_update = "true" if timing.get("mirror_soft_update") else "false"
    return f"""
const R3_MIRROR_POLL_MS = {poll};
const R3_MIRROR_SOFT_UPDATE = {soft_update};
let r3LastUtc = (document.getElementById('r3-mirror-results') || {{}}).dataset?.updatedAtUtc || '';

function r3PatchMirrorDisplays(j) {{
  if (!j) return;
  const results = document.getElementById('r3-mirror-results');
  if (results && j.updated_at_utc) results.dataset.updatedAtUtc = String(j.updated_at_utc);
}}

function r3ReinitMirrorUi() {{}}

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

async function r3RefreshUiPreferSoft() {{
  if (R3_MIRROR_SOFT_UPDATE && await r3SoftMirrorRefresh()) return true;
  location.reload();
  return false;
}}

async function r3PollMirror() {{
  try {{
    const r = await fetch('/api/r3/mirror', {{ cache: 'no-store' }});
    if (!r.ok) return;
    const j = await r.json();
    const utc = (j && j.updated_at_utc) ? String(j.updated_at_utc) : '';
    if (utc && r3LastUtc && utc !== r3LastUtc) {{
      if (R3_MIRROR_SOFT_UPDATE && await r3SoftMirrorRefresh()) {{
        r3PatchMirrorDisplays(j);
        return;
      }}
    }}
    if (utc) r3LastUtc = utc;
    r3PatchMirrorDisplays(j);
  }} catch (e) {{ /* fail-closed */ }}
}}

async function r3OneClickStart() {{
  const btn = document.getElementById('r3-start-btn');
  const hint = document.getElementById('r3-start-hint');
  if (btn) {{ btn.disabled = true; btn.textContent = '…'; }}
  if (hint) hint.textContent = '';
  try {{
    const r = await fetch('/api/r3/start', {{ method: 'POST', cache: 'no-store' }});
    let j = {{}};
    try {{ j = await r.json(); }} catch (e) {{ j = {{}}; }}
    if (!r.ok) {{
      const msg = j.message_de || j.headline_de || j.next_de || 'Erneut';
      if (hint) hint.textContent = msg;
      if (btn) {{ btn.disabled = false; btn.textContent = 'Erneut'; }}
      return;
    }}
    if (hint) hint.textContent = j.headline_de || j.next_de || '';
    if (j.package_ready && j.t212_trusted) {{
      if (btn) {{ btn.disabled = true; btn.textContent = j.cta_de || 'Bereit'; }}
      setTimeout(() => {{ r3RefreshUiPreferSoft(); }}, 800);
      return;
    }}
    if (btn) {{ btn.disabled = false; btn.textContent = j.cta_de || 'Erneut'; }}
  }} catch (e) {{
    if (hint) hint.textContent = 'Erneut';
    if (btn) {{ btn.disabled = false; btn.textContent = 'Start'; }}
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
        from analytics.r3_surface import exec_mirror_mode, trading_functions_exec_only
        from analytics.r3_trading_functions import render_r3_trading_functions_html

        exec_html = render_r3_trading_functions_html(
            root,
            exec_only=trading_functions_exec_only(root),
        )
    except Exception as exc:
        _LOG.warning("Auftrag-Oberfläche nicht geladen: %s", exc)
        exec_html = "" if exec_mirror_mode(root) else (
            '<p class="r3-mirror-foot">Auftrag-Oberfläche nicht geladen</p>'
        )
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
    state = build_exec_mirror_state(root, refresh_scans=False)
    body_html = render_mirror_body_html(root, state)
    timing = _mirror_timing(root)

    from analytics.r3_trading_functions import R3_TRADING_FUNCTIONS_CSS, R3_TRADING_FUNCTIONS_JS
    from analytics.r3_t212_setup_ui import t212_setup_css, t212_setup_js

    css = _mirror_css()
    js = _mirror_refresh_js(timing)
    fit_js = _mirror_viewport_fit_js()
    trading_js = R3_TRADING_FUNCTIONS_JS
    setup_js = t212_setup_js()
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
    {t212_setup_css()}
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
  <script>window.R3_HUB_PORT = {port};window.R3_EXEC_ONLY=true;</script>
  <script>{trading_js}</script>
  <script>{setup_js}</script>
  <script>{fit_js}</script>
  <script>{js}</script>
</body>
</html>"""
    return page.encode("utf-8")
