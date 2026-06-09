#!/usr/bin/env python3
"""Build a single ChatGPT submission folder for P14 (message + attachments)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outgoing_cursor_observation" / "p14_paper_forward"
TARGET = ROOT / "Daten fuer Reviewer" / "EINREICHUNG_P14_PaperForward"
LEGACY = ROOT / "Daten fuer Reviewer" / "p14_paper_forward_jetzt_einreichen"
LEGACY_MSG = ROOT / "Daten fuer Reviewer" / "CHATGPT_ESKALATION_P14_PAPER_FORWARD.txt"

ATTACHMENTS = [
    "cursor_p14_paper_forward_package.zip",
    "cursor_p14_paper_forward_package.zip.sha256",
    "CURSOR_P14_EXECUTION_REPORT.md",
    "CURSOR_P14_HASH_MANIFEST.json",
    "CURSOR_P14_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
    "CURSOR_P15_ENQUEUED_WORK_UNIT_PROMPT.md",
]

MESSAGE = """================================================================================
CHATGPT-EINREICHUNG P14 — Copy-Paste unten, alle anderen Dateien in DIESEM Ordner anhängen
================================================================================

--- BEGINN NACHRICHT ---

Betreff: Verbindliche Review- und Freigabeentscheidung — P14 Paper Forward (500 EUR, Trading 212 Demo Read-Only) abgeschlossen; P15 erforderlich

Sehr geehrter externer Reviewer,

wir eskalieren zur verbindlichen Entscheidung über **P14** und die **nächste zulässige Entwicklungsstufe P15**.

Bitte antwortet in **einer Nachricht** mit klarer Freigabe oder präziser Blockerliste.


----------------------------------------------------------------------
1. STAND
----------------------------------------------------------------------

Git HEAD: e4685bb62b00e4cbf7c2626f050a2a31cd001f5b
Champion: R3_w075_q065_noexit (unverändert)
REAL_MONEY=NO | BROKER_ORDERS=DISABLED | SIMULATION_ONLY=YES

P10–P14 lokal verifiziert, nicht zurückgesetzt.
P14: PASS_WITH_TRADING212_CREDENTIALS_PENDING
Run: p14_20260601T135134Z | Tests: 7 passed


----------------------------------------------------------------------
2. P14 ERGEBNIS
----------------------------------------------------------------------

User-Referenzportfolio (Screenshot, nicht als Ledger verifiziert):
  8/8 gemappt (OXY, VUSD, WDC, SNDK, STX, INTC, MU, CIEN), 500 EUR

Model A (fractional): portfolio ~499,31 EUR, net_pnl -0,69 EUR, CIEN non-executable
Model B (whole units): portfolio ~499,52 EUR, MU+CIEN non-executable

Trading-212 Demo: AWAITING_CREDENTIALS (non-blocking), read-only, keine Orders
Runtime: RUNNING_PAPER_FORWARD_SIMULATION_ONLY


----------------------------------------------------------------------
3. ANHÄNGE (alle fünf Dateien + ZIP in dieser Submission)
----------------------------------------------------------------------

  cursor_p14_paper_forward_package.zip
  SHA256: 1fd104cfd26b0977f1993f89bfef30a7c92b4666e3576314f281e8362a2adb5d
  + Sidecar, Execution Report, Hash Manifest, Assessment, P15 Prompt


----------------------------------------------------------------------
4. ERWARTETE ANTWORT
----------------------------------------------------------------------

  P14_SPINE_ACCEPTED = YES | NO | CONDITIONAL
  P14_TRADING212_DEMO_READ_ONLY_ARCHITECTURE = APPROVED | BLOCKED
  P14_USER_REFERENCE_PORTFOLIO_HANDLING = ACCEPTED | NEEDS_REMEDIATION
  P14_TRADING212_CREDENTIALS_PENDING = ACCEPTED_AS_NON_BLOCKING | BLOCKING
  NAECHSTE_PHASE = P15 | HOLD | REMEDIATE_P14
  P15_PAPER_PERFORMANCE_SCALING = APPROVED | BLOCKED
  BLOCKER_LIST = (leer oder nummeriert)
  CURSOR_NEXT_PROMPT = (ein Absatz, falls P15 freigegeben)

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
    missing = [name for name in ATTACHMENTS if not (SOURCE / name).is_file()]
    if missing:
        print(f"Missing source files in {SOURCE}: {missing}", file=sys.stderr)
        return 1

    if TARGET.is_dir():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    for name in ATTACHMENTS:
        shutil.copy2(SOURCE / name, TARGET / name)
    (TARGET / "CHATGPT_NACHRICHT.txt").write_text(MESSAGE, encoding="utf-8")

    if LEGACY.is_dir():
        shutil.rmtree(LEGACY)
    if LEGACY_MSG.is_file():
        LEGACY_MSG.unlink()

    files = sorted(p.name for p in TARGET.iterdir() if p.is_file())
    print(f"Created: {TARGET}")
    print("Files:", ", ".join(files))
    _open_folder(TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
