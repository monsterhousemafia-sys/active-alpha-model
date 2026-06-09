"""Öffentliche Nutzer-Oberfläche — minimal, ohne Aktien-Details."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

_CONFIG_REL = Path("control/r3_public.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import json

        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def load_public_config(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = _load_json(root / _CONFIG_REL)
    if cfg:
        return cfg
    return {
        "user_facing_minimal": True,
        "hide_trading_in_ui": True,
        "tagline_de": "Offenes Research — ein Cockpit, kollektive Rechenkraft.",
        "donate": {"enabled": True, "headline_de": "Projekt vorantreiben", "body_de": "", "cta_de": "Spenden", "url": ""},
        "support_ways_de": [],
    }


def hide_trading_in_ui(root: Path) -> bool:
    return bool(load_public_config(root).get("hide_trading_in_ui", True))


def donate_reply_de(root: Path) -> str:
    cfg = load_public_config(root)
    d = cfg.get("donate") or {}
    lines = [
        str(d.get("headline_de") or "Projekt vorantreiben"),
        "",
        str(d.get("body_de") or "Spenden helfen bei Entwicklung und Betrieb."),
    ]
    url = str(d.get("url") or "").strip()
    if url:
        lines.extend(["", f"Link: {url}"])
    else:
        lines.extend(["", str(d.get("alt_de") or "Kontaktiere den Betreiber für Spenden.")])
    lines.extend(["", str(d.get("thanks_de") or "Rechenkraft ohne Geld: /join")])
    return "\n".join(lines)


def public_starter_prompts(root: Path) -> List[Dict[str, str]]:
    _ = root
    return [
        {"label": "Was ist R3?", "message": "Was ist R3?"},
        {"label": "Mitmachen", "message": "/fragen"},
        {"label": "Spenden", "message": "/spende"},
        {"label": "Join", "message": "/join"},
        {"label": "Kontinuität", "message": "/kontinuität"},
    ]


def public_guidance_de(root: Path, *, voice: bool = False) -> str:
    cfg = load_public_config(root)
    opener = "Ich höre zu — " if voice else "Hallo — "
    ways = cfg.get("support_ways_de") or []
    lines = [
        opener + "wobei kann ich dir helfen?",
        "",
        "Das Wichtigste:",
        "· R3 = offenes Research-Cockpit auf deinem Rechner",
        "· Kein Vorwissen nötig — Rechenkraft oder Spende reichen",
        "· Rechenkraft: /join · Spende: /spende · Fragen: einfach tippen",
    ]
    if ways:
        lines.append("")
        for w in ways[:3]:
            lines.append(f"· {w.get('title_de')}: {w.get('body_de')} ({w.get('action_de')})")
    lines.extend(["", "Antworte kurz — ich leite dich weiter."])
    return "\n".join(lines)


def render_support_section(root: Path) -> str:
    """Minimaler Support-Block statt Forschungszweig-Details."""
    cfg = load_public_config(root)
    esc = lambda t: html.escape(str(t or ""), quote=True)
    d = cfg.get("donate") or {}
    ways = cfg.get("support_ways_de") or []
    way_html = ""
    for w in ways[:3]:
        way_html += (
            f'<div class="fz-way"><strong>{esc(w.get("title_de"))}</strong>'
            f'<p>{esc(w.get("body_de"))}</p>'
            f'<code>{esc(w.get("action_de"))}</code></div>'
        )
    url = str(d.get("url") or "").strip()
    donate_btn = (
        f'<a class="fz-donate-btn" href="{esc(url)}" target="_blank" rel="noopener">{esc(d.get("cta_de"))}</a>'
        if url
        else f'<button type="button" class="fz-donate-btn" data-cmd="/spende">{esc(d.get("cta_de") or "Spenden")}</button>'
    )
    return f"""
<section class="forschungszweig fz-public" id="forschungszweig" aria-label="Projekt unterstützen">
  <div class="fz-head">
    <div class="fz-eyebrow">Mitmachen</div>
    <h2 class="fz-title">{esc(d.get("headline_de") or "R3 unterstützen")}</h2>
    <p class="fz-mission">{esc(cfg.get("tagline_de"))}</p>
    <p class="fz-sep">{esc(d.get("body_de"))}</p>
  </div>
  <div class="fz-ways">{way_html}</div>
  <div class="fz-donate-row">{donate_btn}<span class="fz-donate-note">{esc(d.get("thanks_de"))}</span></div>
</section>"""
