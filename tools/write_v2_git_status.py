"""Write CODEX_V2_GIT_STATUS.txt from git commands."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"
OUT = doc_path("CODEX_V2_GIT_STATUS.txt")


def git_output(args: list[str]) -> str:
    proc = subprocess.run([GIT, *args], capture_output=True, text=True, cwd=ROOT, check=False)
    return (proc.stdout or proc.stderr or "").strip()


def main() -> None:
    existing = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
    if "# AFTER V2 REMEDIATION COMMIT" not in existing:
        sections = [
            existing.rstrip(),
            "# AFTER V2 REMEDIATION COMMIT",
            git_output(["status", "--short", "--branch"]),
            git_output(["log", "--oneline", "--decorate", "--all", "-n", "20"]),
            git_output(["rev-parse", "HEAD"]),
        ]
        OUT.write_text("\n\n".join(s for s in sections if s) + "\n", encoding="utf-8")
    else:
        sections = [
            "# BEFORE V2 REMEDIATION",
            git_output(["status", "--short", "--branch"]),
            git_output(["log", "--oneline", "--decorate", "--all", "-n", "20"]),
            git_output(["rev-parse", "HEAD"]),
        ]
        OUT.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
