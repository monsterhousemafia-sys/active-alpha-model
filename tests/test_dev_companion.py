from __future__ import annotations

from pathlib import Path

from ui.interactive_cockpit.dev_companion import (
    format_cursor_handoff,
    get_dev_runtime_info,
    write_cursor_handoff_file,
)


def test_dev_runtime_info_includes_root(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    info = get_dev_runtime_info(tmp_path)
    assert str(tmp_path) in info["runtime_root"]
    assert "credential_storage" in info


def test_cursor_handoff_redacts_and_writes(tmp_path: Path) -> None:
    text = format_cursor_handoff(
        tmp_path,
        nav_view="t212",
        state={"broker": {"credentials_configured": True, "status": "OK"}},
        extra_note="Test ohne Secret",
    )
    assert "t212" in text
    assert "TRADING212_API_SECRET=geheim" not in text
    path = write_cursor_handoff_file(tmp_path, text)
    assert path.is_file()
    assert "Marktanalyse Dev-Kontext" in path.read_text(encoding="utf-8")
