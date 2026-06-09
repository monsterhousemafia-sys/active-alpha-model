#!/usr/bin/env python3
"""Report repo hygiene: dirty counts, archive size, forbidden-touch paths."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FORBIDDEN_TOUCH = (
    "promotion_gate_config.yaml",
    "control/operational_champion.json",
    "control/last_known_good_state.json",
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "model_output_sp500_pit_t212/strategy_daily_returns.csv",
)

AUTHORITATIVE_EVIDENCE = Path("control/evidence")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def main() -> int:
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [ln for ln in status.stdout.splitlines() if ln.strip()]
    untracked = sum(1 for ln in lines if ln.startswith("??"))
    modified = sum(1 for ln in lines if ln.startswith(" M") or ln.startswith("M "))

    archive = ROOT / "evidence" / "archive"
    archive_bytes = _dir_size(archive)
    archive_files = sum(1 for _ in archive.rglob("*") if _.is_file()) if archive.is_dir() else 0

    report = {
        "generated_at_utc": _utc_now(),
        "git_short_status_lines": len(lines),
        "git_untracked": untracked,
        "git_modified": modified,
        "evidence_archive_files": archive_files,
        "evidence_archive_bytes": archive_bytes,
        "authoritative_evidence_dir": str(AUTHORITATIVE_EVIDENCE),
        "forbidden_touch_paths": list(FORBIDDEN_TOUCH),
        "notes": [
            "Regenerable artefacts belong under evidence/archive/ (gitignored).",
            "Gate JSON belongs under control/evidence/ only via export tools.",
        ],
    }
    out = ROOT / "control" / "repo_hygiene_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
