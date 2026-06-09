"""Cooperative cancellation for long-running Marktanalyse jobs."""
from __future__ import annotations

_cancel_requested = False


def request_cancel() -> None:
    global _cancel_requested
    _cancel_requested = True


def clear_cancel() -> None:
    global _cancel_requested
    _cancel_requested = False


def cancel_requested() -> bool:
    return _cancel_requested


def check_cancelled(context: str = "") -> None:
    if _cancel_requested:
        label = f" ({context})" if context else ""
        raise KeyboardInterrupt(f"Marktanalyse abgebrochen{label}")
