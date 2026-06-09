"""Forschungszweig Finanzierung — tägliche Aktienprognose, getrennt vom R3-OS-Bau."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_forschungszweig.json")
_EVIDENCE_REL = Path("evidence/r3_forschungszweig_latest.json")
_BRANCH_ID = "forschungszweig_finanzierung"


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


def load_forschungszweig_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "title_de": "Forschungszweig · Finanzierung",
        "branch_id": _BRANCH_ID,
    }


def classify_mandate_branch(mandate_de: str, cfg: Optional[Dict[str, Any]] = None) -> str:
    """os | forschung — anhand Schlüsselwörter."""
    cfg = cfg or {}
    text = str(mandate_de or "").strip().lower()
    if text.startswith("forschung ") or text.startswith("prognose ") or text.startswith("forschungszweig "):
        return _BRANCH_ID
    for kw in cfg.get("scope_keywords_de") or []:
        if str(kw).lower() in text:
            return _BRANCH_ID
    return "r3_os"


def strip_branch_prefix(mandate_de: str) -> str:
    raw = str(mandate_de or "").strip()
    for prefix in ("forschung ", "prognose ", "forschungszweig "):
        if raw.lower().startswith(prefix):
            return raw[len(prefix) :].strip()
    return raw


def _load_trading_day(root: Path) -> Dict[str, Any]:
    try:
        from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

        return load_trading_day_cockpit_doc(root) or {}
    except Exception:
        pass
    for rel in ("evidence/trading_day_latest.json",):
        doc = _load_json(Path(root) / rel)
        if doc:
            return doc
    return {}


def _load_prediction_profile(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / "control/prediction_operations.json")
    if not doc:
        return {}
    active = str(doc.get("active_profile") or "")
    prof = (doc.get("profiles") or {}).get(active) or {}
    return {
        "active_profile": active,
        "description_de": prof.get("description") or prof.get("note"),
        "governance_de": (doc.get("governance") or {}).get("note_de"),
    }


def _funding_tier(root: Path) -> Dict[str, Any]:
    road = _load_json(Path(root) / "control/ROADMAP_REVENUE_FUNDED_EXPANSION.json")
    tiers = road.get("product_tiers") or []
    active = next((t for t in tiers if str(t.get("status") or "").upper() == "ACTIVE"), tiers[0] if tiers else {})
    return {
        "roadmap_id": road.get("roadmap_id"),
        "north_star_de": road.get("north_star_de"),
        "active_tier_de": active.get("name_de"),
        "price_model_de": active.get("price_model"),
    }


def build_forschungszweig_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_forschungszweig_config(root)
    td = _load_trading_day(root)
    pred = _load_prediction_profile(root)
    funding = _funding_tier(root)

    warnings = td.get("warnings") or {}
    h1 = td.get("h1") or {}
    research_queue: List[Dict[str, Any]] = []
    try:
        from analytics.r3_pilot_central import load_board

        for item in load_board(root).get("items") or []:
            if item.get("branch") == _BRANCH_ID:
                research_queue.append(item)
    except Exception:
        pass

    headline = str(warnings.get("headline_de") or td.get("next_step_de") or "Tagesprognose — trading-day starten")
    prognosis_de = (
        f"{td.get('quote_coverage_de', '—')} · "
        f"Profil {pred.get('active_profile', '—')} · "
        f"{td.get('learning_message_de', '')[:120]}"
    ).strip()

    geheimnis_de = ""
    try:
        from analytics.r3_prognose_secrets import build_prognose_secrets_doc, format_geheimnis_reply_de

        sec = build_prognose_secrets_doc(root)
        if sec.get("share_in_chat") and sec.get("top_picks"):
            lines = format_geheimnis_reply_de(sec).splitlines()
            geheimnis_de = "\n".join(lines[2:10])
    except Exception:
        pass

    king_32b: Dict[str, Any] = {}
    try:
        from analytics.king_32b_forschung import build_king_32b_forschung_status

        king_32b = build_king_32b_forschung_status(root, persist=True)
    except Exception:
        pass

    doc = {
        "schema_version": 2,
        "branch_id": _BRANCH_ID,
        "updated_at_utc": _utc_now(),
        "king_32b_forschung": king_32b,
        "title_de": cfg.get("title_de"),
        "mission_de": cfg.get("mission_de"),
        "financing_de": cfg.get("financing_de"),
        "os_separation_de": cfg.get("os_separation_de"),
        "headline_de": headline,
        "prognosis_de": prognosis_de,
        "traffic_de": td.get("traffic"),
        "rebalance_due": bool(td.get("rebalance_due")),
        "next_step_de": td.get("next_step_de"),
        "prediction": pred,
        "h1": {
            "status": h1.get("status"),
            "progress_pct": h1.get("progress_pct"),
            "sealed": h1.get("sealed"),
            "banner_de": h1.get("banner_de"),
        },
        "funding": funding,
        "daily_cycle_de": cfg.get("daily_cycle_de"),
        "owned_commands": cfg.get("owned_commands"),
        "research_queue": research_queue[:6],
        "chat_hint_de": cfg.get("chat_hint_de"),
        "geheimnis_de": geheimnis_de,
        "chat_secrets_enabled": bool((cfg.get("chat_secrets") or {}).get("enabled", True)),
        "commands_de": "python3 tools/ai_kernel.py trading-day · learn · refresh · /geheimnis im Chat",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def render_forschungszweig_section(status: Dict[str, Any]) -> str:
    import html

    esc = lambda t: html.escape(str(t or ""), quote=True)
    if not status:
        return ""
    queue = status.get("research_queue") or []
    queue_html = ""
    for item in queue[:4]:
        queue_html += (
            f'<li><span class="fz-status">{esc(item.get("status"))}</span> '
            f'{esc((item.get("mandate_de") or "")[:90])}</li>'
        )
    h1 = status.get("h1") or {}
    funding = status.get("funding") or {}
    k32 = status.get("king_32b_forschung") or {}
    g = k32.get("growth") or {}
    king_html = ""
    if k32.get("is_forschungsprojekt"):
        king_html = (
            f'<div class="fz-king32b" id="fz-king32b" data-phase="{esc(g.get("phase"))}">'
            f'<span class="fz-k32b-badge">Forschung · König {esc(k32.get("model") or "32B")}</span>'
            f'<p class="fz-k32b-phase">Wachstum: <strong>{esc(g.get("phase"))}</strong> — '
            f'{esc(g.get("phase_de"))}</p>'
            f'<p class="fz-k32b-grow">{esc(g.get("wants_to_grow_de"))}</p></div>'
        )

    return f"""
