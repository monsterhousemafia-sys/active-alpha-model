"""Mission / Aufklärung — einmalig im Preview-Hub lesen."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

_REL = Path("control/PREVIEW_MANIFEST_DE.json")


def load_preview_manifest(root: Path) -> Dict[str, Any]:
    root = Path(root)
    path = root / _REL
    if not path.is_file():
        return {
            "schema_version": 1,
            "required_read": True,
            "title_de": "Active Alpha",
            "one_liner_de": "Offene Research-Plattform auf Linux.",
            "sections": [],
            "ack_button_de": "Verstanden",
            "storage_key": "aa_manifest_v1_ack",
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def manifest_sections_html(sections: List[Dict[str, Any]]) -> str:
    import html

    rows = []
    for s in sections:
        rows.append(
            f"<article class='mf-block'><h3>{html.escape(str(s.get('headline_de') or ''))}</h3>"
            f"<p>{html.escape(str(s.get('body_de') or ''))}</p></article>"
        )
    return "".join(rows)
