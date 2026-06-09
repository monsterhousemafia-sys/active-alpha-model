"""R3 Login + Session-Manager — Phase B Meilenstein 1."""
from __future__ import annotations

from pathlib import Path

from analytics.r3_login_shell import render_login_page
from analytics.r3_session_manager import (
    is_r3_session_active,
    load_login_config,
    mark_session_started,
    resolve_hub_entry_path,
)


def test_login_config_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_login_config(root)
    assert cfg.get("session_manager") is True
    assert (root / "control/r3_login_shell.json").is_file()


def test_login_page_renders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_login_shell.json").write_text(
        '{"title_de":"R3","post_login_path":"/desktop","login_path":"/login"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("USER", "testuser")
    body = render_login_page(tmp_path).decode("utf-8")
    assert "R3 Sitzung starten" in body or "Weiter zu R3" in body
    assert "/api/session/start" in body


def test_session_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USER", "op")
    (tmp_path / "control").mkdir()
    (tmp_path / "control/r3_login_shell.json").write_text(
        '{"require_login_before_desktop":true,"post_login_path":"/desktop","login_path":"/login","session_ttl_hours":12}',
        encoding="utf-8",
    )
    assert is_r3_session_active(tmp_path) is False
    assert resolve_hub_entry_path(tmp_path) == "/login"
    mark_session_started(tmp_path)
    assert is_r3_session_active(tmp_path) is True
    assert resolve_hub_entry_path(tmp_path) == "/desktop"