<section class="forschungszweig" id="forschungszweig" aria-label="Forschungszweig Finanzierung">
  <div class="fz-head">
    <div class="fz-eyebrow">Finanzierung des Projekts</div>
    <h2 class="fz-title">{esc(status.get('title_de'))}</h2>
    <p class="fz-mission">{esc(status.get('mission_de'))}</p>
    <p class="fz-sep">{esc(status.get('os_separation_de'))}</p>
    {king_html}
  </div>
  <div class="fz-prognosis" id="fz-prognosis">
    <div class="fz-prog-label">Tagesprognose heute</div>
    <p class="fz-headline" id="fz-headline">{esc(status.get('headline_de'))}</p>
    <p class="fz-detail" id="fz-detail">{esc(status.get('prognosis_de'))}</p>
    <p class="fz-next" id="fz-next">{esc(status.get('next_step_de'))}</p>
    <p class="fz-h1" id="fz-h1">H1: {esc(h1.get('banner_de') or h1.get('status'))}</p>
    <pre class="fz-geheimnis" id="fz-geheimnis">{esc(status.get('geheimnis_de'))}</pre>
    <p class="fz-geheimnis-hint">Chat: <code>/geheimnis</code> — Prognose teilen, damit Mitwirkende einsteigen</p>
  </div>
  <div class="fz-funding">
    <span class="fz-tier">{esc(funding.get('active_tier_de'))}</span>
    <span class="fz-fin">{esc(status.get('financing_de'))}</span>
  </div>
  <div class="fz-queue-wrap">
    <h3>Beiträge Forschungszweig</h3>
    <ul class="fz-queue" id="fz-queue">{queue_html or '<li class="fz-empty">/beitrag forschung &lt;Idee&gt;</li>'}</ul>
  </div>
  <p class="fz-cmds">{esc(status.get('commands_de'))}</p>
</section>"""
