"""Frozen EXE signal path — subprocess fallback to project .venv."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_frozen_signal_uses_subprocess(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")
    venv_py = tmp_path / ".venv" / "Scripts"
    venv_py.mkdir(parents=True)
    (venv_py / "python.exe").write_bytes(b"")

    out_dir = tmp_path / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    (out_dir / "latest_target_portfolio.csv").write_text("symbol,weight\n", encoding="utf-8")

    monkeypatch.setattr("aa_frozen.is_frozen_exe", lambda: True)

    proc = MagicMock(returncode=0, stdout="ok", stderr="")

    with patch("analytics.live_trading_operations.subprocess.run", return_value=proc) as run:
        from analytics.live_trading_operations import run_champion_signal_update

        result = run_champion_signal_update(tmp_path, timeout_s=60)

    assert result["ok"] is True
    assert result.get("via_subprocess") is True
    assert run.called
    cmd = run.call_args[0][0]
    assert "active_alpha_model.py" in cmd[1]


def test_signal_fails_without_venv_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")
    monkeypatch.setattr("aa_frozen.is_frozen_exe", lambda: True)

    from analytics.live_trading_operations import run_champion_signal_update

    result = run_champion_signal_update(tmp_path, timeout_s=10)
    assert result["ok"] is False
    assert ".venv" in result.get("message_de", "")
