#!/usr/bin/env python3
"""P12A Read-Only Online Market Data Ingestion."""
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

from aa_decision_cockpit_readonly_snapshot import write_p12a_online_market_data_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from research.g1.hashing import file_sha256
from research.p12a.constants import INITIAL_PAPER_CAPITAL_EUR, REAL_MONEY_CAPITAL_EUR
from research.p12a.ingestion import run_ingestion_cycle

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P12A_ONLINE_MARKET_DATA_INGESTION"
OBS = ROOT / "outgoing_cursor_observation" / "p12a_online_market_data_ingestion"

P11_ID = "P11_COST_STRESS_AND_STATISTICAL_RESEARCH_VALIDATION"
P12A_ID = "P12A_READ_ONLY_ONLINE_MARKET_DATA_INGESTION"
P12B_ID = "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE"
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
    dest = ROOT / "control" / "audit_backups" / ts / "P12A_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def mark_p12a_in_progress() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    for phase in pipeline.get("phases") or []:
        if str(phase.get("id")) == P12A_ID:
            phase["status"] = "IN_PROGRESS"
    pipeline["current_phase"] = P12A_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def verify_p11_preserved(pipeline: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures = []
    p11 = next((p for p in pipeline.get("phases") or [] if p.get("id") == P11_ID), None)
    if not p11 or str(p11.get("status")) != "PASS":
        failures.append(P11_ID)
    if resolve_locked_champion(ROOT) != CHAMPION:
        failures.append("CHAMPION_CHANGED")
    return not failures, failures


def _resolve_p12a_status(preserved: bool, ingestion: Dict[str, Any]) -> str:
    if not preserved:
        return "FAILED_REQUIRING_LOCAL_REPAIR"
    if not ingestion.get("quality_passed"):
        return "FAILED_DATA_QUALITY_GATE"
    if not ingestion.get("replay_deterministic"):
        return "FAILED_REPLAY_DETERMINISM_GATE"
    return "PASS_WITH_READONLY_ONLINE_INGESTION_READY"


def run_p12a(*, force_online: bool = False) -> Dict[str, Any]:
    run_id = f"p12a_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()
    pipeline = mark_p12a_in_progress()
    preserved, preservation_failures = verify_p11_preserved(pipeline)

    ingestion = run_ingestion_cycle(ROOT, force_online=force_online)
    p12a_status = _resolve_p12a_status(preserved, ingestion)

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p12a_status": p12a_status,
        "pipeline_preserved": preserved,
        "pipeline_preservation_failures": preservation_failures,
        "ingestion": ingestion,
        "safety": {
            "simulation_only": True,
            "real_money": False,
            "broker_order_submission": False,
            "live_trading": False,
            "broker_order_routing": False,
            "champion_changed": False,
            "initial_paper_capital_eur": INITIAL_PAPER_CAPITAL_EUR,
            "real_money_capital_eur": REAL_MONEY_CAPITAL_EUR,
        },
    }

    atomic_write_json(DOCS / "P12A_INGESTION_RESULT.json", result)
    atomic_write_json(DOCS / "P12A_SAFETY_BOUNDARY_VERIFICATION.json", result["safety"])

    p12b_prompt = "\n".join(
        [
            "# P12B — Virtual Execution Engine and 500 EUR Paper Portfolio",
            "",
            "Execute as **separate work unit** only.",
            "",
            "INITIAL_PAPER_CAPITAL_EUR = 500.00",
            "REAL_MONEY = NO | BROKER_ORDER_SENT = NO | NOT_LIVE_AUTHORIZED = YES",
            "",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p12b_prompt, encoding="utf-8")

    if p12a_status.startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P12A_ID)
        result["p12b_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p12b_enqueue"] = {"ok": False, "message": "P12A gate not PASS"}

    write_p12a_online_market_data_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P12A_ONLINE_INGESTION" / run_id / "p12a_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p12a_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    (OBS / "CURSOR_P12A_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P12A Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                "",
                "## Deliverables",
                "- Read-only provider adapters (replay fixture + optional yfinance)",
                "- Raw immutable store + observation ledger + normalized store",
                "- Data quality gates (missing/stale/outlier)",
                "- Replay determinism verification",
                "- Provider health in control/p12a_provider_health.json",
                "",
                "No broker orders. No live trading. Champion unchanged.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    p12b = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p12b.is_file():
        shutil.copy2(p12b, OBS / "CURSOR_P12B_ENQUEUED_WORK_UNIT_PROMPT.md")

    (OBS / "CURSOR_P12A_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P12A Objective Technical Assessment",
                "",
                f"Status: {status}",
                f"Provider: {result.get('ingestion', {}).get('provider')}",
                f"Quality: {result.get('ingestion', {}).get('quality_status')}",
                f"Replay deterministic: {result.get('ingestion', {}).get('replay_deterministic')}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p12a_online_market_data_ingestion_package.zip"
    include = [
        DOCS,
        Path("research/p12a"),
        Path("market_data/p12a_online_ingestion"),
        Path("control/p12a_provider_health.json"),
        Path("control/review_snapshot/p12a_online_market_data_ingestion_snapshot.json"),
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
        tool = ROOT / "tools/run_p12a_online_market_data_ingestion.py"
        if tool.is_file():
            zf.write(tool, "tools/run_p12a_online_market_data_ingestion.py")
            hash_manifest["tools/run_p12a_online_market_data_ingestion.py"] = file_sha256(tool)

    zh = file_sha256(zip_path)
    (OBS / "cursor_p12a_online_market_data_ingestion_package.zip.sha256").write_text(
        f"{zh}  cursor_p12a_online_market_data_ingestion_package.zip\n",
        encoding="utf-8",
    )
    hash_manifest["cursor_p12a_online_market_data_ingestion_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P12A_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-online", action="store_true")
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p12a(force_online=args.force_online)
    out = build_output_package(result)
    print(
        json.dumps(
            {"p12a_status": result.get("p12a_status"), "p12b_enqueue": result.get("p12b_enqueue"), "dir": str(out.resolve())},
            indent=2,
        )
    )
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p12a_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
