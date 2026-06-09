#!/usr/bin/env python3
"""Single entry: bootstrap G0R4R3 transport, run remediation, stage reviewer folder."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.is_file():
    PY = Path(sys.executable)

REVIEWER_PASS = ROOT / "Daten fuer Reviewer" / "G0R4R3_jetzt_einreichen"
REVIEWER_BLOCKED = ROOT / "Daten fuer Reviewer" / "G0R4R3_BLOCKED_jetzt_an_Reviewer"
OUT_PASS = ROOT / "outgoing_external_reviews" / "g0r4r3"
OUT_BLOCKED = ROOT / "outgoing_external_reviews" / "g0r4r3_BLOCKED"
DROPIN_SHA = "02b1d97f845d5d666ef852bf3c4cd725bfe54efb05f73cc47663e772c3b879c7"
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "outgoing_external_reviews"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_drop_in() -> Path | None:
    for dirpath, dirnames, filenames in __import__("os").walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        if Path(dirpath).parts and Path(dirpath).parts[0] == "outgoing_external_reviews":
            continue
        for fn in filenames:
            if fn == "G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT.zip" or fn.startswith(
                "G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT"
            ):
                p = Path(dirpath) / fn
                if p.is_file() and sha256_file(p) == DROPIN_SHA:
                    return p
    return None


def stage_reviewer_copy(src_dir: Path, dest_dir: Path) -> None:
    if not src_dir.is_dir():
        return
    dest_dir.mkdir(parents=True, exist_ok=True)
    for existing in dest_dir.iterdir():
        if existing.is_file():
            existing.unlink()
    for src in sorted(src_dir.iterdir()):
        if src.is_file():
            shutil.copy2(src, dest_dir / src.name)


def run_step(script: str) -> int:
    proc = subprocess.run([str(PY), str(TOOLS / script)], cwd=ROOT, check=False)
    return proc.returncode


def main() -> int:
    found = find_drop_in()
    if found:
        print(f"G0R4R3 drop-in detected: {found}")
    else:
        print("G0R4R3 drop-in not found; attempting bootstrap fallback on preinstalled bundle")

    run_step("_g0r4r3_drop_in_bootstrap.py")
    rc = run_step("complete_g0r4r3_submission.py")

    if OUT_PASS.is_dir() and any(OUT_PASS.iterdir()):
        stage_reviewer_copy(OUT_PASS, REVIEWER_PASS)
        print(f"PASS artefacts staged: {REVIEWER_PASS}")
    elif OUT_BLOCKED.is_dir() and any(OUT_BLOCKED.iterdir()):
        stage_reviewer_copy(OUT_BLOCKED, REVIEWER_BLOCKED)
        msg = REVIEWER_BLOCKED / "CHATGPT_TRANSPORT_FEHLT_NACHRICHT.txt"
        if not msg.is_file():
            msg.write_text(
                "G0R4R3 BLOCKED: REQUIRED_G0R4R3_TRANSPORT_INPUT_NOT_FOUND_OR_INVALID\n"
                "Drop-in: G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT.zip\n"
                "SHA-256: 02b1d97f845d5d666ef852bf3c4cd725bfe54efb05f73cc47663e772c3b879c7\n",
                encoding="utf-8",
            )
        print(f"BLOCKED diagnostics staged: {REVIEWER_BLOCKED}")

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
