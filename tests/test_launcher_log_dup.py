"""Regression tests for launcher logging (no duplicate lines)."""
from __future__ import annotations

from pathlib import Path


def test_log_writes_once_with_tee(tmp_path: Path, monkeypatch):
    from aa_launcher_log import TeeStream, log_line, start_run_log
    import sys

    import tools.active_alpha_launcher as launcher

    start_run_log(tmp_path)
    original_stdout = sys.stdout
    sys.stdout = TeeStream(None, log_line)
    launcher._ui = None
    try:
        launcher.log("[TEST] single line")
    finally:
        sys.stdout = original_stdout

    text = (tmp_path / "marktanalyse_last_run.log").read_text(encoding="utf-8")
    assert text.count("[TEST] single line") == 1
