"""R3 KI — sichere Datei-Anhänge im Chat."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

from analytics.r3_ki_storage import attachments_dir, load_ki_gui_config

_META_SUFFIX = ".json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_name(name: str) -> str:
    base = Path(str(name or "upload")).name
    base = re.sub(r"[^\w.\-]+", "_", base, flags=re.UNICODE)
    return base[:120] or "upload.txt"


def _allowed_extension(root: Path, filename: str) -> bool:
    cfg = load_ki_gui_config(root)
    att = cfg.get("attachments") or {}
    ext = Path(filename).suffix.lower()
    allowed = [str(x).lower() for x in att.get("allowed_extensions") or []]
    return ext in allowed


def save_upload(
    root: Path,
    *,
    filename: str,
    data: bytes,
    mime: str = "",
) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_ki_gui_config(root)
    att_cfg = cfg.get("attachments") or {}
    if not att_cfg.get("enabled", True):
        return {"ok": False, "message_de": "Anhänge deaktiviert"}
    max_bytes = int(att_cfg.get("max_bytes") or 2_097_152)
    if len(data) > max_bytes:
        return {"ok": False, "message_de": f"Datei zu groß (max {max_bytes // 1024} KB)"}
    if not data:
        return {"ok": False, "message_de": "Leere Datei"}
    safe = _safe_name(filename)
    if not _allowed_extension(root, safe):
        return {"ok": False, "message_de": f"Dateityp nicht erlaubt: {Path(safe).suffix}"}
    mime = str(mime or "application/octet-stream")
    prefixes = [str(p) for p in att_cfg.get("allowed_mime_prefixes") or ["text/", "application/json"]]
    if not any(mime.startswith(p) for p in prefixes) and not safe.endswith((".md", ".txt", ".py", ".json")):
        return {"ok": False, "message_de": "MIME-Typ nicht erlaubt"}

    att_id = uuid.uuid4().hex[:16]
    dest = attachments_dir()
    dest.mkdir(parents=True, exist_ok=True)
    blob_path = dest / f"{att_id}.bin"
    blob_path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()[:16]
    meta = {
        "schema_version": 1,
        "id": att_id,
        "filename": safe,
        "mime": mime,
        "size_bytes": len(data),
        "sha256_prefix": digest,
        "uploaded_at_utc": _utc_now(),
        "blob": str(blob_path),
    }
    atomic_write_json(dest / f"{att_id}{_META_SUFFIX}", meta)
    return {
        "ok": True,
        "id": att_id,
        "filename": safe,
        "size_bytes": len(data),
        "mime": mime,
        "headline_de": f"Anhang gespeichert: {safe}",
    }


def save_upload_b64(root: Path, *, filename: str, content_b64: str, mime: str = "") -> Dict[str, Any]:
    try:
        data = base64.b64decode(str(content_b64 or ""), validate=True)
    except Exception:
        return {"ok": False, "message_de": "Ungültiges Base64"}
    return save_upload(root, filename=filename, data=data, mime=mime)


def load_attachment_meta(att_id: str) -> Optional[Dict[str, Any]]:
    att_id = re.sub(r"[^a-f0-9]", "", str(att_id or ""))[:32]
    if not att_id:
        return None
    meta_path = attachments_dir() / f"{att_id}{_META_SUFFIX}"
    if not meta_path.is_file():
        return None
    try:
        doc = json.loads(meta_path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def read_attachment_text(root: Path, att_id: str, *, max_chars: int = 12000) -> str:
    meta = load_attachment_meta(att_id)
    if not meta:
        return ""
    blob = Path(str(meta.get("blob") or ""))
    base = attachments_dir().resolve()
    try:
        resolved = blob.resolve()
        if not str(resolved).startswith(str(base)):
            return ""
    except OSError:
        return ""
    if not blob.is_file():
        return ""
    try:
        text = blob.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    header = f"--- Anhang {meta.get('filename')} ({meta.get('size_bytes')} B) ---\n"
    return (header + text)[:max_chars]


def build_attachments_context(root: Path, attachment_ids: List[str], *, max_chars: int = 14000) -> str:
    chunks: List[str] = []
    used = 0
    for att_id in attachment_ids:
        block = read_attachment_text(root, att_id)
        if not block:
            continue
        if used + len(block) > max_chars:
            block = block[: max(0, max_chars - used)]
        chunks.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "\n\n".join(chunks)


def list_recent_attachments(*, limit: int = 20) -> List[Dict[str, Any]]:
    dest = attachments_dir()
    if not dest.is_dir():
        return []
    metas: List[Tuple[float, Dict[str, Any]]] = []
    for path in dest.glob(f"*{_META_SUFFIX}"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                metas.append((path.stat().st_mtime, doc))
        except (json.JSONDecodeError, OSError):
            continue
    metas.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for _, doc in metas[:limit]:
        out.append(
            {
                "id": doc.get("id"),
                "filename": doc.get("filename"),
                "size_bytes": doc.get("size_bytes"),
                "uploaded_at_utc": doc.get("uploaded_at_utc"),
            }
        )
    return out
