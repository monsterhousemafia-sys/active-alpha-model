"""Generate PORTFOLIO_100EUR_NACHKAUF_PLAN.pdf."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Daten fuer Reviewer" / "PORTFOLIO_100EUR_NACHKAUF_PLAN.pdf"
FONT_REG = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

MAX_POSITION_EUR = 100.0
NEW_CASH_EUR = 100.0

CURRENT = {
    "OXY": 71.69,
    "WDC": 71.08,
    "STX": 71.49,
    "INTC": 70.75,
    "MU": 71.22,
    "CIEN": 70.76,
}

# P16C-normalized weights among 6 executable positions
P16C_WEIGHT_SHARE = {
    "OXY": 17.7018,
    "WDC": 15.1915,
    "STX": 12.5713,
    "INTC": 8.3908,
    "MU": 7.6908,
    "CIEN": 7.5708,
}

ALLOCATION = [
    ("OXY", 28.0),
    ("WDC", 29.0),
    ("STX", 29.0),
    ("Cash (Reserve/Puffer)", 14.0),
]


def _eur(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class PlanPDF(FPDF):
    def header(self) -> None:
        self.set_font("Arial", "B", 16)
        self.set_text_color(20, 40, 80)
        self.cell(0, 10, "100-EUR-Nachkaufplan — P16C-Ausrichtung", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=Align.C)
        self.set_font("Arial", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(
            0,
            6,
            "Marktanalyse Decision Cockpit  |  Stand: 2026-06-01  |  Champion: R3_w075_q065_noexit",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            align=Align.C,
        )
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Arial", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Seite {self.page_no()}/{{nb}}  —  Entscheidungsunterstuetzung, keine Anlageberatung", align=Align.C)


def _table_header(pdf: PlanPDF, widths: list[float], headers: list[str], fills: tuple[int, int, int] = (30, 60, 110)) -> None:
    pdf.set_font("Arial", "B", 8)
    pdf.set_fill_color(*fills)
    pdf.set_text_color(255, 255, 255)
    for w, h in zip(widths, headers):
        pdf.cell(w, 7, h, border=1, fill=True, align=Align.C)
    pdf.ln()


def _table_row(
    pdf: PlanPDF,
    widths: list[float],
    cells: list[str],
    *,
    bold: bool = False,
    fill: tuple[int, int, int] | None = None,
    height: float = 7.0,
) -> None:
    pdf.set_font("Arial", "B" if bold else "", 8)
    if fill:
        pdf.set_fill_color(*fill)
    pdf.set_text_color(30, 30, 30)
    align_last = len(widths) > 4 and widths[-1] > 80
    for i, (w, text) in enumerate(zip(widths, cells)):
        align = Align.L if align_last and i == len(cells) - 1 else Align.C
        pdf.cell(w, height, text, border=1, fill=bool(fill), align=align)
    pdf.ln()


def build_pdf() -> Path:
    after = {sym: CURRENT[sym] + amt for sym, amt in ALLOCATION if sym in CURRENT}
    weight_sum = sum(P16C_WEIGHT_SHARE.values())

    pdf = PlanPDF(orientation="L", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_font("Arial", "", str(FONT_REG))
    pdf.add_font("Arial", "B", str(FONT_BOLD))
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.add_page()

    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(
        0,
        5,
        f"Ausgangslage: 6 Positionen je ca. 71 EUR (VUSD/SNDK bereits aus dem Depot).  "
        f"Neues Kapital: {_eur(NEW_CASH_EUR)}.\n"
        "Strategie: Nur untergewichtete Titel (OXY, WDC, STX) nach P16C-Gewichten nachkaufen.  "
        f"Positionslimit: max. {_eur(MAX_POSITION_EUR)} je Titel.\n"
        "Orders nur manuell in Trading 212 — keine automatische Ausfuehrung.",
    )
    pdf.ln(4)

    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(20, 40, 80)
    pdf.cell(0, 8, "1. Nachkaufplan (100 EUR)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w1 = [14, 28, 22, 22, 22, 22, 130]
    _table_header(pdf, w1, ["#", "Position", "Aktion", "Ist EUR", "Kauf EUR", "Danach EUR", "Begruendung"])
    rows = [
        ("1", "OXY", "KAUFEN", _eur(CURRENT["OXY"]), _eur(28.0), _eur(after["OXY"]), "Groesste P16C-Luecke; Cap nahe 100 EUR"),
        ("2", "WDC", "KAUFEN", _eur(CURRENT["WDC"]), _eur(29.0), _eur(after["WDC"]), "Zweitgroesste Luecke; Cap nahe 100 EUR"),
        ("3", "STX", "KAUFEN", _eur(CURRENT["STX"]), _eur(29.0), _eur(after["STX"]), "Drittgroesste Luecke; Cap nahe 100 EUR"),
        ("4", "Cash", "HALTEN", "-", _eur(14.0), "Reserve", "Puffer / Mindestreserve — nicht in INTC/MU/CIEN"),
        ("-", "INTC", "HALTEN", _eur(CURRENT["INTC"]), "0", _eur(CURRENT["INTC"]), "Bereits uebergewichtet vs. P16C"),
        ("-", "MU", "HALTEN", _eur(CURRENT["MU"]), "0", _eur(CURRENT["MU"]), "Bereits uebergewichtet vs. P16C"),
        ("-", "CIEN", "HALTEN", _eur(CURRENT["CIEN"]), "0", _eur(CURRENT["CIEN"]), "Bereits uebergewichtet vs. P16C"),
    ]
    for row in rows:
        fill = (235, 248, 235) if row[2] == "KAUFEN" else (245, 245, 250) if row[2] == "HALTEN" else None
        _table_row(pdf, w1, list(row), fill=fill)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "2. Ausfuehrungsreihenfolge in Trading 212", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w2 = [18, 22, 28, 28, 80]
    _table_header(pdf, w2, ["Schritt", "Aktion", "Instrument", "Betrag EUR", "Hinweis"], fills=(40, 90, 60))
    exec_rows = [
        ("1", "Kauf", "OXY", "28", "Limit-Order wenn moeglich"),
        ("2", "Kauf", "WDC", "29", "Limit-Order wenn moeglich"),
        ("3", "Kauf", "STX", "29", "Limit-Order wenn moeglich"),
        ("4", "—", "Cash", "14", "Als Reserve auf Konto belassen"),
    ]
    for row in exec_rows:
        _table_row(pdf, w2, list(row), fill=(240, 255, 240) if row[1] == "Kauf" else (248, 248, 252))

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "3. Was nicht tun", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w3 = [40, 50, 150]
    _table_header(pdf, w3, ["Vermeiden", "Beispiel", "Grund"], fills=(120, 40, 40))
    avoid = [
        ("Gleichverteilung", "17 EUR in alle 6", "Verschaerft Fehlgewicht bei INTC/MU/CIEN"),
        ("Positionslimit", ">29 EUR in eine Position", "Pilot-Regel: max. 100 EUR je Titel"),
        ("Nachkauf", "INTC, MU, CIEN", "Gegen P16C — bereits uebergewichtet"),
    ]
    for row in avoid:
        _table_row(pdf, w3, list(row), fill=(255, 240, 240))

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "4. Zielbild nach Umsetzung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w4 = [22, 26, 26, 26, 26, 26]
    _table_header(pdf, w4, ["Position", "Vorher EUR", "Kauf EUR", "Nachher EUR", "P16C-Anteil %", "Status"])
    for sym in ["OXY", "WDC", "STX", "INTC", "MU", "CIEN"]:
        buy = 28.0 if sym == "OXY" else 29.0 if sym in ("WDC", "STX") else 0.0
        nxt = CURRENT[sym] + buy
        pct = 100.0 * P16C_WEIGHT_SHARE[sym] / weight_sum
        status = "Ziel ~100 EUR" if sym in ("OXY", "WDC", "STX") else "Halten"
        _table_row(
            pdf,
            w4,
            [sym, _eur(CURRENT[sym]), _eur(buy) if buy else "0", _eur(nxt), f"{pct:.1f}".replace(".", ","), status],
            fill=(248, 250, 252),
        )
    _table_row(pdf, w4, ["Cash-Reserve", "-", _eur(14.0), _eur(14.0), "-", "Puffer"], bold=True, fill=(230, 245, 230))

    pdf.ln(6)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "5. Checkliste", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Arial", "", 10)
    for item in [
        "[ ]  OXY ca. 28 EUR gekauft",
        "[ ]  WDC ca. 29 EUR gekauft",
        "[ ]  STX ca. 29 EUR gekauft",
        "[ ]  14 EUR als Cash-Reserve belassen",
        "[ ]  INTC / MU / CIEN nicht nachgekauft",
        "[ ]  Optional: Read-only API in Marktanalyse fuer Abgleich",
    ]:
        pdf.cell(0, 7, item, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build_pdf())
