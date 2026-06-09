#!/usr/bin/env python3
"""Build the single ChatGPT reviewer submission folder (message + attachments)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
REVIEWER_ROOT = ROOT / "Daten fuer Reviewer"
TARGET = REVIEWER_ROOT / "EINREICHUNG_jetzt_an_ChatGPT"

LEGACY_FOLDERS = (
    "EINREICHUNG_P14_PaperForward",
    "EINREICHUNG_P15_PaperRuntime",
    "EINREICHUNG_P16_ForwardObservation",
    "p14_paper_forward_jetzt_einreichen",
)

PHASES: Tuple[Tuple[str, str, List[str]], ...] = (
    (
        "P16H",
        "p16h_confirmed_order_workflow",
        [
            "cursor_p16h_confirmed_order_workflow_package.zip",
            "cursor_p16h_confirmed_order_workflow_package.zip.sha256",
            "CURSOR_P16H_EXECUTION_REPORT.md",
            "CURSOR_P16H_HASH_MANIFEST.json",
            "CURSOR_P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16H_PRODUCT_READINESS_ASSESSMENT.md",
            "CURSOR_P16H_CONFIRMED_ORDER_WORKFLOW_POLICY.md",
            "CURSOR_P16H_USER_OPERATION_GUIDE.md",
        ],
    ),
    (
        "P16G",
        "p16g_interactive_desktop_product",
        [
            "cursor_p16g_interactive_desktop_product_package.zip",
            "cursor_p16g_interactive_desktop_product_package.zip.sha256",
            "CURSOR_P16G_EXECUTION_REPORT.md",
            "CURSOR_P16G_HASH_MANIFEST.json",
            "CURSOR_P16G_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16G_PRODUCT_READINESS_ASSESSMENT.md",
            "CURSOR_P16G_NEXT_WORK_UNIT_PROMPT.md",
            "CURSOR_P16G_USER_OPERATION_GUIDE.md",
            "CURSOR_P16G_GUI_AND_EXE_BUILD_REPORT.md",
            "CURSOR_P16G_TRADING212_REQUIRED_INTEGRATION_REPORT.md",
        ],
    ),
    (
        "P16F_DESKTOP",
        "p16f_desktop_product_intraday_trigger",
        [
            "cursor_p16f_desktop_product_intraday_trigger_package.zip",
            "cursor_p16f_desktop_product_intraday_trigger_package.zip.sha256",
            "CURSOR_P16F_EXECUTION_REPORT.md",
            "CURSOR_P16F_HASH_MANIFEST.json",
            "CURSOR_P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16F_PRODUCT_READINESS_ASSESSMENT.md",
            "CURSOR_P16F_NEXT_WORK_UNIT_PROMPT.md",
            "CURSOR_ID0_INTRADAY_BRANCH_PROMPT.md",
            "CURSOR_P16F_MANUAL_LIVE_PILOT_POLICY.md",
            "CURSOR_P16F_INTRADAY_TRIGGER_POLICY_50EUR.md",
            "CURSOR_P16F_GUI_AND_EXE_BUILD_REPORT.md",
        ],
    ),
    (
        "P16F",
        "p16f_manual_ticket_risk_remediation",
        [
            "cursor_p16f_manual_ticket_risk_remediation_package.zip",
            "cursor_p16f_manual_ticket_risk_remediation_package.zip.sha256",
            "CURSOR_P16F_EXECUTION_REPORT.md",
            "CURSOR_P16F_HASH_MANIFEST.json",
            "CURSOR_P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16F_NEXT_WORK_UNIT_PROMPT.md",
            "CURSOR_P16F_MANUAL_LIVE_PILOT_POLICY.md",
        ],
    ),
    (
        "P16E",
        "p16e_fast_track_manual_live_readiness",
        [
            "cursor_p16e_fast_track_manual_live_readiness_package.zip",
            "cursor_p16e_fast_track_manual_live_readiness_package.zip.sha256",
            "CURSOR_P16E_EXECUTION_REPORT.md",
            "CURSOR_P16E_HASH_MANIFEST.json",
            "CURSOR_P16E_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16E_NEXT_WORK_UNIT_PROMPT.md",
            "CURSOR_P16E_MANUAL_LIVE_PILOT_POLICY.md",
        ],
    ),
    (
        "P16D",
        "p16d_validated_forward_runtime",
        [
            "cursor_p16d_validated_forward_runtime_package.zip",
            "cursor_p16d_validated_forward_runtime_package.zip.sha256",
            "CURSOR_P16D_EXECUTION_REPORT.md",
            "CURSOR_P16D_HASH_MANIFEST.json",
            "CURSOR_P16D_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16D_NEXT_WORK_UNIT_PROMPT.md",
        ],
    ),
    (
        "P16C",
        "p16c_forward_runtime_correction",
        [
            "cursor_p16c_forward_runtime_correction_package.zip",
            "cursor_p16c_forward_runtime_correction_package.zip.sha256",
            "CURSOR_P16C_EXECUTION_REPORT.md",
            "CURSOR_P16C_HASH_MANIFEST.json",
            "CURSOR_P16C_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16C_NEXT_WORK_UNIT_PROMPT.md",
        ],
    ),
    (
        "P16B",
        "p16b_continuous_forward_runtime",
        [
            "cursor_p16b_continuous_forward_runtime_package.zip",
            "cursor_p16b_continuous_forward_runtime_package.zip.sha256",
            "CURSOR_P16B_EXECUTION_REPORT.md",
            "CURSOR_P16B_HASH_MANIFEST.json",
            "CURSOR_P16B_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16B_NEXT_WORK_UNIT_PROMPT.md",
        ],
    ),
    (
        "P16",
        "p16_forward_observation_scaling",
        [
            "cursor_p16_forward_observation_scaling_package.zip",
            "cursor_p16_forward_observation_scaling_package.zip.sha256",
            "CURSOR_P16_EXECUTION_REPORT.md",
            "CURSOR_P16_HASH_MANIFEST.json",
            "CURSOR_P16_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16_NEXT_WORK_UNIT_PROMPT.md",
        ],
    ),
    (
        "P15",
        "p15_paper_runtime_validation",
        [
            "cursor_p15_paper_runtime_validation_package.zip",
            "cursor_p15_paper_runtime_validation_package.zip.sha256",
            "CURSOR_P15_EXECUTION_REPORT.md",
            "CURSOR_P15_HASH_MANIFEST.json",
            "CURSOR_P15_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P16_ENQUEUED_WORK_UNIT_PROMPT.md",
        ],
    ),
    (
        "P14",
        "p14_paper_forward",
        [
            "cursor_p14_paper_forward_package.zip",
            "cursor_p14_paper_forward_package.zip.sha256",
            "CURSOR_P14_EXECUTION_REPORT.md",
            "CURSOR_P14_HASH_MANIFEST.json",
            "CURSOR_P14_OBJECTIVE_TECHNICAL_ASSESSMENT.md",
            "CURSOR_P15_ENQUEUED_WORK_UNIT_PROMPT.md",
        ],
    ),
)


def _open_folder(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def _read_sha256(sidecar: Path) -> str:
    if not sidecar.is_file():
        return ""
    parts = sidecar.read_text(encoding="utf-8").strip().split()
    return parts[0] if parts else ""


def _load_runtime_summary(phase: str) -> Dict[str, Any]:
    candidates = {
        "P16H": ROOT / "paper/p16h/p16h_runtime_summary.json",
        "P16G": ROOT / "paper/p16g/p16g_runtime_summary.json",
        "P16F_DESKTOP": ROOT / "paper/p16f/p16f_desktop_runtime_summary.json",
        "P16F": ROOT / "paper/p16f/p16f_runtime_summary.json",
        "P16E": ROOT / "paper/p16e/p16e_runtime_summary.json",
        "P16D": ROOT / "paper/p16d/p16d_runtime_summary.json",
        "P16C": ROOT / "paper/p16c/p16c_runtime_summary.json",
        "P16B": ROOT / "paper/p16b/p16b_runtime_summary.json",
        "P16": ROOT / "paper/p16/p16_runtime_summary.json",
        "P15": ROOT / "paper/p15/p15_runtime_summary.json",
    }
    path = candidates.get(phase)
    if path and path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _pick_phase() -> Optional[Tuple[str, Path, List[str]]]:
    for label, obs_name, files in PHASES:
        source = ROOT / "outgoing_cursor_observation" / obs_name
        zip_name = files[0]
        if (source / zip_name).is_file():
            missing = [f for f in files if not (source / f).is_file()]
            if not missing:
                return label, source, files
    return None


def _build_message(phase: str, source: Path, files: List[str], runtime: Dict[str, Any]) -> str:
    sha = _read_sha256(source / files[1])
    status = runtime.get("p16b_implementation_status") or runtime.get("p16_implementation_status") or runtime.get("implementation_status") or "see Execution Report"
    obs = runtime.get("valid_observation_count", runtime.get("observation_count", "n/a"))
    next_wu = "P16B_CONTINUE_FORWARD_OBSERVATION_WINDOW"
    if phase == "P16H":
        next_wu = "P16H_INTERACTIVE_READONLY_ACCOUNT_MONITORING_AFTER_LOCAL_CREDENTIAL_CONFIGURATION"
        scope = "CONFIRMED_ORDER_WORKFLOW"
        status = runtime.get("p16h_status", status)
    elif phase == "P16G":
        next_wu = "P16H_INTERACTIVE_READONLY_ACCOUNT_MONITORING_AFTER_LOCAL_CREDENTIAL_CONFIGURATION"
        scope = "INTERACTIVE_DESKTOP_T212_READONLY_UI"
        status = runtime.get("p16g_status", status)
    elif phase == "P16F_DESKTOP":
        next_wu = runtime.get("next_work_unit", "P16G_DESKTOP_PRODUCT_READONLY_ACCOUNT_CONFIGURATION_AND_MONITORING")
        scope = "DESKTOP_PRODUCT_INTRADAY_TRIGGER_50EUR"
        status = runtime.get("p16f_desktop_status", status)
    elif phase == "P16F":
        next_wu = "P16G_READONLY_REAL_ACCOUNT_CONFIGURATION_AND_MANUAL_TICKET_GENERATION"
        scope = "MANUAL_TICKET_RISK_REMEDIATION"
        status = runtime.get("p16f_implementation_status", status)
    elif phase == "P16E":
        next_wu = "P16F_MANUAL_LIVE_PILOT_TICKET_REVIEW_AND_READONLY_RECONCILIATION"
        scope = "FAST_TRACK_MANUAL_LIVE_PILOT_READINESS"
        status = runtime.get("p16e_implementation_status", status)
    elif phase == "P16D":
        next_wu = "P16E_CONTINUE_POST_BASELINE_VALIDATED_OBSERVATION_WINDOW"
        scope = "VALIDATED_FORWARD_RUNTIME_HARDENING"
        status = runtime.get("p16d_implementation_status", status)
    elif phase == "P16C":
        next_wu = "P16D_CONTINUE_VALIDATED_FORWARD_OBSERVATION_WINDOW"
        scope = "FORWARD_RUNTIME_CORRECTION"
    elif phase == "P16B":
        next_wu = "P16C_CONTINUE_VALIDATED_FORWARD_OBSERVATION_WINDOW"
        scope = runtime.get("p16b_scope", "CONTINUOUS_FORWARD_PAPER_RUNTIME_REMEDIATION")
    elif phase == "P16":
        next_wu = "P16B_CONTINUE_FORWARD_OBSERVATION_WINDOW"
        scope = runtime.get("p16_scope_classification", "FORWARD_OBSERVATION_AND_SIMULATION_ONLY")
    elif phase == "P15":
        next_wu = "P16_READ_ONLY_FORWARD_OBSERVATION_AND_VIRTUAL_SCALING_EVIDENCE"
        scope = "PAPER_RUNTIME_VALIDATION"
    else:
        next_wu = "P15"
        scope = "PAPER_FORWARD_INITIALIZATION"

    attach_list = "\n".join(f"  - {name}" for name in files)

    return f"""================================================================================
