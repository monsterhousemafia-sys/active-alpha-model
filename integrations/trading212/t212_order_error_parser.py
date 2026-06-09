"""Parse T212 limit-order HTTP errors into actionable categories."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedT212OrderError:
    category: str
    detail_type: str
    message_de: str
    min_quantity: Optional[float] = None


_MIN_QTY_RE = re.compile(r"must trade at least ([0-9]+(?:\.[0-9]+)?)", re.I)


def parse_t212_order_error(message: str) -> ParsedT212OrderError:
    low = str(message or "").lower()
    detail_type = ""
    if "/api-errors/" in low:
        try:
            detail_type = low.split("/api-errors/", 1)[1].split('"', 1)[0]
        except IndexError:
            detail_type = ""

    if "min-quantity-exceeded" in low or "must trade at least" in low:
        m = _MIN_QTY_RE.search(str(message or ""))
        min_q = float(m.group(1)) if m else None
        return ParsedT212OrderError(
            category="min_quantity",
            detail_type=detail_type or "min-quantity-exceeded",
            message_de=(
                f"Mindest-Stückzahl laut T212: {min_q:.4f}."
                if min_q
                else "Stückzahl unter T212-Minimum."
            ),
            min_quantity=min_q,
        )

    if "insufficient-free-for-stocks-buy" in low or "insufficient funds" in low:
        return ParsedT212OrderError(
            category="insufficient",
            detail_type=detail_type or "insufficient-free-for-stocks-buy",
            message_de="insufficient funds",
        )

    if "invalid-request" in low or "invalid payload" in low:
        return ParsedT212OrderError(
            category="invalid_request",
            detail_type=detail_type or "invalid-request",
            message_de="Ungültige Order-Daten.",
        )

    if "429" in low or "too many requests" in low or "toomanyrequests" in low:
        return ParsedT212OrderError(
            category="rate_limit",
            detail_type=detail_type or "rate_limit",
            message_de="429",
        )

    if "403" in low or "forbidden" in low or "scope" in low or "permission" in low:
        return ParsedT212OrderError(
            category="permission",
            detail_type=detail_type or "forbidden",
            message_de="permission",
        )

    return ParsedT212OrderError(
        category="unknown",
        detail_type=detail_type or "unknown",
        message_de=str(message or "unknown")[:200],
    )


def is_min_quantity_error(message: str | None) -> bool:
    return parse_t212_order_error(str(message or "")).category == "min_quantity"


def extract_min_quantity(message: str | None) -> Optional[float]:
    return parse_t212_order_error(str(message or "")).min_quantity
