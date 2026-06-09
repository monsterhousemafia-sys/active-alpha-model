#!/usr/bin/env python3
"""P12C Prospective Forward Paper Trading Evaluation."""
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

from aa_decision_cockpit_readonly_snapshot import write_p12c_forward_paper_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from research.g1.hashing import file_sha256
from research.p12c.constants import PAPER_INITIAL_CAPITAL_EUR, REAL_MONEY_CAPITAL_EUR
from research.p12c.forward_runner import run_forward_paper_evaluation

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P12C_FORWARD_PAPER_TRADING"
OBS = ROOT / "outgoing_cursor_observation" / "p12c_forward_paper_trading"

P12B_ID = "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE"
P12C_ID = "P12C_PROSPECTIVE_FORWARD_PAPER_TRADING_EVALUATION"
P13_ID = "P13_CAPITAL_SCALING_READINESS_AND_DISABLED_BROKER_ADAPTER"
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
    dest = ROOT / "control" / "audit_backups" / ts / "P12C_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def mark_p12c_in_progress() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    for phase in pipeline.get("phases") or []:
        if str(phase.get("id")) == P12C_ID:
            phase["status"] = "IN_PROGRESS"
    pipeline["current_phase"] = P12C_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def verify_p12b_preserved(pipeline: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures = []
    p12b = next((p for p in pipeline.get("phases") or [] if p.get("id") == P12B_ID), None)
    if not p12b or str(p12b.get("status")) != "PASS":
        failures.append(P12B_ID)
    if resolve_locked_champion(ROOT) != CHAMPION:
        failures.append("CHAMPION_CHANGED")
    return not failures, failures


def _resolve_p12c_status(preserved: bool, forward: Dict[str, Any]) -> str:
    if not preserved:
        return "FAILED_REQUIRING_LOCAL_REPAIR"
    status = forward.get("paper_trading_status", "")
    if status == "FAILED_DATA_QUALITY_GATE":
        return "FAILED_DATA_QUALITY_GATE"
    if status == "FAILED_EXECUTION_MODEL_GATE":
        return "FAILED_EXECUTION_MODEL_GATE"
    if status == "COMPLETED_EVALUATION_WINDOW" and forward.get("lookahead_verified"):
        return "PASS_WITH_FORWARD_PAPER_EVALUATION_COMPLETE"
    return "PASS_WITH_EXPLICIT_FORWARD_LIMITATIONS"


def run_p12c() -> Dict[str, Any]:
    run_id = f"p12c_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()
    pipeline = mark_p12c_in_progress()
    preserved, preservation_failures = verify_p12b_preserved(pipeline)

    forward = run_forward_paper_evaluation(ROOT)
    p12c_status = _resolve_p12c_status(preserved, forward)

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p12c_status": p12c_status,
        "pipeline_preserved": preserved,
        "pipeline_preservation_failures": preservation_failures,
        "forward_evaluation": forward,
        "safety": {
            "simulation_only": True,
            "real_money": False,
            "broker_order_submission": False,
            "live_trading": False,
            "champion_changed": False,
            "initial_paper_capital_eur": PAPER_INITIAL_CAPITAL_EUR,
            "real_money_capital_eur": REAL_MONEY_CAPITAL_EUR,
        },
    }

    atomic_write_json(DOCS / "P12C_FORWARD_EVALUATION.json", result)
    atomic_write_json(DOCS / "P12C_SAFETY_BOUNDARY_VERIFICATION.json", result["safety"])

    p13_prompt = "\n".join(
        [
            "# P13 — Capital Scaling Readiness and Disabled Broker Adapter",
            "",
            "Execute as **separate work unit** only.",
            "",
            "BROKER_ADAPTER_ENABLED = NO | REAL_ORDER_ROUTING_ENABLED = NO",
            "",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p13_prompt, encoding="utf-8")

    if p12c_status.startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P12C_ID)
        result["p13_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p13_enqueue"] = {"ok": False, "message": "P12C gate not PASS"}

    write_p12c_forward_paper_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P12C_FORWARD_PAPER" / run_id / "p12c_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p12c_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    ev = result.get("forward_evaluation", {}).get("evaluation", {})
    (OBS / "CURSOR_P12C_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P12C Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                "",
                f"Paper status: {result.get('forward_evaluation', {}).get('paper_trading_status')}",
                f"Portfolio value EUR: {ev.get('current_portfolio_value_eur')}",
                f"Net PnL EUR: {ev.get('cumulative_net_performance_eur')}",
                "",
                "Prospective forward evaluation — simulation only.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    p13 = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p13.is_file():
        shutil.copy2(p13, OBS / "CURSOR_P13_ENQUEUED_WORK_UNIT_PROMPT.md")

    (OBS / "CURSOR_P12C_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P12C Objective Technical Assessment",
                "",
                f"Status: {status}",
                f"Lookahead verified: {result.get('forward_evaluation', {}).get('lookahead_verified')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p12c_forward_paper_trading_package.zip"
    include = [
        DOCS,
        Path("research/p12c"),
        Path("paper_output/p12c_forward"),
        Path("control/review_snapshot/p12c_forward_paper_trading_snapshot.json"),
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
        tool = ROOT / "tools/run_p12c_forward_paper_trading.py"
        if tool.is_file():
            zf.write(tool, "tools/run_p12c_forward_paper_trading.py")
            hash_manifest["tools/run_p12c_forward_paper_trading.py"] = file_sha256(tool)

    zh = file_sha256(zip_path)
    (OBS / "cursor_p12c_forward_paper_trading_package.zip.sha256").write_text(
        f"{zh}  cursor_p12c_forward_paper_trading_package.zip\n",
        encoding="utf-8",
    )
    hash_manifest["cursor_p12c_forward_paper_trading_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P12C_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p12c()
    out = build_output_package(result)
    print(
        json.dumps(
            {"p12c_status": result.get("p12c_status"), "p13_enqueue": result.get("p13_enqueue"), "dir": str(out.resolve())},
            indent=2,
        )
    )
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p12c_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
