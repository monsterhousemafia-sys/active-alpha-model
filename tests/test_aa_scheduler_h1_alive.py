"""H1-Prozess-Erkennung — active_alpha_model.py zählt als laufender Backtest."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from analytics.aa_scheduler import _h1_process_alive


def test_h1_alive_via_active_alpha_model() -> None:
    root = Path("/tmp/aa-test")
    run_dir = "/data/validation_runs/20260606T102626Z_DAILY_ALPHA_H1"
    needle = "20260606T102626Z_DAILY_ALPHA_H1"

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        if "run_validation_matrix" in cmd:
            proc.stdout = ""
        elif "active_alpha_model.py" in cmd:
            proc.stdout = f"9999 python active_alpha_model.py --out-dir .../{needle}"
        else:
            proc.stdout = ""
        return proc

    with patch("analytics.aa_scheduler.subprocess.run", side_effect=fake_run):
        assert _h1_process_alive(root, run_dir) is True


def test_h1_not_alive_when_no_match() -> None:
    root = Path("/tmp/aa-test")
    run_dir = "/data/validation_runs/20260606T102626Z_DAILY_ALPHA_H1"

    def fake_run(cmd, **kwargs):
        proc = MagicMock()
        proc.stdout = ""
        return proc

    with patch("analytics.aa_scheduler.subprocess.run", side_effect=fake_run):
        assert _h1_process_alive(root, run_dir) is False
