"""R3 Mirror Capital — Trust-Gating für Spiegel und Order-Oberfläche."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_mirror_capital import (
    OPERATOR_SYNC_HINT_DE,
    collect_execution_package,
    gate_execution_package,
    gate_orders_doc_for_display,
    resolve_mirror_account,
)
from tests.r3_order_fixtures import seed_orders_stack


def test_untrusted_caps_execution_and_orders(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": False,
                "credentials_configured": True,
                "broker_status": "CONNECTION_FAILED_RETRY_AVAILABLE",
                "cash_eur": None,
            }
        ),
        encoding="utf-8",
    )
    acct = resolve_mirror_account(tmp_path)
    assert acct.get("t212_trusted") is False
    assert acct.get("investable_eur") is None
    assert acct.get("capital_message_de") == OPERATOR_SYNC_HINT_DE

    orders_path = tmp_path / "evidence/r3_stock_orders_latest.json"
    raw = json.loads(orders_path.read_text(encoding="utf-8"))
    pkg = gate_execution_package(collect_execution_package(raw), t212_trusted=False)
    assert pkg.get("notional_eur") == 0.0
    assert pkg.get("lines") == []

    gated = gate_orders_doc_for_display(raw, t212_trusted=False)
    assert gated.get("stocks") == []
    assert float((gated.get("initial_package") or {}).get("notional_eur") or 0) == 0.0
