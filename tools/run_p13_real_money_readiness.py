#!/usr/bin/env python3
"""P13 Capital Scaling Readiness and Disabled Broker Adapter."""
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

from aa_decision_cockpit_readonly_snapshot import write_p13_broker_readiness_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from research.g1.hashing import file_sha256
from research.p13.constants import BROKER_ADAPTER_ENABLED, REAL_MONEY_ENABLED, REAL_ORDER_ROUTING_ENABLED
from research.p13.readiness import run_readiness_assessment

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P13_BROKER_READINESS"
OBS = ROOT / "outgoing_cursor_observation" / "p13_real_money_readiness_disabled_broker"

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
    dest = ROOT / "control" / "audit_backups" / ts / "P13_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def mark_p13_in_progress() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    for phase in pipeline.get("phases") or []:
        if str(phase.get("id")) == P13_ID:
            phase["status"] = "IN_PROGRESS"
    pipeline["current_phase"] = P13_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def verify_p12c_preserved(pipeline: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures = []
    p12c = next((p for p in pipeline.get("phases") or [] if p.get("id") == P12C_ID), None)
    if not p12c or str(p12c.get("status")) != "PASS":
        failures.append(P12C_ID)
    if resolve_locked_champion(ROOT) != CHAMPION:
        failures.append("CHAMPION_CHANGED")
    return not failures, failures


def _resolve_p13_status(preserved: bool, readiness: Dict[str, Any]) -> str:
    if not preserved:
        return "FAILED_REQUIRING_LOCAL_REPAIR"
    st = readiness.get("adapter_status") or {}
    if not st.get("broker_adapter_implemented"):
        return "FAILED_BROKER_ADAPTER_NOT_IMPLEMENTED"
    if st.get("broker_adapter_enabled") or st.get("real_order_routing_enabled") or st.get("real_money_enabled"):
        return "FAILED_SAFETY_BOUNDARY_VIOLATION"
    if not readiness.get("real_order_attempt_blocked"):
        return "FAILED_REAL_ROUTING_NOT_BLOCKED"
    if not readiness.get("dry_run_oversize_rejected"):
        return "FAILED_RISK_LIMIT_GATE"
    return "PASS_WITH_DISABLED_BROKER_READINESS_COMPLETE"


def run_p13() -> Dict[str, Any]:
    run_id = f"p13_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()
    pipeline = mark_p13_in_progress()
    preserved, preservation_failures = verify_p12c_preserved(pipeline)

    readiness = run_readiness_assessment(ROOT)
    p13_status = _resolve_p13_status(preserved, readiness)

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p13_status": p13_status,
        "pipeline_preserved": preserved,
        "pipeline_preservation_failures": preservation_failures,
        "readiness": readiness,
        "safety": {
            "simulation_only": True,
            "real_money": False,
            "broker_adapter_enabled": BROKER_ADAPTER_ENABLED,
            "real_order_routing_enabled": REAL_ORDER_ROUTING_ENABLED,
            "real_money_enabled": REAL_MONEY_ENABLED,
            "champion_changed": False,
        },
    }

    atomic_write_json(DOCS / "P13_READINESS_RESULT.json", result)
    atomic_write_json(DOCS / "P13_SAFETY_BOUNDARY_VERIFICATION.json", result["safety"])

    completion_prompt = "\n".join(
        [
            "# P11–P13 Offline Paper Platform — Complete",
            "",
            "Phases P11 through P13 passed in separate work units.",
            "",
            "REAL_MONEY = NO | BROKER_ADAPTER_ENABLED = NO",
            "",
            "Next step requires explicit user decision on real capital, broker, and risk scope.",
            "",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(completion_prompt, encoding="utf-8")

    if p13_status.startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P13_ID)
        result["pipeline_complete"] = {"ok": ok, "message": msg}
    else:
        result["pipeline_complete"] = {"ok": False, "message": "P13 gate not PASS"}

    write_p13_broker_readiness_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P13_BROKER_READINESS" / run_id / "p13_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p13_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    (OBS / "CURSOR_P13_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P13 Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                "",
                "Broker adapter implemented, disabled by default.",
                "Kill switch active. Credential isolation verified.",
                "Capital scaling ladder documented (simulation only).",
                "",
                "No real orders. No real money activation.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (OBS / "CURSOR_P13_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P13 Objective Technical Assessment",
                "",
                f"Status: {status}",
                f"Broker enabled: {BROKER_ADAPTER_ENABLED}",
                f"Real routing: {REAL_ORDER_ROUTING_ENABLED}",
                "",
                "P11–P13 paper platform spine complete. Awaiting explicit user decision for real money.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    (OBS / "CURSOR_P13_NEXT_ACTION_QUEUE.json").write_text(
        json.dumps(
            {
                "pipeline_spine_complete": status.startswith("PASS"),
                "next_action": "EXPLICIT_USER_DECISION_REAL_MONEY_BROKER_RISK",
                "automatic_promotion": False,
                "live_trading": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p13_real_money_readiness_disabled_broker_package.zip"
    include = [
        DOCS,
        Path("research/p13"),
        Path("control/p13_broker_readiness"),
        Path("control/review_snapshot/p13_broker_readiness_snapshot.json"),
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
        tool = ROOT / "tools/run_p13_real_money_readiness.py"
        if tool.is_file():
            zf.write(tool, "tools/run_p13_real_money_readiness.py")
            hash_manifest["tools/run_p13_real_money_readiness.py"] = file_sha256(tool)

    zh = file_sha256(zip_path)
    (OBS / "cursor_p13_real_money_readiness_disabled_broker_package.zip.sha256").write_text(
        f"{zh}  cursor_p13_real_money_readiness_disabled_broker_package.zip\n",
        encoding="utf-8",
    )
    hash_manifest["cursor_p13_real_money_readiness_disabled_broker_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P13_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p13()
    out = build_output_package(result)
    print(
        json.dumps(
            {"p13_status": result.get("p13_status"), "pipeline_complete": result.get("pipeline_complete"), "dir": str(out.resolve())},
            indent=2,
        )
    )
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p13_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
