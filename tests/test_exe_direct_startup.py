"""Direct EXE startup — OS profile and project root."""
from __future__ import annotations

import os
from pathlib import Path

from aa_exe_direct_startup import (
    apply_marktanalyse_os_profile,
    direct_exe_ready_message,
    direct_exe_requirements,
)


def test_os_profile_sets_signal_mode(monkeypatch) -> None:
    monkeypatch.delenv("AA_RUN_MODE", raising=False)
    apply_marktanalyse_os_profile()
    assert os.environ.get("AA_RUN_MODE") == "signal"
    assert os.environ.get("AA_PARALLEL_BACKTEST_BACKEND") == "thread"


def test_direct_exe_requirements(tmp_path: Path) -> None:
    (tmp_path / "active_alpha_model.py").write_text("", encoding="utf-8")
    req = direct_exe_requirements(tmp_path)
    assert req["active_alpha_model"] is True
    assert req["venv_python"] is False
    msg = direct_exe_ready_message(req)
    assert ".venv" in msg
