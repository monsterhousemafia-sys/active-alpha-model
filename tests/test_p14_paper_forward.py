"""P14 paper forward tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from integrations.trading212.t212_environment_guard import DEMO_BASE_URL, LIVE_HOST, assert_demo_url
from integrations.trading212.t212_request_allowlist import validate_get_path, validate_method
from paper.p14.engine import run_p14_paper_forward
from research.p14.predecessor_verification import verify_predecessors


def test_t212_live_url_blocked() -> None:
    with pytest.raises(PermissionError):
        assert_demo_url(f"https://{LIVE_HOST}/api/v0/equity/account/summary")


def test_t212_demo_url_allowed() -> None:
    assert_demo_url(DEMO_BASE_URL)


def test_t212_write_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/orders/market")


def test_t212_order_get_path_blocked() -> None:
    with pytest.raises(PermissionError):
        validate_get_path("/equity/orders/market")


def test_allocation_normalization(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    alloc = json.loads((root / "paper/config/p14_user_reference_allocation_500eur.json").read_text(encoding="utf-8"))
    assert alloc["displayed_weight_sum_pct"] == 99.99
    assert alloc["normalization_applied"] is True
    assert abs(sum(p["paper_target_notional_eur"] for p in alloc["positions"]) - 500.0) < 0.05
    assert alloc["source_verified_as_broker_ledger"] is False


def test_predecessor_verification(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    pred = verify_predecessors(root)
    assert pred["all_predecessors_verified"] is True


def test_p14_paper_forward(tmp_path: Path) -> None:
    # copy configs
    import shutil

    root = Path(__file__).resolve().parents[1]
    for rel in ("paper/config/p14_user_reference_allocation_500eur.json",):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    out = run_p14_paper_forward(tmp_path)
    assert out["initial_capital_eur"] == 500.0
    assert out["simulation_only"] is True
    assert out["broker_order_sent"] is False
