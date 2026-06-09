from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_advisor_bridge import (
    bridge_status,
    format_bridge_status_de,
    handle_bridge_command,
    load_openai_key_into_env,
    migrate_secret_file_to_keyring,
    store_openai_key,
    validate_openai_key,
)


def test_validate_openai_key() -> None:
    assert validate_openai_key("") == "Key fehlt"
    assert validate_openai_key("bad") is not None
    assert validate_openai_key("sk-" + "a" * 40) is None


def test_store_and_load_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "r3_external_advisors.json").write_text(
        '{"enabled":true,"openai":{"enabled":true,"keyring_name":"openai_api_key","env_var":"OPENAI_API_KEY"}}',
        encoding="utf-8",
    )
    key = "sk-" + "x" * 48
    with patch("analytics.secure_credential_portal.keyring_available", return_value=True):
        with patch("analytics.secure_credential_portal.keyring_set", return_value=True) as ks:
            with patch("analytics.secure_credential_portal.keyring_get", return_value=key):
                out = store_openai_key(tmp_path, key)
    assert out.get("ok")
    ks.assert_called_once()
    with patch("analytics.secure_credential_portal.keyring_get", return_value=key):
        loaded = load_openai_key_into_env(tmp_path, force=True)
    assert loaded.get("configured")
    assert loaded.get("key_source") in ("keyring", "env")


def test_migrate_secret_file(tmp_path: Path) -> None:
    secret = tmp_path / "control" / "secrets" / "openai_api_key"
    secret.parent.mkdir(parents=True)
    key = "sk-" + "m" * 48
    secret.write_text(key + "\n", encoding="utf-8")
    (tmp_path / "control" / "r3_external_advisors.json").write_text(
        '{"enabled":true,"openai":{"enabled":true,"keyring_name":"openai_api_key"}}',
        encoding="utf-8",
    )
    with patch("analytics.alpha_model_advisor_bridge.store_openai_key", return_value={"ok": True}) as st:
        doc = migrate_secret_file_to_keyring(tmp_path)
    assert doc.get("ok")
    st.assert_called_once()


def test_bridge_command_status(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "r3_external_advisors.json").write_text(
        '{"enabled":true,"openai":{"enabled":true,"model":"gpt-4o-mini"}}',
        encoding="utf-8",
    )
    with patch("analytics.alpha_model_advisor_bridge.resolve_advisor_key", return_value=("", "")):
        doc = handle_bridge_command(tmp_path, "/berater-key")
    assert doc.get("bridge")
    assert "Berater-Bridge" in str(doc.get("reply_de") or "")


def test_format_bridge_status_de(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control" / "r3_external_advisors.json").write_text(
        '{"enabled":true,"openai":{"enabled":true,"model":"gpt-4o-mini"}}',
        encoding="utf-8",
    )
    with patch("analytics.alpha_model_advisor_bridge.resolve_advisor_key", return_value=("", "")):
        text = format_bridge_status_de(tmp_path)
    assert "advisor-key-store" in text
