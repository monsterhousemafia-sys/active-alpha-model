from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.r3_external_advisor import (
    advisor_status,
    fetch_chatgpt_tip,
    handle_advisor_command,
    is_advisor_command,
)


def test_is_advisor_command() -> None:
    assert is_advisor_command("/tipp Wie schneller bauen?")
    assert is_advisor_command("/kombi Trading UI")
    assert is_advisor_command("/berater")
    assert not is_advisor_command("/status")


def test_berater_status() -> None:
    root = Path(__file__).resolve().parents[1]
    st = advisor_status(root)
    assert "headline_de" in st
    assert "ollama_ready" in st


def test_tipp_without_key() -> None:
    root = Path(__file__).resolve().parents[1]
    with patch("analytics.r3_external_advisor.resolve_openai_api_key", return_value=("", "")):
        out = handle_advisor_command(root, "/tipp Wie testen?")
    assert out.get("advisor")
    assert out.get("ok") is False or "Key" in str(out.get("reply_de", "")) + str(out.get("message_de", ""))


def test_fetch_chatgpt_mock() -> None:
    root = Path(__file__).resolve().parents[1]
    with patch("analytics.r3_external_advisor.resolve_primary_cloud_provider", return_value="openai"):
        with patch("analytics.r3_external_advisor.resolve_openai_api_key", return_value=("sk-test", "env")):
            with patch(
                "analytics.r3_external_advisor._openai_chat",
                return_value=("Kurzer Tipp: pytest -k pilot", {"model": "gpt-4o-mini"}),
            ):
                out = fetch_chatgpt_tip(root, "Wie testen?")
    assert out.get("ok")
    assert "Tipp" in out.get("tip_de", "") or "pytest" in out.get("tip_de", "")
