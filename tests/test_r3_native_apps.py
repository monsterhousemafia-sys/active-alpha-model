"""R3 native Kern-Apps."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_native_apps import (
    NATIVE_CSS,
    NATIVE_JS,
    _warn_rows,
    build_notifications,
    launch_native_app,
    list_files,
    native_apps_ready,
    native_settings,
)


def test_native_apps_ready_project() -> None:
    root = Path(__file__).resolve().parents[1]
    assert native_apps_ready(root) is True


def test_list_files_home() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = list_files(root, subpath="")
    assert doc.get("ok") is True
    assert "entries" in doc


def test_launch_native_files() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = launch_native_app(root, "files")
    assert doc.get("ok") is True
    assert doc.get("native") is True


def test_native_settings_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = native_settings(root)
    assert doc.get("ok") is True
    assert "step_a" in doc


def test_warn_rows_nested_dict() -> None:
    doc = {"warnings": {"warnings": [{"message_de": "A"}, {"detail_de": "B"}]}}
    assert len(_warn_rows(doc)) == 2


def test_build_notifications_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_notifications(root)
    assert doc.get("ok") is True
    assert isinstance(doc.get("items"), list)


def test_native_window_layer_assets() -> None:
    assert "r3-native-win" in NATIVE_CSS
    assert "r3NativeWinEnsureStage" in NATIVE_JS
    assert "r3WinSnap" in NATIVE_JS
    assert "r3-native-light--close" in NATIVE_CSS
    assert "r3NativeFilesBind" in NATIVE_JS
    assert "data-r3-idx" in NATIVE_JS
    assert "r3NativeNetworkBind" in NATIVE_JS


def test_native_open_does_not_block_on_fetch() -> None:
    """UI öffnet sofort — API-Check nur im Hintergrund."""
    idx = NATIVE_JS.find("async function r3NativeOpen")
    body = NATIVE_JS[idx : idx + 1400]
    assert "try { opener(); }" in body
    assert "fetch('/api/desktop/native" in body
    assert body.find("try { opener(); }") < body.find("fetch('/api/desktop/native")


def test_list_files_rejects_traversal(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_native_apps.json").write_text("{}", encoding="utf-8")
    doc = list_files(tmp_path, subpath="../etc")
    assert doc.get("ok") is True
    assert "etc" not in str(doc.get("path"))