CHATGPT — Copy-Paste unten; alle anderen Dateien in DIESEM Ordner anhängen
Phase: {phase} | Ordner: EINREICHUNG_jetzt_an_ChatGPT
================================================================================

--- BEGINN NACHRICHT ---

Betreff: {phase} Einreichung — Active Alpha Paper Platform (Simulation Only)

Status: {status}
Scope: {scope}
Champion: R3_w075_q065_noexit (unverändert)
REAL_MONEY=NO | BROKER_ORDERS=DISABLED | SIMULATION_ONLY=YES

Kernfakten:
  Forward feed validated: {runtime.get('forward_feed_validated', 'n/a')}
  Valid observations: {obs}
  Data mode: {runtime.get('data_mode', 'n/a')}
  Virtual portfolio ~{runtime.get('paper_observation', {}).get('portfolio_value_eur', 'n/a')} EUR (500 EUR Start)
  T212 provider verified: {runtime.get('t212_provider_verified_mappings', '0/8')}
  Nächste Work Unit: {next_wu}

ZIP SHA256: {sha or 'see .sha256 sidecar'}

Anhänge (alle Dateien in diesem Ordner außer dieser Nachricht):
{attach_list}

Bitte bestätigen:
  {phase}_SPINE_ACCEPTED = YES | NO | CONDITIONAL
  NAECHSTE_PHASE = {next_wu} | HOLD | REMEDIATE

--- ENDE NACHRICHT ---


Dateien in diesem Ordner ({len(files) + 1} Stück):
  1. CHATGPT_NACHRICHT.txt  (dieser Text)
{chr(10).join(f'  {i + 2}. {name}' for i, name in enumerate(files))}
"""


def _cleanup_legacy() -> None:
    for name in LEGACY_FOLDERS:
        path = REVIEWER_ROOT / name
        if path.is_dir():
            shutil.rmtree(path)


def main() -> int:
    picked = _pick_phase()
    if picked is None:
        print("No complete observation package found. Run the latest phase orchestrator first.", file=sys.stderr)
        return 1

    phase, source, files = picked
    runtime = _load_runtime_summary(phase)

    _cleanup_legacy()
    if TARGET.is_dir():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)

    for name in files:
        shutil.copy2(source / name, TARGET / name)

    message = _build_message(phase, source, files, runtime)
    (TARGET / "CHATGPT_NACHRICHT.txt").write_text(message, encoding="utf-8")

    _open_folder(TARGET)
    print(json.dumps({"phase": phase, "folder": str(TARGET), "files": len(files) + 1}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
