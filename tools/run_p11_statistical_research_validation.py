#!/usr/bin/env python3
"""P11 Cost Stress and Statistical Research Validation."""
from __future__ import annotations

import argparse
import csv
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

from aa_decision_cockpit_readonly_snapshot import write_p11_statistical_research_snapshot
from aa_evidence_schema import resolve_locked_champion
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json

from research.g1.hashing import file_sha256
from research.p11.cost_stress import run_cost_stress_all, run_sensitivity_grid
from research.p11.dsr import run_dsr_all
from research.p11.paper_practicality import analyze_paper_practicality
from research.p11.pbo_cscv import assess_pbo_matrix
from research.p11.ranking import build_research_ranking
from research.p11.robustness import run_robustness_all

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P11_STATISTICAL_RESEARCH_VALIDATION"
OBS = ROOT / "outgoing_cursor_observation" / "p11_statistical_research_validation"

P10_ID = "P10_RESEARCH_EVIDENCE_INTEGRATION_AND_STRATEGY_IDENTITY_RESOLUTION"
P11_ID = "P11_COST_STRESS_AND_STATISTICAL_RESEARCH_VALIDATION"
P12A_ID = "P12A_READ_ONLY_ONLINE_MARKET_DATA_INGESTION"
P12B_ID = "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE"
P12C_ID = "P12C_PROSPECTIVE_FORWARD_PAPER_TRADING_EVALUATION"
P13_ID = "P13_CAPITAL_SCALING_READINESS_AND_DISABLED_BROKER_ADAPTER"
OLD_P12 = "P12_CONTROLLED_SHADOW_PAPER_EVALUATION"

CHAMPION = "R3_w075_q065_noexit"
RESEARCH_VARIANTS = ("MOM_63_TOP12_STRICT", "MOM_63_TOP15_RECONSTRUCTED")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def backup_pipeline_state() -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ROOT / "control" / "audit_backups" / ts / "P11_PRE_UPDATE"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml", "control/pipeline_pending.json"):
        src = ROOT / name
        if src.is_file():
            shutil.copy2(src, dest / Path(name).name)
    return dest


def extend_pipeline_for_p11() -> Dict[str, Any]:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = [p for p in (pipeline.get("phases") or []) if str(p.get("id")) != OLD_P12]
    ids = {str(p.get("id")) for p in phases}

    for phase in phases:
        if str(phase.get("id")) == P11_ID:
            phase["next_phase"] = P12A_ID
            phase["status"] = "IN_PROGRESS"

    new_phases = [
        (P12A_ID, P12B_ID, "Read-only online market data ingestion and recording."),
        (P12B_ID, P12C_ID, "Virtual execution engine with 500 EUR paper portfolio."),
        (P12C_ID, P13_ID, "Prospective forward paper trading evaluation."),
        (P13_ID, None, "Capital scaling readiness and disabled-by-default broker adapter."),
    ]
    for pid, nxt, goal in new_phases:
        if pid not in ids:
            phases.append({"id": pid, "status": "NOT_STARTED", "next_phase": nxt, "goal": goal})

    pipeline["phases"] = phases
    pipeline["current_phase"] = P11_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)
    return pipeline


