"""Gesprächserhalt — unabhängig von Cursor weiterentwickeln."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_continuity.json")
_SHARE_CONV = Path(".local/share/r3-os/conversation")
_MANIFEST_NAME = "continuity_manifest.json"
_ARCHIVE_NAME = "conversation_archive.jsonl"
_BRIEF_NAME = "continuity_brief_de.md"
_EVIDENCE_REL = Path("evidence/r3_continuity_latest.json")

_MANIFEST_SEED_DE = """# R3 Kontinuität — Cursor-Anker

Wir bauen R3 als Betriebssystem-Oberfläche auf Ubuntu.

**Anker:** Cursor-Agent (dieser Chat) — vollständig erhalten bis zum Ende.
**R3 Desktop:** Cockpit :17890/desktop — System-Oberfläche.
**Ollama:** Nur Fallback im Cockpit — ersetzt den Anker nicht.

## Feste Pfade
- Arbeitsbaum: /home/machinax7/active_alpha_model
- Anker-Archiv: ~/.local/share/r3-os/conversation/
- Cockpit: http://127.0.0.1:17890/desktop
- Tunnel-KI: evidence/ki_tunnel_connection_latest.json

## Erreicht (Auszug)
- Phase B aktiv (~40%): Native Apps, Pakete; offen: Login/Session, WM/Spaces, H1-Seal
- Desktop-Migration: Cursor primär, R3 Vollbild, Ollama Fallback
- KI-Tunnel: Cloudflare Quick-Tunnel aktiv
- Schritt A Code 100% · H1 parallel ~99% RUNNING stabil

## Als Nächstes
- Meilenstein 1: Login + Session-Manager
- Fenster-Management (Snap/Spaces)
- H1-Seal abwarten (automatisch)
- Anker sichern: python3 tools/ai_kernel.py r3-preserve

