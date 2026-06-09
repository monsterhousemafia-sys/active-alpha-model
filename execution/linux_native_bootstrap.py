"""Re-apply native Linux order environment after compute-flag cleanup."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def reapply_native_order_environment(root: Path) -> Dict[str, Any]:
    """Restore review mode, trading mode, and live-trading flags for GUI orders."""
    root = Path(root)
    from execution.confirmed_live.p17_review_mode_preferences import apply_saved_review_mode_to_environment
    from execution.confirmed_live.trading_mode_policy import apply_saved_trading_mode
    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    review_on = apply_saved_review_mode_to_environment(root)
    mode = apply_saved_trading_mode(root)
    live = ensure_live_trading_enabled(root, changed_by="native_bootstrap")
    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from execution.confirmed_live.live_trading_enablement import live_submission_allowed

    return {
        "review_mode_enabled": review_on,
        "trading_mode": mode,
        "live_trading": live,
        "review_mode_active": review_mode_active(),
        "live_submission_allowed": live_submission_allowed(root),
    }
