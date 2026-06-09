"""Universal Lite Worker OS launch."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.ulwo_launch import build_install_script, build_ulwo_bundle, load_ulwo_config, render_download_page


def test_load_ulwo_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_ulwo_config(root)
    assert cfg.get("product_name") == "Universal Lite Worker OS"


def test_build_ulwo_bundle(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    doc = build_ulwo_bundle(root)
    assert doc.get("ok") is True
    zip_path = Path(doc["zip_path"])
    assert zip_path.is_file()
    assert zip_path.stat().st_size > 500


def test_install_script_contains_curl() -> None:
    root = Path(__file__).resolve().parents[1]
    sh = build_install_script(root, hub="http://127.0.0.1:17890")
    assert "curl -fsSL" in sh
    assert "Universal_Lite_Worker_OS" in sh


def test_download_page() -> None:
    root = Path(__file__).resolve().parents[1]
    body = render_download_page(root, hub="http://127.0.0.1:17890").decode("utf-8")
    assert "Universal Lite Worker OS" in body
    assert "/api/ulwo/bundle.zip" in body
