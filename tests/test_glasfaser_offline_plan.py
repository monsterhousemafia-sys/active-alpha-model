"""Glasfaser-Umzug — 3-Phasen-Plan."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.glasfaser_offline_plan import (
    _backup_worker_zip,
    evaluate_gate,
    initiate_glasfaser_plan,
    load_glasfaser_plan,
    scan_glasfaser_offline,
    set_glasfaser_phase,
)


def _seed(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1]
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/GLASFASER_OFFLINE_PLAN.json").write_text(
        (src / "control/GLASFASER_OFFLINE_PLAN.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(parents=True)
    (tmp_path / "docs/LINUX_COMMUNITY_DE.md").write_text("# test\n" * 50, encoding="utf-8")


def test_plan_has_three_phases(tmp_path: Path) -> None:
    _seed(tmp_path)
    plan = load_glasfaser_plan(tmp_path)
    assert len(plan.get("phases") or []) == 3


def test_initiate_sets_before_offline(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = initiate_glasfaser_plan(tmp_path, persist=True)
    assert doc.get("active_phase_id") == "before_offline"
    state = json.loads((tmp_path / "control/glasfaser_offline_state.json").read_text(encoding="utf-8"))
    assert state.get("status") == "ACTIVE"
    assert (tmp_path / "evidence/glasfaser_offline_latest.json").is_file()


def test_go_offline_phase(tmp_path: Path) -> None:
    _seed(tmp_path)
    initiate_glasfaser_plan(tmp_path, persist=False)
    scan = set_glasfaser_phase(tmp_path, phase_id="during_offline", ack=True, persist=True)
    assert scan.get("active_phase_id") == "during_offline"
    assert evaluate_gate(tmp_path, "offline_ack")["ok"] is True


def test_zip_backup(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path)
    lite = tmp_path.parent / "active_alpha_worker_LITE.zip"
    lite.write_bytes(b"PK" + b"\x00" * 2000)
    monkeypatch.setattr(
        "analytics.worker_export_sync.load_export_marker",
        lambda _r: {"lite_zip": str(lite)},
    )
    out = _backup_worker_zip(tmp_path)
    assert out.get("ok") is True
    assert (tmp_path / "evidence/glasfaser_offline/worker_LITE_backup.zip").is_file()


def test_tunnel_token_gate_reports_missing(tmp_path: Path) -> None:
    _seed(tmp_path)
    with patch(
        "analytics.remote_hub_access.remote_access_status",
        return_value={"tunnel_token_set": False, "stable": False},
    ):
        g = evaluate_gate(tmp_path, "tunnel_token_set")
    assert g["ok"] is False
    assert "setup_cloudflare_tunnel_token" in g["detail_de"]
