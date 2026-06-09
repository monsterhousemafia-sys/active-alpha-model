"""Desktop-Update Phase B."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from analytics.r3_desktop_update import desktop_hub_path, run_desktop_update_action


def test_desktop_hub_path_phase_b(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("analytics.r3_step_b.is_phase_b_active", lambda root: True)
    assert desktop_hub_path(tmp_path) == "/desktop"


def test_desktop_update_no_display(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_os_fusion.json").write_text(
        '{"phase":"B","phase_b_title_de":"B"}', encoding="utf-8"
    )
    (tmp_path / "control/r3_step_b.json").write_text(
        '{"released":true,"phase_active":true}', encoding="utf-8"
    )
    monkeypatch.setattr(
        "analytics.r3_os_supremacy.install_r3_supremacy",
        lambda root: {"ok": True, "headline_de": "ok"},
    )
    monkeypatch.setattr(
        "analytics.r3_desktop_os.install_desktop_os",
        lambda root: {"ok": True},
    )
    monkeypatch.setattr(
        "tools.preview_hub.ensure_hub_running",
        lambda root, port=17890, restart=False: 17890,
    )
    monkeypatch.setattr(
        "analytics.r3_step_b.evaluate_step_b",
        lambda root, persist=True: {"headline_de": "Phase B", "step_b_percent": 40},
    )
    monkeypatch.setattr("analytics.r3_step_b.is_phase_b_active", lambda root: True)
    monkeypatch.setattr(
        "analytics.h1_migration_guard.ensure_h1_migration_healthy",
        lambda root, auto_fix=True: {"ok": True},
    )
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    doc = run_desktop_update_action(tmp_path, launch_ui=True)
    assert doc.get("phase") == "B"
    assert (tmp_path / "evidence/r3_desktop_update_latest.json").is_file()