## Befehle (Anker + System)
- Hier in Cursor schreiben — Hauptkanal
- python3 tools/ai_kernel.py r3-preserve
- python3 tools/ai_kernel.py r3-desktop-update
- Cockpit-Slash: /status · /geheimnis · /desktop
"""


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


def load_continuity_config(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIG_REL) or {
        "conversation_share": str(_SHARE_CONV),
        "max_archive_messages": 400,
        "max_context_messages": 40,
    }


def conversation_dir() -> Path:
    return Path.home() / _SHARE_CONV


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def _clean_user_text(text: str) -> str:
    text = re.sub(r"<user_query>\s*", "", text)
    text = re.sub(r"\s*</user_query>", "", text)
    return text.strip()


def parse_transcript_jsonl(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if not path.is_file():
        return rows
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            doc = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = str(doc.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        msg = doc.get("message") or {}
        text = _extract_text(msg.get("content"))
        if not text or "[REDACTED]" in text:
            continue
        if role == "user":
            text = _clean_user_text(text)
        if len(text) < 4:
            continue
        rows.append({"role": role, "text": text[:8000]})
    return rows


def _transcript_priority(path: Path, cfg: Dict[str, Any]) -> Tuple[int, float]:
    """Höher = bevorzugt; dann neueste mtime."""
    text = str(path)
    preferred = str(cfg.get("preferred_transcript_id") or "")
    if preferred and preferred in text:
        rank = 3
    elif "active-alpha-model" in text or "active_alpha_model" in text:
        rank = 2
    elif "empty-window" in text:
        rank = 0
    else:
        rank = 1
    mtime = path.stat().st_mtime if path.exists() else 0.0
    return rank, mtime


def discover_transcript_files(root: Path) -> List[Path]:
    cfg = load_continuity_config(root)
    home = Path.home()
    found: List[Path] = []
    seen: set[str] = set()
    for pattern in cfg.get("transcript_globs") or []:
        for path in home.glob(str(pattern)):
            if path.is_file() and path.suffix == ".jsonl":
                if "subagents" in str(path):
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(path)
    found.sort(key=lambda p: _transcript_priority(p, cfg), reverse=True)
    return found


def _merge_messages(files: List[Path], *, limit: int) -> Tuple[List[Dict[str, str]], str]:
    merged: List[Dict[str, str]] = []
    source = ""
    for path in files:
        chunk = parse_transcript_jsonl(path)
        if not chunk:
            continue
        if not source:
            source = str(path)
        merged.extend(chunk)
        if len(merged) >= limit:
            break
    return merged[-limit:], source


def build_continuity_brief(root: Path, messages: List[Dict[str, str]]) -> str:
    cfg = load_continuity_config(root)
    from analytics.r3_dev_trail import build_dev_trail

    trail = build_dev_trail(root)
    paths = trail.get("paths") or {}
    lines = [_MANIFEST_SEED_DE.strip(), "", "## Letzte Gesprächspunkte", ""]
    for msg in messages[-12:]:
        role = "Du" if msg.get("role") == "user" else "R3/Agent"
        text = str(msg.get("text") or "").split("\n")[0][:240]
        lines.append(f"- **{role}:** {text}")
    lines.extend(
        [
            "",
            f"Aktualisiert: {_utc_now()}",
            f"Quelle Arbeitsbaum: {paths.get('project_root', cfg.get('project_root', ''))}",
        ]
    )
    return "\n".join(lines) + "\n"


def _load_existing_archive(limit: int) -> List[Dict[str, str]]:
    try:
        from analytics.r3_ki_storage import read_archive_rows

        return read_archive_rows(limit=limit)
    except Exception:
        return []


def _ki_session_archive_rows(limit: int) -> List[Dict[str, str]]:
    try:
        from analytics.r3_ki_storage import load_session

        rows: List[Dict[str, str]] = []
        for msg in load_session().get("messages") or []:
            role = str(msg.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            text = str(msg.get("content") or "").strip()
            if text:
                rows.append({"role": role, "text": text})
        return rows[-limit:]
    except Exception:
        return []


def _merge_archive_rows(*chunks: List[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    merged: List[Dict[str, str]] = []
    for chunk in chunks:
        merged.extend(chunk)
    if len(merged) <= limit:
        return merged
    return merged[-limit:]


def _anchor_mode(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("anchor_mode")) and str(cfg.get("primary_interface") or "") == "cursor_chat"


def preserve_conversation(root: Path, *, import_cursor: bool = False) -> Dict[str, Any]:
    """Archiv + Manifest lokal sichern — Cursor-Anker bleibt vollständig erhalten."""
    root = Path(root)
    cfg = load_continuity_config(root)
    limit = int(cfg.get("max_archive_messages") or 400)
    dest = conversation_dir()
    dest.mkdir(parents=True, exist_ok=True)

    anchor = _anchor_mode(cfg)
    legacy = bool(cfg.get("legacy_cursor_import")) and (import_cursor or anchor)
    messages = _load_existing_archive(limit)
    source = "r3_archive"
    ki_rows = _ki_session_archive_rows(limit)
    if ki_rows:
        messages = _merge_archive_rows(messages, ki_rows, limit=limit)
        source = "r3_archive+ki_session"
    if legacy:
        files = discover_transcript_files(root)
        cursor_msgs, cursor_src = _merge_messages(files, limit=limit)
        if cursor_msgs:
            messages = _merge_archive_rows(messages, cursor_msgs, limit=limit)
            source = cursor_src or source

    archive_path = dest / _ARCHIVE_NAME
    if messages:
        with archive_path.open("w", encoding="utf-8") as fh:
            for row in messages:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    brief = build_continuity_brief(root, messages)
    (dest / _BRIEF_NAME).write_text(brief, encoding="utf-8")

    manifest = {
        "schema_version": 2,
        "preserved_at_utc": _utc_now(),
        "anchor_mode": anchor,
        "independence_de": cfg.get("independence_de"),
        "primary_interface": cfg.get("primary_interface", "r3_ki"),
        "cursor_anchor_de": cfg.get("cursor_role_de"),
        "cursor_required": anchor,
        "message_count": len(messages),
        "source_transcript": source or None,
        "paths": {
            "conversation_dir": str(dest),
            "archive": str(archive_path),
            "brief": str(dest / _BRIEF_NAME),
            "project_root": str(cfg.get("project_root") or root.resolve()),
            "anchor_policy": str((root / "control/alpha_model_workshop_policy.json").resolve()),
        },
        "operator_de": cfg.get("operator_de"),
        "headline_de": (
            "Cursor-Anker vollständig gesichert — Gespräch und Mandat erhalten"
            if anchor
            else "Gespräch lokal gesichert — Alpha Model KI übernimmt (IDE optional entfernbar)"
        ),
    }
    atomic_write_json(dest / _MANIFEST_NAME, manifest)
    atomic_write_json(root / _EVIDENCE_REL, manifest)
    evidence_brief = root / "evidence/r3_continuity_brief_de.md"
    evidence_brief.write_text(brief, encoding="utf-8")
    manifest["paths"]["evidence_brief"] = str(evidence_brief)

    try:
        from analytics.r3_dev_trail import record_dev_change

        record_dev_change(
            root,
            title_de="R3-Gespräch lokal gesichert",
            detail_de=f"{len(messages)} Nachrichten → {dest}",
            status="done",
        )
    except Exception:
        pass

    return manifest


def load_continuity_context(root: Path, *, max_chars: int = 14000) -> str:
    """Kontext für R3 KI — Manifest + Kurzbrief + letzte Turns."""
    dest = conversation_dir()
    chunks: List[str] = []
    brief = dest / _BRIEF_NAME
    if brief.is_file():
        chunks.append(brief.read_text(encoding="utf-8", errors="replace")[: max_chars // 2])
    manifest = _load_json(dest / _MANIFEST_NAME)
    if manifest:
        chunks.append(
            "Manifest: "
            + json.dumps(
                {
                    "preserved_at": manifest.get("preserved_at_utc"),
                    "messages": manifest.get("message_count"),
                    "cursor_required": manifest.get("cursor_required"),
                    "project_root": (manifest.get("paths") or {}).get("project_root"),
                },
                ensure_ascii=False,
            )
        )
    archive = dest / _ARCHIVE_NAME
    if archive.is_file():
        tail: List[str] = []
        try:
            lines = archive.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines[-20:]:
                try:
                    row = json.loads(line)
                    role = row.get("role", "?")
                    text = str(row.get("text") or "")[:500]
                    tail.append(f"{role}: {text}")
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        if tail:
            chunks.append("Letzte Gesprächszeilen:\n" + "\n---\n".join(tail))
    body = "\n\n".join(chunks)
    return body[:max_chars]


def continuity_status(root: Path) -> Dict[str, Any]:
    dest = conversation_dir()
    manifest = _load_json(dest / _MANIFEST_NAME)
    if not manifest:
        manifest = _load_json(Path(root) / _EVIDENCE_REL)
    ok = bool(manifest.get("preserved_at_utc"))
    anchor = bool(manifest.get("anchor_mode"))
    return {
        "ok": ok,
        "anchor_mode": anchor,
        "cursor_required": anchor,
        "preserved": ok,
        "manifest": manifest,
        "headline_de": (
            manifest.get("headline_de")
            if ok
            else "Noch nicht gesichert — python3 tools/ai_kernel.py r3-preserve"
        ),
    }


_R3_CHAT_REQUIRED = (
    "evidence/r3_identity_handoff_de.md",
    "evidence/r3_continuity_brief_de.md",
    "evidence/r3_agent_constitution_de.md",
    "control/r3_continuity.json",
    "control/r3_ki_gui.json",
    "control/r3_ki_chat_layout.json",
    "control/r3_agent_growth.json",
    "control/r3_os_fusion.json",
)


def _archive_tail_text(root: Path, *, lines: int = 30) -> str:
    dest = conversation_dir()
    archive = dest / _ARCHIVE_NAME
    if not archive.is_file():
        return ""
    try:
        all_lines = archive.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    parts: List[str] = []
    for line in all_lines[-lines:]:
        try:
            row = json.loads(line)
            parts.append(str(row.get("text") or ""))
        except json.JSONDecodeError:
            continue
    return "\n".join(parts)


def verify_r3_chat_ready(root: Path) -> Dict[str, Any]:
    """Prüft, ob R3 Chat ohne Cursor betriebsbereit ist."""
    root = Path(root)
    checks: List[Dict[str, Any]] = []

    def _add(cid: str, label_de: str, ok: bool, detail_de: str = "") -> None:
        checks.append({"id": cid, "label_de": label_de, "ok": ok, "detail_de": detail_de})

    for rel in _R3_CHAT_REQUIRED:
        path = root / rel
        _add(
            f"file:{rel}",
            f"Datei {rel}",
            path.is_file() and path.stat().st_size > 0,
            f"{path.stat().st_size} B" if path.is_file() else "fehlt",
        )

    archive = conversation_dir() / _ARCHIVE_NAME
    msg_n = 0
    if archive.is_file():
        try:
            msg_n = sum(1 for _ in archive.open(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    _add("archive", "Gesprächsarchiv", msg_n >= 1, f"{msg_n} Nachrichten")

    st = continuity_status(root)
    manifest = st.get("manifest") or {}
    _add(
        "preserve",
        "r3-preserve Manifest",
        bool(st.get("ok")),
        str(manifest.get("preserved_at_utc") or "—"),
    )

    try:
        from analytics.r3_ki_storage import session_path

        sess_ok = session_path().is_file()
        _add("ki_session", "KI-Sitzung", sess_ok, str(session_path()))
    except Exception:
        _add("ki_session", "KI-Sitzung", False, "—")

    try:
        from analytics.local_llm_bridge import health_report

        llm = health_report(root)
        ready_llm = bool(llm.get("ready"))
        _add(
            "ollama",
            "Ollama Freitext",
            True,
            f"{'bereit' if ready_llm else 'Slash ok'} · {llm.get('resolved_model') or 'llm-setup'}",
        )
    except Exception as exc:
        _add("ollama", "Ollama Freitext", True, f"Slash ok · {str(exc)[:40]}")

    step_detail = "—"
    code_ok = False
    try:
        from analytics.r3_step_a import evaluate_step_a

        step = evaluate_step_a(root)
        code_ok = bool(step.get("step_a_code_complete"))
        done = step.get("step_a_done")
        total = step.get("step_a_total")
        step_detail = f"Code {step.get('step_a_code_percent')}% · {done}/{total}"
    except Exception as exc:
        step_detail = str(exc)[:80]
    _add("step_a", "Schritt-A-Code vollständig", code_ok, step_detail)

    ctx_ok = len(load_continuity_context(root)) >= 2000

    passed = sum(1 for c in checks if c.get("ok"))
    total = len(checks)
    ready = passed == total and ctx_ok
    return {
        "ready_for_r3_chat": ready,
        "ready_for_new_chat": ready,
        "cursor_required": False,
        "checks_passed": passed,
        "checks_total": total,
        "checks": checks,
        "headline_de": (
            "R3 Chat bereit — ohne Cursor"
            if ready
            else f"R3 Chat unvollständig — {passed}/{total} Checks grün"
        ),
        "smoke_prompt_de": (
            "Prüfe R3 Kontinuität: /kontinuität, evaluate_step_a, nächster Meilenstein. "
            "Deutsch, ohne Code zu ändern."
        ),
        "archive_dir": str(conversation_dir()),
    }


def verify_migration(root: Path) -> Dict[str, Any]:
    """Legacy-Alias — R3 Chat ohne Cursor."""
    return verify_r3_chat_ready(root)
