from __future__ import annotations

import json
from pathlib import Path

from analytics.whatsapp_auto_send import auto_send_capabilities, auto_send_self, bootstrap_firefox_profile, firefox_profile_dir


def test_auto_send_manual_skip(tmp_path: Path) -> None:
    doc = auto_send_self(
        tmp_path,
        phone="4915756402383",
        text="https://example.com/join",
        zip_path=None,
        cfg={"auto_send_mode": "manual"},
    )
    assert doc.get("skipped") is True


def test_auto_send_fails_without_engines(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("analytics.whatsapp_auto_send.playwright_available", lambda: False)
    monkeypatch.setattr("analytics.whatsapp_auto_send.xdotool_available", lambda: False)
    monkeypatch.setattr("analytics.whatsapp_auto_send.pyautogui_available", lambda: False)
    monkeypatch.setattr("analytics.x11_send.xlib_available", lambda: False)
    doc = auto_send_self(
        tmp_path,
        phone="4915756402383",
        text="hello",
        zip_path=None,
        cfg={"auto_send_mode": "auto"},
    )
    assert doc.get("ok") is False
    assert doc.get("attempts")


def test_bootstrap_firefox_profile(tmp_path: Path) -> None:
    prof = tmp_path / "ff_profile"
    doc = bootstrap_firefox_profile(prof)
    assert doc.get("ok") is True
    assert (prof / "user.js").is_file()
    assert "termsofuse.bypassNotification" in (prof / "user.js").read_text(encoding="utf-8")
    assert (prof / "distribution/policies.json").is_file()


def test_capabilities(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("analytics.whatsapp_auto_send.playwright_available", lambda: False)
    monkeypatch.setattr("analytics.whatsapp_auto_send.xdotool_available", lambda: True)
    cfg = {"playwright_session_dir": "control/secrets/whatsapp_playwright"}
    caps = auto_send_capabilities(tmp_path, cfg)
    assert caps.get("xdotool") is True
    assert caps.get("playwright") is False
