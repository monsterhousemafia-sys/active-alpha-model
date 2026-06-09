"""Refresh guard — no concurrent quote refresh hangs."""
from __future__ import annotations

from aa_refresh_guard import end_quote_refresh, try_begin_quote_refresh


def test_quote_refresh_single_flight() -> None:
    end_quote_refresh()
    assert try_begin_quote_refresh() is True
    assert try_begin_quote_refresh() is False
    end_quote_refresh()
    assert try_begin_quote_refresh() is True
    end_quote_refresh()
