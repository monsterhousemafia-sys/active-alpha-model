"""R3 native paths."""
from __future__ import annotations

from pathlib import Path

from analytics.r3_paths import migrate_legacy_share, public_status_paths, r3_share_dir


def test_r3_share_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert str(r3_share_dir()).endswith(".local/share/r3-os")


def test_public_status_paths_r3(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    paths = public_status_paths(tmp_path)
    assert "r3-os" in paths["user_txt"]
    assert "active-alpha" not in paths["user_txt"]


def test_migrate_legacy_share(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    leg = tmp_path / ".local/share/active-alpha"
    leg.mkdir(parents=True)
    (leg / "operator_latest.txt").write_text("legacy", encoding="utf-8")
    doc = migrate_legacy_share()
    assert (tmp_path / ".local/share/r3-os/operator_latest.txt").read_text() == "legacy"
