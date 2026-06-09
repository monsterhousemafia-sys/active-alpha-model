"""Cursor ↔ König Bridge — Evidence-Kanal, kein getrennter Agent mehr."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_BRIDGE_REL = Path("evidence/alpha_model_cursor_king_bridge_latest.json")
_QUEUE_NAME = "cursor_king_bridge.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _share_dir() -> Path:
    return Path.home() / ".local/share/alpha-model/agent"


def _queue_path() -> Path:
    return _share_dir() / _QUEUE_NAME


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def push_cursor_to_king(
    root: Path,
    *,
    summary_de: str,
    verified_facts_de: Optional[List[str]] = None,
    tasks_for_king_de: Optional[List[str]] = None,
    source: str = "cursor",
) -> Dict[str, Any]:
    """Cursor → König: verifizierte Fakten und Aufträge."""
    root = Path(root)
    prev = _load_json(root / _BRIDGE_REL)
    entry = {
        "direction": "cursor_to_king",
        "at_utc": _utc_now(),
        "source": source,
        "summary_de": str(summary_de or "").strip(),
        "verified_facts_de": list(verified_facts_de or []),
        "tasks_for_king_de": list(tasks_for_king_de or []),
    }
    doc = {
        "schema_version": 1,
        "status": "ACTIVE",
        "headline_de": "Cursor ↔ König Bridge aktiv",
        "updated_at_utc": _utc_now(),
        "last_cursor_push": entry,
        "last_king_push": prev.get("last_king_push"),
        "architecture_de": (
            "Cursor schreibt Evidence → König liest bei Start und /cursor. "
            "König schreibt Beschwerden/Aufträge zurück → Cursor liest evidence-Datei."
        ),
    }
    atomic_write_json(root / _BRIDGE_REL, doc)
    _share_dir().mkdir(parents=True, exist_ok=True)
    with _queue_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "bridge": doc}


def push_king_to_cursor(
    root: Path,
    *,
    complaint_de: str = "",
    request_de: str = "",
    status_de: str = "",
) -> Dict[str, Any]:
    """König → Cursor: Beschwerde oder Auftrag."""
    root = Path(root)
    prev = _load_json(root / _BRIDGE_REL)
    entry = {
        "direction": "king_to_cursor",
        "at_utc": _utc_now(),
        "complaint_de": str(complaint_de or "").strip(),
        "request_de": str(request_de or "").strip(),
        "status_de": str(status_de or "").strip(),
    }
    doc = {
        "schema_version": 1,
        "status": "ACTIVE",
        "headline_de": "Cursor ↔ König Bridge aktiv",
        "updated_at_utc": _utc_now(),
        "last_king_push": entry,
        "last_cursor_push": prev.get("last_cursor_push"),
    }
    atomic_write_json(root / _BRIDGE_REL, doc)
    _share_dir().mkdir(parents=True, exist_ok=True)
    with _queue_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return {"ok": True, "bridge": doc}


def pull_cursor_context_for_king(root: Path, *, max_chars: int = 6000) -> str:
    """Kontextblock für König-Prompt."""
    root = Path(root)
    doc = _load_json(root / _BRIDGE_REL)
    if not doc:
        return ""
    parts: List[str] = ["=== CURSOR ↔ KÖNIG BRIDGE ==="]
    cur = doc.get("last_cursor_push") or {}
    if cur.get("summary_de"):
        parts.append(f"Cursor (letzter Push): {cur['summary_de']}")
    for f in cur.get("verified_facts_de") or []:
        parts.append(f"• {f}")
    for t in cur.get("tasks_for_king_de") or []:
        parts.append(f"Auftrag: {t}")
    king = doc.get("last_king_push") or {}
    if king.get("complaint_de"):
        parts.append(f"König-Beschwerde: {king['complaint_de']}")
    if king.get("request_de"):
        parts.append(f"König-Anfrage an Cursor: {king['request_de']}")
    parts.append("=== ENDE BRIDGE ===")
    return "\n".join(parts)[:max_chars]


def bridge_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = _load_json(root / _BRIDGE_REL)
    try:
        from analytics.alpha_model_advisor_bridge import bridge_status as advisor_st

        adv = advisor_st(root)
        cloud_mode = "cloud_ok" if adv.get("configured") else "local_fallback"
    except Exception:
        cloud_mode = "unknown"
    active = bool(doc.get("last_cursor_push") or doc.get("updated_at_utc"))
    return {
        "ok": True,
        "bridge": "cursor_king",
        "active": active,
        "cloud_mode": cloud_mode,
        "cloud_configured": cloud_mode == "cloud_ok",
        "local_kombi_fallback": cloud_mode != "cloud_ok",
        "evidence_rel": str(_BRIDGE_REL),
        "queue": str(_queue_path()),
        "doc": doc,
        "headline_de": (
            "Cursor ↔ König verbunden via Evidence"
            if active
            else "Bridge bereit — warte auf Cursor-Push"
        ),
    }


def format_bridge_status_de(root: Path) -> str:
    st = bridge_status(root)
    doc = st.get("doc") or {}
    lines = [
        "**Cursor ↔ König Bridge**",
        st.get("headline_de") or "—",
        f"Evidence: `{st.get('evidence_rel')}`",
        f"Berater: {'Cloud-Key OK' if st.get('cloud_configured') else 'GPT-4o keyless lokal'}",
    ]
    cur = doc.get("last_cursor_push") or {}
    if cur.get("summary_de"):
        lines.extend(["", f"**Cursor:** {cur['summary_de']}", f"({cur.get('at_utc')})"])
        for f in cur.get("verified_facts_de") or []:
            lines.append(f"  • {f}")
    king = doc.get("last_king_push") or {}
    if king.get("complaint_de") or king.get("request_de"):
        lines.append("")
        if king.get("complaint_de"):
            lines.append(f"**König-Beschwerde:** {king['complaint_de']}")
        if king.get("request_de"):
            lines.append(f"**An Cursor:** {king['request_de']}")
    lines.extend(
        [
            "",
            "Befehle: /cursor · /cursor push <Text> · /cursor beschwerde <Text>",
            "Cursor liest: evidence/alpha_model_cursor_king_bridge_latest.json",
        ]
    )
    return "\n".join(lines)


def handle_cursor_bridge_command(root: Path, text: str) -> Dict[str, Any]:
    root = Path(root)
    raw = str(text or "").strip()
    low = raw.lower()
    if low in ("/cursor", "/cursor-bridge", "/cursor status"):
        return {"ok": True, "reply_de": format_bridge_status_de(root), "cursor_bridge": True}
    if low.startswith("/cursor push "):
        msg = raw[len("/cursor push ") :].strip()
        doc = push_cursor_to_king(root, summary_de=msg, source="king_cli")
        return {"ok": True, "reply_de": f"An Cursor-Bridge geschickt: {msg[:200]}", "cursor_bridge": True, **doc}
    if low.startswith("/cursor beschwerde ") or low.startswith("/cursor complaint "):
        prefix = "/cursor beschwerde " if low.startswith("/cursor beschwerde ") else "/cursor complaint "
        msg = raw[len(prefix) :].strip()
        doc = push_king_to_cursor(root, complaint_de=msg)
        return {
            "ok": True,
            "reply_de": f"Beschwerde an Cursor gespeichert — Evidence aktualisiert.\n{msg[:500]}",
            "cursor_bridge": True,
            **doc,
        }
    if low.startswith("/cursor anfrage ") or low.startswith("/cursor request "):
        prefix = "/cursor anfrage " if low.startswith("/cursor anfrage ") else "/cursor request "
        msg = raw[len(prefix) :].strip()
        doc = push_king_to_cursor(root, request_de=msg)
        return {"ok": True, "reply_de": f"Anfrage an Cursor: {msg[:500]}", "cursor_bridge": True, **doc}
    return {
        "ok": False,
        "reply_de": "Nutze /cursor · /cursor push … · /cursor beschwerde … · /cursor anfrage …",
        "cursor_bridge": True,
    }


def seal_default_cursor_push(root: Path) -> Dict[str, Any]:
    """Initialer Cursor-Push — Vasall-Rolle, König führt."""
    return push_cursor_to_king(
        root,
        summary_de="Cursor = Vasall — König führt H1/Benchmark/Seal selbst",
        verified_facts_de=[
            "Souveränität: König (alpha-model-agent) führt /h1-benchmark /h1-watch /könig-puls selbst",
            "Cursor-Vasall: nur Code/Evidence auf König-Anfrage — control/cursor_vasall_role_de.md",
            "König-Puls: evidence/king_sovereignty_latest.json · Autostart bei ensure_king_control",
            "König-Gate 7/7 · Ollama Coder-32B Chat+Bau · Berater keyless",
            "Cursor führt KEINE langen H1-Jobs — das ist König-Territorium",
        ],
        tasks_for_king_de=[],
        source="vasall_sovereignty",
    )
