"""R3 KI — lokaler Chat-Speicher (unabhängig von Cursor)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/r3_ki_gui.json")
_SESSION_REL = Path(".local/share/r3-os/ki_console_session.json")
_ATTACH_DIR_REL = Path(".local/share/r3-os/chat-attachments")
_EVIDENCE_REL = Path("evidence/r3_ki_storage_latest.json")
_ARCHIVE_NAME = "conversation_archive.jsonl"


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


def load_ki_gui_config(root: Path) -> Dict[str, Any]:
    cfg = _load_json(Path(root) / _CONFIG_REL)
    if cfg:
        return cfg
    return {
        "session_max_messages": 48,
        "session_max_chars_per_message": 8000,
        "attachments": {"enabled": True, "max_bytes": 2_097_152, "max_per_message": 4},
        "internet": {"enabled": True, "fetch_enabled": True},
        "import": {"seed_session_messages": 36},
    }


def session_path() -> Path:
    return Path.home() / _SESSION_REL


def attachments_dir() -> Path:
    return Path.home() / _ATTACH_DIR_REL


def _trim_messages(messages: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    limit = int(cfg.get("session_max_messages") or 48)
    max_chars = int(cfg.get("session_max_chars_per_message") or 8000)
    rows: List[Dict[str, Any]] = []
    for msg in messages:
        if str(msg.get("role") or "") not in ("user", "assistant", "system"):
            continue
        row = dict(msg)
        content = str(row.get("content") or "")[:max_chars]
        row["content"] = content
        atts = row.get("attachments")
        if isinstance(atts, list):
            row["attachments"] = [str(a) for a in atts[: int((cfg.get("attachments") or {}).get("max_per_message") or 4)]]
        rows.append(row)
    return rows[-limit:]


def load_session() -> Dict[str, Any]:
    path = session_path()
    if not path.is_file():
        return {"schema_version": 2, "messages": [], "updated_at_utc": None}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            return {"schema_version": 2, "messages": []}
        if int(doc.get("schema_version") or 1) < 2:
            doc["schema_version"] = 2
        return doc
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 2, "messages": []}


def save_session(messages: List[Dict[str, Any]], *, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = load_ki_gui_config(Path.cwd())
    trimmed = _trim_messages(messages, cfg)
    doc = {
        "schema_version": 2,
        "updated_at_utc": _utc_now(),
        "messages": trimmed,
    }
    if meta:
        doc.update({k: v for k, v in meta.items() if k not in doc})
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)
    return doc


def persistable_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [m for m in messages if str(m.get("role") or "") != "system"]


def _attachment_names(att_ids: List[str]) -> List[str]:
    names: List[str] = []
    try:
        from analytics.r3_ki_attachments import load_attachment_meta
    except Exception:
        return [str(a) for a in att_ids]
    for att_id in att_ids:
        meta = load_attachment_meta(str(att_id))
        names.append(str(meta.get("filename") or att_id) if meta else str(att_id))
    return names


def history_for_ui(root: Path, *, limit: int = 40) -> List[Dict[str, Any]]:
    _ = root
    doc = load_session()
    rows: List[Dict[str, Any]] = []
    for msg in list(doc.get("messages") or [])[-limit:]:
        role = str(msg.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        att_ids = [str(a) for a in (msg.get("attachments") or [])]
        rows.append(
            {
                "role": role,
                "content": str(msg.get("content") or ""),
                "attachments": att_ids,
                "attachment_names": _attachment_names(att_ids) if att_ids else [],
                "at_utc": msg.get("at_utc"),
            }
        )
    return rows


def conversation_archive_path() -> Path:
    return Path.home() / Path(".local/share/r3-os/conversation") / _ARCHIVE_NAME


def read_archive_rows(*, limit: Optional[int] = None) -> List[Dict[str, str]]:
    path = conversation_archive_path()
    if not path.is_file():
        return []
    rows: List[Dict[str, str]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = str(row.get("role") or "")
        text = str(row.get("text") or row.get("content") or "").strip()
        if role not in ("user", "assistant") or len(text) < 1:
            continue
        rows.append({"role": role, "text": text})
    if limit and len(rows) > limit:
        return rows[-limit:]
    return rows


def append_turn_to_archive(*, user_text: str, assistant_text: str) -> None:
    """Jeder R3-Chat-Turn landet im lokalen Archiv — ohne Cursor."""
    path = conversation_archive_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _utc_now()
    lines: List[str] = []
    user = str(user_text or "").strip()
    assistant = str(assistant_text or "").strip()
    if user:
        lines.append(json.dumps({"role": "user", "text": user[:8000], "at_utc": now}, ensure_ascii=False))
    if assistant:
        lines.append(json.dumps({"role": "assistant", "text": assistant[:8000], "at_utc": now}, ensure_ascii=False))
    if not lines:
        return
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")


def ensure_ki_boot(root: Path) -> None:
    """Leere Sitzung nach Neustart aus R3-Archiv füllen — kein Cursor."""
    root = Path(root)
    cfg = load_ki_gui_config(root)
    imp = cfg.get("import") or {}
    if not imp.get("on_boot", True):
        return
    if list(load_session().get("messages") or []):
        return
    seed_session_from_archive(root)


def append_turn(
    stored: List[Dict[str, Any]],
    *,
    user_text: str,
    assistant_text: str,
    attachments: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    now = _utc_now()
    stored = list(stored)
    user_row: Dict[str, Any] = {"role": "user", "content": user_text, "at_utc": now}
    if attachments:
        user_row["attachments"] = list(attachments)
    stored.append(user_row)
    stored.append({"role": "assistant", "content": assistant_text, "at_utc": now})
    return stored


def seed_session_from_archive(root: Path, *, limit: Optional[int] = None) -> Dict[str, Any]:
    """R3-Archiv → KI-Sitzung (lokal unter ~/.local/share/r3-os)."""
    root = Path(root)
    cfg = load_ki_gui_config(root)
    imp = cfg.get("import") or {}
    limit = int(limit or imp.get("seed_session_messages") or 36)
    manifest: Dict[str, Any] = {}
    archive = conversation_archive_path()
    if not archive.is_file() and imp.get("legacy_cursor_import"):
        from analytics.r3_conversation_continuity import preserve_conversation

        manifest = preserve_conversation(root, import_cursor=True)
    rows = read_archive_rows(limit=limit)
    messages: List[Dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "")[: int(cfg.get("session_max_chars_per_message") or 8000)]
        if len(text) < 2:
            continue
        messages.append(
            {
                "role": row.get("role"),
                "content": text,
                "at_utc": _utc_now(),
                "imported": True,
                "source": "r3_archive",
            }
        )
    session_doc = save_session(
        messages,
        meta={
            "imported_at_utc": _utc_now(),
            "import_source": manifest.get("source_transcript"),
            "archive_messages": manifest.get("message_count"),
            "headline_de": "Chat aus R3-Archiv in KI-Sitzung geladen",
        },
    )
    evidence = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "session_messages": len(messages),
        "archive_messages": len(rows) or manifest.get("message_count"),
        "source": "r3_archive",
        "cursor_required": False,
            "source_transcript": manifest.get("source_transcript"),
        "headline_de": session_doc.get("headline_de"),
        "paths": {
            "session": str(session_path()),
            "archive": str(archive),
            "attachments": str(attachments_dir()),
        },
    }
    atomic_write_json(root / _EVIDENCE_REL, evidence)
    try:
        from analytics.r3_dev_trail import record_dev_change

        record_dev_change(
            root,
            title_de="Chat in R3 KI-Speicher übernommen",
            detail_de=f"{len(messages)} Sitzungsnachrichten · Archiv {manifest.get('message_count')}",
            status="done",
        )
    except Exception:
        pass
    return {**evidence, "manifest": manifest, "session": session_doc}


def storage_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    session = load_session()
    msgs = list(session.get("messages") or [])
    att_dir = attachments_dir()
    att_count = 0
    if att_dir.is_dir():
        att_count = sum(1 for p in att_dir.iterdir() if p.is_file() and p.suffix == ".json")
    return {
        "ok": True,
        "schema_version": session.get("schema_version", 2),
        "message_count": len(msgs),
        "imported_at_utc": session.get("imported_at_utc"),
        "updated_at_utc": session.get("updated_at_utc"),
        "attachments_count": att_count,
        "session_path": str(session_path()),
        "headline_de": (
            f"R3 KI-Speicher · {len(msgs)} Nachrichten"
            + (f" · importiert {session.get('imported_at_utc', '')[:10]}" if session.get("imported_at_utc") else "")
        ),
    }
