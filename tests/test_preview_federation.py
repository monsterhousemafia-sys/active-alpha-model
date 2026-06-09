from __future__ import annotations

import json
from pathlib import Path

from analytics.preview_federation import (
    build_federation_summary,
    build_share_package,
    is_worker_bundle,
    merge_federation_into_report,
    prepare_worker_bundle_config,
    resolve_worker_hub_url,
    upsert_worker,
)


def test_upsert_and_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PREVIEW_KING", "0")
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "stale_after_s": 900, "join_token": "tok-test"}),
        encoding="utf-8",
    )
    out = upsert_worker(
        tmp_path,
        {
            "worker_id": "node-a",
            "hostname": "node-a",
            "role": "compute",
            "cpus": 8,
            "join_token": "tok-test",
            "preview_ok": True,
            "updated_at_utc": "2026-06-06T12:00:00+00:00",
        },
    )
    assert out["ok"] is True
    summary = build_federation_summary(tmp_path)
    assert summary["workers_online"] >= 1
    assert summary["total_cpus"] >= 8
    ids = {w.get("worker_id") for w in summary.get("workers") or []}
    assert "node-a" in ids


def test_merge_into_report(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text("{}", encoding="utf-8")
    report = merge_federation_into_report(tmp_path, {"passed": 1, "total": 1})
    assert "federation" in report


def test_worker_bundle_detection(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    assert is_worker_bundle(tmp_path) is False
    (tmp_path / "control/preview_worker_join.json").write_text(
        '{"auto_start": true, "hub_join_url": "http://10.0.0.5:17890"}',
        encoding="utf-8",
    )
    assert is_worker_bundle(tmp_path) is True
    assert resolve_worker_hub_url(tmp_path) == "http://10.0.0.5:17890"


def test_prepare_worker_bundle_config(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        '{"public_base_url": "http://192.168.1.1:17890"}',
        encoding="utf-8",
    )
    cfg = prepare_worker_bundle_config(tmp_path)
    assert cfg["role"] == "worker"
    assert cfg["hub_join_url"].startswith("http://")
    assert cfg["auto_start"] is True


def test_share_package_has_join_url(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"public_base_url": "http://10.0.0.5:17890"}),
        encoding="utf-8",
    )
    pkg = build_share_package(tmp_path)
    assert pkg["join_url"].endswith("/join")
    assert "ACTIVE_ALPHA_WORKER_START" in (pkg.get("join_command_de") or "")
    assert pkg.get("export_command_de") == "ai_kernel spread-remote"
    assert "Windows_START" in (pkg.get("join_command_lite_de") or "")


def test_upsert_rejects_bad_token(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "join_token": "secret"}),
        encoding="utf-8",
    )
    out = upsert_worker(
        tmp_path,
        {"worker_id": "w1", "role": "compute", "cpus": 4, "join_token": "wrong"},
    )
    assert out["ok"] is False


def test_prepare_bundle_has_join_token(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"public_base_url": "http://10.0.0.5:17890"}),
        encoding="utf-8",
    )
    cfg = prepare_worker_bundle_config(tmp_path)
    assert cfg.get("join_token")
