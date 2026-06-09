"""Desktop-Migration — R3 KI lokal primär."""

from __future__ import annotations



from pathlib import Path

from unittest.mock import MagicMock



from analytics.r3_desktop_migration import (

    cursor_handoff_reply_de,

    is_desktop_cursor_primary,

    write_local_primary_policy,

)





def test_write_local_primary_policy(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.setenv("HOME", str(tmp_path))

    monkeypatch.setattr(

        "analytics.alpha_model_interface_kernel.interface_stack_status",

        lambda root: {"ok": True},

    )

    out = write_local_primary_policy(tmp_path)

    assert out.get("ok") is True

    foundation = (tmp_path / "control/alpha_model_interface.json").read_text(encoding="utf-8")

    assert "r3_ki" in foundation

    assert is_desktop_cursor_primary(tmp_path) is False





def test_local_handoff_no_cursor_account_gate() -> None:

    text = cursor_handoff_reply_de(Path("."))

    assert "R3 KI lokal" in text

    assert "active-alpha-chat" in text

    assert "Konto" in text





def test_run_full_desktop_migration_no_display(tmp_path: Path, monkeypatch) -> None:

    monkeypatch.chdir(tmp_path)

    (tmp_path / "control").mkdir(parents=True, exist_ok=True)

    (tmp_path / "control/r3_os_fusion.json").write_text('{"phase":"B"}', encoding="utf-8")

    (tmp_path / "control/r3_step_b.json").write_text(

        '{"released":true,"phase_active":true}', encoding="utf-8"

    )

    monkeypatch.setattr(

        "analytics.r3_desktop_migration.write_local_primary_policy",

        lambda root: {"ok": True, "foundation": {}, "marker": {}},

    )

    monkeypatch.setattr(

        "analytics.r3_desktop_update.run_desktop_update_action",

        lambda root, launch_ui=True: {"ok": True, "headline_de": "ok"},

    )

    monkeypatch.delenv("DISPLAY", raising=False)

    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)

    from analytics.r3_desktop_migration import run_full_desktop_migration



    doc = run_full_desktop_migration(tmp_path, launch_ui=False)

    assert doc.get("primary_interface") == "r3_ki"

    assert (tmp_path / "evidence/r3_desktop_migration_latest.json").is_file()

