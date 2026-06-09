"""Trading 212 — Nutzertexte mit Symbolen (keine rohen HTTP-Codes in der EXE)."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

# Symbole für die Desktop-UI (Windows/Qt)
SYM_OK = "✓"
SYM_ERR = "✗"
SYM_WAIT = "⏱"
SYM_KEY = "🔑"
SYM_MONEY = "💶"
SYM_WARN = "⚠"
SYM_INFO = "ℹ"


def _strip_http_codes(text: str) -> str:
    return re.sub(r"\bHTTP\s*\d{3}\b", "", text, flags=re.I).replace("  ", " ").strip()


def _parse_json_detail(raw: str) -> dict[str, Any]:
    brace = raw.find("{")
    if brace < 0:
        return {}
    try:
        blob = json.loads(raw[brace:])
        return blob if isinstance(blob, dict) else {}
    except json.JSONDecodeError:
        return {}


def humanize_t212_error(message: str | None, *, last_sync_utc: Optional[str] = None) -> str:
    """
    Turn broker/technical messages into plain German with a leading symbol.
    Never leaves bare 'HTTP 429' style text for end users.
    """
    if not message or not str(message).strip():
        return f"{SYM_WARN} Unbekannter Fehler — bitte erneut versuchen."

    raw = str(message).strip()
    low = raw.lower()
    detail = _parse_json_detail(raw)
    detail_type = str(detail.get("type") or "").lower()
    detail_text = str(detail.get("detail") or detail.get("title") or "").lower()

    if "429" in low or "rate-limit" in low or "rate limit" in low or "zu viele anfragen" in low:
        lines = [
            f"{SYM_WAIT} Zu viele Anfragen bei Trading 212.",
            "Bitte 1–2 Minuten warten, dann erneut testen oder «Aktualisieren».",
        ]
        if last_sync_utc:
            when = str(last_sync_utc)[:19].replace("T", " ")
            lines.append(f"Letzter erfolgreicher Abruf: {when} (UTC).")
        return "\n".join(lines)

    if "401" in low or "bad api" in low or "unauthorized" in low:
        return (
            f"{SYM_KEY} API Key oder Secret ist ungültig.\n"
            "Bitte in der Trading-212-App einen neuen Key mit Lese- und Order-Rechten erzeugen."
        )

    if "403" in low or "scope" in low or "missing for api" in low:
        return (
            f"{SYM_KEY} API-Key hat nicht die nötigen Rechte (403).\n"
            "In T212: Key mit Konto lesen und Orders ausführen aktivieren."
        )

    if "min-quantity-exceeded" in detail_type or "must trade at least" in detail_text:
        m = re.search(r"must trade at least ([0-9]+(?:\.[0-9]+)?)", raw, re.I)
        min_q = m.group(1) if m else "—"
        return (
            f"{SYM_INFO} Stückzahl zu klein — T212-Minimum: {min_q}.\n"
            "Die App passt die Menge beim nächsten Versuch automatisch an."
        )

    if "extended-hours-trading-not-allowed" in detail_type or "extended hours" in detail_text:
        return (
            f"{SYM_INFO} Extended-Hours sind für dieses Konto nicht freigeschaltet.\n"
            "Orders nur während US-Regular-Session (Mo–Fr 09:30–16:00 New York)."
        )

    if "insufficient-free-for-stocks-buy" in detail_type or "insufficient funds" in detail_text:
        return (
            f"{SYM_MONEY} Trading 212 lehnt den Aktienkauf ab (nicht die API-Berechtigung).\n"
            "Ihr Key hat «Orders ausführen» — die Order erreicht T212, wird aber abgewiesen.\n"
            "Guthaben/Reservierung reicht für diese Order nicht (oder Session/Pending-Orders).\n"
            "Typische Ursachen: (1) US-Regular-Session geschlossen (Mo–Fr 09:30–16:00 New York), "
            "(2) Kauf einmal in der T212-App testen (gleiches Instrument), "
            "(3) Invest-Konto (API nur Invest/Stocks ISA), (4) offene Pending-Orders in T212."
        )

    if "400" in low or "abgelehnt" in low:
        if "timevalidity" in low or "gültigkeit" in low:
            return (
                f"{SYM_ERR} Order-Parameter von Trading 212 abgelehnt.\n"
                "Bitte App neu starten und erneut «Order ausführen»."
            )
        return (
            f"{SYM_ERR} Trading 212 hat die Order abgelehnt.\n"
            "Limit, Stückzahl oder Guthaben prüfen — in der T212-App gegentesten."
        )

    if "408" in low or "timed-out" in low or "timeout" in low:
        return f"{SYM_WAIT} Zeitüberschreitung bei Trading 212 — bitte später erneut versuchen."

    if "connection" in low or "verbindung" in low or "network" in low:
        cleaned = _strip_http_codes(raw)
        return f"{SYM_ERR} Verbindung zu Trading 212 fehlgeschlagen.\n{cleaned[:200]}"

    if "nicht konfiguriert" in low or "not_configured" in low or "credentials" in low:
        return f"{SYM_KEY} API noch nicht gespeichert — Key und Secret eingeben und speichern."

    if "warten" in low and "sekunden" in low:
        return f"{SYM_WAIT} {_strip_http_codes(raw)}"

    cleaned = _strip_http_codes(raw)
    if len(cleaned) < 8:
        return f"{SYM_WARN} Verbindungsproblem — bitte erneut versuchen."
    return f"{SYM_ERR} {cleaned[:280]}"


def humanize_connection_status(status: str | None, last_error: str | None = None) -> str:
    """Status line for minimal invest / broker panel."""
    st = str(status or "").upper()
    if st in (
        "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "DEMO_READONLY_CONNECTED",
        "CONNECTED_READONLY_OK",
    ):
        return f"{SYM_OK} Trading 212 verbunden"
    if st == "RATE_LIMITED_SHOWING_CACHED_DATA":
        return humanize_t212_error(last_error or "429")
    if st == "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI":
        return f"{SYM_KEY} API Key und Secret speichern"
    if last_error:
        return humanize_t212_error(last_error)
    if st == "CONNECTION_FAILED_RETRY_AVAILABLE":
        return f"{SYM_ERR} Verbindung fehlgeschlagen — «Aktualisieren»"
    return f"{SYM_WARN} {st.replace('_', ' ').title()}"


def success_message(text: str) -> str:
    return f"{SYM_OK} {text}"


def format_scaled_order_notice(
    *,
    symbol: str,
    target_notional_eur: float,
    executed_notional_eur: float,
    quantity: float,
    limit_price_eur: float,
    scaled_down: bool,
    attempt_count: int = 1,
) -> str:
    """User dialog after order sent (incl. auto-scale explanation)."""
    lines = [
        f"{SYM_OK} Order an Trading 212 gesendet.",
        f"{symbol} · {quantity:.2f} Stück · Limit {limit_price_eur:.2f} €",
        f"Orderwert ca. {executed_notional_eur:.2f} €",
    ]
    if scaled_down or target_notional_eur > executed_notional_eur + 0.05:
        lines.insert(
            1,
            f"{SYM_INFO} Auf ausführbares Kontingent skaliert: "
            f"geplant ca. {target_notional_eur:.2f} € → jetzt ca. {executed_notional_eur:.2f} €.",
        )
        if attempt_count > 1:
            lines.append(f"(Automatisch angepasst nach {attempt_count} Versuch/Versuchen.)")
    lines.append("Bitte in der Trading-212-App prüfen.")
    return "\n".join(lines)


def throttle_wait_message(seconds: int) -> str:
    return (
        f"{SYM_WAIT} Bitte {seconds} Sekunden warten.\n"
        "Trading 212 erlaubt nur wenige API-Anfragen pro Minute."
    )
