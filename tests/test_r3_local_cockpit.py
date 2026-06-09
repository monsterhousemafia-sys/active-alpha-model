from __future__ import annotations

from pathlib import Path

from analytics.r3_local_cockpit import launch_session_cockpit, prefer_native_shell


def test_prefer_native_shell_default() -> None:
    root = Path(__file__).resolve().parents[1]
    assert prefer_native_shell(root) is True


def test_launch_native_cockpit_cmd_uses_str_path_not_posixpath_repr(
    tmp_path: Path, monkeypatch
) -> None:
    """Subprocess -c muss Path('/…') nutzen — nicht PosixPath (NameError)."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".venv/bin").mkdir(parents=True)
    (root / ".venv/bin/python3").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("AA_PROJECT_ROOT", str(root))
    captured: list[list[str]] = []

    def _fake_call(cmd, **kwargs):
        captured.append(list(cmd))
        return 0

    monkeypatch.setattr("analytics.r3_local_cockpit.subprocess.call", _fake_call)
    monkeypatch.setattr(
        "analytics.stack_integrity.ensure_hub_reliable",
        lambda *a, **k: 17890,
    )
    from analytics.r3_local_cockpit import launch_native_cockpit

    launch_native_cockpit(root, hub_path="/r3", block=True)
    assert captured
    script = captured[0][2]
    assert "PosixPath" not in script
    assert f"Path('{root}')" in script or f'Path("{root}")' in script


def test_launch_session_cockpit_no_browser_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    doc = launch_session_cockpit(tmp_path, hub_path="/r3", block=False)
    assert doc.get("shell") != "browser"
    assert "browser" not in str(doc.get("error_de") or "").lower() or doc.get("ok") is False
