"""Runtime guard rails — close env bypass loopholes outside explicit test harness."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

# Env flags that authorize bypassing production safety (CI / matrix only).
AUTOMATED_TEST_FLAGS = (
    "AA_OFFLINE_COCKPIT_TEST",
    "AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST",
    "AA_INTERACTIVE_COCKPIT_SMOKE_TEST",
    "AA_DECISION_COCKPIT_SMOKE_TEST",
    "AA_PYTEST_SESSION",
)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def is_automated_test_session() -> bool:
    """True when an explicit automated-test env flag is set."""
    return any(_env_flag(name) for name in AUTOMATED_TEST_FLAGS)


def multi_instance_bypass_allowed() -> bool:
    """Multi-instance bypass only in automated test sessions — never in normal EXE use."""
    if not is_automated_test_session():
        return False
    return os.environ.get("AA_ALLOW_MULTI_INSTANCE", "0").strip().lower() in {"1", "true", "yes", "on"}


def record_subsystem_error(
    state: Dict[str, Any],
    *,
    code: str,
    message: str,
    subsystem: str = "runtime",
) -> None:
    """Append a visible subsystem error — never swallow silently."""
    errors = state.setdefault("subsystem_errors", [])
    if not isinstance(errors, list):
        errors = []
        state["subsystem_errors"] = errors
    entry = {"code": code, "subsystem": subsystem, "message": str(message)[:240]}
    if not any(e.get("code") == code and e.get("message") == entry["message"] for e in errors):
        errors.append(entry)


def truncate_error(exc: BaseException, limit: int = 200) -> str:
    return str(exc)[:limit]
