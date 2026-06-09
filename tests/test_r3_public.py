from __future__ import annotations

from pathlib import Path

from analytics.r3_ki_console import handle_ki_message
from analytics.r3_public import (
    donate_reply_de,
    hide_trading_in_ui,
    public_starter_prompts,
    render_support_section,
)


def test_hide_trading_default() -> None:
    root = Path(__file__).resolve().parents[1]
    assert hide_trading_in_ui(root) is True


def test_public_starters_no_aktien() -> None:
    root = Path(__file__).resolve().parents[1]
    labels = [s["label"] for s in public_starter_prompts(root)]
    assert "Spenden" in labels
    assert not any("Aktien" in x for x in labels)


def test_donate_reply() -> None:
    root = Path(__file__).resolve().parents[1]
    text = donate_reply_de(root)
    assert "Spende" in text or "spende" in text.lower()
    assert "/join" in text


def test_handle_spende(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("analytics.r3_ki_console.save_session", lambda _m, **k: {})
    out = handle_ki_message(tmp_path, "/spende")
    assert out.get("donate") is True
    assert out.get("ok") is True


def test_support_section_html() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_support_section(root)
    assert "fz-public" in html
    assert "/spende" in html
