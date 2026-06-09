"""R3 Local-First — lokal wirksam, eine HTTPS-Spiegelung."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.preview_federation import hub_public_base_url
from analytics.r3_local_first import (
    apply_r3_local_first,
    https_mirror_base_url,
    is_r3_local_first,
    local_hub_authoritative_url,
    verify_r3_local_first,
)


def test_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.r3_local_first import load_local_first_policy

    policy = load_local_first_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"


def test_apply_local_first_dedupes_mirror(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_local_first_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE", "eliminate_duplicate_tunnels": True}),
        encoding="utf-8",
    )
    mirror = "https://one-mirror.trycloudflare.com"
    other = "https://other-mirror.trycloudflare.com"
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "public_base_url": mirror,
                "public_base_url_locked": True,
                "bind_host": "0.0.0.0",
                "lan_bind": True,
                "remote_workers_expected": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/cloudflare_tunnel.json").write_text(
        json.dumps({"public_url": other}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/ki_tunnel_connection_latest.json").write_text(
        json.dumps(
            {
                "public_base_url": other,
                "freedom_path_de": [f"Tunnel: {other}/desktop", f"Lokal: {other}/join"],
            }
        ),
        encoding="utf-8",
    )
    doc = apply_r3_local_first(tmp_path)
    assert doc.get("ok") is True
    assert doc.get("https_mirror") == mirror
    fed = json.loads((tmp_path / "control/preview_federation.json").read_text(encoding="utf-8"))
    assert fed.get("bind_host") == "127.0.0.1"
    assert fed.get("remote_workers_expected") is False
    assert fed.get("public_base_url") == mirror
    cf = json.loads((tmp_path / "control/cloudflare_tunnel.json").read_text(encoding="utf-8"))
    assert cf.get("public_url") == mirror
    ki = json.loads((tmp_path / "evidence/ki_tunnel_connection_latest.json").read_text(encoding="utf-8"))
    assert ki.get("public_base_url") == mirror
    assert other not in json.dumps(ki)
    runtime = json.loads((tmp_path / "control/alpha_model_local_runtime.json").read_text(encoding="utf-8"))
    assert runtime.get("local_only") is True


def test_hub_public_url_stays_local_when_local_first(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_local_first_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE"}),
        encoding="utf-8",
    )
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps(
            {
                "public_base_url": "https://mirror.trycloudflare.com",
                "public_base_url_locked": True,
                "bind_host": "127.0.0.1",
                "hub_port": 17890,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    assert is_r3_local_first(tmp_path)
    assert hub_public_base_url(tmp_path) == "http://127.0.0.1:17890"
    assert https_mirror_base_url(tmp_path) == "https://mirror.trycloudflare.com"
    assert local_hub_authoritative_url(tmp_path, path="/desktop") == "http://127.0.0.1:17890/desktop"


def test_verify_local_first_project() -> None:
    root = Path(__file__).resolve().parents[1]
    apply_r3_local_first(root)
    doc = verify_r3_local_first(root)
    assert doc.get("checks_passed", 0) >= 4
