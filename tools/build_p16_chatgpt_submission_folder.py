#!/usr/bin/env python3
"""Build a single ChatGPT submission folder for P16."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outgoing_cursor_observation" / "p16_forward_observation_scaling"
TARGET = ROOT / "Daten fuer Reviewer" / "EINREICHUNG_P16_ForwardObservation"

ATTACHMENTS = [
    "cursor_p16_forward_observation_scaling_package.zip",
    "cursor_p16_forward_observation_scaling_package.zip.sha256",
    "CURSOR_P16_EXECUTION_REPORT.md",
    "CURSOR_P16_HASH_MANIFEST.json",
    "CURSOR_P16_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
    "CURSOR_P16_NEXT_WORK_UNIT_PROMPT.md",
]

MESSAGE = """================================================================================
CHATGPT-EINREICHUNG P16 — Copy-Paste unten, alle anderen Dateien in DIESEM Ordner anhängen
================================================================================

--- BEGINN NACHRICHT ---

Betreff: P16 abgeschlossen — Read-Only Forward Observation + Virtual Scaling Evidence

P16 STATUS: PASS_FORWARD_OBSERVATION_RUNNING_SAMPLE_INSUFFICIENT (oder siehe Execution Report)
Scope: FORWARD_OBSERVATION_AND_SIMULATION_ONLY — Real-Money-Dossier NOT_DECISION_READY
Champion: R3_w075_q065_noexit | REAL_MONEY=NO | BROKER_ORDERS=DISABLED

Nächste Work Unit: P16B_CONTINUE_FORWARD_OBSERVATION_WINDOW (wenn Sample < Mindestfenster)

Bitte bestätigen:
  P16_SPINE_ACCEPTED = YES | NO | CONDITIONAL
  NAECHSTE_PHASE = P16B | P17 | HOLD

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
        print(f"Run tools/run_p16_forward_observation_scaling.py first. Missing: {missing}", file=sys.stderr)
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
