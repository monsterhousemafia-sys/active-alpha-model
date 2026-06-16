#!/usr/bin/env python3
"""Remove development clutter and regenerable data junk (no model/champion/validation runs)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARCHIVE_NAME = "active_alpha_model_monolith_backup.py"

REMOVE_FILES = (
    "active_alpha_model.diff",
    "active_alpha_control_center.diff",
    "aa_dashboard.diff",
    "run_active_alpha_model.diff",
    "build_launcher.log",
    ".marktanalyse_setup_hint",
    "marktanalyse_last_run.log",
)

REMOVE_DIRS = (
    ".pytest_cache",
    "__pycache__",
)

ROOT_LOG_GLOBS = ("*.log", "build_launcher_*.log")
ROOT_BACKUP_GLOBS = ("*.bak", "*.bak1", "*.bak2")
REVIEW_ZIP_GLOB = "codex_*.zip"
LEGACY_GIT_GLOB = ".git.legacy-backup-*"
EVIDENCE_LOG_GLOBS = ("evidence/**/*.log", "validation_runs/**/*.log")
MODEL_LOG_GLOBS = ("model_output_sp500_pit_t212/*.log",)
SPREAD_PROFILE_REL = Path("control/secrets/whatsapp_firefox_profile")
REPAIR_BACKUPS_REL = Path("control/repair_backups")
REPORT_REL = Path("evidence/project_junk_cleanup_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _skip(path: Path) -> bool:
    parts = path.parts
    return ".venv" in parts or "Marktanalyse" in parts


def _purge_pycache(base: Path) -> List[str]:
    removed: List[str] = []
    for path in base.rglob("__pycache__"):
        if _skip(path):
            continue
        shutil.rmtree(path, ignore_errors=True)
        try:
            removed.append(str(path.relative_to(ROOT)))
        except ValueError:
            removed.append(str(path))
    return removed


def _delete_path(path: Path, *, dry_run: bool) -> str:
    if not path.exists() or _skip(path):
        return ""
    rel = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name
    if dry_run:
        return f"dry-run delete: {rel}"
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)
    except OSError:
        return ""
    return rel


def cleanup(
    root: Path,
    *,
    dry_run: bool = False,
    aggressive: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    actions: List[str] = []
    bytes_hint = 0

    for name in REMOVE_FILES:
        hit = _delete_path(root / name, dry_run=dry_run)
        if hit:
            actions.append(hit)

    for name in REMOVE_DIRS:
        hit = _delete_path(root / name, dry_run=dry_run)
        if hit:
            actions.append(hit)

    actions.extend(_purge_pycache(root))

    for pattern in ROOT_BACKUP_GLOBS + ROOT_LOG_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                hit = _delete_path(path, dry_run=dry_run)
                if hit:
                    actions.append(hit)

    for path in sorted(root.glob(REVIEW_ZIP_GLOB)):
        if path.is_file():
            hit = _delete_path(path, dry_run=dry_run)
            if hit:
                actions.append(hit)

    for path in sorted(root.glob(LEGACY_GIT_GLOB)):
        hit = _delete_path(path, dry_run=dry_run)
        if hit:
            actions.append(hit)

    for path in sorted((root / ".cursor").glob("debug*.log")):
        hit = _delete_path(path, dry_run=dry_run)
        if hit:
            actions.append(hit)

    for pattern in EVIDENCE_LOG_GLOBS + MODEL_LOG_GLOBS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                hit = _delete_path(path, dry_run=dry_run)
                if hit:
                    actions.append(hit)

    backup = root / ARCHIVE_NAME
    if backup.is_file():
        if dry_run:
            actions.append(f"dry-run archive: {ARCHIVE_NAME}")
        else:
            archive_dir = root / "archive"
            archive_dir.mkdir(exist_ok=True)
            target = archive_dir / ARCHIVE_NAME
            if target.is_file():
                target.unlink()
            backup.replace(target)
            actions.append(f"{ARCHIVE_NAME} -> archive/")

    if aggressive:
        spread = root / SPREAD_PROFILE_REL
        if spread.is_dir():
            try:
                bytes_hint += sum(f.stat().st_size for f in spread.rglob("*") if f.is_file())
            except OSError:
                pass
            hit = _delete_path(spread, dry_run=dry_run)
            if hit:
                actions.append(f"spread_browser_profile: {hit}")

        repair = root / REPAIR_BACKUPS_REL
        if repair.is_dir():
            hit = _delete_path(repair, dry_run=dry_run)
            if hit:
                actions.append(f"repair_backups: {hit}")

    # Remove stale project_junk archives from prior runs (regenerable clutter)
    archive_root = root / "evidence" / "archive"
    if archive_root.is_dir():
        for old in sorted(archive_root.glob("project_junk_*")):
            hit = _delete_path(old, dry_run=dry_run)
            if hit:
                actions.append(f"old_cleanup_archive: {hit}")

    report: Dict[str, Any] = {
        "schema_version": 1,
        "cleaned_at_utc": _utc_now(),
        "dry_run": dry_run,
        "aggressive": aggressive,
        "action_count": len(actions),
        "actions": actions[:200],
        "archive_dir": None,
        "bytes_hint_spread_profile": bytes_hint if aggressive else 0,
        "protected_de": [
            "model_output_sp500_pit_t212 (Caches, CSV, Champion-Signal)",
            "validation_runs (H1-Backtest)",
            "control/ (Policies, außer repair_backups bei --aggressive)",
            "evidence/*.json (Audit-Artefakte)",
        ],
    }

    if not dry_run:
        from aa_safe_io import atomic_write_json

        atomic_write_json(root / REPORT_REL, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="Also delete spread Firefox profile + repair_backups (regenerable)",
    )
    args = parser.parse_args()
    report = cleanup(ROOT, dry_run=args.dry_run, aggressive=args.aggressive)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report.get("actions"):
        print("[CLEANUP OK] Nichts zu entfernen.")
    else:
        mode = "DRY-RUN" if args.dry_run else "OK"
        print(f"[CLEANUP {mode}] {report['action_count']} Aktionen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
