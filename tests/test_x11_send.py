from __future__ import annotations

import time
from pathlib import Path

from analytics import x11_send


def test_attach_zip_dialog_missing_file(tmp_path: Path) -> None:
    doc = x11_send.attach_zip_dialog(str(tmp_path / "missing.zip"))
    assert doc.get("ok") is False


def test_copy_clipboard_empty() -> None:
    doc = x11_send.copy_clipboard("   ")
    assert doc.get("ok") is False


def test_attach_zip_dialog_mocked(monkeypatch, tmp_path: Path) -> None:
    z = tmp_path / "world.zip"
    z.write_bytes(b"zip")
    calls: list[str] = []

    def fake_hotkey(*keys: str):
        calls.append("+".join(keys))
        return {"ok": True, "detail_de": "hotkey"}

    def fake_key(key: str = "Return"):
        calls.append(key)
        return {"ok": True, "detail_de": key}

    monkeypatch.setattr(x11_send, "press_hotkey", fake_hotkey)
    monkeypatch.setattr(x11_send, "press_key", fake_key)
    monkeypatch.setattr(x11_send, "copy_clipboard", lambda _t: {"ok": True, "tool": "mock"})
    monkeypatch.setattr(time, "sleep", lambda _s: None)

    doc = x11_send.attach_zip_dialog(str(z))
    assert doc.get("ok") is True
    assert doc.get("zip_auto") is True
    assert "shift+Tab" in calls or "Shift_L+Tab" in "+".join(calls) or any("Tab" in c for c in calls)
