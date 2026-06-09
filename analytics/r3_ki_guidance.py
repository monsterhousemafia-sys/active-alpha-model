"""R3 KI — geführte Mensch-Maschine-Schnittstelle (Fragen stellen)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


_STARTER_PROMPTS_LEGACY: List[Dict[str, str]] = [
    {"label": "Welche Aktien heute?", "message": "Welche Aktien heute?"},
    {"label": "R3 Power Status", "message": "/r3"},
    {"label": "Prognose-Geheimnis", "message": "/geheimnis"},
    {"label": "Nächster Schritt?", "message": "Was ist der nächste Schritt?"},
    {"label": "R3 System", "message": "/desktop"},
    {"label": "Mandat", "message": "/wachstum"},
    {"label": "Etwas bauen", "message": "/beitrag "},
]

_VAGUE = frozenset(
    {
        "ja",
        "nein",
        "ok",
        "okay",
        "hilfe",
        "help",
        "weiter",
        "mach",
        "go",
        "hm",
        "hmm",
        "äh",
        "ja bitte",
        "los",
        "start",
    }
)


def needs_guidance(message: str, *, attachment_ids: Optional[List[str]] = None) -> bool:
    if attachment_ids:
        return False
    raw = str(message or "").strip()
    if not raw or raw.startswith("/"):
        return False
    low = raw.lower().rstrip("?.! ")
    if low in _VAGUE:
        return True
    if len(raw) < 10 and " " not in raw:
        return True
    return False


def build_guidance_reply(root: Path, *, voice: bool = False) -> str:
    root = Path(root)
    next_hint = ""
    try:
        from analytics.r3_local_surface import collect_ki_next_steps

        next_hint = str(collect_ki_next_steps(root).get("next_step_de") or "").strip()
    except Exception:
        pass

    from analytics.r3_public import hide_trading_in_ui, public_guidance_de

    if hide_trading_in_ui(root):
        return public_guidance_de(root, voice=voice)

    opener = "Ich höre zu — " if voice else "Gern helfe ich — "
    lines = [
        opener + "was möchtest du als Nächstes?",
        "",
        "1. Fragen — R3, Mitmachen, Status",
        "2. Rechenkraft — /join (ohne Geld)",
        "3. Spende — /spende (Projekt beschleunigen)",
        "4. Datei — Anhang per Clip-Symbol oder hierher ziehen",
    ]
    if next_hint and "aktie" not in next_hint.lower() and "trading" not in next_hint.lower():
        lines.extend(["", f"Hinweis: {next_hint[:180]}"])
    lines.extend(["", "Antworte kurz — ich leite dich weiter."])
    return "\n".join(lines)


def starter_prompts(root: Path) -> List[Dict[str, str]]:
    from analytics.r3_public import hide_trading_in_ui, public_starter_prompts

    if hide_trading_in_ui(root):
        return public_starter_prompts(root)
    return list(_STARTER_PROMPTS_LEGACY)


def collect_voice_warnings(root: Path) -> List[str]:
    """Stale-Sync + schlechter Tag — für R3-Sprachausgabe."""
    root = Path(root)
    warnings: List[str] = []
    try:
        from analytics.r3_daily_postmortem import load_postmortem_status, run_daily_postmortem

        pm = load_postmortem_status(root)
        if not pm or not pm.get("as_of_date"):
            pm = run_daily_postmortem(root, persist=True)
        voice = str(pm.get("voice_warning_de") or "").strip()
        if voice:
            warnings.append(voice)
    except Exception:
        pass
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=False)
        if not trust.get("trusted"):
            msg = str(trust.get("message_de") or "").strip()
            if msg and msg not in warnings:
                warnings.append(msg)
    except Exception:
        pass
    return warnings[:3]


def guidance_payload(root: Path, *, voice: bool = False) -> Dict[str, Any]:
    voice_warnings = collect_voice_warnings(root) if voice else []
    reply = build_guidance_reply(root, voice=voice)
    if voice and voice_warnings:
        reply = voice_warnings[0] + "\n\n" + reply
    return {
        "ok": True,
        "guidance": True,
        "reply_de": reply,
        "voice_warning_de": voice_warnings[0] if voice_warnings else None,
        "voice_warnings_de": voice_warnings,
        "starters": starter_prompts(root),
        "ollama_required": False,
    }
