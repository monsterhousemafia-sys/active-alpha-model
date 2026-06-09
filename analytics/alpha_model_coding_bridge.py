"""Alpha Model — Coding-Brücke für den Entfaltungsraum (nicht 1:1 Cursor, aber /bau + Kernel)."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_CODING_PREFIXES = (
    "/bau ",
    "/build ",
    "/beitrag ",
    "/contribute ",
)
_AUTO_PREFIXES = (
    "bau ",
    "fix ",
    "implementiere ",
    "patch ",
    "codier ",
)


def is_agent_chamber() -> bool:
    return os.environ.get("AA_AGENT_CHAMBER", "").strip() in ("1", "true", "yes")


def coding_bridge_status(root: Path) -> Dict[str, Any]:
    from analytics.r3_build_channel import build_channel_status

    st = build_channel_status(root)
    st["chamber_active"] = is_agent_chamber()
    st["bridge"] = "alpha_model_coding"
    try:
        from analytics.alpha_model_entfaltung_32b import build_kernel_limits

        st["max_steps"] = int(build_kernel_limits(root).get("max_steps") or 14)
    except Exception:
        try:
            from analytics.r3_build_kernel import load_kernel_config

            st["max_steps"] = int(load_kernel_config(root).get("max_steps") or 14)
        except Exception:
            st["max_steps"] = 14
    if is_agent_chamber():
        st["autonomy_de"] = "voll — König im Entfaltungsraum (/bau, volle Pfade, 128 Schritte)"
    else:
        st["autonomy_de"] = "reduziert — nur im Entfaltungsraum"
    return st


def _is_coding_command(raw: str) -> bool:
    low = raw.strip().lower()
    if low in ("/bau", "/build", "/bau status", "/build status", "/bau apply", "/build apply"):
        return True
    if low.startswith("/bau ") or low.startswith("/build "):
        return True
    if low.startswith("/beitrag ") or low.startswith("/contribute "):
        return True
    return False


def _normalize_task(raw: str) -> str:
    s = raw.strip()
    for p in ("/beitrag ", "/contribute ", "/bau kernel ", "/build kernel ", "/bau ", "/build "):
        if s.lower().startswith(p):
            return s[len(p) :].strip()
    for p in _AUTO_PREFIXES:
        if s.lower().startswith(p):
            return s[len(p) :].strip()
    return s


def handle_coding_command(root: Path, raw: str) -> Dict[str, Any]:
    """Route /bau, /beitrag und Auto-Prefixe zum Build-Kernel (nur Entfaltungsraum)."""
    if not is_agent_chamber():
        return {
            "ok": False,
            "reply_de": (
                "Coding-Kernel nur im Entfaltungsraum (`alpha-model-agent` / `AA_AGENT_CHAMBER=1`). "
                "Cockpit bleibt Runtime — dort kein autonomes Datei-Schreiben."
            ),
        }

    from analytics.r3_build_channel import handle_build_command

    line = raw.strip()
    low = line.lower()
    if low.startswith("/beitrag ") or low.startswith("/contribute "):
        task = _normalize_task(line)
        line = f"/bau {task}"

    doc = handle_build_command(root, line)
    reply = str(doc.get("reply_de") or doc.get("headline_de") or "")
    if doc.get("trace"):
        steps = doc.get("steps") or len(doc.get("trace") or [])
        try:
            from analytics.r3_build_kernel import load_kernel_config

            max_s = int(load_kernel_config(root).get("max_steps") or 12)
        except Exception:
            max_s = 12
        if is_agent_chamber():
            reply = f"{reply}\n\n—\nSchritte: {steps} · König-Modus (max {max_s})"
        else:
            reply = (
                f"{reply}\n\n—\nSchritte: {steps} · max {max_s} · "
                f"Pfade: tools/, analytics/, tests/, control/"
            )
    return {
        "ok": bool(doc.get("ok")),
        "reply_de": reply[:12000],
        "coding": True,
        "applied": doc.get("applied"),
        "kernel_doc": {k: doc.get(k) for k in ("finished", "steps", "summary_de", "next_de") if doc.get(k)},
    }


def try_auto_coding(root: Path, raw: str) -> Optional[Dict[str, Any]]:
    """Nur bei klaren Bau-Verben — kein stilles IDE-Coding auf jede Chat-Zeile."""
    if not is_agent_chamber():
        return None
    low = raw.strip().lower()
    if _is_coding_command(raw):
        return handle_coding_command(root, raw)
    if any(low.startswith(p) for p in _AUTO_PREFIXES) and len(raw.strip()) > 12:
        return handle_coding_command(root, raw)
    return None


def render_coding_help_de() -> str:
    return (
        "**Coding (König-Modus)** — lokal, auditierbar, ohne künstliche Deckel:\n"
        "· `/bau <Aufgabe>` — Coder-32B (read/write/grep/pytest, bis 128 Schritte, GPU preload)\n"
        "· `/bau status` · `/bau apply` · `/beitrag <Patch>`\n"
        "· Kurz: `bau …` / `fix …` / `implementiere …`\n"
        "· `/kombi <frage>` · `/tipp <frage>` — Cloud-Berater + Ollama\n"
        "· `/berater-key` — Key-Status · Setup advisor-key-store\n"
        "Schutz nur gegen Secrets (.env) und destruktive Befehle — kein Git/pip."
    )
