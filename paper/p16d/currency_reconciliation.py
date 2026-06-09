"""Currency reconciliation for multi-currency portfolio."""
from __future__ import annotations

from typing import Any, Dict, List


def reconcile_currency_paths(
    *,
    fx_obs: Dict[str, Any],
    instrument_conversions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    usd_ok = fx_obs.get("usd_fx_quality_gate") == "PASS"
    gbp_ok = fx_obs.get("gbp_fx_quality_gate") == "PASS"
    executed = [c for c in instrument_conversions if c.get("portfolio_scope") == "PROVISIONAL_EXECUTABLE"]
    ref_only = [c for c in instrument_conversions if c.get("allowed_action", "").startswith("OBSERVATION")]

    exec_ok = all(c.get("conversion_valid") for c in executed)
    if exec_ok and usd_ok:
        gate = "PASS_FOR_EXECUTED_PORTFOLIO_ONLY"
    elif all(c.get("conversion_valid") for c in instrument_conversions) and usd_ok and gbp_ok:
        gate = "PASS_FOR_FULL_REFERENCE_PORTFOLIO"
    elif any(c.get("conversion_valid") for c in instrument_conversions):
        gate = "PARTIAL_AFFECTED_INSTRUMENTS_EXCLUDED"
    else:
        gate = "FAIL_RUNTIME_PAUSED"

    return {
        "multi_currency_runtime_gate": gate,
        "usd_path": "PASS" if usd_ok else "FAIL",
        "gbp_path": "PASS" if gbp_ok else ("PARTIAL" if usd_ok else "FAIL"),
        "executed_instruments_reconciled": exec_ok,
        "reference_observation_only_count": len(ref_only),
        "executed_count": len(executed),
    }
