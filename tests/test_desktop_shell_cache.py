from __future__ import annotations

import json
import time
from pathlib import Path

import os

from analytics.desktop_shell_cache import (
    cache_paths,
    cache_stale_vs_evidence,
    get_desktop_html_for_hub,
    warm_desktop_cache,
    write_desktop_cache,
)


def test_desktop_fast_render_under_three_seconds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: False)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps(
            {
                "section_title_de": "R3 System",
                "features": [{"id": "terminal", "category": "werkzeug", "label_de": "Terminal"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps({"title_de": "R3 Test"}),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_governance_status.json").write_text(
        json.dumps({"status": "COMPLETE", "progress_pct": 100, "sealed": False}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"passed": 1, "total": 1, "overall_pass": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/launch_progress_latest.json").write_text(
        json.dumps({"overall_pct": 92, "headline_de": "Bereit", "milestones": [], "tiles": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/cognitive_kernel_latest.json").write_text(
        json.dumps(
            {
                "successor_active": True,
                "kernel_generation": 2,
                "headline_de": "Kernel OK",
                "interface": {"active_interface": "build_kernel", "headline_de": "R3"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "profile_used": "daily_alpha_h1", "signal_date": "2026-06-05"}),
        encoding="utf-8",
    )
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"apps": [{"id": "hub", "tier": "core", "label_de": "Hub", "hub_path": "/api/health"}]}),
        encoding="utf-8",
    )
    start = time.monotonic()
    body = get_desktop_html_for_hub(tmp_path, fast=True)
    elapsed = time.monotonic() - start
    text = body.decode("utf-8")
    assert elapsed < 12.0, f"desktop render too slow: {elapsed:.2f}s"
    assert "r3-desktop" in text
    assert "r3-mirror-results" in text
    assert "r3-freigabe-btn" in text
    assert "T212" in text


def test_desktop_cache_served(tmp_path: Path) -> None:
    pad = b"x" * 200
    write_desktop_cache(
        tmp_path,
        b"<html>" + pad + b"<body id='r3-desktop-shell'>cached</body></html>",
        fast=True,
    )
    body = get_desktop_html_for_hub(tmp_path, fast=True, live_prep=False)
    assert b"cached" in body


def _seed_minimal_desktop_fixtures(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps({"section_title_de": "R3", "features": []}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps({"title_de": "R3 Test"}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "profile_used": "daily_alpha_h1", "signal_date": "2026-06-05"}),
        encoding="utf-8",
    )


def test_cache_invalidated_when_evidence_newer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr("aa_adaptive_runtime.probe_internet_prices", lambda **k: False)
    _seed_minimal_desktop_fixtures(tmp_path)
    marker = b"ONLY_CACHED_MARKER_XYZ"
    pad = b"x" * 200
    write_desktop_cache(tmp_path, b"<html>" + pad + marker + b"</html>", fast=True)
    ev = tmp_path / "evidence/r3_freigabe_latest.json"
    ev.write_text('{"updated_at_utc": "2026-06-08T12:00:00+00:00"}', encoding="utf-8")
    cache_path, _ = cache_paths(tmp_path)
    os.utime(ev, (cache_path.stat().st_mtime + 5, cache_path.stat().st_mtime + 5))
    assert cache_stale_vs_evidence(tmp_path) is True
    body = get_desktop_html_for_hub(tmp_path, fast=True, live_prep=False)
    assert marker not in body
