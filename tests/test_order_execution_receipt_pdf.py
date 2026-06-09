from pathlib import Path

from execution.confirmed_live.order_execution_receipt_pdf import write_order_execution_receipt


def test_write_order_receipt_pdf(tmp_path: Path) -> None:
    ok, msg = write_order_execution_receipt(
        tmp_path,
        symbol="INTC",
        t212_id="INTC_US_EQ",
        target_notional_eur=42.0,
        limit_price_eur=94.0,
        free_cash_eur=444.0,
        plan_preview={
            "quantity": 0.45,
            "executable_notional_eur": 42.3,
            "scaled_down": False,
        },
        result={
            "ok": False,
            "stage": "submission",
            "error": "insufficient funds",
            "user_message_de": "Testmeldung",
            "attempts": [{"attempt": 1, "quantity": 0.45, "executable_notional_eur": 42.3, "ok": False, "error": "x"}],
        },
        pick={"signal_date": "2026-06-02", "reason_de": "Test"},
    )
    assert ok, msg
    assert Path(msg).is_file()
    assert Path(msg).with_suffix(".json").is_file()
