from __future__ import annotations

import sys
from pathlib import Path


def test_tee_stream_handles_none_stdout(tmp_path: Path):
    from aa_launcher_log import TeeStream, log_line, start_run_log

    log_path = start_run_log(tmp_path)
    stream = TeeStream(None, log_line)
    n = stream.write("[INFO] test\n")
    assert n > 0
    stream.flush()
    text = log_path.read_text(encoding="utf-8")
    assert "[INFO] test" in text


def test_install_log_tee_with_none_stdout(tmp_path: Path, monkeypatch):
    from aa_launcher_log import install_log_tee, start_run_log

    monkeypatch.setattr(sys, "stdout", None, raising=False)
    monkeypatch.setattr(sys, "stderr", None, raising=False)
    start_run_log(tmp_path)
    install_log_tee()
    print("[INFO] windowed", flush=True)
    assert "[INFO] windowed" in (tmp_path / "marktanalyse_last_run.log").read_text(encoding="utf-8")
