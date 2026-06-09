from __future__ import annotations

from pathlib import Path

from analytics.r3_native_apps import NATIVE_APP_IDS, launch_native_app, list_apps, network_panel
from analytics.r3_ubuntu_closure import evaluate_ubuntu_closure, render_ubuntu_closure_section
from analytics.r3_ubuntu_shell import launch_shell_feature


def test_closure_evaluate() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = evaluate_ubuntu_closure(root)
    assert doc.get("closure_percent", 0) >= 50
    assert len(doc.get("features") or []) >= 20
    assert "counts" in doc


def test_closure_render() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_ubuntu_closure_section(root)
    assert "r3-ubuntu-closure" in html
    assert "Ubuntu" in html or "Abschluss" in html


def test_native_tiles_launch() -> None:
    root = Path(__file__).resolve().parents[1]
    for fid in ("calculator", "network", "updates", "lock"):
        assert fid in NATIVE_APP_IDS
        doc = launch_native_app(root, fid)
        assert doc.get("native") is True


def test_shell_native_routing() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = launch_shell_feature(root, "calculator")
    assert doc.get("native") is True


def test_list_apps() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = list_apps(root)
    assert doc.get("ok") is True


def test_network_panel() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = network_panel(root)
    assert doc.get("panel") == "network"
    assert doc.get("plane_ui") is True
