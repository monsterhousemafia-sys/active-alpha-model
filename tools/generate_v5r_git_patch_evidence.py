"""Generate git show patch evidence for V5R external audit."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
GIT = Path(r"C:\Program Files\Git\cmd\git.exe")
VALIDATED_BASE = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"
REQUIRED_BASE_PATCHES = ("70652b9", "a47a8fe")


def _git(args: list[str]) -> str:
    proc = subprocess.run([str(GIT), *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def _commits_after(base: str) -> list[str]:
    text = _git(["log", "--reverse", "--format=%H", f"{base}..HEAD"]).strip()
    return [line.strip() for line in text.splitlines() if line.strip()]


def main() -> int:
    if not GIT.is_file():
        raise SystemExit("git not found")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for short in REQUIRED_BASE_PATCHES:
        out = EVIDENCE / f"git_show_{short}.patch"
        out.write_text(_git(["show", "--patch", short]), encoding="utf-8")
        written.append(out.name)
    for full in _commits_after(VALIDATED_BASE):
        short = full[:7]
        out = EVIDENCE / f"git_show_{short}.patch"
        out.write_text(_git(["show", "--patch", full]), encoding="utf-8")
        written.append(out.name)
    manifest = EVIDENCE / "v5r_git_patch_manifest.txt"
    manifest.write_text("\n".join(sorted(set(written))) + "\n", encoding="utf-8")
    print(f"wrote {len(set(written))} patch files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
