"""Format T212 EUR cash balances with live USD equivalent (highlighted)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_USD_HIGHLIGHT = "#7eb8ff"  # matches cockpit ACCENT; keep integrations free of ui.*


def eur_to_usd(eur_amount: float, usd_to_eur_rate: float) -> Optional[float]:
    """Convert EUR to USD using usd_to_eur_rate (EUR per 1 USD)."""
    if usd_to_eur_rate is None or usd_to_eur_rate <= 0:
        return None
    return float(eur_amount) / float(usd_to_eur_rate)


def usd_per_eur(usd_to_eur_rate: float) -> Optional[float]:
    if usd_to_eur_rate is None or usd_to_eur_rate <= 0:
        return None
    return 1.0 / float(usd_to_eur_rate)


def fetch_display_fx(root: Path) -> Dict[str, Any]:
    """Live USD/EUR for cash display; never uses static fallback."""
    root = Path(root)
    try:
        from paper.p16d.multi_currency_fx_feed import fetch_multi_currency_fx

        obs = fetch_multi_currency_fx(root)
    except Exception as exc:
        return {
            "ok": False,
            "usd_to_eur_rate": None,
            "usd_per_eur": None,
            "source": "UNAVAILABLE",
            "fx_event_time_utc": None,
            "error": str(exc),
        }
    rate = obs.get("usd_to_eur_rate")
    ok = obs.get("usd_fx_quality_gate") == "PASS" and rate and float(rate) > 0
    return {
        "ok": bool(ok),
        "usd_to_eur_rate": float(rate) if ok else None,
        "usd_per_eur": usd_per_eur(float(rate)) if ok else None,
        "source": str(obs.get("usd_fx_source") or ""),
        "fx_event_time_utc": obs.get("fx_event_time_utc"),
        "error": obs.get("usd_error") or "",
    }


def _usd_span(usd: float) -> str:
    return (
        f' <span style="color:{_USD_HIGHLIGHT}; font-weight:700; font-size:105%">'
        f"(≈ ${usd:,.2f} USD)</span>"
    )


def format_eur_line_html(
    label: str,
    eur: Optional[float],
    *,
    usd_to_eur_rate: Optional[float],
) -> str:
    if eur is None:
        return f"{label}  —"
    line = f"{label}  {float(eur):,.2f} €"
    if usd_to_eur_rate and usd_to_eur_rate > 0:
        usd = eur_to_usd(float(eur), usd_to_eur_rate)
        if usd is not None:
            line += _usd_span(usd)
    return line


def format_cash_display_html(
    *,
    cash_eur: Optional[float],
    cash_breakdown: Optional[Dict[str, Any]],
    fx: Dict[str, Any],
) -> Tuple[str, str]:
    """
    Return (rich_text_lines, fx_footer_de).
    Every EUR amount includes highlighted USD equivalent when FX is available.
    """
    bd = cash_breakdown or {}
    rate = fx.get("usd_to_eur_rate") if fx.get("ok") else None
    lines: List[str] = []
    lines.append(
        format_eur_line_html("Frei handelbar (T212)", cash_eur, usd_to_eur_rate=rate)
    )
    reserved = bd.get("reserved_for_orders_eur")
    if reserved is not None and float(reserved) > 0:
        lines.append(
            format_eur_line_html(
                "Reserviert (Orders)", float(reserved), usd_to_eur_rate=rate
            )
        )
    in_pies = bd.get("in_pies_eur")
    if in_pies is not None and float(in_pies) > 0:
        lines.append(
            format_eur_line_html(
                "In Pies (nicht planbar)", float(in_pies), usd_to_eur_rate=rate
            )
        )
    total = bd.get("total_account_value_eur")
    if total is not None:
        lines.append(
            format_eur_line_html(
                "Kontowert gesamt (Info)", float(total), usd_to_eur_rate=rate
            )
        )
    if fx.get("ok") and fx.get("usd_per_eur"):
        ts = (fx.get("fx_event_time_utc") or "")[:19].replace("T", " ")
        footer = (
            f"Spot: 1 EUR = {float(fx['usd_per_eur']):.4f} USD "
            f"({fx.get('source') or 'FX'}, {ts} UTC)"
        )
    else:
        footer = "USD-Gegenwert: Kurs momentan nicht verfügbar (nur EUR angezeigt)."
    return "<br>".join(lines), footer


def format_cash_display_plain(
    *,
    cash_eur: Optional[float],
    cash_breakdown: Optional[Dict[str, Any]],
    fx: Dict[str, Any],
) -> Tuple[str, str]:
    """Plain-text cash block (interactive cockpit QLabel without RichText)."""
    bd = cash_breakdown or {}
    rate = fx.get("usd_to_eur_rate") if fx.get("ok") else None
    lines: List[str] = []

    def _plain_line(label: str, eur: Optional[float]) -> str:
        if eur is None:
            return f"{label}  —"
        text = f"{label}  {float(eur):,.2f} €"
        if rate and rate > 0:
            usd = eur_to_usd(float(eur), float(rate))
            if usd is not None:
                text += f"  (≈ ${usd:,.2f} USD)"
        return text

    lines.append(_plain_line("Frei handelbar (T212)", cash_eur))
    reserved = bd.get("reserved_for_orders_eur")
    if reserved is not None and float(reserved) > 0:
        lines.append(_plain_line("Reserviert (Orders)", float(reserved)))
    in_pies = bd.get("in_pies_eur")
    if in_pies is not None and float(in_pies) > 0:
        lines.append(_plain_line("In Pies (nicht planbar)", float(in_pies)))
    total = bd.get("total_account_value_eur")
    if total is not None:
        lines.append(_plain_line("Kontowert gesamt (Info)", float(total)))
    if fx.get("ok") and fx.get("usd_per_eur"):
        ts = (fx.get("fx_event_time_utc") or "")[:19].replace("T", " ")
        footer = (
            f"Spot: 1 EUR = {float(fx['usd_per_eur']):.4f} USD "
            f"({fx.get('source') or 'FX'}, {ts} UTC)"
        )
    else:
        footer = "USD-Gegenwert: Kurs momentan nicht verfügbar (nur EUR angezeigt)."
    return "\n".join(lines), footer


def eur_amount_with_usd_suffix(
    eur: Any,
    *,
    usd_to_eur_rate: Optional[float],
) -> str:
    """Single amount for overview cards: '123,45 €  (≈ $134.00 USD)'."""
    if eur is None:
        return "—"
    try:
        val = float(eur)
    except (TypeError, ValueError):
        return "—"
    text = f"{val:,.2f} €"
    if usd_to_eur_rate and usd_to_eur_rate > 0:
        usd = eur_to_usd(val, float(usd_to_eur_rate))
        if usd is not None:
            text += f"  (≈ ${usd:,.2f} USD)"
    return text
