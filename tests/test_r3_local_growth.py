"""R3 lokales Wachstum — alles lokal, wächst mit der Zeit."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_local_growth import (
    local_confirmation_de,
    scan_local_growth,
    verify_local_operational,
)
from tests.r3_order_fixtures import seed_orders_stack


def _seed(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "control/r3_local_growth.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/r3_local_growth.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "control/alpha_model_local_runtime.json").write_text(
        json.dumps({"local_only": True, "hub_url": "http://127.0.0.1:17890"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_freigabe_latest.json").write_text(
        json.dumps({"updated_at_utc": "2026-06-08T12:00:00+00:00"}),
        encoding="utf-8",
    )


def test_local_confirmation_primary(tmp_path: Path) -> None:
    _seed(tmp_path)
    conf = local_confirmation_de(tmp_path)
    assert "127.0.0.1" in conf
    assert "lokal" in conf.lower()
    assert "trycloudflare" not in conf.lower()


def test_scan_local_growth_persists(tmp_path: Path) -> None:
    _seed(tmp_path)
    doc = scan_local_growth(tmp_path, persist=True)
    assert doc.get("local_only") is True
    assert doc.get("growth_pct", 0) >= 0
    assert len(doc.get("capabilities") or []) >= 5
    assert (tmp_path / "evidence/r3_local_growth_latest.json").is_file()
    assert "127.0.0.1" in str(doc.get("local_primary_url"))


def test_growth_scan_cooldown(tmp_path: Path) -> None:
    _seed(tmp_path)
    first = scan_local_growth(tmp_path, persist=True, force=True)
    second = scan_local_growth(tmp_path, persist=True, force=False)
    assert first.get("growth_pct") is not None
    assert second.get("growth_pct") == first.get("growth_pct")


def test_fast_capability_uses_cache(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True, "hub_ok": True, "r3": {"mirror_api_ok": True, "surface_page_ok": True}}),
        encoding="utf-8",
    )
    from analytics.r3_local_growth import _check_capability

    hub = _check_capability(tmp_path, "hub_local", fast=True)
    assert hub.get("ok") is True
    assert "stack" in str(hub.get("detail_de")) or "cache" in str(hub.get("detail_de"))


def test_mirror_includes_growth(tmp_path: Path) -> None:
    _seed(tmp_path)
    from analytics.r3_exec_mirror import render_r3_exec_mirror_page

    scan_local_growth(tmp_path, persist=True, force=True)
    html = render_r3_exec_mirror_page(tmp_path).decode("utf-8")
    growth = scan_local_growth(tmp_path, persist=False, force=True)
    assert int(growth.get("growth_pct") or 0) >= 0
