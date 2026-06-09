from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools import universal_preview_worker as uw


def test_load_join_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / uw.JOIN_NAME).write_text(
        json.dumps({"hub_join_url": "http://10.0.0.1:17890", "join_token": "tok"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(uw, "bundle_dir", lambda: tmp_path)
    doc = uw.load_join_config()
    assert doc["hub_join_url"] == "http://10.0.0.1:17890"


def test_load_join_config_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(uw, "bundle_dir", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        uw.load_join_config()


def test_collect_contribution(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(uw, "stable_worker_id", lambda: "host-abc12345")
    doc = {"hub_join_url": "http://10.0.0.1:17890", "join_token": "secret"}
    payload = uw.collect_contribution(doc)
    assert payload["worker_id"] == "host-abc12345"
    assert payload["role"] == "compute"
    assert payload["cpus"] >= 1
    assert payload["join_token"] == "secret"
    assert payload["preview_ok"] is True
    assert payload["remote_join"] is False


def test_collect_contribution_remote(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(uw, "stable_worker_id", lambda: "host-abc12345")
    doc = {"hub_join_url": "https://x.trycloudflare.com", "join_token": "secret"}
    payload = uw.collect_contribution(doc)
    assert payload["remote_join"] is True


def test_stable_worker_id_persists(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    a = uw.stable_worker_id()
    b = uw.stable_worker_id()
    assert a == b
    assert (home / uw._WORKER_STATE_DIR / uw._WORKER_ID_FILE).is_file()


def test_contribute_ok(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(uw, "hub_health", lambda hub: True)
    monkeypatch.setattr(uw, "stable_worker_id", lambda: "w-test")
    join_doc = {"hub_join_url": "http://10.0.0.1:17890", "join_token": "tok"}

    class FakeResp:
        status = 200

        def read(self) -> bytes:
            return json.dumps({"ok": True, "message_de": "OK"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        out = uw.contribute("http://10.0.0.1:17890", join_doc)
    assert out["worker_id"] == "w-test"
    assert out["contribute"]["ok"] is True


def test_main_once(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / uw.JOIN_NAME).write_text(
        json.dumps({"hub_join_url": "http://10.0.0.1:17890"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(uw, "bundle_dir", lambda: tmp_path)
    monkeypatch.setattr(
        uw,
        "contribute",
        lambda hub, doc: {"worker_id": "w1", "hub": hub, "contribute": {"ok": True}},
    )
    monkeypatch.setattr(uw, "_pull_and_run", lambda hub, wid, cpus: [])
    assert uw.main(["--once"]) == 0


def test_lite_bundle_files(tmp_path: Path) -> None:
    """Gate-Struktur: Lite-Paket enthält alle START-Dateien."""
    from analytics.community_spread_plan import _is_lite_worker_bundle

    (tmp_path / "preview_worker_join.json").write_text("{}", encoding="utf-8")
    (tmp_path / "worker.py").write_text("# worker\n", encoding="utf-8")
    (tmp_path / "Windows_START.bat").write_text("@echo off\n", encoding="utf-8")
    assert _is_lite_worker_bundle(tmp_path) is True
