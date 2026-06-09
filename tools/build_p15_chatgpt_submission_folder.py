#!/usr/bin/env python3
"""Build a single ChatGPT submission folder for P15."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outgoing_cursor_observation" / "p15_paper_runtime_validation"
TARGET = ROOT / "Daten fuer Reviewer" / "EINREICHUNG_P15_PaperRuntime"

ATTACHMENTS = [
    "cursor_p15_paper_runtime_validation_package.zip",
    "cursor_p15_paper_runtime_validation_package.zip.sha256",
    "CURSOR_P15_EXECUTION_REPORT.md",
    "CURSOR_P15_HASH_MANIFEST.json",
    "CURSOR_P15_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
    "CURSOR_P16_ENQUEUED_WORK_UNIT_PROMPT.md",
]

MESSAGE = """================================================================================
CHATGPT-EINREICHUNG P15 — Copy-Paste unten, alle anderen Dateien in DIESEM Ordner anhängen
================================================================================

--- BEGINN NACHRICHT ---

Betreff: P15 abgeschlossen — Paper Runtime Validation (conditional P14 basis)

P15 STATUS: PASS_RUNTIME_IMPLEMENTED_TRADING212_CREDENTIALS_OPTIONAL_PENDING
P14: CONDITIONAL preserved | Forward runtime: NOT_YET_PROVEN on live feed
Champion: R3_w075_q065_noexit | REAL_MONEY=NO | BROKER_ORDERS=DISABLED

Blocker remediated:
  B001 Runtime status model corrected
  B002 Static vs provider mapping (0/8 provider verified, 8/8 static candidates)
  B003 Test evidence packaged (20 passed)
  B004 T212 guard hardened (exact URL + GET allowlist)
  B005 P15 execution prompt replaced

Nächste Phase: P16 Virtual Scaling Evaluation and Real-Money Decision Dossier

Bitte bestätigen:
  P15_SPINE_ACCEPTED = YES | NO | CONDITIONAL
  NAECHSTE_PHASE = P16 | HOLD | REMEDIATE_P15

--- ENDE NACHRICHT ---
"""


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    missing = [n for n in ATTACHMENTS if not (SOURCE / n).is_file()]
    if missing:
        print(f"Run tools/run_p15_paper_runtime_validation.py first. Missing: {missing}", file=sys.stderr)
        return 1
    if TARGET.is_dir():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    for name in ATTACHMENTS:
        shutil.copy2(SOURCE / name, TARGET / name)
    (TARGET / "CHATGPT_NACHRICHT.txt").write_text(MESSAGE, encoding="utf-8")
    _open_folder(TARGET)
    print(f"Created: {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
