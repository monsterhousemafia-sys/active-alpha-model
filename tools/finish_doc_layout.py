#!/usr/bin/env python3
"""Finalize docs/ layout: protected hashes, RELOCATED map, misc cleanups."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISC = ROOT / "docs/integrity/protected_hashes/misc"
DOC_PATHS = ROOT / "aa_doc_paths.py"
HASH_RE = re.compile(
    r"^CODEX_(?P<phase>[A-Z0-9]+)_PROTECTED_HASHES_(?P<when>BEFORE|AFTER)\.json$"
)


def move_protected_hashes() -> list[tuple[str, str]]:
    moves: list[tuple[str, str]] = []
    wrong_g0 = ROOT / "docs/integrity/protected_hashes/G0"
    if wrong_g0.is_file():
        dest_dir = ROOT / "docs/integrity/protected_hashes/G0_dir"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "CODEX_G0_PROTECTED_HASHES_AFTER.json"
        if not dest.is_file():
            shutil.move(str(wrong_g0), str(dest))
            moves.append(("protected_hashes/G0", dest.name))
        dest_dir.rename(ROOT / "docs/integrity/protected_hashes/G0")
    if MISC.is_dir():
        for src in sorted(MISC.glob("CODEX_*_PROTECTED_HASHES_*.json")):
            m = HASH_RE.match(src.name)
            if not m:
                continue
            phase = m.group("phase")
            dest_dir = ROOT / "docs/integrity/protected_hashes" / phase
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            if dest.is_file():
                src.unlink()
            else:
                shutil.move(str(src), str(dest))
            moves.append((f"misc/{src.name}", str(dest.relative_to(ROOT)).replace("\\", "/")))
        if MISC.is_dir() and not any(MISC.iterdir()):
            MISC.rmdir()
    return moves


def sync_relocated_map() -> int:
    text = DOC_PATHS.read_text(encoding="utf-8")
    updated = text
    updated = updated.replace(
        "docs/phases/misc/CODEX_EXTERNAL_REVIEW_DECISION_PACKET.md",
        "docs/review/CODEX_EXTERNAL_REVIEW_DECISION_PACKET.md",
    )
    updated = updated.replace(
        "docs/phases/misc/CODEX_RISK_OFF_CHALLENGER_EVIDENCE_REPORT.md",
        "docs/governance/CODEX_RISK_OFF_CHALLENGER_EVIDENCE_REPORT.md",
    )
    updated = updated.replace(
        "docs/phases/V0R/CODEX_V0R_HOOK_STATUS.txt",
        "docs/phases/V0R/CODEX_V0R_HOOK_STATUS.txt",
    )
    updated = re.sub(
        r"docs/integrity/protected_hashes/misc/(CODEX_([A-Z0-9]+)_PROTECTED_HASHES_[^\"]+\.json)",
        r"docs/integrity/protected_hashes/\2/\1",
        updated,
    )
    if updated != text:
        DOC_PATHS.write_text(updated, encoding="utf-8")
    return int(updated != text)


def main() -> int:
    moves = move_protected_hashes()
    map_changed = sync_relocated_map()
    manifest = ROOT / "docs/reorganization_manifest.json"
    payload = {}
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["finish_layout"] = {
        "hash_moves": moves,
        "relocated_map_synced": bool(map_changed),
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"hash_moves": len(moves), "relocated_map_synced": map_changed}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
