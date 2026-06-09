from pathlib import Path

from execution.confirmed_live.order_draft_service import (
    create_draft,
    load_drafts,
    load_queue_summary,
    prune_stale_order_drafts,
    prune_superseded_drafts_for_instrument,
)
from integrations.trading212.t212_order_pacing import (
    MIN_LIMIT_ORDER_GAP_S,
    can_place_limit_order_now,
)


def test_prune_clears_old_drafts(tmp_path: Path) -> None:
    create_draft(
        tmp_path,
        instrument="INTC",
        side="BUY",
        max_notional_eur=10,
        limit_price=10,
        t212_id="INTC_US_EQ",
        quantity=1,
    )
    removed = prune_stale_order_drafts(tmp_path, max_age_minutes=0.0)
    assert removed >= 1
    q = load_queue_summary(tmp_path)
    assert q["waiting_review"] == 0


def test_prune_superseded_keeps_one_symbol_draft(tmp_path: Path) -> None:
    create_draft(
        tmp_path,
        instrument="INTC",
        side="BUY",
        max_notional_eur=10,
        limit_price=10,
        t212_id="INTC_US_EQ",
        quantity=1,
    )
    keep = create_draft(
        tmp_path,
        instrument="INTC",
        side="BUY",
        max_notional_eur=8,
        limit_price=10,
        t212_id="INTC_US_EQ",
        quantity=0.8,
    )
    removed = prune_superseded_drafts_for_instrument(
        tmp_path, "INTC", keep_draft_id=keep["draft_id"]
    )
    assert removed == 1
    assert len(load_drafts(tmp_path)) == 1


def test_order_rate_limit_blocks_rapid_resubmit(tmp_path: Path) -> None:
    from integrations.trading212.t212_order_pacing import record_limit_order_result

    record_limit_order_result(tmp_path, success=False, error="HTTP 429")
    ok, msg = can_place_limit_order_now(tmp_path)
    assert ok is False
    assert "429" not in msg
    assert MIN_LIMIT_ORDER_GAP_S >= 2.5
