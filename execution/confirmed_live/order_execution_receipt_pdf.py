"""PDF receipt after «Order ausführen» — audit trail for the user."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_RECEIPTS_REL = Path("live_pilot/confirmed_execution/order_receipts")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y%m%d_%H%M%S")


def _receipts_dir(root: Path) -> Path:
    d = Path(root) / _RECEIPTS_REL
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_line(text: str, *, max_len: int = 120) -> str:
    s = str(text or "").strip()
    s = re.sub(r"[^\S\n]+", " ", s)
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s or "—"


def _eur(val: Any) -> str:
    if val is None:
        return "—"
    try:
        return f"{float(val):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _font_family(pdf: Any) -> str:
    from fpdf import FPDF

    assert isinstance(pdf, FPDF)
    regular = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
    bold = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arialbd.ttf"
    if regular.is_file() and bold.is_file():
        pdf.add_font("Arial", "", str(regular))
        pdf.add_font("Arial", "B", str(bold))
        return "Arial"
    return "Helvetica"


def write_order_execution_receipt(
    root: Path,
    *,
    symbol: str,
    t212_id: str,
    target_notional_eur: float,
    limit_price_eur: float,
    free_cash_eur: float | None,
    plan_preview: Dict[str, Any],
    result: Dict[str, Any],
    pick: Optional[Dict[str, Any]] = None,
    stage: str = "submission",
) -> Tuple[bool, str]:
    """
    Write PDF protocol under live_pilot/confirmed_execution/order_receipts/.
    Returns (ok, path_or_error_message).
    """
    root = Path(root)
    try:
        from fpdf import FPDF
        from fpdf.enums import Align, XPos, YPos
    except ImportError as exc:
        return False, f"PDF-Bibliothek fehlt: {exc}"

    sym = str(symbol).upper()
    ok = bool(result.get("ok"))
    ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    fname = f"ORDER_{sym}_{_utc_stamp()}_{'OK' if ok else 'FAIL'}.pdf"
    out_path = _receipts_dir(root) / fname

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.alias_nb_pages()
    font = _font_family(pdf)
    pdf.add_page()
    content_w = pdf.w - pdf.l_margin - pdf.r_margin

    def title(text: str) -> None:
        pdf.set_font(font, "B", 14)
        pdf.set_text_color(20, 40, 80)
        pdf.cell(0, 9, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=Align.L)
        pdf.ln(2)

    def section(h: str) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "B", 11)
        pdf.set_text_color(30, 60, 110)
        pdf.cell(0, 7, h, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    def line(label: str, value: str) -> None:
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "", 9)
        pdf.set_text_color(20, 20, 20)
        pdf.multi_cell(content_w, 5, f"{label}: {_safe_line(value, max_len=200)}")

    title("Order-Ausfuehrungsprotokoll — Marktanalyse")
    line("Zeit (UTC)", ts)
    line("Ergebnis", "ERFOLGREICH" if ok else "FEHLGESCHLAGEN / ABGEBROCHEN")
    line("Phase", stage)
    line("Symbol", sym)
    line("T212 Ticker", t212_id)
    if pick:
        line("Signal-Datum", str(pick.get("signal_date") or "—"))
        line("Empfehlung", _safe_line(str(pick.get("reason_de") or ""), max_len=180))

    section("Planung vor Absendung")
    line("Ziel-Betrag (Modell)", _eur(target_notional_eur))
    line("Limit-Preis (EUR)", _eur(limit_price_eur))
    line("Frei handelbar (T212)", _eur(free_cash_eur))
    line("Geplante Stueckzahl", str(plan_preview.get("quantity", "—")))
    line("Geplantes Volumen", _eur(plan_preview.get("executable_notional_eur")))
    line("Autom. verkleinert (Plan)", "Ja" if plan_preview.get("scaled_down") else "Nein")

    section("Ausfuehrung")
    line("Status", str(result.get("status") or result.get("stage") or result.get("error") or "—"))
    if result.get("executed_quantity") is not None:
        line("Gesendete Stueckzahl", str(result.get("executed_quantity")))
    if result.get("executed_notional_eur") is not None:
        line("Gesendetes Volumen", _eur(result.get("executed_notional_eur")))
    if result.get("scaled_down") is not None:
        line("An T212 skaliert", "Ja" if result.get("scaled_down") else "Nein")

    resp = result.get("response")
    if isinstance(resp, dict) and resp:
        line("T212 Order-ID", str(resp.get("id") or "—"))
        line("T212 Status", str(resp.get("status") or "—"))
        line("T212 Seite", str(resp.get("side") or "—"))

    draft = result.get("draft") or {}
    if draft:
        line("Entwurf-ID", str(draft.get("draft_id") or "—"))

    section("Meldung an Sie")
    line("Text", _safe_line(str(result.get("user_message_de") or ""), max_len=500))

    attempts: List[Dict[str, Any]] = list(result.get("attempts") or [])
    if attempts:
        section("Sendeversuche")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "B", 8)
        pdf.set_fill_color(30, 60, 110)
        pdf.set_text_color(255, 255, 255)
        cols = [12, 22, 28, 18, 110]
        for w, h in zip(cols, ["#", "Stk.", "EUR", "OK", "Fehler"]):
            pdf.cell(w, 6, h, border=1, fill=True, align=Align.C)
        pdf.ln()
        pdf.set_text_color(30, 30, 30)
        for row in attempts:
            fill = (245, 245, 245) if int(row.get("attempt", 0)) % 2 == 0 else None
            if fill:
                pdf.set_fill_color(*fill)
            pdf.set_font(font, "", 7.5)
            cells = [
                str(row.get("attempt", "")),
                str(row.get("quantity", "")),
                str(row.get("executable_notional_eur", "")),
                "ja" if row.get("ok") else "nein",
                _safe_line(str(row.get("error") or ""), max_len=80),
            ]
            for w, c in zip(cols, cells):
                pdf.cell(w, 5.5, c, border=1, fill=bool(fill))
            pdf.ln()

    err_raw = str(result.get("error") or "")
    if err_raw and not ok:
        section("Technischer Fehler (gekuerzt)")
        pdf.set_x(pdf.l_margin)
        pdf.set_font(font, "", 7)
        pdf.multi_cell(content_w, 4, _safe_line(err_raw, max_len=400))

    section("Hinweis")
    pdf.set_x(pdf.l_margin)
    pdf.set_font(font, "", 8)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(
        content_w,
        4,
        "Dieses PDF dokumentiert den App-Versuch «Order ausfuehren». "
        "Offene Orders und Ausfuehrung pruefen Sie in der Trading-212-App. "
        "Keine Anlageberatung.",
    )

    meta_path = out_path.with_suffix(".json")
    meta_path.write_text(
        json.dumps(
            {
                "generated_at_utc": ts,
                "pdf": str(out_path),
                "symbol": sym,
                "ok": ok,
                "target_notional_eur": target_notional_eur,
                "limit_price_eur": limit_price_eur,
                "result_summary": {
                    "ok": ok,
                    "stage": result.get("stage"),
                    "status": result.get("status"),
                    "error": (err_raw or "")[:300],
                },
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    try:
        pdf.output(str(out_path))
    except OSError as exc:
        return False, str(exc)

    return True, str(out_path)


def open_receipt_pdf(path: str) -> bool:
    """Open PDF with default viewer on Windows."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        os.startfile(str(p))  # noqa: S606 — Windows only
        return True
    except OSError:
        return False
