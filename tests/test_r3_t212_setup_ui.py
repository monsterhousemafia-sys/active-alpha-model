"""R3 T212 Setup UI — einmalige Web-Eingabe."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.r3_t212_operator_api import (
    credentials_configured,
    mark_operator_api_setup_complete,
    needs_operator_api_setup,
    resolve_operator_api_state,
    save_t212_credentials_from_web,
)
from analytics.r3_t212_setup_ui import render_t212_setup_panel


def test_setup_panel_shown_when_needed(tmp_path: Path) -> None:
    assert needs_operator_api_setup(tmp_path) is True
    html = render_t212_setup_panel(tmp_path, show=True)
    assert "r3-t212-setup" in html
    assert "Key" in html
    assert render_t212_setup_panel(tmp_path, show=False) == ""


def test_setup_complete_after_mark(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    mark_operator_api_setup_complete(tmp_path)
    assert needs_operator_api_setup(tmp_path) is False


def test_credentials_configured_false_without_env(tmp_path: Path) -> None:
    assert credentials_configured(tmp_path) is False


def test_save_applies_credentials(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    with patch(
        "integrations.trading212.t212_credentials_ui_controller.apply_credentials_from_gui",
        return_value={"stored": "SESSION_ONLY", "persisted_layers": []},
    ), patch(
        "analytics.r3_t212_api_bond.ensure_r3_t212_api_bond",
        return_value={"setup_ok": True, "t212_trusted": False, "headline_de": "", "next_de": "Kurz warten"},
    ), patch(
        "analytics.r3_t212_account_identity.confirm_t212_account",
        return_value={"ok": True},
    ):
        out = save_t212_credentials_from_web(tmp_path, api_key="k", api_secret="s")
    assert out.get("ok") is True
    assert needs_operator_api_setup(tmp_path) is False
    assert (tmp_path / ".env").is_file()
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "TRADING212_API_KEY=k" in text
    assert "TRADING212_API_SECRET=s" in text


def test_save_requires_both_fields(tmp_path: Path) -> None:
    out = save_t212_credentials_from_web(tmp_path, api_key="", api_secret="x")
    assert out.get("ok") is False


def test_resolve_operator_api_state(tmp_path: Path) -> None:
    state = resolve_operator_api_state(tmp_path)
    assert state.get("needs_api_setup") is True
    assert state.get("operator_api_ready") is False
    (tmp_path / "control").mkdir(parents=True)
    mark_operator_api_setup_complete(tmp_path)
    state2 = resolve_operator_api_state(tmp_path)
    assert state2.get("needs_api_setup") is False


def test_exec_mirror_allows_credentials_post() -> None:
    from analytics.local_apps_registry import exec_mirror_route_allowed

    assert exec_mirror_route_allowed("POST", "/api/r3/t212/credentials") is True
