from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_local_runtime import (
    apply_local_runtime,
    dampen_warning_for_local,
    is_local_only,
    load_local_runtime,
    verify_local_runtime,
)
from analytics.preview_federation import hub_bind_host, hub_public_base_url


def test_local_runtime_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_local_runtime(root)
    assert cfg.get("local_only") is True
    assert "127.0.0.1" in str(cfg.get("hub_url") or "")


def test_apply_and_verify() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = apply_local_runtime(root)
    assert doc.get("ok") is True
    v = verify_local_runtime(root)
    assert v.get("checks_passed", 0) >= 4
    assert hub_bind_host(root) == "127.0.0.1"
    assert hub_public_base_url(root).startswith("http://127.0.0.1")
    assert is_local_only(root) is True


def test_dampen_fictive_warning() -> None:
    root = Path(__file__).resolve().parents[1]
    assert dampen_warning_for_local(root, "OFFLINE_OR_FICTIVE_PRICES", "critical") == "info"
    assert dampen_warning_for_local(root, "OTHER", "critical") == "critical"
