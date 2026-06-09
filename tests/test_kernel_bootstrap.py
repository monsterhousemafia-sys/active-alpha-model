from __future__ import annotations

import json
from pathlib import Path

from analytics.kernel_bootstrap import run_kernel_bootstrap, safety_checks


def test_kernel_bootstrap_writes_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_LINUX_NATIVE_APP", "1")
    (tmp_path / "control").mkdir()
    (tmp_path / "control/AI_KERNEL.json").write_text(
        json.dumps(
            {
                "mode": "linux_native_pilot",
                "go_live_date": "2026-06-08",
                "safety": {"auto_execute_real_money": False, "gui_confirm_required": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/pilot_day_trading.json").write_text(
        json.dumps({"live_trading": {"rebalance_every_trading_days": 1}}),
        encoding="utf-8",
    )
    report = run_kernel_bootstrap(tmp_path, snap={}, write_evidence=True)
    assert report["safety"]["ok"]
    assert (tmp_path / "evidence/ai_kernel_bootstrap_latest.json").is_file()


def test_safety_blocks_auto_money(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_LINUX_NATIVE_APP", "1")
    kernel = {"mode": "linux_native_pilot", "safety": {"auto_execute_real_money": True}}
    out = safety_checks(tmp_path, kernel)
    assert not out["ok"]
    assert "no_auto_money" in out["blockers"]