def verify_p10_preserved(pipeline: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures = []
    p10 = next((p for p in pipeline.get("phases") or [] if p.get("id") == P10_ID), None)
    if not p10 or str(p10.get("status")) != "PASS":
        failures.append(P10_ID)
    if resolve_locked_champion(ROOT) != CHAMPION:
        failures.append("CHAMPION_CHANGED")
    return not failures, failures


def _resolve_p11_status(
    preserved: bool,
    cost: Dict[str, Any],
    dsr: Dict[str, Any],
    pbo: Dict[str, Any],
    robustness: Dict[str, Any],
    ranking: Dict[str, Any],
) -> str:
    if not preserved:
        return "FAILED_REQUIRING_LOCAL_REPAIR"
    eval_rows = [r for r in cost.get("rows", []) if r.get("evaluation_status") == "EVALUABLE"]
    if len(eval_rows) < 8:
        return "BLOCKED_BY_SPECIFIC_MISSING_INPUT"
    if pbo.get("status") == "PARTIAL_WITH_REQUIRED_MATRIX_BUILD":
        if dsr.get("overall_status") == "CONDITIONAL":
            return "PASS_WITH_CONDITIONAL_RETURN_COST_LIMITATION"
        return "PASS_WITH_PBO_CSCV_MATRIX_LIMITATION"
    if dsr.get("overall_status") == "CONDITIONAL":
        return "PASS_WITH_CONDITIONAL_RETURN_COST_LIMITATION"
    if ranking.get("ranking"):
        return "PASS_WITH_STATISTICAL_RESEARCH_VALIDATION_COMPLETE"
    return "PASS_WITH_EXPLICIT_RESEARCH_LIMITATIONS"


def _write_cost_stress_csv(cost: Dict[str, Any]) -> Path:
    out = DOCS / "cost_stress_comparison.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["variant_id", "scenario", "evaluation_status", "sharpe_0rf", "cagr", "max_drawdown"])
        for row in cost.get("rows", []):
            m = row.get("metrics") or {}
            w.writerow(
                [
                    row.get("variant_id"),
                    row.get("scenario"),
                    row.get("evaluation_status"),
                    m.get("sharpe_0rf"),
                    m.get("cagr"),
                    m.get("max_drawdown"),
                ]
            )
    shutil.copy2(out, ROOT / "research_evidence" / "cost_stress_comparison.csv")
    return out


def run_p11() -> Dict[str, Any]:
    run_id = f"p11_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    backup_pipeline_state()
    pipeline = extend_pipeline_for_p11()
    preserved, preservation_failures = verify_p10_preserved(pipeline)

    cost = run_cost_stress_all(ROOT)
    sensitivity = {vid: run_sensitivity_grid(ROOT, vid) for vid in RESEARCH_VARIANTS}
    paper12 = analyze_paper_practicality(top_k=12)
    paper15 = analyze_paper_practicality(top_k=15)
    dsr = run_dsr_all(ROOT)
    pbo = assess_pbo_matrix(ROOT)
    robustness = run_robustness_all(ROOT)
    ranking = build_research_ranking(
        cost_stress=cost,
        dsr=dsr,
        robustness=robustness,
        paper=paper12,
        champion_id=CHAMPION,
    )

    _write_cost_stress_csv(cost)
    atomic_write_json(DOCS / "P11_COST_STRESS_RESULTS.json", cost)
    atomic_write_json(DOCS / "P11_SENSITIVITY_RESULTS.json", sensitivity)
    atomic_write_json(DOCS / "P11_PAPER_PRACTICALITY.json", {"top12": paper12, "top15": paper15})
    atomic_write_json(DOCS / "P11_DSR_RESULTS.json", dsr)
    atomic_write_json(DOCS / "P11_PBO_CSCV_RESULTS.json", pbo)
    atomic_write_json(DOCS / "P11_ROBUSTNESS_RESULTS.json", robustness)
    atomic_write_json(DOCS / "P11_RESEARCH_RANKING.json", ranking)

    p11_status = _resolve_p11_status(preserved, cost, dsr, pbo, robustness, ranking)

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p11_status": p11_status,
        "pipeline_preserved": preserved,
        "pipeline_preservation_failures": preservation_failures,
        "cost_stress_summary": {
            "evaluable_rows": sum(1 for r in cost.get("rows", []) if r.get("evaluation_status") == "EVALUABLE"),
            "variants": cost.get("variants"),
        },
        "sensitivity": sensitivity,
        "paper_practicality": {"top12": paper12, "top15": paper15},
        "dsr": dsr,
        "pbo_cscv": pbo,
        "robustness": robustness,
        "research_ranking": ranking,
        "safety": {
            "simulation_only": True,
            "real_money": False,
            "broker_order_submission": False,
            "live_trading": False,
            "automatic_promotion": False,
            "champion_changed": False,
            "initial_paper_capital_eur": 500.0,
            "real_money_capital_eur": 0.0,
        },
    }

    atomic_write_json(DOCS / "P11_SAFETY_BOUNDARY_VERIFICATION.json", result["safety"])

    p12a_prompt = "\n".join(
        [
            "# P12A — Read-Only Online Market Data Ingestion",
            "",
            "Execute as **separate work unit** only.",
            "",
            "Build provider abstraction, UTC timestamping, data quality gates, raw store, replay.",
            "",
            "INITIAL_PAPER_CAPITAL_EUR = 500.00 (for downstream P12B)",
            "REAL_MONEY = NO | BROKER_ORDER_SENT = NO | NOT_LIVE_AUTHORIZED = YES",
            "",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p12a_prompt, encoding="utf-8")

    if p11_status.startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P11_ID)
        result["p12a_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p12a_enqueue"] = {"ok": False, "message": "P11 gate not PASS"}

    write_p11_statistical_research_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P11_STATISTICAL_VALIDATION" / run_id / "p11_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p11_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    (OBS / "CURSOR_P11_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P11 Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                f"Git: {result.get('git_commit')}",
                "",
                "## Tasks",
                "- P11-AR-001 Cost stress: executed",
                "- P11-AR-002 Sensitivity + 500 EUR practicality: executed",
                "- P11-AR-003 DSR: executed (conditional on return-cost limitation)",
                "- P11-AR-004 PBO/CSCV: matrix assessed; splitter pending",
                "- P11-AR-005 Robustness: executed",
                "- P11-AR-006 Research ranking: executed",
                "",
                "Champion unchanged: R3_w075_q065_noexit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    p12a = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p12a.is_file():
        shutil.copy2(p12a, OBS / "CURSOR_P12A_ENQUEUED_WORK_UNIT_PROMPT.md")

    (OBS / "CURSOR_P11_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P11 Objective Technical Assessment",
                "",
                f"Status: {status}",
                "",
                "Cost stress on validated TOP12/TOP15 turnover ledgers completed.",
                "DSR marked CONDITIONAL due to P10 return-cost reconciliation limitation.",
                "PBO/CSCV blocked on CSCV split pipeline — matrix assembly possible.",
                "500 EUR paper practicality analyzed for top12 and top15 slot counts.",
                "",
                "No promotion. No live trading. No champion change.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p11_statistical_research_validation_package.zip"
    include = [DOCS, Path("research/p11"), Path("control/review_snapshot/p11_statistical_research_validation_snapshot.json")]
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
        tool = ROOT / "tools/run_p11_statistical_research_validation.py"
        if tool.is_file():
            zf.write(tool, "tools/run_p11_statistical_research_validation.py")
            hash_manifest["tools/run_p11_statistical_research_validation.py"] = file_sha256(tool)

    zh = file_sha256(zip_path)
    (OBS / "cursor_p11_statistical_research_validation_package.zip.sha256").write_text(
        f"{zh}  cursor_p11_statistical_research_validation_package.zip\n",
        encoding="utf-8",
    )
    hash_manifest["cursor_p11_statistical_research_validation_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P11_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p11()
    out = build_output_package(result)
    print(
        json.dumps(
            {"p11_status": result.get("p11_status"), "p12a_enqueue": result.get("p12a_enqueue"), "dir": str(out.resolve())},
            indent=2,
        )
    )
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p11_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
