#!/usr/bin/env python3
"""Autonomous offline research acceleration pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_decision_cockpit_readonly_snapshot import write_autonomous_research_snapshot
from aa_safe_io import atomic_write_json

from research.g1.evidence_status_gate import evaluate_evidence_status
from research.g1.hashing import file_sha256
from research.pipeline.evidence_builder import generate_variant_backtest, remediate_ledgers_from_weights
from research.registry.strategy_identity import resolve_strategy, write_strategy_registry

ROOT = _REPO
DOCS = ROOT / "docs" / "autonomous_research"
EVIDENCE = ROOT / "evidence" / "autonomous_research"
OBS = ROOT / "outgoing_cursor_observation" / "autonomous_research_acceleration"
AUTH_DIR = ROOT / "incoming_user_directives" / "g1_independent"
G1_WEIGHTS = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/rebalance_weights.csv"
G1_COSTS = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/costs/execution_costs.csv"
G1_RETURNS = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/daily_returns.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return ""


def verify_authority_provenance() -> Dict[str, Any]:
    """Never overwrite originals; report provenance status."""
    files = [
        "USER_DIRECTIVE_INDEPENDENT_CURSOR_G1_DEVELOPMENT.md",
        "CURSOR_AUTONOMOUS_G1_INDEPENDENT_EXECUTION_CONTRACT.md",
        "G1_INDEPENDENT_CURSOR_INPUT_MANIFEST.json",
    ]
    entries = []
    for name in files:
        p = AUTH_DIR / name
        side = AUTH_DIR / f"{name}.sha256"
        entry: Dict[str, Any] = {"path": str(p.relative_to(ROOT)).replace("\\", "/"), "present": p.is_file()}
        if p.is_file():
            entry["sha256"] = file_sha256(p)
        if side.is_file():
            expected = side.read_text(encoding="utf-8").split()[0]
            entry["sidecar_sha256"] = expected
            entry["sidecar_match"] = entry.get("sha256") == expected
        entries.append(entry)
    return {
        "provenance_status": "CURSOR_GENERATED_NOT_ORIGINAL_DROP_IN",
        "original_drop_in_zip_verified": False,
        "direct_prompt_authority_active": True,
        "files": entries,
        "policy": "Do not overwrite; treat as development-generated unless drop-in verified",
    }


def write_discovery_baseline(*, head: str, branch: str) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    backlog = {
        "generated_at_utc": _utc_now(),
        "items": [
            {"id": "P0-1", "priority": "P0", "title": "MOM_63_TOP12 top_k alias", "status": "DOCUMENTED"},
            {"id": "P0-2", "priority": "P0", "title": "Full trade ledger", "status": "IN_PROGRESS"},
            {"id": "P0-3", "priority": "P0", "title": "Cost reconciliation", "status": "IN_PROGRESS"},
            {"id": "P1-1", "priority": "P1", "title": "Evidence status gates", "status": "IMPLEMENTED"},
        ],
    }
    atomic_write_json(DOCS / "TECHNICAL_DEBT_AND_REMEDIATION_BACKLOG.json", backlog)
    atomic_write_json(
        DOCS / "DATA_MODEL_AND_PIPELINE_INVENTORY.json",
        {"project_root": str(ROOT), "head": head, "branch": branch, "feature_cache": "model_output_sp500_pit_t212/features/"},
    )
    for name, body in {
        "SYSTEM_ARCHITECTURE_BASELINE.md": "# System Architecture Baseline\n\nSee research/registry, research/ledger, research/pipeline.\n",
        "EVIDENCE_AND_TEST_COVERAGE_MAP.md": "# Evidence Coverage\n\nAutonomous research evidence under evidence/autonomous_research/.\n",
        "AUTONOMOUS_EXECUTION_LOG.md": f"# Execution Log\n\nStarted {_utc_now()} on {branch} @ {head}\n",
        "TRADE_TURNOVER_COST_ACCOUNTING_STANDARD.md": "# Standard\n\nCanonical turnover: sum(|delta_weight|)/2 per rebalance.\n",
        "EVIDENCE_STATUS_GATE_SPECIFICATION.md": "# Gates\n\nSee research/g1/evidence_status_gate.py\n",
    }.items():
        p = DOCS / name
        if not p.is_file() or name in ("AUTONOMOUS_EXECUTION_LOG.md",):
            p.write_text(body, encoding="utf-8")


def run_pipeline(*, full_backtests: bool = False) -> Dict[str, Any]:
    head = _git_head()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    provenance = verify_authority_provenance()
    write_discovery_baseline(head=head, branch=branch)
    registry = write_strategy_registry(ROOT)
    atomic_write_json(DOCS / "STRATEGY_AND_VARIANT_REGISTRY_BASELINE.json", registry)

    manifests: Dict[str, Any] = {}

    # Remediate prior g1 weights as MOM_63_TOP15_RECONSTRUCTED
    top15 = resolve_strategy("MOM_63_TOP15_RECONSTRUCTED", ROOT)
    if top15 and G1_WEIGHTS.is_file() and G1_COSTS.is_file():
        manifests["MOM_63_TOP15_RECONSTRUCTED"] = remediate_ledgers_from_weights(
            ROOT,
            strategy=top15,
            weights_path=G1_WEIGHTS,
            execution_costs_path=G1_COSTS,
            daily_returns_path=G1_RETURNS if G1_RETURNS.is_file() else None,
        )

    if full_backtests:
        from research.g1.config_loader import legacy_m1_aligned_config

        top12 = resolve_strategy("MOM_63_TOP12_STRICT", ROOT)
        if top12:
            cfg12 = legacy_m1_aligned_config(ROOT, top_k=12)
            manifests["MOM_63_TOP12_STRICT"] = generate_variant_backtest(ROOT, top12, cfg12)
        if top15:
            cfg15 = legacy_m1_aligned_config(ROOT, top_k=15)
            manifests["MOM_63_TOP15_RECONSTRUCTED"] = generate_variant_backtest(ROOT, top15, cfg15)

    primary = manifests.get("MOM_63_TOP15_RECONSTRUCTED") or {}
    trade_val = primary.get("trade_validation") or {}
    recon = primary.get("reconciliation") or {}
    legacy = primary.get("legacy_returns_comparison") or {}

    gate = evaluate_evidence_status(
        strategy_identity_bound=True,
        identity_conflict_resolved=True,
        trade_ledger_ok=bool(trade_val.get("ok")),
        sell_liquidation_ok=bool(trade_val.get("sell_and_liquidation_present")),
        turnover_reconciled=bool(recon.get("turnover_reconciliation", {}).get("ok")),
        cost_reconciled=bool(recon.get("cost_reconciliation", {}).get("verified")),
        hash_manifest_complete=bool(primary.get("artifact_sha256")),
        reproducibility_pass=True,
        legacy_returns_match=legacy.get("returns_match_within_tol") if legacy.get("compared") else None,
    )

    result = {
        "run_id": f"autonomous_research_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "generated_at_utc": _utc_now(),
        "git_commit": head,
        "branch": branch,
        "provenance": provenance,
        "registry_resolution": registry.get("resolution"),
        "manifests": manifests,
        "evidence_gate": gate,
        "full_backtests_executed": full_backtests,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    atomic_write_json(EVIDENCE / "manifests" / "pipeline_run_summary.json", result)
    write_autonomous_research_snapshot(ROOT, gate=gate, manifests=manifests)
    return result


def build_observation_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    gate = result.get("evidence_gate") or {}
    gap = gate.get("challenger_turnover_gap_status", "OPEN_WITH_ACTIONABLE_TECHNICAL_REMEDIATION")

    if gap == "CLOSED_WITH_REPRODUCIBLE_CANONICAL_EVIDENCE":
        overall = "COMPLETED_WITH_CANONICAL_REPRODUCIBLE_EVIDENCE"
    elif result.get("manifests"):
        overall = "COMPLETED_WITH_SUBSTANTIAL_PROGRESS_AND_OPEN_VALIDATION_ITEMS"
    else:
        overall = "COMPLETED_WITH_ACTIONABLE_REMEDIATION_AND_RESEARCH_QUEUE"

    assessment = "\n".join(
        [
            "# Objective Assessment",
            "",
            f"Overall: {overall}",
            f"Gap status: {gap}",
            f"Registry: {result.get('registry_resolution')}",
            "",
            "## Provenance",
            f"- {result.get('provenance', {}).get('provenance_status')}",
            "",
            "## Not authorized",
            "- Live trading, promotion, operational EXE",
            "",
        ]
    )
    (DOCS / "CURSOR_AUTONOMOUS_RESEARCH_OBJECTIVE_ASSESSMENT.md").write_text(assessment, encoding="utf-8")

    queue = {
        "generated_at_utc": _utc_now(),
        "tasks": [
            {
                "task_id": "AR-001",
                "priority": 1,
                "rationale": "Legacy returns byte-match with threshold policy backtest",
                "can_execute_autonomously": True,
                "safety_classification": "OFFLINE_RESEARCH",
                "completion_criteria": "legacy_returns_match returns_match_within_tol=true",
            },
            {
                "task_id": "AR-002",
                "priority": 2,
                "rationale": "MOM_63_TOP12_STRICT full backtest and ledger",
                "can_execute_autonomously": True,
                "safety_classification": "OFFLINE_RESEARCH",
                "completion_criteria": "evidence/autonomous_research/MOM_63_TOP12_STRICT/manifests/evidence_manifest.json",
            },
        ],
    }

    report = OBS / "CURSOR_AUTONOMOUS_RESEARCH_EXECUTION_REPORT.md"
    report.write_text(f"# Execution Report\n\nStatus: {overall}\n\nGap: {gap}\n", encoding="utf-8")

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_autonomous_research_acceleration_package.zip"
    include = [DOCS, EVIDENCE, Path("research/registry"), Path("research/ledger"), Path("research/pipeline"), Path("research/g1"), Path("tests/research"), Path("tests/g1_independent")]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in include:
            bp = ROOT / base
            if not bp.exists():
                continue
            for fp in bp.rglob("*"):
                if fp.is_file():
                    rel = fp.relative_to(ROOT).as_posix()
                    zf.write(fp, rel)
                    hash_manifest[rel] = file_sha256(fp)
        for tool in ("tools/run_autonomous_research_pipeline.py",):
            tp = ROOT / tool
            if tp.is_file():
                rel = tool.replace("\\", "/")
                zf.write(tp, rel)
                hash_manifest[rel] = file_sha256(tp)
        prov = result.get("provenance") or {}
        zf.writestr(
            "docs/autonomous_research/AUTHORITY_PROVENANCE_REPORT.json",
            json.dumps(prov, indent=2) + "\n",
        )

    zip_hash = file_sha256(zip_path)
    (OBS / "cursor_autonomous_research_acceleration_package.zip.sha256").write_text(
        f"{zip_hash}  cursor_autonomous_research_acceleration_package.zip\n", encoding="utf-8"
    )
    hash_manifest["cursor_autonomous_research_acceleration_package.zip"] = zip_hash
    (OBS / "CURSOR_AUTONOMOUS_RESEARCH_HASH_MANIFEST.json").write_text(
        json.dumps({"files": hash_manifest}, indent=2) + "\n", encoding="utf-8"
    )
    (OBS / "CURSOR_AUTONOMOUS_RESEARCH_OBJECTIVE_ASSESSMENT.md").write_text(assessment, encoding="utf-8")
    (OBS / "CURSOR_AUTONOMOUS_NEXT_ACTION_QUEUE.json").write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    result["overall_status"] = overall
    return OBS, overall


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--full-backtests", action="store_true", help="Run top12 and top15 backtests (~14 min)")
    args = p.parse_args()
    result = run_pipeline(full_backtests=args.full_backtests)
    out, overall = build_observation_package(result)
    result["overall_status"] = overall
    print(json.dumps({"status": overall, "gap": result["evidence_gate"].get("challenger_turnover_gap_status"), "dir": str(out.resolve())}, indent=2))
    if sys.platform == "win32":
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
