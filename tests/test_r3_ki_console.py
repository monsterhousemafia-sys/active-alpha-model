from __future__ import annotations

from pathlib import Path

from analytics.r3_ki_console import _help_de, handle_ki_message, render_ki_console_section


def test_render_ki_console_has_input() -> None:
    html = render_ki_console_section({"next_step_de": "learn"}, health={"ready": True, "model": "qwen"})
    assert "ki-input" in html
    assert "Spenden" in html or "/beitrag" in html
    assert "learn" in html


def test_handle_ki_help_without_ollama(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("analytics.r3_ki_console.save_session", lambda _m, **k: {})
    out = handle_ki_message(tmp_path, "/hilfe")
    assert out.get("ok") is True
    assert out.get("help") is True


def test_handle_ki_geheimnis_without_ollama(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr("analytics.r3_ki_console.save_session", lambda _m, **k: {})
    out = handle_ki_message(root, "/geheimnis")
    assert out.get("ok") is True
    assert out.get("prognose") is True
    assert out.get("unified") is True
    assert "Prognose" in out.get("reply_de", "")


def test_render_ki_console_has_upload_and_chips() -> None:
    html = render_ki_console_section({"next_step_de": "x"}, health={"ready": True, "model": "qwen"})
    assert "ki-file" in html
    assert "ki-chip" in html
    assert "ki-internet" in html
    assert "ki-mic-btn" in html
    assert "ki-send-btn" in html
    assert "ki-rail" in html
    assert "Spenden" in html or "/spende" in html
