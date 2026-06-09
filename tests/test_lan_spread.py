from __future__ import annotations

import json
from pathlib import Path

from analytics.preview_federation import (
    apply_lan_spread,
    hub_bind_host,
    hub_public_base_url,
    verify_lan_spread,
)


def test_hub_bind_respects_lan_bind_over_local_only(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_bind": "127.0.0.1"}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "lan_bind": True,
                "bind_host": "0.0.0.0",
                "public_base_url": "http://192.168.0.42:17890",
                "remote_access_mode": "lan",
            }
        ),
        encoding="utf-8",
    )
    assert hub_bind_host(tmp_path) == "0.0.0.0"
    assert hub_public_base_url(tmp_path) == "http://192.168.0.42:17890"


def test_apply_lan_spread_sets_federation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.preview_federation.detect_lan_ip",
        lambda: "192.168.55.10",
    )

    def _fake_hub(root, restart=False):
        return {"ok": True, "restarted": restart}

    monkeypatch.setattr("tools.preview_hub.ensure_hub_running", _fake_hub)

    def _fake_export(*_a, **_k):
        marker = tmp_path / "evidence/community_spread_export.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        zip_path = tmp_path / "worker_LITE.zip"
        zip_path.write_bytes(b"zip")
        marker.write_text(
            json.dumps({"lite_zip": str(zip_path)}),
            encoding="utf-8",
        )
        return 0

    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0, "stderr": ""})())
    monkeypatch.setattr(
        "analytics.preview_federation._try_ufw_allow",
        lambda _port: {"ok": True, "skipped": True},
    )

    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"hub_port": 17890, "join_token": "tok"}),
        encoding="utf-8",
    )
    doc = apply_lan_spread(tmp_path, home_zip_copy=False)
    assert doc.get("ok") is True
    fed = json.loads((tmp_path / "control/preview_federation.json").read_text(encoding="utf-8"))
    assert fed.get("lan_bind") is True
    assert fed.get("bind_host") == "0.0.0.0"
    assert fed.get("public_base_url") == "http://192.168.55.10:17890"
    assert fed.get("remote_access_mode") == "lan"


def test_verify_lan_spread_checks(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "lan_bind": False,
                "bind_host": "127.0.0.1",
                "public_base_url": "http://127.0.0.1:17890",
            }
        ),
        encoding="utf-8",
    )
    doc = verify_lan_spread(tmp_path)
    assert doc.get("checks_total", 0) >= 4
    assert doc.get("ok") is False
