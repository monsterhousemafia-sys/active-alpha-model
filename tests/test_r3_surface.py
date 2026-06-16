"""R3 — eine Oberfläche, keine Legacy-Bildschirme."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.desktop_shell_cache import read_cached_desktop_html, write_desktop_cache
from analytics.r3_surface import (
    CANONICAL_SURFACE_PATH,
    SURFACE_RENDER_VERSION,
    canonical_surface_path,
    exec_mirror_mode,
    is_exec_mirror_surface,
    surface_cache_valid,
    trading_functions_exec_only,
)


def test_exec_mirror_canonical_path(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    assert exec_mirror_mode(tmp_path) is True
    assert is_exec_mirror_surface(tmp_path) is True
    assert canonical_surface_path(tmp_path) == CANONICAL_SURFACE_PATH
    assert trading_functions_exec_only(tmp_path) is True


def test_stale_cache_rejected_without_surface_version(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    cache = tmp_path / "evidence/desktop_shell_page_latest.html"
    meta = tmp_path / "evidence/desktop_shell_cache_meta.json"
    cache.write_bytes(b"<html>legacy desktop fusion tiles</html>" * 20)
    meta.write_text(json.dumps({"bytes": 100, "fast": True}), encoding="utf-8")
    assert read_cached_desktop_html(tmp_path) is None


def test_cache_valid_only_with_matching_surface_version(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    good = {
        "surface_render_version": SURFACE_RENDER_VERSION,
        "exec_mirror_only": True,
        "surface_path": CANONICAL_SURFACE_PATH,
    }
    assert surface_cache_valid(tmp_path, good) is True
    assert surface_cache_valid(tmp_path, {**good, "surface_render_version": "old"}) is False


def test_write_desktop_cache_tags_surface_version(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    body = b"<html><body>R3 mirror only " + (b"x" * 120) + b"</body></html>"
    write_desktop_cache(tmp_path, body, fast=True)
    cached = read_cached_desktop_html(tmp_path)
    assert cached == body
