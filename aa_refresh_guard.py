"""Non-blocking refresh helpers — prevent stacked network/quote work from hanging the UI."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

_quote_lock = threading.Lock()
_quote_in_progress = False
_quote_started_mono = 0.0
_QUOTE_STALE_IN_PROGRESS_S = 90.0


def try_begin_quote_refresh() -> bool:
    """Return False if another quote refresh is already running (not stale)."""
    global _quote_in_progress, _quote_started_mono
    with _quote_lock:
        now = time.monotonic()
        if _quote_in_progress and (now - _quote_started_mono) < _QUOTE_STALE_IN_PROGRESS_S:
            return False
        _quote_in_progress = True
        _quote_started_mono = now
        return True


def end_quote_refresh() -> None:
    global _quote_in_progress
    with _quote_lock:
        _quote_in_progress = False


def quote_refresh_in_progress() -> bool:
    with _quote_lock:
        return _quote_in_progress


def run_with_timeout(
    fn: Callable[[], T],
    *,
    timeout_s: float,
    default: Optional[T] = None,
) -> T:
    """Run callable in a worker thread; return default on timeout."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn)
        try:
            return fut.result(timeout=max(1.0, float(timeout_s)))
        except FuturesTimeout:
            return default  # type: ignore[return-value]
