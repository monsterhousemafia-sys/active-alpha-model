#!/usr/bin/env python3
"""One-shot repo hygiene: archive loose root clutter, remove duplicates (no model changes)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "evidence" / "archive" / "20260602_ui_cleanup"

# Regenerable PyInstaller scratch
REMOVABLE_DIR_GLOBS = (
    "build/decision_cockpit/work",
    "build/decision_cockpit/work_fail_closed_test",
)

# Stale duplicate smoke evidence
STALE_EVIDENCE = (
    "evidence/p16g_interactive_gui_smoke_test_result.json",
    "evidence/p17_interactive_gui_smoke_test_result.json",
    "evidence/interactive_cockpit_full_function_matrix.json.bak",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _archive_path(src: Path) -> Path:
    try:
        rel = src.relative_to(ROOT)
    except ValueError:
        rel = Path(src.name)
    dest = ARCHIVE / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    return dest


def main() -> int:
    actions: list[dict] = []
    ARCHIVE.mkdir(parents=True, exist_ok=True)

    for rel in STALE_EVIDENCE:
        path = ROOT / rel
        if path.is_file():
            dest = _archive_path(path)
            if dest.exists():
                path.unlink()
                actions.append({"action": "deleted_stale_duplicate", "path": rel})
            else:
                shutil.move(str(path), str(dest))
                actions.append({"action": "archived_stale_evidence", "path": rel})

    for rel in REMOVABLE_DIR_GLOBS:
        path = ROOT / rel
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            actions.append({"action": "removed_build_workdir", "path": rel})

    # Root-level duplicate review zips (keep sidecars in docs/)
    for src in sorted(ROOT.glob("codex_*_resubmission.zip")):
        if not src.is_file():
            continue
        dest = _archive_path(src)
        if dest.exists():
            src.unlink()
        else:
            shutil.move(str(src), str(dest))
        actions.append({"action": "archived_root_zip", "path": src.name})

    # Orphan pytest cache at repo root only (not .venv)
    pycache = ROOT / "__pycache__"
    if pycache.is_dir():
        shutil.rmtree(pycache, ignore_errors=True)
        actions.append({"action": "removed_root_pycache", "path": "__pycache__"})

    report = {
        "generated_at_utc": _utc_now(),
        "archive_dir": str(ARCHIVE.relative_to(ROOT)),
        "actions": actions,
        "action_count": len(actions),
    }
    out = ROOT / "evidence" / "repo_cleanup_session_report.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
