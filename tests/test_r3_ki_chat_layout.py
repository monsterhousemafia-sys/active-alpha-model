from __future__ import annotations

from pathlib import Path

from analytics.r3_ki_chat_layout import (
    continuity_reply_de,
    quick_chips,
    render_session_rail_html,
    session_rail,
)
from analytics.r3_ki_console import handle_ki_message, render_ki_console_section


def test_session_rail_configured() -> None:
    root = Path(__file__).resolve().parents[1]
    assert len(session_rail(root)) >= 4


def test_render_has_rail_and_module_cmds() -> None:
    html = render_ki_console_section({"next_step_de": "H1"}, health={"ready": True, "model": "qwen"})
    assert "ki-rail" in html
    assert "ki-chat-layout" in html
    assert "data-module-cmds" in html
    assert "data-auto-send" in html


def test_handle_join_and_migration(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr("analytics.r3_ki_console.save_session", lambda _m, **k: {})

    join = handle_ki_message(root, "/join")
    assert join.get("ok") is True
    assert "/join" in join.get("reply_de", "")

    mig = handle_ki_message(root, "/kontinuität")
    assert mig.get("ok") is True
    assert mig.get("route_de") == "Kontinuität"
    assert "R3" in mig.get("reply_de", "") or "Checks" in mig.get("reply_de", "")


def test_quick_chips_public() -> None:
    root = Path(__file__).resolve().parents[1]
    chips = quick_chips(root, public_ui=True)
    cmds = {c.get("cmd") for c in chips}
    assert "/fragen" in cmds
    assert "/kontinuität" in cmds


def test_rail_html_has_actions() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_session_rail_html(root)
    assert "data-rail-action" in html
    assert "data-rail-cmd" in html


def test_continuity_reply_r3_native() -> None:
    root = Path(__file__).resolve().parents[1]
    text = continuity_reply_de(root)
    assert "ohne Cursor" in text or "r3-os" in text
