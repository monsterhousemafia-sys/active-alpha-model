"""Generate PORTFOLIO_UMSTELLUNG_PLAN.pdf (P16C screenshot-normalized weights)."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Daten fuer Reviewer" / "PORTFOLIO_UMSTELLUNG_PLAN.pdf"
FONT_REG = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

# P16C reference weights (% of 500 EUR reference) — paper/config/p16c_cost_adjusted_initial_allocation_500eur.json
P16C_WEIGHTS_PCT = {
    "OXY": 17.7018,
    "WDC": 15.1915,
    "STX": 12.5713,
    "INTC": 8.3908,
    "MU": 7.6908,
    "CIEN": 7.5708,
}
P16C_TARGET_500 = {
    "OXY": 88.51,
    "WDC": 75.96,
    "STX": 62.86,
    "INTC": 41.95,
    "MU": 38.45,
    "CIEN": 37.85,
}

CURRENT_EUR = {
    "OXY": 48.59,
    "WDC": 43.21,
    "STX": 34.90,
    "INTC": 23.45,
    "MU": 21.36,
    "CIEN": 20.68,
    "VUSD": 48.15,
    "SNDK": 36.28,
}
CURRENT_WEIGHT_PCT = {
    "OXY": 17.7,
    "VUSD": 17.68,
    "WDC": 15.19,
    "SNDK": 13.2,
    "STX": 12.57,
    "INTC": 8.39,
    "MU": 7.69,
    "CIEN": 7.57,
}

DEPLOYABLE_EUR = 427.0
RESERVE_EUR = 50.0
TOTAL_EUR = 477.0
CASH_AVAILABLE_EUR = 200.0


def _eur(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _plan() -> dict:
    weight_sum = sum(P16C_WEIGHTS_PCT.values())
    targets = {sym: round(DEPLOYABLE_EUR * (w / weight_sum), 2) for sym, w in P16C_WEIGHTS_PCT.items()}
    targets["OXY"] = round(DEPLOYABLE_EUR - sum(v for k, v in targets.items() if k != "OXY"), 2)

    deltas = {sym: round(targets[sym] - CURRENT_EUR[sym], 2) for sym in P16C_WEIGHTS_PCT}
    sell_total = round(CURRENT_EUR["VUSD"] + CURRENT_EUR["SNDK"], 2)
    buy_total = round(sum(d for d in deltas.values() if d > 0), 2)
    available = round(sell_total + CASH_AVAILABLE_EUR, 2)
    reserve_left = round(available - buy_total, 2)

    after_pct_6 = {sym: 100.0 * targets[sym] / DEPLOYABLE_EUR for sym in P16C_WEIGHTS_PCT}
    after_pct_total = {sym: 100.0 * targets[sym] / TOTAL_EUR for sym in P16C_WEIGHTS_PCT}

    exec_buys = sorted(
        [(sym, deltas[sym]) for sym in P16C_WEIGHTS_PCT if deltas[sym] > 0],
        key=lambda x: -x[1],
    )

    return {
        "targets": targets,
        "deltas": deltas,
        "sell_total": sell_total,
        "buy_total": buy_total,
        "available": available,
        "reserve_left": reserve_left,
        "after_pct_6": after_pct_6,
        "after_pct_total": after_pct_total,
        "exec_buys": exec_buys,
        "weight_sum": weight_sum,
    }


class PlanPDF(FPDF):
    def header(self) -> None:
        self.set_font("Arial", "B", 16)
        self.set_text_color(20, 40, 80)
        self.cell(0, 10, "Portfolio-Umstellung — Handlungsplan (P16C-Gewichte)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=Align.C)
        self.set_font("Arial", "", 9)
        self.set_text_color(80, 80, 80)
        self.cell(
            0,
            6,
            "Marktanalyse Decision Cockpit  |  Stand: 2026-06-01  |  Champion: R3_w075_q065_noexit  |  Policy: P16C",
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
    height: float = 6.5,
) -> None:
    pdf.set_font("Arial", "B" if bold else "", 7.5)
    if fill:
        pdf.set_fill_color(*fill)
    pdf.set_text_color(30, 30, 30)
    for w, text in zip(widths, cells):
        pdf.cell(w, height, text, border=1, fill=bool(fill), align=Align.L if w == widths[-1] and len(widths) > 4 else Align.C)
    pdf.ln()


def build_pdf() -> Path:
    plan = _plan()
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
        f"Gesamt: ca. {_eur(TOTAL_EUR)} (277 EUR investiert + 200 EUR Cash)  |  Reserve: {_eur(RESERVE_EUR)}  |  "
        f"Anlageziel: ca. {_eur(DEPLOYABLE_EUR)} in 6 Positionen\n"
        "Gewichtung: Screenshot-Verhaeltnisse (P16C), NICHT gleichverteilt (kein 16,67 % je Position).\n"
        "Orders nur manuell in Trading 212 ausfuehren — keine automatische Orderausfuehrung.",
    )
    pdf.ln(3)

    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(20, 40, 80)
    pdf.cell(0, 8, "1. Uebersicht: Was wird umgestellt?", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w1 = [8, 16, 20, 14, 14, 14, 14, 14, 90]
    h1 = ["#", "Position", "Aktion", "Ist EUR", "Ziel EUR", "Delta", "Ziel % (6)", "Ziel % ges.", "Begruendung"]
    _table_header(pdf, w1, h1)

    rows1: list[tuple] = [
        (
            "1",
            "VUSD",
            "VERKAUFEN",
            _eur(CURRENT_EUR["VUSD"]),
            "0",
            f"-{_eur(CURRENT_EUR['VUSD'])}",
            "0",
            "0",
            "Blockiert; GBP/LSE — nicht im ausfuehrbaren Set",
        ),
        (
            "2",
            "SNDK",
            "VERKAUFEN",
            _eur(CURRENT_EUR["SNDK"]),
            "0",
            f"-{_eur(CURRENT_EUR['SNDK'])}",
            "0",
            "0",
            "Blockiert; Identitaet unklar — Ueberlappung mit WDC",
        ),
    ]
    for i, sym in enumerate(["OXY", "WDC", "STX", "INTC", "MU", "CIEN"], start=3):
        tgt = plan["targets"][sym]
        delta = plan["deltas"][sym]
        rows1.append(
            (
                str(i),
                sym,
                "NACHKAUFEN",
                _eur(CURRENT_EUR[sym]),
                _eur(tgt),
                f"+{_eur(delta)}",
                _pct(plan["after_pct_6"][sym]),
                _pct(plan["after_pct_total"][sym]),
                f"P16C-Ziel {_eur(P16C_TARGET_500[sym])} bei 500 EUR Referenz",
            )
        )
    rows1.append(("-", "Cash", "HALTEN", "-", _eur(RESERVE_EUR), "-", "-", _pct(100 * RESERVE_EUR / TOTAL_EUR), "Mindestreserve Pilot-Policy"))

    for i, row in enumerate(rows1):
        action_fill = (255, 235, 235) if row[2] == "VERKAUFEN" else (235, 248, 235) if row[2] == "NACHKAUFEN" else (245, 245, 250)
        _table_row(pdf, w1, list(row), fill=action_fill, height=7)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "2. Zielgewichte (Referenz P16C)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w1b = [20, 22, 28, 28, 28, 28]
    _table_header(pdf, w1b, ["Position", "Screenshot %", "P16C % (500 EUR)", "P16C Ziel EUR", "Normalisiert % (6)", "Skaliert EUR (427)"], fills=(40, 70, 110))
    for sym in ["OXY", "WDC", "STX", "INTC", "MU", "CIEN"]:
        _table_row(
            pdf,
            w1b,
            [
                sym,
                _pct(CURRENT_WEIGHT_PCT[sym]),
                _pct(P16C_WEIGHTS_PCT[sym]),
                _eur(P16C_TARGET_500[sym]),
                _pct(plan["after_pct_6"][sym]),
                _eur(plan["targets"][sym]),
            ],
            fill=(248, 250, 252),
        )

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "3. Geldfluss", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w2 = [12, 120, 40]
    _table_header(pdf, w2, ["Schritt", "Beschreibung", "Betrag EUR"], fills=(40, 90, 60))
    flow = [
        ("A", "Verkauf VUSD", f"+{_eur(CURRENT_EUR['VUSD'])}"),
        ("B", "Verkauf SNDK", f"+{_eur(CURRENT_EUR['SNDK'])}"),
        ("C", "Bereits vorhandenes Cash", f"+{_eur(CASH_AVAILABLE_EUR)}"),
        ("", "Summe verfuegbar", _eur(plan["available"])),
        ("D", "Nachkaeufe (6 Positionen)", f"-{_eur(plan['buy_total'])}"),
        ("E", "Verbleibende Reserve", f"ca. {_eur(plan['reserve_left'])}"),
    ]
    for i, row in enumerate(flow):
        bold = row[0] == ""
        fill = (230, 245, 230) if bold else ((248, 248, 248) if i % 2 == 0 else None)
        _table_row(pdf, w2, list(row), bold=bold, fill=fill)

    pdf.ln(4)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "4. Ausfuehrungsreihenfolge in Trading 212", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w3 = [18, 22, 30, 30]
    _table_header(pdf, w3, ["Reihenfolge", "Aktion", "Instrument", "ca. Betrag EUR"])
    exec_rows = [
        ("1", "Verkauf", "VUSD", _eur(CURRENT_EUR["VUSD"]).split()[0]),
        ("2", "Verkauf", "SNDK", _eur(CURRENT_EUR["SNDK"]).split()[0]),
    ]
    for n, (sym, delta) in enumerate(plan["exec_buys"], start=3):
        exec_rows.append((str(n), "Kauf", sym, _eur(delta).split()[0]))
    for row in exec_rows:
        fill = (255, 240, 240) if row[1] == "Verkauf" else (240, 255, 240)
        _table_row(pdf, w3, list(row), fill=fill)

    pdf.ln(2)
    pdf.set_font("Arial", "", 8)
    pdf.cell(0, 5, "Empfehlung: Limit-Orders verwenden, wo moeglich. Groesste Nachkaeufe zuerst: OXY, WDC, STX.", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.add_page()
    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(20, 40, 80)
    pdf.cell(0, 8, "5. Vorher / Nachher (Zielbild)", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    w4 = [22, 26, 26, 24, 24, 24]
    _table_header(pdf, w4, ["Position", "Vorher EUR", "Nachher EUR", "Vorher %", "Nachher % (6)", "Nachher % ges."])
    comp = []
    for sym in ["OXY", "WDC", "STX", "INTC", "MU", "CIEN"]:
        comp.append(
            (
                sym,
                _eur(CURRENT_EUR[sym]),
                _eur(plan["targets"][sym]),
                _pct(CURRENT_WEIGHT_PCT[sym]),
                _pct(plan["after_pct_6"][sym]),
                _pct(plan["after_pct_total"][sym]),
            )
        )
    comp.extend(
        [
            ("VUSD", _eur(CURRENT_EUR["VUSD"]), "0", _pct(CURRENT_WEIGHT_PCT["VUSD"]), "0", "0"),
            ("SNDK", _eur(CURRENT_EUR["SNDK"]), "0", _pct(CURRENT_WEIGHT_PCT["SNDK"]), "0", "0"),
            ("Aktien gesamt", "ca. 277", f"ca. {_eur(DEPLOYABLE_EUR).split()[0]}", "-", "100", _pct(100 * DEPLOYABLE_EUR / TOTAL_EUR)),
            ("Cash-Reserve", _eur(CASH_AVAILABLE_EUR), f"ca. {_eur(plan['reserve_left']).split()[0]}", "-", "-", _pct(100 * plan["reserve_left"] / TOTAL_EUR)),
        ]
    )
    for i, row in enumerate(comp):
        bold = row[0] in ("Aktien gesamt", "Cash-Reserve")
        _table_row(pdf, w4, list(row), bold=bold, fill=(245, 248, 252) if i % 2 == 0 else None)

    pdf.ln(6)
    pdf.set_font("Arial", "B", 11)
    pdf.cell(0, 8, "6. Checkliste nach Umstellung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Arial", "", 10)
    for item in [
        "[ ]  VUSD verkauft",
        "[ ]  SNDK verkauft",
        "[ ]  OXY, WDC, STX, INTC, MU, CIEN gemaess P16C-Gewichten nachgekauft",
        "[ ]  Reserve >= 50 EUR auf dem Konto",
        "[ ]  Optional: Read-only API in Marktanalyse eintragen",
    ]:
        pdf.cell(0, 7, item, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build_pdf())
