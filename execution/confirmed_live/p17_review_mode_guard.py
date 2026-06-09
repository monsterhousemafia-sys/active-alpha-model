"""P17 hard guard — no live network order submission during review phase."""
from __future__ import annotations

import os
from typing import Any, Dict

P17_ENV = "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"
BLOCK_REASON = "P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"


def review_mode_active() -> bool:
    """Default ON unless explicitly disabled by saved preference or env."""
    val = os.environ.get(P17_ENV, "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def assert_live_network_submission_allowed() -> None:
    if review_mode_active():
        raise RuntimeError(BLOCK_REASON)
    if os.environ.get("AA_NO_LIVE_ORDER_SUBMISSION", "").strip() == "1":
        raise RuntimeError("LIVE_SUBMISSION_BLOCKED_BY_ENV")


def submission_status_summary() -> Dict[str, Any]:
    return {
        "p17_review_mode": review_mode_active(),
        "live_network_submission_allowed_in_p17": False if review_mode_active() else None,
        "block_reason": BLOCK_REASON if review_mode_active() else None,
    }
