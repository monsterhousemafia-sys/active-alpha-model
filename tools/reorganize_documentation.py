#!/usr/bin/env python3
"""One-time / idempotent documentation layout under docs/."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KEEP_AT_ROOT = {
    "AGENTS.md",
    "IMPLEMENTATION_STATUS.md",
    "REPO_HYGIENE.md",
    "NEXT_CURSOR_PROMPT.md",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md",
    "VISION_PROGRESS.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "DEVELOPMENT_PIPELINE.json",
    "Marktanalyse.exe.sha256",
}

APPROVAL_PREFIX = "EXTERNAL_REVIEW_APPROVAL_"
PHASE_ORDER = (
    "P9A",
    "V1R3",
    "V1R2",
    "V1R",
    "V2R",
    "V4R3",
    "V4R2",
    "V4R",
    "V5R",
    "V0R",
    "G2",
    "G1",
    "G0",
    "V0",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _phase_for_codex(name: str) -> str | None:
    if not name.startswith("CODEX_"):
        return None
    for phase in PHASE_ORDER:
        if name.startswith(f"CODEX_{phase}_"):
            return phase
    if name.startswith("CODEX_MATRIX_"):
        return "governance"
    return "misc"


def _target_for(name: str) -> Path | None:
    if name in KEEP_AT_ROOT or name.startswith(APPROVAL_PREFIX):
        return None
    if name.endswith("_EXTERNAL_REVIEW_STATUS.md") and name[0] in "GP":
        return ROOT / "docs" / "review" / "status" / name
    if name in {"CONTROL_AUTHORIZATION_CONFLICT_REPORT.md", "G1_COMPARISON_LOGIC.md"}:
        return ROOT / "docs" / "governance" / name
    if name.startswith("CODEX_") and name.endswith("_PROTECTED_HASHES_BEFORE.json"):
        phase = _phase_for_codex(name.replace("_PROTECTED_HASHES_BEFORE.json", "")) or "misc"
        return ROOT / "docs" / "integrity" / "protected_hashes" / phase / name
    if name.startswith("CODEX_") and name.endswith("_PROTECTED_HASHES_AFTER.json"):
        phase = _phase_for_codex(name.replace("_PROTECTED_HASHES_AFTER.json", "")) or "misc"
        return ROOT / "docs" / "integrity" / "protected_hashes" / phase / name
    if name.startswith("CODEX_") and (
        name.endswith("_GIT_STATUS.txt")
        or name.endswith("_BUILD_LOG.txt")
        or name.endswith("_TEST_OUTPUT.txt")
        or name.endswith("_PREBUILD_TEST_OUTPUT.txt")
        or name.endswith("_POSTBUILD_TEST_OUTPUT.txt")
        or name.endswith(".log")
    ):
        phase = _phase_for_codex(name.split("_GIT")[0].split("_BUILD")[0].split("_TEST")[0].split("_PRE")[0].split("_POST")[0]) or "misc"
        if not phase or phase == "misc":
            m = re.match(r"CODEX_([A-Z0-9]+)_", name)
            phase = m.group(1) if m else "misc"
        return ROOT / "docs" / "integrity" / "session_logs" / phase / name
    if name.startswith("CODEX_"):
        phase = _phase_for_codex(name) or "misc"
        folder = "governance" if phase == "governance" else "phases" / Path()  # fix below
        if phase == "governance":
            return ROOT / "docs" / "governance" / name
        return ROOT / "docs" / "phases" / phase / name
    if name.startswith("codex_") and name.endswith(".zip.sha256"):
        return ROOT / "docs" / "review" / "sidecars" / name
    if name == "EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md":
        return ROOT / "docs" / "review" / "templates" / name
    return None


def _target_for_fixed(name: str) -> Path | None:
    if name in KEEP_AT_ROOT or name.startswith(APPROVAL_PREFIX):
        return None
    if name.endswith("_EXTERNAL_REVIEW_STATUS.md") and (name.startswith("G") or name.startswith("P9")):
        return ROOT / "docs" / "review" / "status" / name
    if name in {"CONTROL_AUTHORIZATION_CONFLICT_REPORT.md", "G1_COMPARISON_LOGIC.md"}:
        return ROOT / "docs" / "governance" / name
    if name.startswith("CODEX_") and "_PROTECTED_HASHES_BEFORE.json" in name:
        phase = _phase_for_codex(name.replace("_PROTECTED_HASHES_BEFORE.json", "")) or "misc"
        return ROOT / "docs" / "integrity" / "protected_hashes" / phase / name
    if name.startswith("CODEX_") and "_PROTECTED_HASHES_AFTER.json" in name:
        phase = _phase_for_codex(name.replace("_PROTECTED_HASHES_AFTER.json", "")) or "misc"
        return ROOT / "docs" / "integrity" / "protected_hashes" / phase / name
    if name.startswith("CODEX_") and any(
        name.endswith(s)
        for s in (
            "_GIT_STATUS.txt",
            "_BUILD_LOG.txt",
            "_TEST_OUTPUT.txt",
            "_PREBUILD_TEST_OUTPUT.txt",
            "_POSTBUILD_TEST_OUTPUT.txt",
            "_REVIEW_ZIP_SHA256.txt",
        )
    ) or (name.startswith("CODEX_") and name.endswith(".log")):
        m = re.match(r"CODEX_([A-Z0-9]+)_", name)
        phase = m.group(1) if m else "misc"
        return ROOT / "docs" / "integrity" / "session_logs" / phase / name
    if name.startswith("CODEX_") and name.endswith(".json") and "PROTECTED" not in name:
        phase = _phase_for_codex(name) or "misc"
        if phase == "governance":
            return ROOT / "docs" / "governance" / name
        return ROOT / "docs" / "phases" / phase / name
    if name.startswith("CODEX_"):
        phase = _phase_for_codex(name) or "misc"
        if phase == "governance":
            return ROOT / "docs" / "governance" / name
        return ROOT / "docs" / "phases" / phase / name
    if name.startswith("codex_") and name.endswith(".zip.sha256"):
        return ROOT / "docs" / "review" / "sidecars" / name
    if name == "EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md":
        return ROOT / "docs" / "review" / "templates" / name
    return None


def collect_moves() -> dict[str, str]:
    moves: dict[str, str] = {}
    for path in sorted(ROOT.iterdir()):
        if not path.is_file():
            continue
        target = _target_for_fixed(path.name)
        if target is None:
            continue
        moves[path.name] = str(target.relative_to(ROOT)).replace("\\", "/")
    return moves


def apply_moves(moves: dict[str, str]) -> list[str]:
    moved = []
    for name, rel in moves.items():
        src = ROOT / name
        dst = ROOT / rel
        if not src.is_file():
            alt = ROOT / rel
            if alt.is_file():
                continue
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file():
            continue
        shutil.move(str(src), str(dst))
        moved.append(name)
    return moved


def write_doc_paths(moves: dict[str, str]) -> None:
    lines = [
        '"""Canonical documentation paths (relocated under docs/)."""',
        "from __future__ import annotations",
        "",
        "from pathlib import Path",
        "",
        "ROOT = Path(__file__).resolve().parent",
        "",
        "KEEP_AT_ROOT = frozenset({",
    ]
    for k in sorted(KEEP_AT_ROOT):
        lines.append(f'    "{k}",')
    lines.append("})")
    lines.append("")
    lines.append("RELOCATED: dict[str, str] = {")
    for k in sorted(moves):
        lines.append(f'    "{k}": "{moves[k]}",')
    lines.append("}")
    lines.append("")
    lines.append("")
    lines.append("def doc_path(name: str) -> Path:")
    lines.append('    """Resolve documentation file (legacy root basename -> docs layout)."""')
    lines.append("    rel = RELOCATED.get(name)")
    lines.append("    if rel:")
    lines.append("        return ROOT / rel")
    lines.append("    return ROOT / name")
    lines.append("")
    lines.append("")
    lines.append("def doc_rel(name: str) -> str:")
    lines.append('    """Relative path string for ZIP manifests and reports."""')
    lines.append("    return str(doc_path(name).relative_to(ROOT)).replace(chr(92), '/')")
    lines.append("")
    (ROOT / "aa_doc_paths.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    moves = collect_moves()
    moved = apply_moves(moves)
    write_doc_paths(moves)
    manifest = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "moved_count": len(moved),
        "moved": moved,
        "relocated_total": len(moves),
    }
    out = ROOT / "docs" / "reorganization_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
