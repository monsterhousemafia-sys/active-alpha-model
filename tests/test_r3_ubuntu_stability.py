from __future__ import annotations

import os

from analytics.r3_ubuntu_stability import apply_ubuntu_qt_env, resolve_fullscreen


def test_resolve_fullscreen_wayland_windowed(monkeypatch) -> None:
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("R3_FULLSCREEN", raising=False)
    assert resolve_fullscreen({"start_fullscreen": True, "start_fullscreen_wayland": False}) is False


def test_resolve_fullscreen_x11(monkeypatch) -> None:
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("R3_FULLSCREEN", raising=False)
    assert resolve_fullscreen({"start_fullscreen": True}) is True


def test_apply_ubuntu_qt_env_password_store() -> None:
    env = apply_ubuntu_qt_env({})
    assert "--password-store=basic" in env.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    assert env.get("QTWEBENGINE_DISABLE_SANDBOX") == "1"
    assert "QT_QPA_PLATFORM" not in env or env.get("QT_QPA_PLATFORM") != "xcb"
