"""R3 Funktionskette — technische Order-Vorbereitung → Submit → UI."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_freigabe import (
    FREIGABE_GOVERNANCE_NOTE_DE,
    load_freigabe,
    package_ready,
    refresh_freigabe_evidence,
)
from analytics.r3_stock_orders import refresh_stock_order_evidence, submit_r3_initial_package
from analytics.r3_trading_functions import build_r3_trading_functions, render_r3_trading_functions_html
from tests.r3_order_fixtures import seed_orders_stack


def test_full_chain_build_refresh_package_ready(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    orders = refresh_stock_order_evidence(tmp_path)
    status = package_ready(tmp_path)

    assert orders["buy_count"] >= 1
    assert orders["initial_package"]["active"] is True
    assert float(orders["initial_package"]["notional_eur"]) > 0
    assert status["ready"] is True

    doc = refresh_freigabe_evidence(tmp_path)
    assert (tmp_path / "evidence/r3_freigabe_latest.json").is_file()
    assert doc["package_ready"] is True
    assert doc.get("governance_note_de") == FREIGABE_GOVERNANCE_NOTE_DE


def test_ui_exec_button_ready_when_package_active(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_freigabe_evidence(tmp_path)

    ready_html = render_r3_trading_functions_html(tmp_path)
    assert "r3-freigabe-btn ready" in ready_html
    assert "T212" in ready_html
    assert "r3-freigabe-governance" in ready_html
    assert "auto_execute_real_money" in ready_html

    _patch_pkg_inactive(tmp_path)

    blocked_html = render_r3_trading_functions_html(tmp_path)
    assert "r3-freigabe-btn ready" not in blocked_html
    assert "r3-freigabe-btn blocked" in blocked_html

    exec_html = render_r3_trading_functions_html(tmp_path, exec_only=True)
    assert "r3-freigabe-governance" not in exec_html
    assert "auto_execute_real_money" not in exec_html


def test_load_prep_creates_evidence_when_missing(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    doc = load_freigabe(tmp_path)
    assert doc.get("package_ready") is True
    assert (tmp_path / "evidence/r3_freigabe_latest.json").is_file()


def test_package_not_ready_when_inactive(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    orders = json.loads((tmp_path / "evidence/r3_trading_functions_latest.json").read_text(encoding="utf-8"))
    orders["initial_package"]["active"] = False
    (tmp_path / "evidence/r3_trading_functions_latest.json").write_text(json.dumps(orders), encoding="utf-8")
    orders2 = json.loads((tmp_path / "evidence/r3_stock_orders_latest.json").read_text(encoding="utf-8"))
    orders2["initial_package"]["active"] = False
    (tmp_path / "evidence/r3_stock_orders_latest.json").write_text(json.dumps(orders2), encoding="utf-8")
    assert package_ready(tmp_path)["ready"] is False


def _write(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def _patch_pkg_inactive(tmp_path: Path) -> None:
    fn_path = tmp_path / "evidence/r3_trading_functions_latest.json"
    if fn_path.is_file():
        fn_doc = json.loads(fn_path.read_text(encoding="utf-8"))
        fn_doc["initial_package"] = {**(fn_doc.get("initial_package") or {}), "active": False}
        _write(fn_path, fn_doc)
    orders_path = tmp_path / "evidence/r3_stock_orders_latest.json"
    orders = json.loads(orders_path.read_text(encoding="utf-8"))
    orders["initial_package"] = {**(orders.get("initial_package") or {}), "active": False}
    orders_path.write_text(json.dumps(orders), encoding="utf-8")


def test_submit_initial_package_requires_confirm(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    out = submit_r3_initial_package(tmp_path, confirmed=False)
    assert out["ok"] is False
    assert out["error"] == "CONFIRMATION_REQUIRED"


def test_submit_blocks_when_freigabe_not_ready(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    with patch(
        "analytics.r3_freigabe.package_ready",
        return_value={"ready": False, "headline_de": "T212-Konto bestätigen"},
    ):
        out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is False
    assert out["error"] == "FREIGABE_NOT_READY"


@patch("analytics.r3_stock_orders._try_execute_pending_r3_deferred", return_value=None)
@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=True)
@patch("analytics.r3_stock_orders._precheck_order_rows", return_value={"ok": True, "failures": [], "quote_snapshot": {}})
@patch("analytics.r3_stock_orders._execute_stock_row")
@patch("analytics.r3_stock_orders._grant_r3_lease")
def test_submit_not_blocked_by_open_trading_cycle(
    mock_lease, mock_exec, _mock_precheck, _mock_live, _mock_auto, _mock_deferred, tmp_path: Path
) -> None:
    mock_lease.return_value = {"ok": True}
    mock_exec.return_value = {"ok": True, "notional_eur": 320.0, "symbol": "STX"}
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": False}),
        encoding="utf-8",
    )
    out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is True
    assert out.get("mode") == "initial_package"


@patch("analytics.r3_stock_orders._try_execute_pending_r3_deferred", return_value=None)
@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=True)
@patch("analytics.r3_stock_orders._precheck_order_rows", return_value={"ok": True, "failures": [], "quote_snapshot": {}})
@patch("analytics.r3_stock_orders._execute_stock_row")
@patch("analytics.r3_stock_orders._grant_r3_lease")
def test_batch_partial_success_persisted(
    mock_lease, mock_exec, _mock_precheck, _mock_live, _mock_auto, _mock_deferred, tmp_path: Path
) -> None:
    mock_lease.return_value = {"ok": True}
    mock_exec.side_effect = [
        {"ok": True, "notional_eur": 100.0, "symbol": "STX"},
        {"ok": False, "notional_eur": 50.0, "symbol": "SPY", "error": "BROKER_REJECT"},
    ]
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out.get("partial") is True
    assert out["orders_submitted"] == 1
    assert out["orders_failed"] == 1
    batch = json.loads((tmp_path / "evidence/r3_order_batch_latest.json").read_text())
    assert batch.get("partial") is True


@patch("analytics.r3_stock_orders._try_execute_pending_r3_deferred", return_value=None)
@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=True)
@patch("analytics.r3_stock_orders._precheck_order_rows", return_value={"ok": True, "failures": [], "quote_snapshot": {}})
@patch("analytics.r3_stock_orders._execute_stock_row")
@patch("analytics.r3_stock_orders._grant_r3_lease")
def test_submit_initial_package_uses_stock_orders_batch(
    mock_lease, mock_exec, _mock_precheck, _mock_live, _mock_auto, _mock_deferred, tmp_path: Path
) -> None:
    mock_lease.return_value = {"ok": True}
    mock_exec.return_value = {"ok": True, "notional_eur": 320.0, "symbol": "STX"}
    seed_orders_stack(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)

    out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is True
    assert out["mode"] == "initial_package"
    assert out["execution_path_de"] == "r3_stock_orders_batch"
    assert mock_exec.call_count >= 1
    mock_lease.assert_called_once()
    assert (tmp_path / "evidence/r3_order_batch_latest.json").is_file()


@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=False)
@patch("analytics.r3_stock_orders._resolve_limit_price", return_value=0.0)
def test_initial_package_defers_when_no_live_quotes(_mock_limit, _mock_live, _mock_auto, tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    from execution.confirmed_live.us_equity_deferred_intents import default_policy, save_policy

    save_policy(tmp_path, default_policy())
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "champion_id": "R3_w075_q065_noexit",
                "signal_date": "2026-06-05",
                "allocations": [{"symbol": "STX", "target_eur": 50.0, "side": "BUY"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "paper/p16d/fx_observation_ledger").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper/p16d/fx_observation_ledger/fx_observations.jsonl").write_text(
        json.dumps({"usd_to_eur_rate": 0.86, "usd_fx_quality_gate": "PASS"}) + "\n",
        encoding="utf-8",
    )
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    with patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_deferred",
        return_value=25.0,
    ):
        out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is True
    assert out.get("mode") == "deferred_package"
    assert int(out.get("orders_deferred") or 0) >= 1
    assert (tmp_path / "evidence/r3_order_batch_latest.json").is_file()


def test_trading_functions_and_orders_share_stocks(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    fn_doc = build_r3_trading_functions(tmp_path, persist=True)
    orders = json.loads((tmp_path / "evidence/r3_stock_orders_latest.json").read_text())
    fn_syms = [r["symbol"] for r in fn_doc.get("stocks") or []]
    ord_syms = [r["symbol"] for r in orders.get("stocks") or []]
    assert fn_syms == ord_syms
    assert fn_doc["initial_package"]["notional_eur"] == orders["initial_package"]["notional_eur"]
    assert fn_doc.get("orders_ref") == "evidence/r3_stock_orders_latest.json"


def test_ensure_kernel_remerges_stale_king_symbol(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    king_path = tmp_path / "evidence/king_trading_assist_latest.json"
    king = json.loads(king_path.read_text())
    king["trade_decisions"].append({"symbol": "FAKE", "side": "BUY", "sanctioned": True})
    king_path.write_text(json.dumps(king), encoding="utf-8")
    from analytics.kernel_trade_decisions import ensure_kernel_trade_decisions

    doc = ensure_kernel_trade_decisions(tmp_path)
    follow_on = list(doc.get("follow_on_suggestions") or [])
    syms = {str(d.get("symbol") or "").upper() for d in follow_on}
    assert "FAKE" not in syms
    assert "STX" in syms
    assert doc.get("advisory_only") is True


def test_refresh_orders_scales_to_t212_and_stays_consistent(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path, ref=640.93)
    build_r3_trading_functions(tmp_path, persist=True)
    doc = refresh_stock_order_evidence(tmp_path)
    buys = [r for r in doc["stocks"] if r.get("side") == "BUY"]
    assert buys
    buy_sum = sum(float(r.get("notional_eur") or r.get("gap_eur") or 0) for r in buys)
    pkg_n = float(doc["initial_package"]["notional_eur"])
    assert pkg_n > 0
    assert abs(buy_sum - pkg_n) < 2.0
    assert package_ready(tmp_path)["ready"] is True
