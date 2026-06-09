#!/usr/bin/env python3
"""G2 pre-registered statistical validation protocol (documentation only, no recompute)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_evidence_schema import LOCKED_CHAMPION
from aa_safe_io import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
G2_DIR = ROOT / "control" / "evidence" / "g2_preregistration"
G2_PROTOCOL = G2_DIR / "statistical_validation_protocol.json"
G2_LEDGER = G2_DIR / "g2_trial_ledger_challenger_mom63.json"
G2_REPORT = doc_path("CODEX_G2_PREREGISTRATION_PROTOCOL.md")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_g2_package(root: Path | None = None) -> Dict[str, Any]:
    root = Path(root or ROOT)
    protocol = {
        "schema_version": 1,
        "phase": "G2_PRE_REGISTERED_STATISTICAL_VALIDATION",
        "status": "PREREGISTERED_AWAITING_G1_PASS_AND_EXTERNAL_APPROVAL",
        "generated_at_utc": _utc_now(),
        "prerequisite_phases": [
            "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION",
        ],
        "variants": {
            "champion": LOCKED_CHAMPION,
            "m1_control": "M1_MOM_BLEND_MATCHED_CONTROLS",
            "challenger": "MOM_63_TOP12",
        },
        "gates_unchanged": True,
        "cost_stress": {
            "approved_scenario": "PLUS_25_BPS",
            "scenarios": ["BASELINE", "PLUS_10_BPS", "PLUS_25_BPS", "PLUS_50_BPS", "SLIPPAGE_TURNOVER_STRESS"],
            "requires_variant_specific_turnover": True,
        },
        "multiple_testing": {
            "dsr_required_probability": 0.95,
            "trial_ledger_required": True,
            "pbo_cscv_requires_candidate_matrix": True,
        },
        "robustness": {
            "subperiod_stability_screen": "informational",
            "robustness_evidence_gate": "ROBUSTNESS_EVIDENCE",
        },
        "forbidden_before_g2_approval": [
            "backtest_execution",
            "cost_stress_recompute",
            "dsr_pbo_cscv_recompute",
            "promotion",
            "shadow",
            "paper",
            "real_money",
        ],
    }

    ledger = {
        "schema_version": 1,
        "trial_id": "G2_MOM63_CHALLENGER_VS_CHAMPION_M1",
        "variant": "MOM_63_TOP12",
        "champion_reference": LOCKED_CHAMPION,
        "control_reference": "M1_MOM_BLEND_MATCHED_CONTROLS",
        "reason_for_trial": "Pre-registered cost-stress, DSR, PBO/CSCV and robustness for MOM_63_TOP12 after G1 turnover artefacts exist.",
        "predefined_parameters": {
            "calendar_alignment_min_observations": 200,
            "cost_model": "trading212_us+fx_0bps+slippage_2bps",
            "incremental_stress_bps": [0, 10, 25, 50],
            "dsr_required_probability": 0.95,
        },
        "primary_benchmark": LOCKED_CHAMPION,
        "secondary_benchmarks": ["M1_MOM_BLEND_MATCHED_CONTROLS"],
        "acceptance_criteria": [
            "CHALLENGER_TURNOVER_VERIFIED",
            "COST_STRESS_GATE pass at PLUS_25_BPS vs champion and M1",
            "DSR probability >= 0.95 with preregistered trial count",
            "ROBUSTNESS_EVIDENCE gate pass or documented fail-closed block",
        ],
        "created_before_execution": True,
        "created_at_utc": _utc_now(),
        "g1_prerequisite": True,
        "execution_authorized": False,
    }

    report = "\n".join(
        [
            "# G2 Pre-Registered Statistical Validation Protocol",
            "",
            f"Generated: {protocol['generated_at_utc']}",
            "",
            "## Status",
            "",
            "`PREREGISTERED_AWAITING_G1_PASS_AND_EXTERNAL_APPROVAL`",
            "",
            "No DSR, PBO/CSCV, Cost-Stress or Robustness **recomputation** is authorized by this document.",
            "",
            "## Prerequisites",
            "",
            "1. G1 PASS with variant-specific MOM_63_TOP12 turnover artefacts",
            "2. External approval: `EXTERNAL_REVIEW_APPROVAL_G2_PRE_REGISTERED_STATISTICAL_VALIDATION.md` (template TBD)",
            "3. Trial ledger frozen before any G2 computation",
            "",
            "## Frozen thresholds",
            "",
            "- DSR required probability: **0.95**",
            "- Approved cost-stress scenario: **PLUS_25_BPS**",
            "- Champion locked: `" + LOCKED_CHAMPION + "`",
            "",
            "## Machine-readable artefacts",
            "",
            "- `control/evidence/g2_preregistration/statistical_validation_protocol.json`",
            "- `control/evidence/g2_preregistration/g2_trial_ledger_challenger_mom63.json`",
            "",
            "REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL",
            "",
        ]
    )

    G2_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_json(G2_PROTOCOL, protocol)
    atomic_write_json(G2_LEDGER, ledger)
    G2_REPORT.write_text(report, encoding="utf-8")
    return {"protocol": protocol, "ledger": ledger}


def main() -> int:
    result = build_g2_package()
    print(json.dumps({"phase": result["protocol"]["phase"], "status": result["protocol"]["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
