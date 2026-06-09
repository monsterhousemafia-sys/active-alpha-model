"""Phase F — statistical gate evidence for canonical variant set."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from aa_canonical_comparison import (
    CANONICAL_VARIANT_ROLES,
    CONTAMINATED_RETURNS_SHA256,
    resolve_variant_returns_path,
)
from aa_cost_stress import (
    SCENARIOS,
    evaluate_variant_scenario,
    export_cost_stress_status,
    file_sha256,
    resolve_variant_sources,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion
from aa_multiple_testing_adjustment import export_multiple_testing_status
from aa_robustness_evidence import export_robustness_status
from aa_safe_io import atomic_write_json, atomic_write_text
from research.p11.robustness import _subperiod_metrics

RESEARCH_EVIDENCE = Path("research_evidence")
GATE_MATRIX_JSON = Path("evidence") / "phase_f_gate_matrix.json"
GATE_MATRIX_MD = Path("evidence") / "phase_f_gate_matrix.md"
PHASE_F_SUMMARY = Path("evidence") / "phase_f_statistical_evidence_summary.json"

FORWARD_SHADOW_BLOCKER = "NOT_EXTERNALLY_APPROVED_PHASE_F"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def phase_f_variant_sources(root: Path) -> Dict[str, Dict[str, Any]]:
    """Extended sources for all canonical comparison variants."""
    root = Path(root)
    out = dict(resolve_variant_sources(root))
    champion = resolve_locked_champion(root)
    m1_report = root / "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_report.txt"
    default_proof = str(m1_report.relative_to(root)).replace("\\", "/") if m1_report.is_file() else None

    g1_ret = root / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/daily_returns.csv"
    g1_turn = root / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/turnover/rebalance_turnover.csv"
    if g1_ret.is_file():
        out["MOM_63_TOP12"] = {
            "returns_path": str(g1_ret.relative_to(root)).replace("\\", "/"),
            "returns_column": None,
            "decisions_path": str(g1_turn.relative_to(root)).replace("\\", "/") if g1_turn.is_file() else "",
            "baseline_cost_proof_path": default_proof,
            "turnover_verified": g1_turn.is_file(),
            "gate_eligible": g1_ret.is_file() and g1_turn.is_file(),
        }

    for vid, _role in CANONICAL_VARIANT_ROLES:
        if vid in out and out[vid].get("returns_path"):
            continue
        ret_path, reason = resolve_variant_returns_path(root, vid)
        if not ret_path or not ret_path.is_file():
            continue
        sha = file_sha256(ret_path)
        contaminated = sha == CONTAMINATED_RETURNS_SHA256
        rel_ret = str(ret_path.relative_to(root)).replace("\\", "/")
        dec_path = ""
        turn_verified = False
        if vid == champion and not contaminated:
            dec = root / "model_output_sp500_pit_t212/backtest_decisions.csv"
            if dec.is_file():
                dec_path = str(dec.relative_to(root)).replace("\\", "/")
                turn_verified = True
        ar_turn = root / "evidence/autonomous_research" / vid / "turnover_ledgers/turnover_ledger.csv"
        if ar_turn.is_file():
            dec_path = str(ar_turn.relative_to(root)).replace("\\", "/")
            turn_verified = True
        out[vid] = {
            "returns_path": "" if contaminated else rel_ret,
            "returns_column": "strategy_return",
            "decisions_path": dec_path,
            "baseline_cost_proof_path": default_proof,
            "turnover_verified": turn_verified,
            "gate_eligible": bool(rel_ret) and turn_verified and not contaminated,
            "returns_contaminated": contaminated,
            "resolve_note": reason,
        }

    champ_src = out.get(champion, {})
    champ_ret = root / str(champ_src.get("returns_path") or "")
    if champ_ret.is_file() and file_sha256(champ_ret) == CONTAMINATED_RETURNS_SHA256:
        out[champion] = {
            **champ_src,
            "returns_path": "",
            "gate_eligible": False,
            "turnover_verified": False,
            "returns_contaminated": True,
        }
    return out


def ensure_preregistered_trial_ledger(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / RESEARCH_EVIDENCE
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "trial_ledger_preregistered.json"
    if path.is_file():
        return {"status": "EXISTING", "path": str(path.relative_to(root)).replace("\\", "/")}

    variants = [vid for vid, role in CANONICAL_VARIANT_ROLES if role != "QUARANTINED"]
    doc = {
        "trial_id": "CHAMPION_EVIDENCE_GOVERNANCE_MATRIX_V1",
        "variant": AUTHORITATIVE_CHAMPION,
        "reason_for_trial": "Phase F preregistered matrix — risk-off rescue champion vs siblings and research challengers.",
        "predefined_parameters": {
            "authoritative_champion": AUTHORITATIVE_CHAMPION,
            "matrix_variants": variants,
            "cost_stress_scenarios": list(SCENARIOS.keys()),
            "dsr_required_probability": 0.95,
        },
        "primary_benchmark": "R0_LEGACY_ENSEMBLE",
        "secondary_benchmarks": ["M1_MOM_BLEND_MATCHED_CONTROLS", "MOM_63_TOP12"],
        "created_before_execution": True,
        "created_at_utc": _utc_now(),
        "phase": "F",
    }
    atomic_write_json(path, doc)
    return {"status": "CREATED", "path": str(path.relative_to(root)).replace("\\", "/"), "n_variants": len(variants)}


def build_cost_stress_rows(root: Path) -> List[Dict[str, Any]]:
    root = Path(root)
    sources = phase_f_variant_sources(root)
    rows: List[Dict[str, Any]] = []
    for vid, role in CANONICAL_VARIANT_ROLES:
        if role == "QUARANTINED":
            for scen in SCENARIOS:
                rows.append(
                    {
                        "variant_id": vid,
                        "role": role,
                        "scenario": scen,
                        "evaluation_status": "BLOCKED",
                        "gate_result": "BLOCKED",
                        "reason": "quarantined_unauthorized_claim",
                    }
                )
            continue
        src = sources.get(vid, {})
        if src.get("returns_contaminated"):
            for scen in SCENARIOS:
                rows.append(
                    {
                        "variant_id": vid,
                        "role": role,
                        "scenario": scen,
                        "evaluation_status": "BLOCKED",
                        "gate_result": "BLOCKED",
                        "reason": "contaminated_model_output_returns",
                    }
                )
            continue
        for scen_name, scen_def in SCENARIOS.items():
            ev = evaluate_variant_scenario(
                root, vid, src, scen_name, scen_def, allow_turnover_proxy=False
            )
            metrics = ev.get("metrics") or {}
            gate_result = "PASS" if ev.get("evaluation_status") == "EVALUABLE" else "NOT_EVALUABLE"
            if ev.get("comparison_result") in {"PASS", "FAIL"}:
                gate_result = str(ev.get("comparison_result"))
            rows.append(
                {
                    "variant_id": vid,
                    "role": role,
                    "scenario": scen_name,
                    "evaluation_status": ev.get("evaluation_status"),
                    "gate_result": gate_result,
                    "reason": ev.get("reason") or "",
                    "turnover_verified": not bool(ev.get("turnover_is_proxy")),
                    "turnover_is_proxy": bool(ev.get("turnover_is_proxy")),
                    "sharpe_0rf": metrics.get("sharpe_0rf"),
                    "cagr": metrics.get("cagr"),
                    "max_drawdown": metrics.get("max_drawdown"),
                    "n_days": metrics.get("n_days"),
                }
            )
    return rows


def write_cost_stress_artifacts(root: Path, rows: List[Dict[str, Any]]) -> Dict[str, str]:
    root = Path(root)
    out_dir = root / RESEARCH_EVIDENCE
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "cost_stress_comparison.csv"
    if rows:
        fieldnames: List[str] = []
        for r in rows:
            for k in r:
                if k not in fieldnames:
                    fieldnames.append(k)
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)

    lines = [
        "# Cost Stress Gate Report (Phase F)",
        "",
        f"Generated: {_utc_now()}",
        "",
        "| variant_id | role | scenario | status | sharpe | reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        if r.get("scenario") != "PLUS_25_BPS":
            continue
        lines.append(
            f"| {r.get('variant_id')} | {r.get('role')} | {r.get('scenario')} | "
            f"{r.get('gate_result')} | {r.get('sharpe_0rf')} | {r.get('reason') or '-'} |"
        )
    champ = resolve_locked_champion(root)
    champ_row = next((r for r in rows if r.get("variant_id") == champ and r.get("scenario") == "PLUS_25_BPS"), None)
    mom_row = next((r for r in rows if r.get("variant_id") == "MOM_63_TOP12" and r.get("scenario") == "PLUS_25_BPS"), None)
    gate_pass = (
        champ_row
        and mom_row
        and champ_row.get("evaluation_status") == "EVALUABLE"
        and mom_row.get("evaluation_status") == "EVALUABLE"
        and float(mom_row.get("sharpe_0rf") or 0) > float(champ_row.get("sharpe_0rf") or 0)
    )
    lines.extend(
        [
            "",
            "## Gate decision (PLUS_25_BPS)",
            "",
            f"COST_STRESS_GATE: **{'PASS' if gate_pass else 'FAIL / NOT_EVALUABLE'}**",
            "",
        ]
    )
    md_path = out_dir / "cost_stress_gate_report.md"
    atomic_write_text(md_path, "\n".join(lines) + "\n")
    return {
        "cost_stress_comparison.csv": str(csv_path.relative_to(root)).replace("\\", "/"),
        "cost_stress_gate_report.md": str(md_path.relative_to(root)).replace("\\", "/"),
    }


def build_robustness_rows(root: Path) -> List[Dict[str, Any]]:
    root = Path(root)
    sources = phase_f_variant_sources(root)
    from aa_cost_stress import _load_daily_returns

    rows: List[Dict[str, Any]] = []
    for vid, role in CANONICAL_VARIANT_ROLES:
        if role == "QUARANTINED":
            rows.append(
                {
                    "variant_id": vid,
                    "role": role,
                    "status": "BLOCKED",
                    "subperiod_sharpe_stability": "BLOCKED",
                    "reason": "quarantined",
                }
            )
            continue
        src = sources.get(vid, {})
        if src.get("returns_contaminated") or not src.get("returns_path"):
            rows.append(
                {
                    "variant_id": vid,
                    "role": role,
                    "status": "NOT_EVALUABLE",
                    "subperiod_sharpe_stability": "NOT_EVALUABLE",
                    "reason": src.get("returns_contaminated")
                    and "contaminated_returns"
                    or "returns_missing",
                }
            )
            continue
        path = root / str(src["returns_path"])
        series = _load_daily_returns(path, src.get("returns_column"))
        if series is None or series.empty:
            rows.append(
                {
                    "variant_id": vid,
                    "role": role,
                    "status": "NOT_EVALUABLE",
                    "subperiod_sharpe_stability": "NOT_EVALUABLE",
                    "reason": "returns_unparseable",
                }
            )
            continue
        segs = _subperiod_metrics(series)
        sharpes = [s.get("sharpe_0rf") for s in segs if s.get("sharpe_0rf") is not None]
        stable = len(sharpes) >= 2 and min(sharpes) > 0 if sharpes else False
        rows.append(
            {
                "variant_id": vid,
                "role": role,
                "status": "EVALUABLE",
                "subperiod_sharpe_stability": "STABLE_POSITIVE" if stable else "MIXED_OR_NEGATIVE",
                "segment_3_sharpe": segs[-1].get("sharpe_0rf") if segs else None,
                "n_days": int(len(series)),
                "n_segments": len(segs),
            }
        )
    return rows


def build_dsr_summary(root: Path) -> Dict[str, Any]:
    export_multiple_testing_status(root)
    mt = _read_json(root / "control/evidence/multiple_testing_status.json")
    dsr = mt.get("deflated_sharpe") or {}
    lines = [
        "# DSR / Multiple Testing Report (Phase F)",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"- Champion: `{mt.get('champion_variant_id')}`",
        f"- Challenger (DSR series): `{mt.get('challenger_variant_id')}`",
        f"- Trials: {mt.get('tested_variant_count')}",
        f"- DSR status: {dsr.get('status')}",
        f"- DSR probability: {dsr.get('dsr_probability')}",
        f"- MULTIPLE_TESTING_EVIDENCE pass: {(mt.get('MULTIPLE_TESTING_EVIDENCE') or {}).get('pass')}",
        "",
        f"Ledger: `{RESEARCH_EVIDENCE / 'trial_ledger_preregistered.json'}`",
        "",
    ]
    out_dir = root / RESEARCH_EVIDENCE
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "dsr_multiple_testing_report.md"
    atomic_write_text(md_path, "\n".join(lines) + "\n")
    return {"multiple_testing_status": mt, "report": str(md_path.relative_to(root)).replace("\\", "/")}


def write_robustness_gate_report(root: Path, rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# Robustness Gate Report (Phase F)",
        "",
        f"Generated: {_utc_now()}",
        "",
        "| variant_id | role | subperiod stability | seg3 sharpe | status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| {r.get('variant_id')} | {r.get('role')} | {r.get('subperiod_sharpe_stability')} | "
            f"{r.get('segment_3_sharpe', '-')} | {r.get('status')} |"
        )
    path = root / RESEARCH_EVIDENCE / "robustness_gate_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, "\n".join(lines) + "\n")
    return str(path.relative_to(root)).replace("\\", "/")


def build_gate_matrix(
    cost_rows: List[Dict[str, Any]],
    robust_rows: List[Dict[str, Any]],
    dsr_doc: Dict[str, Any],
) -> Dict[str, Any]:
    mt = dsr_doc.get("multiple_testing_status") or {}
    mt_ev = mt.get("MULTIPLE_TESTING_EVIDENCE") or {}
    dsr_status = (mt.get("deflated_sharpe") or {}).get("status", "UNKNOWN")
    dsr_pass = bool(mt_ev.get("pass"))

    by_variant: Dict[str, Dict[str, Any]] = {}
    for vid, role in CANONICAL_VARIANT_ROLES:
        by_variant[vid] = {"variant_id": vid, "role": role}

    for r in cost_rows:
        vid = str(r.get("variant_id"))
        if r.get("scenario") == "PLUS_25_BPS":
            by_variant.setdefault(vid, {})["cost_stress_plus_25_bps"] = r.get("gate_result")
            by_variant[vid]["cost_stress_reason"] = r.get("reason") or ""
        if r.get("scenario") == "BASELINE":
            by_variant[vid]["cost_stress_baseline"] = r.get("gate_result")

    for r in robust_rows:
        vid = str(r.get("variant_id"))
        by_variant.setdefault(vid, {})["robustness_subperiod"] = r.get("subperiod_sharpe_stability")
        by_variant[vid]["robustness_status"] = r.get("status")

    matrix_rows: List[Dict[str, Any]] = []
    for vid, role in CANONICAL_VARIANT_ROLES:
        row = by_variant.get(vid, {})
        is_champion = vid == AUTHORITATIVE_CHAMPION
        is_challenger = vid == "MOM_63_TOP12"
        matrix_rows.append(
            {
                "variant_id": vid,
                "role": role,
                "cost_stress_baseline": row.get("cost_stress_baseline", "NOT_RUN"),
                "cost_stress_plus_25_bps": row.get("cost_stress_plus_25_bps", "NOT_RUN"),
                "robustness_subperiod": row.get("robustness_subperiod", "NOT_RUN"),
                "dsr_multiple_testing": "PASS" if (dsr_pass and is_challenger) else ("N/A" if not is_challenger else dsr_status),
                "paper_forward": "BLOCKED",
                "shadow_collection": "BLOCKED",
                "paper_shadow_blocker": FORWARD_SHADOW_BLOCKER,
                "champion_row": is_champion,
                "overall": _overall_row_status(row, is_champion, dsr_pass),
            }
        )

    return {
        "schema_version": 1,
        "phase": "F",
        "generated_at_utc": _utc_now(),
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "dsr_global_status": dsr_status,
        "dsr_global_pass": dsr_pass,
        "rows": matrix_rows,
    }


def _overall_row_status(row: Dict[str, Any], is_champion: bool, dsr_pass: bool) -> str:
    if row.get("robustness_status") == "BLOCKED":
        return "BLOCKED"
    cost = row.get("cost_stress_plus_25_bps")
    rob = row.get("robustness_subperiod")
    if cost in {"BLOCKED", "NOT_EVALUABLE", None} or rob in {"NOT_EVALUABLE", None}:
        return "NOT_EVALUABLE" if not is_champion else "CHAMPION_ARTIFACT_BLOCKED"
    if is_champion:
        return "PASS" if rob == "STABLE_POSITIVE" else "FAIL"
    return "PASS" if cost == "PASS" and rob == "STABLE_POSITIVE" else "FAIL"


def format_gate_matrix_md(doc: Dict[str, Any]) -> str:
    lines = [
        "# Phase F — Gate × Variante",
        "",
        f"Generated: {doc.get('generated_at_utc')}",
        f"Champion: `{doc.get('authoritative_champion')}`",
        f"DSR (global, challenger): {doc.get('dsr_global_status')} pass={doc.get('dsr_global_pass')}",
        "",
        "| Variante | Rolle | Cost +25bps | Robustheit (3 Segmente) | DSR | Paper | Shadow | Gesamt |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in doc.get("rows") or []:
        tag = " **[CHAMPION]**" if r.get("champion_row") else ""
        lines.append(
            f"| `{r.get('variant_id')}`{tag} | {r.get('role')} | {r.get('cost_stress_plus_25_bps')} | "
            f"{r.get('robustness_subperiod')} | {r.get('dsr_multiple_testing')} | {r.get('paper_forward')} | "
            f"{r.get('shadow_collection')} | {r.get('overall')} |"
        )
    lines.extend(
        [
            "",
            "Paper/Shadow: bewusst **BLOCKED** (keine externe Freigabe für operative Forward/Shadow-Jobs).",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def run_phase_f(root: Path) -> Dict[str, Any]:
    root = Path(root)
    steps: Dict[str, Any] = {}

    steps["F0_trial_ledger"] = ensure_preregistered_trial_ledger(root)
    cost_rows = build_cost_stress_rows(root)
    steps["F1_cost_stress_artifacts"] = write_cost_stress_artifacts(root, cost_rows)
    steps["F1_export_cost_stress_status"] = str(export_cost_stress_status(root))
    robust_rows = build_robustness_rows(root)
    steps["F2_robustness_report"] = write_robustness_gate_report(root, robust_rows)
    steps["F2_export_robustness_status"] = str(export_robustness_status(root))
    steps["F3_dsr"] = build_dsr_summary(root)
    steps["F4_paper_forward"] = {"status": "BLOCKED", "reason": FORWARD_SHADOW_BLOCKER}
    steps["F5_shadow"] = {"status": "BLOCKED", "reason": FORWARD_SHADOW_BLOCKER}

    matrix = build_gate_matrix(cost_rows, robust_rows, steps["F3_dsr"])
    atomic_write_json(root / GATE_MATRIX_JSON, matrix)
    atomic_write_text(root / GATE_MATRIX_MD, format_gate_matrix_md(matrix))

    champ_row = next((r for r in matrix["rows"] if r.get("champion_row")), {})
    summary = {
        "schema_version": 1,
        "phase": "F",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE",
        "authoritative_champion": AUTHORITATIVE_CHAMPION,
        "champion_gate_row": champ_row,
        "n_variants": len(matrix.get("rows") or []),
        "outputs": [
            str(GATE_MATRIX_JSON).replace("\\", "/"),
            str(GATE_MATRIX_MD).replace("\\", "/"),
            str(RESEARCH_EVIDENCE / "cost_stress_comparison.csv").replace("\\", "/"),
            str(RESEARCH_EVIDENCE / "trial_ledger_preregistered.json").replace("\\", "/"),
        ],
        "steps": steps,
    }
    atomic_write_json(root / PHASE_F_SUMMARY, summary)
    return summary
