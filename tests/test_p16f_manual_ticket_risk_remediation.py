"""P16F manual ticket risk remediation tests."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from integrations.trading212.t212_live_readonly_allowlist import validate_live_method
from integrations.trading212.t212_request_allowlist import validate_method
from paper.p16f.real_cash_ledger import build_real_cash_state
from paper.p16f.ticket_batch_budget_allocator import allocate_ticket_batch
from paper.p16f.ticket_supersession import analyze_p16e_ticket_budget, supersede_p16e_tickets
from research.p16f.p16e_import_verification import EXPECTED_P16E_ZIP_SHA256, verify_p16e_import


def test_p16e_import(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[1]
    r = verify_p16e_import(root)
    assert r["zip_sha256_match"] is True
    assert r["expected_sha256"] == EXPECTED_P16E_ZIP_SHA256


def test_p16e_budget_breach_detected() -> None:
    tickets = [
        {"status": "READY_FOR_USER_MANUAL_REVIEW", "maximum_manual_order_notional_eur": 88.51, "estimated_costs_eur": 0.177}
        for _ in range(6)
    ]
    b = analyze_p16e_ticket_budget(tickets)
    assert b["p16e_ready_ticket_count"] == 6
    assert b["budget_breach_confirmed"] is True
    assert b["p16e_aggregate_budget_breach_eur"] > 0


def test_supersede_moves_tickets(tmp_path: Path) -> None:
    pending = tmp_path / "live_pilot/manual_execution/pending_tickets"
    pending.mkdir(parents=True)
    t = {"ticket_id": "abc", "instrument": "OXY", "status": "READY_FOR_USER_MANUAL_REVIEW", "maximum_manual_order_notional_eur": 88.51, "estimated_costs_eur": 0.177}
    (pending / "abc.json").write_text(json.dumps(t), encoding="utf-8")
    out = supersede_p16e_tickets(tmp_path)
    assert out["tickets_superseded"] == 1
    assert not (pending / "abc.json").exists()
    assert (tmp_path / "live_pilot/manual_execution/superseded_invalid_tickets/p16e/abc.json").is_file()


def test_virtual_cash_cannot_authorize_real_tickets(tmp_path: Path) -> None:
    ck = tmp_path / "paper/p16d/runtime_checkpoint.json"
    ck.parent.mkdir(parents=True, exist_ok=True)
    ck.write_text(json.dumps({"cash_eur": 500.0}), encoding="utf-8")
    state = build_real_cash_state(tmp_path, readonly_broker_cash=None)
    assert state["available_real_manual_ticket_budget_eur"] == 0.0
    assert state["virtual_cash_used_as_real_cash_authority"] is False


def test_cumulative_budget_no_ready_without_broker_cash(tmp_path: Path) -> None:
    inst = [{"user_reference_symbol": "OXY", "allowed_action": "VIRTUAL_FILL_VALID"}]
    out = allocate_ticket_batch(tmp_path, instruments=inst, prices_eur={"OXY": 51.0}, available_budget_eur=450.0, broker_cash_verified=False, provider_event_time_available=False)
    assert out["ready_for_user_manual_review"] == 0
    assert out["draft_tickets"] >= 1


def test_cumulative_budget_sequential(tmp_path: Path) -> None:
    inst = [{"user_reference_symbol": s} for s in ("OXY", "WDC", "STX", "INTC", "MU", "CIEN")]
    prices = {s: 50.0 for s in ("OXY", "WDC", "STX", "INTC", "MU", "CIEN")}
    out = allocate_ticket_batch(tmp_path, instruments=inst, prices_eur=prices, available_budget_eur=450.0, broker_cash_verified=True, provider_event_time_available=True)
    assert out["aggregate_ticket_budget_gate"] == "PASS"
    assert out["aggregate_ready_total_eur"] <= 450.0


def test_t212_blocks_writes_and_orders() -> None:
    with pytest.raises(PermissionError):
        validate_method("POST", "/equity/account/summary")
    with pytest.raises(PermissionError):
        validate_live_method("GET", "/equity/orders")


def test_p16f_engine(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    from tests.paper_observation_stub import ensure_observation_dir

    ensure_observation_dir(tmp_path, root, "p16e_fast_track_manual_live_readiness")
    pending = tmp_path / "live_pilot/manual_execution/pending_tickets"
    pending.mkdir(parents=True)
    for i, sym in enumerate(("OXY", "WDC", "STX", "INTC", "MU", "CIEN")):
        t = {"ticket_id": f"id{i}", "instrument": sym, "status": "READY_FOR_USER_MANUAL_REVIEW", "maximum_manual_order_notional_eur": 88.51, "estimated_costs_eur": 0.177}
        (pending / f"id{i}.json").write_text(json.dumps(t), encoding="utf-8")
    for rel in ("paper/config/p14_user_reference_allocation_500eur.json", "paper/config/p16_forward_observation_and_scaling_policy.json"):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dst)
    for ck in ("paper/p16c/runtime_checkpoint.json", "paper/p16d/runtime_checkpoint.json"):
        if (root / ck).is_file():
            d = tmp_path / ck
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / ck, d)

    with mock.patch("paper.p16d.multi_currency_fx_feed.fetch_multi_currency_fx") as mfx:
        mfx.return_value = {"usd_fx_quality_gate": "PASS", "gbp_fx_quality_gate": "PASS", "usd_to_eur_rate": 0.86, "gbp_to_eur_rate": 1.17, "usd_fx_source": "T", "gbp_fx_source": "T", "fx_event_time_utc": "2026-06-01T12:00:00+00:00"}
        from paper.p16f.engine import run_p16f_remediation

        out = run_p16f_remediation(tmp_path)
    assert out["real_capital_deployed_by_cursor_eur"] == 0.0
    assert out["ticket_supersession"]["tickets_superseded"] == 6
    assert out["safety_semantics"]["p16e_ticket_execution_allowed"] is False
