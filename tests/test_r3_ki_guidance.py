from __future__ import annotations

from pathlib import Path

from analytics.r3_ki_guidance import (
    build_guidance_reply,
    needs_guidance,
    starter_prompts,
)
from analytics.r3_ki_console import handle_ki_message, render_ki_console_section


def test_needs_guidance_short_input() -> None:
    assert needs_guidance("ok") is True
    assert needs_guidance("ja") is True
    assert needs_guidance("/geheimnis") is False
    assert needs_guidance("Welche Aktien heute?") is False


def test_guidance_reply_has_questions() -> None:
    root = Path(__file__).resolve().parents[1]
    text = build_guidance_reply(root)
    assert "Spende" in text or "/spende" in text
    assert "geheimnis" not in text.lower()


def test_handle_ki_guide_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("analytics.r3_ki_console.save_session", lambda _m, **k: {})
    out = handle_ki_message(tmp_path, "/fragen")
    assert out.get("guidance") is True
    assert "Spende" in out.get("reply_de", "") or "/spende" in out.get("reply_de", "")


def test_render_ki_console_apple_ui() -> None:
    html = render_ki_console_section({"next_step_de": "learn"}, health={"ready": True, "model": "qwen"})
    assert "ki-chat" in html
    assert "ki-mic-btn" in html
    assert "ki-composer" in html
    assert "ki-starters" in html
    assert len(starter_prompts(Path("."))) >= 3
