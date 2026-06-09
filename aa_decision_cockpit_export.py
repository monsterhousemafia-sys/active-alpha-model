"""Read-only export of Decision Cockpit view model data (V4R isolated paths)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from aa_decision_cockpit_viewmodel import load_decision_cockpit

BLOCKED_EXPORT_PREFIXES = (
    "control",
    "model_output_sp500_pit_t212",
    "validation_runs",
    "runs",
    ".cursor",
    ".git",
)


def validate_export_directory(root: Path, export_dir: Path) -> Tuple[bool, str]:
    """Return (ok, reason). Export must be outside protected project subtrees."""
    root = Path(root).resolve()
    export_dir = Path(export_dir).resolve()
    try:
        export_dir.relative_to(root)
        rel_parts = export_dir.relative_to(root).parts
    except ValueError:
        return True, ""

    if not rel_parts:
        return False, "export_directory_must_not_be_repository_root"

    head = rel_parts[0].lower()
    if head in BLOCKED_EXPORT_PREFIXES:
        return False, f"export_blocked_under_{head}"

    return True, ""


def export_decision_cockpit_json(root: Path, export_dir: Path) -> Path:
    """Write read-only cockpit snapshot to an isolated export directory only."""
    root = Path(root)
    export_dir = Path(export_dir)
    ok, reason = validate_export_directory(root, export_dir)
    if not ok:
        raise ValueError(f"export_path_blocked:{reason}")

    export_dir.mkdir(parents=True, exist_ok=True)
    payload = load_decision_cockpit(root)
    out = export_dir / "decision_cockpit_snapshot.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def cockpit_to_plaintext(data: Dict[str, Any]) -> str:
    lines = []
    for banner in data.get("banners") or []:
        lines.append(f"=== {banner} ===")
    exec_ov = data.get("executive_overview") or {}
    lines.append("\n--- Executive Overview ---")
    for k, v in exec_ov.items():
        lines.append(f"{k}: {v}")
    why = data.get("why_not_promoted") or {}
    lines.append("\n--- Current active blockers ---")
    for b in why.get("current_active_blockers") or []:
        lines.append(f"- {b}")
    lines.append("\n--- Source conflicts ---")
    for c in why.get("source_conflicts") or []:
        lines.append(f"- {c}")
    return "\n".join(lines) + "\n"
