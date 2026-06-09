"""Ollama ensure — Serienreife king_local."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.local_llm_bridge import ensure_ollama_running


def test_ensure_ollama_already_running(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/local_llm.json").write_text(
        '{"base_url": "http://127.0.0.1:11434"}',
        encoding="utf-8",
    )
    with patch("analytics.local_llm_bridge.ollama_available", return_value=True):
        out = ensure_ollama_running(tmp_path)
    assert out["ok"] is True
    assert out["started"] is False


def test_ensure_ollama_starts_serve(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/local_llm.json").write_text(
        '{"base_url": "http://127.0.0.1:11434"}',
        encoding="utf-8",
    )
    calls = {"n": 0}

    def _avail(_base: str, *, timeout_s: float = 3.0) -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    with patch("analytics.local_llm_bridge.ollama_available", side_effect=_avail):
        with patch("analytics.local_llm_bridge.subprocess.run", side_effect=FileNotFoundError):
            with patch("analytics.local_llm_bridge.subprocess.Popen"):
                with patch("analytics.local_llm_bridge.time.sleep"):
                    out = ensure_ollama_running(tmp_path)
    assert out["ok"] is True
    assert out.get("started") is True
