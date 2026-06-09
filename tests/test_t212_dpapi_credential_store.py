"""Windows DPAPI credential persistence for Trading 212 monitoring profile."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_credentials_ui_controller import (
    apply_credentials_from_gui,
    populate_stored_credentials_in_gui,
)
from integrations.trading212.t212_session_credential_store import clear_session_credentials
from integrations.trading212.t212_windows_dpapi_credential_store import (
    forget_monitoring_credentials,
    load_monitoring_credentials,
    save_monitoring_credentials,
)


@pytest.fixture
def cred_root(tmp_path: Path) -> Path:
    forget_monitoring_credentials(tmp_path)
    clear_session_credentials()
    yield tmp_path
    forget_monitoring_credentials(tmp_path)
    clear_session_credentials()


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_dpapi_roundtrip(cred_root: Path) -> None:
    ok, msg = save_monitoring_credentials(cred_root, "test-key", "test-secret")
    assert ok, msg
    loaded = load_monitoring_credentials(cred_root)
    assert loaded is not None
    assert loaded.api_key == "test-key"
    assert loaded.api_secret == "test-secret"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_apply_credentials_persists_via_dpapi_without_keyring(cred_root: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "integrations.trading212.t212_secure_credential_store.secure_store_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "integrations.trading212.t212_secure_credential_store.save_credentials",
        lambda k, s: (False, "NO_KEYRING"),
    )
    monkeypatch.setattr(
        "integrations.trading212.t212_dual_profile_secure_store.save_profile_credentials",
        lambda *a, **k: (False, "NO_KEYRING"),
    )

    res = apply_credentials_from_gui(
        api_key="persist-key",
        api_secret="persist-secret",
        mode="LIVE_READ_ONLY",
        connection_name="Trading 212",
        persist=True,
        session_only=False,
        root=cred_root,
    )
    assert res["stored"] == "PERSISTED"
    assert "DPAPI_LOCAL" in res["persisted_layers"]
    assert load_monitoring_credentials(cred_root) is not None


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_load_credentials_falls_back_to_dpapi(cred_root: Path, monkeypatch) -> None:
    save_monitoring_credentials(cred_root, "fallback-key", "fallback-secret")
    clear_session_credentials()
    monkeypatch.setattr("aa_paths.project_root", lambda: cred_root)
    loaded = load_credentials()
    assert loaded is not None
    assert loaded.api_key == "fallback-key"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_load_credentials_with_explicit_runtime_root(cred_root: Path, monkeypatch) -> None:
    save_monitoring_credentials(cred_root, "runtime-key", "runtime-secret")
    clear_session_credentials()
    other = cred_root / "other"
    other.mkdir()
    monkeypatch.setattr("aa_paths.project_root", lambda: other)
    loaded = load_credentials(cred_root)
    assert loaded is not None
    assert loaded.api_key == "runtime-key"


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI is Windows-only")
def test_populate_gui_fields_from_dpapi(cred_root: Path) -> None:
    from PySide6.QtWidgets import QApplication, QLineEdit

    app = QApplication.instance() or QApplication([])
    save_monitoring_credentials(cred_root, "gui-key", "gui-secret")
    clear_session_credentials()
    key_edit = QLineEdit()
    secret_edit = QLineEdit()
    out = populate_stored_credentials_in_gui(cred_root, key_edit, secret_edit)
    assert out["populated"] is True
    assert key_edit.text() == "gui-key"
    assert secret_edit.text() == "gui-secret"
