#!/usr/bin/env python3
"""Ensure tools can import aa_doc_paths when run as scripts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_IMPORT = re.compile(
    r"^from aa_doc_paths import .+\n",
    re.M,
)
BOOTSTRAP = """import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

"""


def needs_bootstrap(text: str) -> bool:
    if "from aa_doc_paths import" not in text:
        return False
    idx = text.find("from aa_doc_paths import")
    before = text[:idx]
    return "_REPO_ROOT" not in before and "sys.path.insert(0" not in before


def insert_bootstrap(text: str) -> str:
    m = DOC_IMPORT.search(text)
    if not m:
        return text
    return text[: m.start()] + BOOTSTRAP + text[m.start() :]


def fix_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not needs_bootstrap(text):
        return False
    path.write_text(insert_bootstrap(text), encoding="utf-8")
    return True


def main() -> int:
    changed = 0
    for path in sorted(ROOT.glob("tools/*.py")):
        if fix_file(path):
            changed += 1
            print(path.relative_to(ROOT))
    print(f"fixed {changed} tool(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
