from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.bash_gpt4o import (
    bash_gpt4o_ask,
    bash_gpt4o_status,
    format_bash_gpt4o_reply,
    load_bash_gpt4o_config,
)


def test_bash_gpt4o_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_bash_gpt4o_config(root)
    assert cfg.get("display_model") == "gpt-4o"
    assert cfg.get("openai_model") == "gpt-4o"


def test_bash_gpt4o_status_offline(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/bash_gpt4o.json").write_text(
        json.dumps({"display_model": "gpt-4o", "keyless_ok": True}),
        encoding="utf-8",
    )
    with patch("analytics.local_llm_bridge.health_report", return_value={"ready": False}):
        with patch("analytics.alpha_model_advisor_bridge.resolve_advisor_key", return_value=("", None)):
            doc = bash_gpt4o_status(tmp_path)
    assert doc.get("ready") is False
    assert doc.get("display_model") == "gpt-4o"


def test_bash_gpt4o_ask_keyless(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/bash_gpt4o.json").write_text(
        json.dumps(
            {
                "display_model": "gpt-4o",
                "local_ollama_model": "qwen2.5:14b",
                "keyless_ok": True,
            }
        ),
        encoding="utf-8",
    )

    def _health(_root):
        return {"ready": True}

    def _chat(_root, messages, **kwargs):
        return "Test-Antwort", {"model": kwargs.get("model")}

    with patch("analytics.local_llm_bridge.health_report", side_effect=_health):
        with patch("analytics.alpha_model_advisor_bridge.resolve_advisor_key", return_value=("", None)):
            with patch("analytics.local_llm_bridge.chat_completion", side_effect=_chat):
                doc = bash_gpt4o_ask(tmp_path, "Status?")
    assert doc.get("ok") is True
    assert doc.get("display_model") == "gpt-4o"
    assert "Test-Antwort" in format_bash_gpt4o_reply(doc)
