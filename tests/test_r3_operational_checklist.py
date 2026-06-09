"""R3 Betriebs-Checkliste — Scanner."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_operational_checklist import scan_operational_checklist


def _seed(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    src = Path(__file__).resolve().parents[1] / "control/r3_operational_checklist.json"
    (root / "control/r3_operational_checklist.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "promotion_gate_config.yaml").write_text(
        (Path(__file__).resolve().parents[1] / "promotion_gate_config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/r3_order_execution_policy.json").write_text(
        json.dumps({"status": "AUTHORITATIVE", "forbidden_order_sources": ["scheduler"]}),
        encoding="utf-8",
    )
    (root / "control/r3_runtime_profile.json").write_text(
        json.dumps({"status": "AUTHORITATIVE", "mirror_poll_ms": 30000, "mirror_soft_update": True}),
        encoding="utf-8",
    )
    (root / "control/king_32b_autonomous_build.json").write_text(
        json.dumps({"autonomous_build_enabled": True}),
        encoding="utf-8",
    )
    (root / "evidence/king_verify_latest.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (root / "evidence/stack_integrity_latest.json").write_text(
        json.dumps({"stack_ok": True, "hub_ok": True, "r3": {"surface_page_ok": True, "mirror_api_ok": True}}),
        encoding="utf-8",
    )
    (root / "evidence/r3_operational_independence_latest.json").write_text(
        json.dumps({"operational_detach": True, "gates_ok": 11, "gates_total": 11}),
        encoding="utf-8",
    )
    (root / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps(
            {
                "closed": True,
                "stages": [
                    {"id": "internet", "ok": True},
                    {"id": "orders", "ok": True, "detail_de": "AUTHORITATIVE"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "evidence/series_readiness_latest.json").write_text(
        json.dumps({"series_ready": True, "readiness_pct": 100}),
        encoding="utf-8",
    )
    (root / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 640.0, "allocations": []}),
        encoding="utf-8",
    )
    (root / "evidence/r3_stock_orders_latest.json").write_text(
        json.dumps({"buy_count": 2, "sell_count": 0, "initial_package": {"active": True}}),
        encoding="utf-8",
    )
    (root / "evidence/r3_freigabe_latest.json").write_text(json.dumps({"package_ready": True}), encoding="utf-8")
    (root / "evidence/r3_trading_functions_latest.json").write_text(
        json.dumps({"functions": [{"id": "sell_notice", "headline_de": "Verkauf"}]}),
        encoding="utf-8",
    )
    (root / "control/r3_trading_functions_policy.json").write_text(json.dumps({"min_trade_eur": 10}), encoding="utf-8")
    (root / "evidence/r3_closed_loop_latest.json").write_text(json.dumps({"loop_ok": True}), encoding="utf-8")
    (root / "control/prediction_readiness.json").write_text(json.dumps({"order_gate_ok": True}), encoding="utf-8")
    (root / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps({"recommended_actions": []}),
        encoding="utf-8",
    )


def test_scan_orders_stage_id(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")

    with patch("analytics.r3_mirror_state.resolve_submission_mode", return_value={"live_submit": False}):
        with patch("analytics.r3_mirror_state.build_exec_mirror_state") as mock_state:
            mock_state.return_value = {
                "display_headline_de": "OK",
                "system_metrics": [{"evidence_ref": "evidence/x.json"}],
                "execution_package": {"sell_lines": [], "lines": []},
            }
            with patch("analytics.local_llm_bridge.ollama_available", return_value=True):
                doc = scan_operational_checklist(tmp_path, persist=True)

    cycle_items = []
    for sec in doc.get("sections") or []:
        if sec.get("id") == "cycle":
            cycle_items = sec.get("items") or []
    orders = next(i for i in cycle_items if i.get("id") == "orders")
    assert orders.get("ok") is True
    assert (tmp_path / "evidence/r3_operational_checklist_latest.json").is_file()


def test_sell_single_partial_when_no_lines(tmp_path: Path, monkeypatch) -> None:
    _seed(tmp_path)
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")

    with patch("analytics.r3_mirror_state.resolve_submission_mode", return_value={"live_submit": False}):
        with patch("analytics.r3_mirror_state.build_exec_mirror_state") as mock_state:
            mock_state.return_value = {
                "display_headline_de": "OK",
                "system_metrics": [{"evidence_ref": "e"}],
                "execution_package": {"sell_lines": [], "lines": [{"symbol": "A"}]},
            }
            with patch("analytics.local_llm_bridge.ollama_available", return_value=True):
                doc = scan_operational_checklist(tmp_path, persist=False)

    trading = next(s for s in doc["sections"] if s["id"] == "trading")
    sell = next(i for i in trading["items"] if i["id"] == "sell_single")
    assert sell["status"] == "PARTIAL"
    assert sell["ok"] is True
