#!/usr/bin/env python3
"""P12B Virtual Execution Engine and 500 EUR Paper Portfolio."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_decision_cockpit_readonly_snapshot import write_p12b_virtual_execution_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from research.g1.hashing import file_sha256
from research.p12b.constants import PAPER_INITIAL_CAPITAL_EUR, REAL_MONEY_CAPITAL_EUR
from research.p12b.engine import run_virtual_engine_cycle

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P12B_VIRTUAL_EXECUTION_ENGINE"
OBS = ROOT / "outgoing_cursor_observation" / "p12b_virtual_execution_engine"

P12A_ID = "P12A_READ_ONLY_ONLINE_MARKET_DATA_INGESTION"
P12B_ID = "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE"
P12C_ID = "P12C_PROSPECTIVE_FORWARD_PAPER_TRADING_EVALUATION"
CHAMPION = "R3_w075_q065_noexit"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def backup_pipeline_state() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ROOT / "control" / "audit_backups" / ts / "P12B_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def mark_p12b_in_progress() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    for phase in pipeline.get("phases") or []:
        if str(phase.get("id")) == P12B_ID:
            phase["status"] = "IN_PROGRESS"
    pipeline["current_phase"] = P12B_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def verify_p12a_preserved(pipeline: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures = []
    p12a = next((p for p in pipeline.get("phases") or [] if p.get("id") == P12A_ID), None)
    if not p12a or str(p12a.get("status")) != "PASS":
        failures.append(P12A_ID)
    if resolve_locked_champion(ROOT) != CHAMPION:
        failures.append("CHAMPION_CHANGED")
    return not failures, failures


def _resolve_p12b_status(preserved: bool, cycle: Dict[str, Any]) -> str:
    if not preserved:
        return "FAILED_REQUIRING_LOCAL_REPAIR"
    if not cycle.get("cash_reconciliation", {}).get("reconciled"):
        return "FAILED_CASH_RECONCILIATION"
    if not cycle.get("lifecycle", {}).get("has_fill"):
        return "FAILED_EXECUTION_MODEL_GATE"
    if cycle.get("metrics", {}).get("initial_capital_eur") != PAPER_INITIAL_CAPITAL_EUR:
        return "FAILED_CAPITAL_INITIALIZATION"
    return "PASS_WITH_VIRTUAL_PAPER_PORTFOLIO_READY"


def run_p12b() -> Dict[str, Any]:
    run_id = f"p12b_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()
    pipeline = mark_p12b_in_progress()
    preserved, preservation_failures = verify_p12a_preserved(pipeline)

    cycle = run_virtual_engine_cycle(ROOT)
    p12b_status = _resolve_p12b_status(preserved, cycle)

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p12b_status": p12b_status,
        "pipeline_preserved": preserved,
        "pipeline_preservation_failures": preservation_failures,
        "engine_cycle": cycle,
        "safety": {
            "simulation_only": True,
            "real_money": False,
            "broker_order_submission": False,
            "broker_order_routing": False,
            "live_trading": False,
            "champion_changed": False,
            "initial_paper_capital_eur": PAPER_INITIAL_CAPITAL_EUR,
            "real_money_capital_eur": REAL_MONEY_CAPITAL_EUR,
            "paper_leverage_enabled": False,
            "paper_shorting_enabled": False,
        },
    }

    atomic_write_json(DOCS / "P12B_ENGINE_RESULT.json", result)
    atomic_write_json(DOCS / "P12B_SAFETY_BOUNDARY_VERIFICATION.json", result["safety"])

    p12c_prompt = "\n".join(
        [
            "# P12C — Prospective Forward Paper Trading Evaluation",
            "",
            "Execute as **separate work unit** only.",
            "",
            "INITIAL_PAPER_CAPITAL_EUR = 500.00",
            "REAL_MONEY = NO | BROKER_ORDER_SENT = NO | NOT_LIVE_AUTHORIZED = YES",
            "",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p12c_prompt, encoding="utf-8")

    if p12b_status.startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P12B_ID)
        result["p12c_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p12c_enqueue"] = {"ok": False, "message": "P12B gate not PASS"}

    write_p12b_virtual_execution_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P12B_VIRTUAL_EXECUTION" / run_id / "p12b_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p12b_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    (OBS / "CURSOR_P12B_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P12B Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                "",
                f"Initial capital: {PAPER_INITIAL_CAPITAL_EUR} EUR",
                f"Fills: {len(result.get('engine_cycle', {}).get('execution', {}).get('fills', []))}",
                "",
                "Virtual order lifecycle, fees, FX, reconciliation — no broker routing.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    p12c = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p12c.is_file():
        shutil.copy2(p12c, OBS / "CURSOR_P12C_ENQUEUED_WORK_UNIT_PROMPT.md")

    (OBS / "CURSOR_P12B_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P12B Objective Technical Assessment",
                "",
                f"Status: {status}",
                f"Portfolio value EUR: {result.get('engine_cycle', {}).get('metrics', {}).get('portfolio_value_eur')}",
                f"Whole-unit constraint: fractional_shares_enabled=False",
                "",
            ]
        ),
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p12b_virtual_execution_engine_package.zip"
    include = [
        DOCS,
        Path("research/p12b"),
        Path("paper_output/p12b_virtual"),
        Path("control/review_snapshot/p12b_virtual_execution_engine_snapshot.json"),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in include:
            bp = ROOT / base
            if not bp.exists():
                continue
            if bp.is_file():
                rel = bp.relative_to(ROOT).as_posix()
                zf.write(bp, rel)
                hash_manifest[rel] = file_sha256(bp)
                continue
            for fp in bp.rglob("*"):
                if fp.is_file() and "__pycache__" not in fp.parts and not fp.name.endswith(".pyc"):
                    rel = fp.relative_to(ROOT).as_posix()
                    zf.write(fp, rel)
                    hash_manifest[rel] = file_sha256(fp)
        tool = ROOT / "tools/run_p12b_virtual_execution_engine.py"
        if tool.is_file():
            zf.write(tool, "tools/run_p12b_virtual_execution_engine.py")
            hash_manifest["tools/run_p12b_virtual_execution_engine.py"] = file_sha256(tool)

    zh = file_sha256(zip_path)
    (OBS / "cursor_p12b_virtual_execution_engine_package.zip.sha256").write_text(
        f"{zh}  cursor_p12b_virtual_execution_engine_package.zip\n",
        encoding="utf-8",
    )
    hash_manifest["cursor_p12b_virtual_execution_engine_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P12B_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p12b()
    out = build_output_package(result)
    print(
        json.dumps(
            {"p12b_status": result.get("p12b_status"), "p12c_enqueue": result.get("p12c_enqueue"), "dir": str(out.resolve())},
            indent=2,
        )
    )
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p12b_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
