"""Strategic governance — single source of truth sync."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from analytics.champion_runtime_guard import verify_champion_runtime
from analytics.strategic_governance import (
    build_governance_manifest,
    resolve_effective_orders_profile,
    resolve_governance_champion,
    sync_strategic_governance,
)


def _write_strategic_decision(root: Path, *, active: str = "R0_LEGACY_ENSEMBLE") -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/champion_strategic_decision.json").write_text(
        json.dumps(
            {
                "active_champion": active,
                "prior_champion": "R3_w075_q065_noexit",
                "champion_change_executed": True,
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_TEST.md",
            }
        ),
        encoding="utf-8",
    )


def _write_prediction_ops(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "governance_champion": "R0_LEGACY_ENSEMBLE",
                "active_profile": "daily_alpha_h1",
                "fallback_profile": "r3_w075_production",
                "production_fallback": "R3_w075_q065_noexit",
                "experimental_profiles": ["daily_alpha_h1"],
                "profiles": {
                    "daily_alpha_h1": {"variant_key": "DAILY_ALPHA_H1"},
                    "r3_w075_production": {"variant_key": "R3_w075_q065_noexit"},
                },
                "safety": {"real_money": True},
            }
        ),
        encoding="utf-8",
    )


def test_resolve_governance_champion_from_strategic_decision(tmp_path: Path) -> None:
    _write_strategic_decision(tmp_path)
    assert resolve_governance_champion(tmp_path) == "R0_LEGACY_ENSEMBLE"


def test_sync_strategic_governance_aligns_learning_policy(tmp_path: Path) -> None:
    _write_strategic_decision(tmp_path)
    _write_prediction_ops(tmp_path)
    (root := tmp_path)
    (root / "control/learning_collection_policy.json").write_text(
        json.dumps({"active_champion_locked": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    result = sync_strategic_governance(root)
    assert result["status"] == "OK"
    assert result["coherence_ok"] is True
    learning = json.loads((root / "control/learning_collection_policy.json").read_text(encoding="utf-8"))
    assert learning["governance_champion_locked"] == "R0_LEGACY_ENSEMBLE"
    assert learning["active_champion_locked"] == "R0_LEGACY_ENSEMBLE"
    manifest = json.loads((root / "control/strategic_governance.json").read_text(encoding="utf-8"))
    assert manifest["governance_champion"] == "R0_LEGACY_ENSEMBLE"
    assert manifest["active_signal_variant"] == "DAILY_ALPHA_H1"
    assert manifest["production_fallback_variant"] == "R3_w075_q065_noexit"


def test_effective_orders_profile_uses_fallback_when_h1_unsealed(tmp_path: Path) -> None:
    _write_prediction_ops(tmp_path)
    assert resolve_effective_orders_profile(tmp_path) == "r3_w075_production"


def test_build_governance_manifest_coherence_issues_on_drift(tmp_path: Path) -> None:
    _write_strategic_decision(tmp_path)
    _write_prediction_ops(tmp_path)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"governance_champion": "R3_w075_q065_noexit", "active_profile": "daily_alpha_h1"}),
        encoding="utf-8",
    )
    manifest = build_governance_manifest(tmp_path)
    assert manifest["coherence_ok"] is False
    assert manifest["coherence_issues"]


def test_champion_runtime_guard_no_signal_governance_mismatch(tmp_path: Path) -> None:
    from datetime import date, timedelta

    import pandas as pd

    _write_strategic_decision(tmp_path)
    _write_prediction_ops(tmp_path)
    sync_strategic_governance(tmp_path)
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True, exist_ok=True)
    ref = date.today()
    while ref.weekday() >= 5:
        ref -= timedelta(days=1)
    pd.DataFrame(
        [{"ticker": "INTC", "target_weight": 0.1, "signal_date": ref.isoformat()}]
    ).to_csv(out / "latest_target_portfolio.csv", index=False)
    status = verify_champion_runtime(tmp_path)
    assert status.authoritative_champion == "R0_LEGACY_ENSEMBLE"
    assert status.code_champion == "DAILY_ALPHA_H1"
    assert "GOVERNANCE_CHAMPION_DIFFERS_FROM_SIGNAL_PROFILE" not in status.blockers
    assert status.champion_ok
