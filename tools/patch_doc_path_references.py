#!/usr/bin/env python3
"""Patch Python sources to use aa_doc_paths.doc_path for relocated docs."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa_doc_paths import RELOCATED  # noqa: E402

BASES = ("ROOT", "MAIN", "MAIN_ROOT", "WT", "cwd")

PATTERN = re.compile(
    r"(?P<base>ROOT|MAIN|MAIN_ROOT|WT|cwd)\s*/\s*\"(?P<name>(?:CODEX_|codex_)[^\"]+)\""
)


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "CODEX_" not in text and "codex_" not in text:
        return False
    new_text = PATTERN.sub(lambda m: f'doc_path("{m.group("name")}")', text)
    if new_text == text:
        return False
    if "from aa_doc_paths import" not in new_text:
        if new_text.startswith('"""') or new_text.startswith("'''"):
            end = new_text.find('"""', 3) if new_text.startswith('"""') else new_text.find("'''", 3)
            insert_at = end + 3
            while insert_at < len(new_text) and new_text[insert_at] in "\r\n":
                insert_at += 1
            new_text = (
                new_text[:insert_at]
                + "\nfrom aa_doc_paths import doc_path, doc_rel\n"
                + new_text[insert_at:]
            )
        else:
            new_text = "from aa_doc_paths import doc_path, doc_rel\n" + new_text
    elif "doc_path" not in new_text.split("import")[1].split("\n")[0]:
        new_text = new_text.replace(
            "from aa_doc_paths import doc_rel",
            "from aa_doc_paths import doc_path, doc_rel",
        ).replace(
            "from aa_doc_paths import doc_path\n",
            "from aa_doc_paths import doc_path, doc_rel\n",
        )
    path.write_text(new_text, encoding="utf-8")
    return True


def patch_include_lists(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    for name in RELOCATED:
        old = f'"{name}"'
        new = f"doc_rel({old})"
        if old in text and new not in text:
            text = text.replace(old, new)
            changed = True
    if not changed:
        return False
    if "from aa_doc_paths import" not in text:
        text = "from aa_doc_paths import doc_path, doc_rel\n" + text
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    patched = []
    for glob in ("tools/*.py", "tests/*.py", "aa_*.py"):
        for path in ROOT.glob(glob):
            if path.name in {"aa_doc_paths.py", "patch_doc_path_references.py", "reorganize_documentation.py"}:
                continue
            if patch_file(path) or patch_include_lists(path):
                patched.append(str(path.relative_to(ROOT)))
    print("\n".join(patched))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
