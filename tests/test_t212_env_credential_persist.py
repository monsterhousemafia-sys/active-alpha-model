from __future__ import annotations

import os
from pathlib import Path

import pytest

from integrations.trading212.t212_credentials_ui_controller import maybe_migrate_env_credentials_to_disk
from integrations.trading212.t212_env_file_loader import load_env_file
from integrations.trading212.t212_session_credential_store import clear_session_credentials
from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials
from integrations.trading212.t212_windows_dpapi_credential_store import forget_monitoring_credentials


def test_bootstrap_loads_env_and_migrates(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "TRADING212_API_KEY=boot-key\nTRADING212_API_SECRET=boot-secret\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in ("TRADING212_API_KEY", "TRADING212_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    forget_monitoring_credentials(tmp_path)
    clear_session_credentials()
    res = bootstrap_trading212_credentials(tmp_path)
    assert os.environ.get("TRADING212_API_KEY") == "boot-key"
    assert res.get("migration", {}).get("migrated") is True


def test_load_env_file_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("TRADING212_API_KEY=from_file\nTRADING212_API_SECRET=secret\n", encoding="utf-8")
    for key in ("TRADING212_API_KEY", "TRADING212_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TRADING212_API_KEY", "already_set")
    assert load_env_file(env) is True
    assert os.environ["TRADING212_API_KEY"] == "already_set"
    assert os.environ["TRADING212_API_SECRET"] == "secret"


def test_load_credentials_reads_trading212_zugangsdaten_env(tmp_path: Path, monkeypatch) -> None:
    from integrations.trading212.t212_credentials_loader import load_credentials
    from integrations.trading212.t212_session_credential_store import clear_session_credentials

    clear_session_credentials()
    (tmp_path / "trading212_zugangsdaten.env").write_text(
        "TRADING212_API_KEY=zugang-key\nTRADING212_API_SECRET=zugang-secret\n",
        encoding="utf-8",
    )
    for key in ("TRADING212_API_KEY", "TRADING212_API_SECRET"):
        monkeypatch.delenv(key, raising=False)
    creds = load_credentials(tmp_path)
    assert creds is not None
    assert creds.configured
    assert creds.api_key == "zugang-key"
    assert creds.api_secret == "zugang-secret"


@pytest.mark.skipif(os.name != "nt", reason="DPAPI migration is Windows-only")
def test_maybe_migrate_env_credentials_to_disk(tmp_path: Path, monkeypatch) -> None:
    forget_monitoring_credentials(tmp_path)
    clear_session_credentials()
    monkeypatch.setenv("TRADING212_API_KEY", "env-key")
    monkeypatch.setenv("TRADING212_API_SECRET", "env-secret")
    res = maybe_migrate_env_credentials_to_disk(tmp_path)
    assert res.get("migrated") is True
    assert res.get("stored") == "PERSISTED"
