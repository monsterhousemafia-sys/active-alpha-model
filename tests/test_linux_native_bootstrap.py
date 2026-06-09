from __future__ import annotations

import json
from pathlib import Path

from execution.linux_native_bootstrap import reapply_native_order_environment


def test_reapply_restores_review_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_LINUX_NATIVE_APP", "1")
    (tmp_path / "control").mkdir()
    (tmp_path / "control/p17_review_mode_user_preference.json").write_text(
        json.dumps({"review_mode_enabled": False}),
        encoding="utf-8",
    )
    (tmp_path / "control/trading_mode_preference.json").write_text(
        json.dumps({"mode": "ai_assisted"}),
        encoding="utf-8",
    )
    (tmp_path / "control/live_trading_enabled.json").write_text(
        json.dumps({"enabled": True}),
        encoding="utf-8",
    )
    monkeypatch.delenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", raising=False)
    out = reapply_native_order_environment(tmp_path)
    assert out["review_mode_active"] is False
    assert out["live_submission_allowed"] is True
