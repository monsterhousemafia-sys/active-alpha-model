"""Evidence status gate tests."""
from __future__ import annotations

from research.g1.evidence_status_gate import evaluate_evidence_status


def test_premature_closed_prevented():
    result = evaluate_evidence_status(
        strategy_identity_bound=True,
        identity_conflict_resolved=True,
        trade_ledger_ok=False,
        sell_liquidation_ok=False,
        turnover_reconciled=False,
        cost_reconciled=False,
        hash_manifest_complete=False,
        reproducibility_pass=False,
    )
    assert result["evidence_status"] != "CLOSED_WITH_REPRODUCIBLE_CANONICAL_EVIDENCE"
    assert result["premature_closed_prevented"]


def test_canonical_closed_requires_all_checks():
    result = evaluate_evidence_status(
        strategy_identity_bound=True,
        identity_conflict_resolved=True,
        trade_ledger_ok=True,
        sell_liquidation_ok=True,
        turnover_reconciled=True,
        cost_reconciled=True,
        hash_manifest_complete=True,
        reproducibility_pass=True,
        legacy_returns_match=True,
    )
    assert result["evidence_status"] == "CLOSED_WITH_REPRODUCIBLE_CANONICAL_EVIDENCE"
