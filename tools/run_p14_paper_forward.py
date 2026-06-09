#!/usr/bin/env python3
"""P14 Paper Forward 500 EUR with Trading212 Demo Read-Only Observation."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_decision_cockpit_readonly_snapshot import write_p14_paper_forward_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from integrations.trading212.t212_official_api_schema_snapshot import api_schema_snapshot
from paper.p14.engine import run_p14_paper_forward
from research.g1.hashing import file_sha256
from research.p14.predecessor_verification import verify_predecessors

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P14_PAPER_FORWARD"
OBS = ROOT / "outgoing_cursor_observation" / "p14_paper_forward"

P14_ID = "P14_PAPER_FORWARD_500_EUR_WITH_TRADING212_DEMO_READONLY_OBSERVATION"
P15_ID = "P15_PAPER_PERFORMANCE_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT"
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
    dest = ROOT / "control" / "audit_backups" / ts / "P14_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def extend_pipeline_for_p14() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = list(pipeline.get("phases") or [])
    ids = {str(p.get("id")) for p in phases}
    for phase in phases:
        if str(phase.get("id")) == P13_ID:
            phase["next_phase"] = P14_ID
    if P14_ID not in ids:
        phases.append(
            {
                "id": P14_ID,
                "status": "IN_PROGRESS",
                "next_phase": P15_ID,
                "goal": "500 EUR paper forward with T212 demo read-only observation.",
            }
        )
    if P15_ID not in ids:
        phases.append(
            {
                "id": P15_ID,
                "status": "NOT_STARTED",
                "next_phase": None,
                "goal": "Paper performance and virtual capital scaling decision support.",
            }
        )
    pipeline["phases"] = phases
    pipeline["current_phase"] = P14_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def run_p14() -> Dict[str, Any]:
    run_id = f"p14_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()

    pred = verify_predecessors(ROOT)
    if not pred.get("all_predecessors_verified"):
        return {"p14_status": "BLOCKED_PREDECESSOR_INCOMPLETE", "predecessor_verification": pred}

    extend_pipeline_for_p14()
    forward = run_p14_paper_forward(ROOT)

    atomic_write_json(DOCS / "P14_PREDECESSOR_PHASE_HASH_VERIFICATION.json", pred)
    (DOCS / "P14_PREDECESSOR_PHASE_VERIFICATION_REPORT.md").write_text(
        "\n".join(
            [
                "# P14 Predecessor Verification",
                "",
                f"All verified: {pred.get('all_predecessors_verified')}",
                f"Highest phase: {pred.get('highest_locally_verified_phase')}",
                "",
            ]
            + [f"- {p['label']}: {p['verification_status']}" for p in pred.get("phases") or []]
        ),
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P14_PHASE_ROUTING_DECISION.json",
        {"routing": P14_ID, "predecessor": pred, "api_schema": api_schema_snapshot()},
    )

    p14_status = forward.get("implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p14_status": p14_status,
        "predecessor_verification": pred,
        "forward": forward,
        "isolation_mode": "GIT_WORKTREE_WITH_UNCOMMITTED_CHANGES",
        "project_root": str(ROOT),
        "start_baseline": _git_head(),
    }

    p15_prompt = "# P15 — Paper Performance and Virtual Capital Scaling Decision Support\n\nSeparate work unit only.\n"
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p15_prompt, encoding="utf-8")

    if str(p14_status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P14_ID)
        result["p15_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p15_enqueue"] = {"ok": False, "message": "P14 gate not PASS"}

    write_p14_paper_forward_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P14_PAPER_FORWARD" / run_id / "p14_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p14_status", "FAILED")
    (OBS / "CURSOR_P14_EXECUTION_REPORT.md").write_text(
        f"# P14 Execution Report\n\nStatus: **{status}**\n\nRun: {result.get('run_id')}\n",
        encoding="utf-8",
    )
    p15 = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p15.is_file():
        shutil.copy2(p15, OBS / "CURSOR_P15_ENQUEUED_WORK_UNIT_PROMPT.md")
    (OBS / "CURSOR_P14_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        f"# P14 Assessment\n\nStatus: {status}\nChampion unchanged.\n",
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p14_paper_forward_package.zip"
    include = [DOCS, Path("paper/config"), Path("paper/p14"), Path("integrations/trading212")]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in include:
            bp = ROOT / base
            if not bp.exists():
                continue
            for fp in bp.rglob("*"):
                if fp.is_file() and "__pycache__" not in fp.parts and not fp.name.endswith(".pyc"):
                    rel = fp.relative_to(ROOT).as_posix()
                    zf.write(fp, rel)
                    hash_manifest[rel] = file_sha256(fp)
        tool = ROOT / "tools/run_p14_paper_forward.py"
        zf.write(tool, "tools/run_p14_paper_forward.py")
        hash_manifest["tools/run_p14_paper_forward.py"] = file_sha256(tool)
    zh = file_sha256(zip_path)
    (OBS / "cursor_p14_paper_forward_package.zip.sha256").write_text(
        f"{zh}  cursor_p14_paper_forward_package.zip\n", encoding="utf-8"
    )
    hash_manifest["cursor_p14_paper_forward_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P14_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p14()
    if result.get("p14_status") == "BLOCKED_PREDECESSOR_INCOMPLETE":
        print(json.dumps(result, indent=2))
        return 1
    out = build_output_package(result)
    print(json.dumps({"p14_status": result.get("p14_status"), "dir": str(out.resolve())}, indent=2))
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p14_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
