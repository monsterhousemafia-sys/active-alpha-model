"""Strukturierte JSON-Logs für journald (stderr) und Evidence."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def emit_runtime_log(
    component: str,
    event: str,
    *,
    level: str = "info",
    code: int = 0,
    root: Optional[Path] = None,
    persist: bool = False,
    **fields: Any,
) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "ts_utc": _utc_now(),
        "component": str(component),
        "event": str(event),
        "level": str(level),
        "ok": code == 0,
        "code": int(code),
        **fields,
    }
    line = json.dumps(doc, ensure_ascii=False, default=str)
    print(line, file=sys.stderr, flush=True)
    if persist and root is not None:
        try:
            from aa_safe_io import atomic_write_json

            path = Path(root) / "evidence/runtime_journal_tail.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(path, doc)
        except Exception:
            pass
    return doc
