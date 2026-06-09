"""Multi-currency FX runtime gate."""
from __future__ import annotations

from typing import Any, Dict

FX_PASS = "PASS_READ_ONLY_FX_OBSERVATION"
FX_PAUSED = "PAUSED_MISSING_OR_PARTIAL_FX"
FX_TEST = "TEST_FIXTURE_ONLY_NOT_PERFORMANCE_VALID"


def classify_fx_observation(fx_obs: Dict[str, Any], *, test_fixture_mode: bool = False) -> Dict[str, Any]:
    if test_fixture_mode or fx_obs.get("fx_source") == "TEST_FIXTURE_ONLY":
        return {"fx_runtime_gate": FX_TEST, "performance_valid": False}
    usd_ok = fx_obs.get("usd_fx_quality_gate") == "PASS" and fx_obs.get("usd_to_eur_rate")
    gbp_ok = fx_obs.get("gbp_fx_quality_gate") == "PASS" and fx_obs.get("gbp_to_eur_rate")
    if usd_ok and gbp_ok:
        return {"fx_runtime_gate": FX_PASS, "performance_valid": True, "usd_path": "PASS", "gbp_path": "PASS"}
    if usd_ok:
        return {
            "fx_runtime_gate": FX_PAUSED,
            "performance_valid": False,
            "usd_path": "PASS",
            "gbp_path": "PARTIAL" if not gbp_ok else "PASS",
        }
    return {"fx_runtime_gate": FX_PAUSED, "performance_valid": False, "usd_path": "FAIL", "gbp_path": "FAIL"}


def fx_available_for_currency(fx_obs: Dict[str, Any], quote_currency: str) -> bool:
    qc = quote_currency.upper()
    if qc == "EUR":
        return True
    if qc == "USD":
        return fx_obs.get("usd_fx_quality_gate") == "PASS" and bool(fx_obs.get("usd_to_eur_rate"))
    if qc == "GBP":
        return fx_obs.get("gbp_fx_quality_gate") == "PASS" and bool(fx_obs.get("gbp_to_eur_rate"))
    return False
