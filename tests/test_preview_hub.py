from __future__ import annotations

import json
from pathlib import Path

from tools.preview_hub import _hub_healthy, _hub_route_ready, _http_probe, _run_action, make_handler


def test_hub_unknown_action(tmp_path: Path) -> None:
    out = _run_action(tmp_path, "not-real")
    assert out["ok"] is False


def test_hub_health_probe_empty_port() -> None:
    assert _http_probe(1, "/api/health") == b""
    assert _hub_healthy(1) is False
    assert _hub_route_ready(1, "/login") is False


def test_desktop_shell_page_fast(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
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
    from analytics.preview_hub_page import render_desktop_shell_page

    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": True,
                "profile_used": "daily_alpha_h1",
                "signal_date": "2026-06-05",
                "top_picks": [{"ticker": "INTC", "target_weight": 0.12}],
            }
        ),
        encoding="utf-8",
    )
    body = render_desktop_shell_page(tmp_path, port=17890)
    text = body.decode("utf-8")
    assert "r3-desktop" in text
    assert "r3-mirror-results" in text
    assert "Active Alpha" in text
    assert "r3-freigabe-btn" in text
    assert 'class="r3-stock-btn' not in text
    assert "Einzelaktien" not in text
    assert "r3-flow" not in text
    assert 'id="r3-daily-learning"' not in text
    assert 'id="desktop-blockers"' not in text
    assert 'id="r3-central"' not in text
    assert "R3_HUB_PORT" in text


def test_exec_mirror_blocks_legacy_launch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/local_apps_manifest.json").write_text(
        json.dumps({"status": "EXEC_MIRROR_ONLY"}),
        encoding="utf-8",
    )
    from tools.preview_hub import _exec_mirror_route_blocked

    class _Handler:
        def __init__(self) -> None:
            self.status = 0
            self.body = b""

        def send_response(self, code: int) -> None:
            self.status = code

        def send_header(self, key: str, val: str) -> None:
            pass

        def end_headers(self) -> None:
            pass

        @property
        def wfile(self):
            return self

        def write(self, data: bytes) -> None:
            self.body += data

    h = _Handler()
    blocked = _exec_mirror_route_blocked(h, tmp_path, method="GET", path="/launch")
    assert blocked is True
    assert h.status == 410
    assert b"EXEC_MIRROR_ONLY" in h.body


def test_hub_health_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"overall_pass": True, "passed": 1, "total": 1, "cockpit": {}}),
        encoding="utf-8",
    )
    handler_cls = make_handler(tmp_path, 17891)
    assert handler_cls is not None
