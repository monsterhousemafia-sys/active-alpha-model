from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_agent_serve import log_serve_event, run_agent_serve


def test_run_agent_serve_stops_on_code_3(tmp_path: Path) -> None:
    calls = {"n": 0}

    def fake_repl(_root, *, model=None, serve_mode=False):
        calls["n"] += 1
        return 3 if calls["n"] == 1 else 0

    with patch("analytics.alpha_model_agent_serve.log_serve_event"):
        rc = run_agent_serve(tmp_path, repl_fn=fake_repl, restart_delay_s=0.01, ollama_retry_s=0.01)
    assert rc == 0
    assert calls["n"] == 1


def test_run_agent_serve_restarts_on_code_1(tmp_path: Path) -> None:
    calls = {"n": 0}

    def fake_repl(_root, *, model=None, serve_mode=False):
        calls["n"] += 1
        if calls["n"] < 3:
            return 1
        return 3

    with patch("analytics.alpha_model_agent_serve.log_serve_event"):
        rc = run_agent_serve(tmp_path, repl_fn=fake_repl, restart_delay_s=0.01, ollama_retry_s=0.01)
    assert rc == 0
    assert calls["n"] == 3


def test_log_serve_event_writes_evidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / "proj"
    (root / "evidence").mkdir(parents=True)
    (root / "control").mkdir(parents=True)
    (root / "control/alpha_model_agent_home.json").write_text("{}", encoding="utf-8")
    log_serve_event(root, "test-event", ok=True)
    doc = (root / "evidence/alpha_model_agent_serve_latest.json").read_text(encoding="utf-8")
    assert "test-event" in doc
