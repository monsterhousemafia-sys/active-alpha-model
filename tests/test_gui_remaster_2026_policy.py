from __future__ import annotations

import json
from pathlib import Path

from analytics.gui_remaster_gate import (
    load_remaster_policy,
    measure_desktop_render_ms,
    verify_remaster_invariants,
)


def test_remaster_policy_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_remaster_policy(root)
    inv = policy.get("invariants_de") or []
    assert len(inv) >= 4
    assert any("Ein Look" in str(x) for x in inv)
    assert any("Safety" in str(x) for x in inv)


def test_remaster_invariants_gate() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = verify_remaster_invariants(root)
    assert doc["total"] >= 6
    assert doc["ok_count"] >= 5
    assert (root / "evidence/gui_remaster_acceptance_latest.json").is_file()


def test_desktop_fast_render_budget(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: False)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "analytics").mkdir(parents=True)
    for name in (
        "r3_surface_theme.py",
        "preview_hub_page.py",
        "desktop_shell_cache.py",
        "gui_preview_visual.py",
        "preview_status_visual.py",
        "preview_system_status.py",
        "hub_launch_ui.py",
        "r3_launch_world.py",
        "local_apps_registry.py",
        "gui_32b_registry.py",
    ):
        (tmp_path / "analytics" / name).write_text(
            "def x():\n  pass\nfast: bool = True\ndesktop_shell_cache\nrender_local_apps_section\n",
            encoding="utf-8",
        )
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps({"section_title_de": "R3", "features": []}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps({"title_de": "R3", "nav": []}),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_governance_status.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"passed": 1, "total": 1, "overall_pass": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/launch_progress_latest.json").write_text(
        json.dumps({"overall_pct": 90, "headline_de": "OK", "milestones": [], "tiles": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/cognitive_kernel_latest.json").write_text(
        json.dumps({"successor_active": True, "interface": {"active_interface": "build_kernel"}}),
        encoding="utf-8",
    )
    (tmp_path / "control/local_apps_manifest.json").write_text(json.dumps({"apps": []}), encoding="utf-8")
    (tmp_path / "control/gui_remaster_2026_policy.json").write_text(
        Path(__file__).resolve().parents[1].joinpath("control/gui_remaster_2026_policy.json").read_text(),
        encoding="utf-8",
    )
    ms = measure_desktop_render_ms(tmp_path, fast=True)
    assert ms < 20000, f"fast render too slow: {ms:.0f}ms"
