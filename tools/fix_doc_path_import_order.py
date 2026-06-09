#!/usr/bin/env python3
"""Move aa_doc_paths imports below module docstring / __future__."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORT_LINE = "from aa_doc_paths import doc_path, doc_rel\n"
PATTERN = re.compile(r"^from aa_doc_paths import doc_path, doc_rel\n", re.M)


def fix(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if IMPORT_LINE.strip() not in text:
        return False
    text = PATTERN.sub("", text, count=1)
    if 'from __future__ import' in text:
        text = re.sub(
            r"(from __future__ import annotations\n)",
            r"\1\n" + IMPORT_LINE,
            text,
            count=1,
        )
    elif text.startswith("#!"):
        lines = text.splitlines(keepends=True)
        idx = 0
        if lines[0].startswith("#!"):
            idx = 1
        while idx < len(lines) and (lines[idx].strip().startswith('"""') or lines[idx].strip() == ""):
            idx += 1
            if idx > 1 and '"""' in lines[idx - 1]:
                break
        # after docstring block
        if idx < len(lines) and '"""' in "".join(lines[: idx + 1]):
            for i, line in enumerate(lines):
                if line.count('"""') and i > 0:
                    idx = i + 1
                    break
        lines.insert(idx, "\n" + IMPORT_LINE)
        text = "".join(lines)
    else:
        text = IMPORT_LINE + text
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    n = 0
    for path in list(ROOT.glob("tools/*.py")) + list(ROOT.glob("tests/*.py")):
        if fix(path):
            n += 1
    print(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
