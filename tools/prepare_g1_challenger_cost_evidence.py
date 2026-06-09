#!/usr/bin/env python3
"""Read-only G1 challenger cost evidence preparation (no backtests, no cost recompute)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_cost_stress import CHALLENGER, CHAMPION as COST_STRESS_CHAMPION_KEY, M1_VARIANT, resolve_variant_sources
from aa_evidence_schema import LOCKED_CHAMPION, resolve_locked_champion
from aa_safe_io import atomic_write_json
from aa_v2_source_inventory import build_v2_source_inventory, file_sha256

ROOT = Path(__file__).resolve().parents[1]
G1_STATUS = ROOT / "control" / "evidence" / "g1_challenger_cost_preparation_status.json"
G1_INVENTORY = ROOT / "control" / "evidence" / "g1_source_inventory.json"
G1_COMPARISON = doc_path("G1_COMPARISON_LOGIC.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _variant_row(root: Path, variant_id: str, src: Dict[str, Any]) -> Dict[str, Any]:
    ret_rel = str(src.get("returns_path") or "")
    dec_rel = str(src.get("decisions_path") or "")
    ret_path = root / ret_rel if ret_rel else None
    dec_path = root / dec_rel if dec_rel else None
    proof_rel = str(src.get("baseline_cost_proof_path") or "")
    proof_path = root / proof_rel if proof_rel else None
    return {
        "variant_id": variant_id,
        "returns_path": ret_rel or None,
        "returns_present": bool(ret_path and ret_path.is_file()),
        "returns_sha256": file_sha256(ret_path) if ret_path and ret_path.is_file() else "",
        "decisions_path": dec_rel or None,
        "decisions_present": bool(dec_path and dec_path.is_file()),
        "decisions_sha256": file_sha256(dec_path) if dec_path and dec_path.is_file() else "",
        "baseline_cost_proof_path": proof_rel or None,
        "baseline_cost_proof_present": bool(proof_path and proof_path.is_file()),
        "turnover_verified": bool(src.get("turnover_verified")),
        "gate_eligible": bool(src.get("gate_eligible")),
        "turnover_proxy_variant": src.get("turnover_proxy_variant"),
    }


def build_g1_comparison_markdown(champion: str, inventory: Dict[str, Any]) -> str:
    blockers = inventory.get("blockers") or []
    return "\n".join(
        [
            "# G1 Comparison Logic — Champion, M1, Challenger",
            "",
            f"Generated: {inventory.get('generated_at_utc')}",
            "",
            "## Variants under identical calendar policy",
            "",
            f"| Role | Variant ID | Returns artefact | Turnover artefact | Gate eligible |",
            f"|------|------------|------------------|-------------------|---------------|",
            *[
                f"| {v.get('role')} | `{v.get('variant_id')}` | "
                f"{'YES' if v.get('returns_present') else 'NO'} | "
                f"{'YES' if v.get('decisions_present') else 'NO'} | "
                f"{'YES' if v.get('gate_eligible') else 'NO'} |"
                for v in inventory.get("variants") or []
            ],
            "",
            "## Cost model (must match across variants)",
            "",
            "- Fee model: `trading212_us+fx_0bps+slippage_2bps`",
            "- Baseline costs embedded in return series where documented",
            "- Incremental stress applies extra bps on **variant-specific** rebalance turnover only",
            "- Champion reference: `" + champion + "`",
            f"- M1 control: `{M1_VARIANT}`",
            f"- Challenger: `{CHALLENGER}`",
            "",
            "## Comparison rules (read-only preparation)",
            "",
            "1. Align daily return calendars; require ≥200 overlapping observations.",
            "2. Cost-stress uses verified turnover per variant; **no champion turnover proxy for challenger gates**.",
            "3. DSR / multiple-testing uses preregistered trial ledger (G2); no post-hoc threshold changes.",
            "4. Robustness subperiod screen is informational; ROBUSTNESS_EVIDENCE gate remains separate.",
            "",
            "## Current blockers",
            "",
            *(f"- `{b}`" for b in blockers),
            "",
            "## Explicitly not authorized in G1 preparation",
            "",
            "- Shadow / Paper / Promotion / Champion change / Real money",
            "- New backtests without registered G1 approval",
            "",
            "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
            "",
        ]
    )


def prepare_g1(root: Path | None = None) -> Dict[str, Any]:
    root = Path(root or ROOT)
    champion = resolve_locked_champion(root)
    sources = resolve_variant_sources(root)
    v2 = build_v2_source_inventory(root)

    champ_src = sources.get(champion) or sources.get(COST_STRESS_CHAMPION_KEY, {})
    if champion not in sources:
        validated = root / "model_output_sp500_pit_t212" / "latest_validated_run.json"
        champ_src = {
            "returns_path": "model_output_sp500_pit_t212/strategy_daily_returns.csv",
            "decisions_path": "model_output_sp500_pit_t212/backtest_decisions.csv",
            "baseline_cost_proof_path": "model_output_sp500_pit_t212/backtest_report.txt",
            "turnover_verified": True,
            "gate_eligible": validated.is_file(),
        }

    variants: List[Dict[str, Any]] = [
        {**_variant_row(root, champion, champ_src), "role": "CHAMPION"},
        {**_variant_row(root, M1_VARIANT, sources.get(M1_VARIANT, {})), "role": "M1_CONTROL"},
        {**_variant_row(root, CHALLENGER, sources.get(CHALLENGER, {})), "role": "CHALLENGER"},
    ]

    blockers: List[str] = []
    if not variants[2].get("decisions_present"):
        blockers.append("CHALLENGER_TURNOVER_NOT_VERIFIED")
    if not variants[2].get("returns_present"):
        blockers.append("CHALLENGER_RETURNS_MISSING")
    if not v2.get("aligned_calendar_ok"):
        blockers.append("CALENDAR_MISALIGNMENT")
    blockers.append("G1_NOT_EXTERNALLY_APPROVED")

    inventory = {
        "schema_version": 1,
        "phase": "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION",
        "generated_at_utc": _utc_now(),
        "champion": champion,
        "m1_control": M1_VARIANT,
        "challenger": CHALLENGER,
        "variants": variants,
        "aligned_calendar_observations": v2.get("aligned_calendar_observations"),
        "aligned_calendar_ok": v2.get("aligned_calendar_ok"),
        "cost_assumptions": v2.get("cost_assumptions"),
        "blockers": blockers,
        "read_only": True,
        "operative_jobs_executed": False,
    }

    status = {
        "schema_version": 1,
        "phase": "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION",
        "status": "PREPARED_AWAITING_EXTERNAL_APPROVAL",
        "generated_at_utc": _utc_now(),
        "external_approval_required": "EXTERNAL_REVIEW_APPROVAL_G1_READ_ONLY_CHALLENGER_COST_EVIDENCE.md",
        "champion_unchanged": champion,
        "blockers": blockers,
        "gate_eligible_variants": [v["variant_id"] for v in variants if v.get("gate_eligible")],
        "preparation_complete": variants[0]["returns_present"] and variants[1]["returns_present"],
        "turnover_gap": not variants[2].get("decisions_present"),
        "allowed_after_g1_approval": [
            "generate_MOM_63_TOP12_turnover_artefacts",
            "document_identical_comparison_logic",
            "prepare_cost_stress_dsr_robustness_packages",
        ],
        "forbidden_without_separate_approval": [
            "shadow_monitoring",
            "paper_monitoring",
            "promotion",
            "champion_change",
            "real_money_execution",
            "backtest_execution",
        ],
    }

    G1_INVENTORY.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(G1_INVENTORY, inventory)
    atomic_write_json(G1_STATUS, status)
    G1_COMPARISON.write_text(build_g1_comparison_markdown(champion, inventory), encoding="utf-8")
    return {"inventory": inventory, "status": status}


def main() -> int:
    result = prepare_g1()
    print(json.dumps({"status": result["status"]["status"], "blockers": result["status"]["blockers"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
