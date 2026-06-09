"""GUI Preview dedup — avoid hammering Ollama/Qt on repeated runs."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_STAMP_REL = Path("evidence/gui_preview_stamp.json")
_INPUTS_REL = Path("evidence/preview_inputs_stamp.json")
_REPORT_REL = Path("evidence/gui_preview_latest.json")
_DEFAULT_MAX_AGE_S = 1200


def _parse_utc(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def preview_age_seconds(root: Path) -> Optional[float]:
    path = Path(root) / _STAMP_REL
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        at = doc.get("at_utc")
        if not at:
            return None
        ts = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def is_preview_fresh(root: Path, *, max_age_s: int = _DEFAULT_MAX_AGE_S) -> bool:
    age = preview_age_seconds(root)
    return age is not None and age < float(max_age_s)


def load_last_preview_report(root: Path) -> Optional[Dict[str, Any]]:
    path = Path(root) / _REPORT_REL
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def mark_preview_inputs_changed(root: Path, *, source: str) -> Dict[str, Any]:
    """Worker meldet: neue Daten — Preview (König) soll aggregieren."""
    root = Path(root)
    doc = {
        "schema_version": 1,
        "at_utc": _utc_now(),
        "last_source": str(source or "worker")[:80],
    }
    path = root / _INPUTS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def preview_stale_status(root: Path) -> Dict[str, Any]:
    """True wenn Worker-Daten neuer sind als letzter Preview-Lauf."""
    root = Path(root)
    preview_doc: Dict[str, Any] = {}
    inputs_doc: Dict[str, Any] = {}
    try:
        if (root / _STAMP_REL).is_file():
            preview_doc = json.loads((root / _STAMP_REL).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        preview_doc = {}
    try:
        if (root / _INPUTS_REL).is_file():
            inputs_doc = json.loads((root / _INPUTS_REL).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        inputs_doc = {}

    preview_path = root / _STAMP_REL
    inputs_path = root / _INPUTS_REL
    if not preview_path.is_file():
        return {
            "stale": True,
            "reason_de": "Noch kein Preview-Lauf — Command Center aktualisieren.",
            "last_source": str(inputs_doc.get("last_source") or ""),
        }
    if not inputs_path.is_file():
        return {"stale": False, "reason_de": "", "last_source": ""}
    try:
        newer = inputs_path.stat().st_mtime > preview_path.stat().st_mtime
    except OSError:
        preview_ts = _parse_utc(str(preview_doc.get("at_utc") or ""))
        inputs_ts = _parse_utc(str(inputs_doc.get("at_utc") or ""))
        newer = bool(preview_ts and inputs_ts and inputs_ts > preview_ts)
    if not newer:
        return {"stale": False, "reason_de": "", "last_source": ""}
    src = str(inputs_doc.get("last_source") or "Worker")
    return {
        "stale": True,
        "reason_de": f"Neue Daten von {src} — Preview neu für aktuellen Stand.",
        "last_source": src,
    }


def should_skip_gui_preview(
    root: Path,
    *,
    force: bool = False,
    max_age_s: int = _DEFAULT_MAX_AGE_S,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    if force:
        return False, None
    if preview_stale_status(root).get("stale"):
        return False, None
    if not is_preview_fresh(root, max_age_s=max_age_s):
        return False, None
    report = load_last_preview_report(root)
    if report and report.get("overall_pass"):
        return True, report
    return False, None


def mark_gui_preview_done(root: Path, *, mode: str = "stable") -> Dict[str, Any]:
    root = Path(root)
    doc = {"schema_version": 1, "at_utc": _utc_now(), "mode": str(mode)[:40]}
    path = root / _STAMP_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
