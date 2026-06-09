"""Generate PORTFOLIO_GESAMTBERICHT.pdf — full recalculated portfolio report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf
import pandas as pd
from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "Daten fuer Reviewer" / "PORTFOLIO_GESAMTBERICHT.pdf"
FONT_REG = Path(r"C:\Windows\Fonts\arial.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\arialbd.ttf")

CURRENT = {
    "OXY": 71.69,
    "WDC": 71.08,
    "STX": 71.49,
    "INTC": 70.75,
    "MU": 71.22,
    "CIEN": 70.76,
}
P16C_W = {
    "OXY": 17.7018,
    "WDC": 15.1915,
    "STX": 12.5713,
    "INTC": 8.3908,
    "MU": 7.6908,
    "CIEN": 7.5708,
}
W_SUM = sum(P16C_W.values())
RESERVE = 50.0
NEW_CASH = 100.0
VUSD_PROCEEDS = 48.20
MAX_POS = 100.0
REPORT_DATE = "2026-06-01"


def _eur(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _compute() -> dict:
    stocks_now = sum(CURRENT.values())
    total_after = stocks_now + VUSD_PROCEEDS + NEW_CASH
    deployable = total_after - RESERVE

    targets = {s: round(deployable * P16C_W[s] / W_SUM, 2) for s in CURRENT}
    targets["OXY"] = round(deployable - sum(targets[s] for s in CURRENT if s != "OXY"), 2)
    gaps = {s: round(targets[s] - CURRENT[s], 2) for s in CURRENT}

    under = {s: max(0.0, gaps[s]) for s in CURRENT}
    cap_room = {s: round(max(0.0, MAX_POS - CURRENT[s]), 2) for s in CURRENT}
    pos_gap_sum = sum(under.values())
    raw100 = {s: (100.0 * under[s] / pos_gap_sum if pos_gap_sum else 0) for s in CURRENT}
    buy100 = {s: 0.0 for s in CURRENT}
    remaining = 100.0
    order = sorted(under, key=lambda s: -under[s])
    for s in order:
        if remaining <= 0:
            break
        amt = min(raw100[s], cap_room[s], under[s], remaining) if under[s] > 0 else 0
        buy100[s] = round(amt, 2)
        remaining = round(remaining - amt, 2)
    for s in order:
        if remaining <= 0:
            break
        extra = min(cap_room[s] - buy100[s], under[s] - buy100[s], remaining)
        if extra > 0:
            buy100[s] = round(buy100[s] + extra, 2)
            remaining = round(remaining - extra, 2)

    after100 = {s: round(CURRENT[s] + buy100[s], 2) for s in CURRENT}

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=120)
    close = yf.download(list(CURRENT.keys()), start=start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)["Close"]
    mom = {}
    for s in CURRENT:
        ser = close[s].dropna()
        mom[s] = {
            "ret63": round(float(ser.iloc[-1] / ser.iloc[max(-64, -len(ser))] - 1) * 100, 2),
            "ret21": round(float(ser.iloc[-1] / ser.iloc[max(-22, -len(ser))] - 1) * 100, 2),
        }

    capped_targets = {s: min(MAX_POS, targets[s]) for s in CURRENT}
    capped_targets["STX"] = min(MAX_POS, targets["STX"])

    return {
        "stocks_now": round(stocks_now, 2),
        "total_after": round(total_after, 2),
        "deployable": round(deployable, 2),
        "targets": targets,
        "gaps": gaps,
        "buy100": buy100,
        "reserve_after_100": round(remaining, 2),
        "after100": after100,
        "mom": mom,
        "capped": capped_targets,
    }


class ReportPDF(FPDF):
    def header(self) -> None:
        self.set_font("Arial", "B", 15)
        self.set_text_color(20, 40, 80)
        self.cell(0, 9, "Portfolio-Gesamtbericht — Neuberechnung", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align=Align.C)
        self.set_font("Arial", "", 8)
        self.set_text_color(90, 90, 90)
        self.cell(
            0,
            5,
            f"Marktanalyse Decision Cockpit  |  Stand: {REPORT_DATE}  |  Champion: R3_w075_q065_noexit  |  Policy: P16C",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
            align=Align.C,
        )
        self.ln(3)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Arial", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Seite {self.page_no()}/{{nb}}  —  Entscheidungsunterstuetzung, keine Anlageberatung", align=Align.C)

    def section(self, title: str) -> None:
        self.ln(2)
        self.set_font("Arial", "B", 11)
        self.set_text_color(20, 40, 80)
        self.cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def body(self, text: str) -> None:
        self.set_font("Arial", "", 9)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 4.5, text)
        self.ln(1)


def _header_row(pdf: ReportPDF, widths: list[float], headers: list[str], rgb: tuple[int, int, int] = (30, 60, 110)) -> None:
    pdf.set_font("Arial", "B", 7.5)
    pdf.set_fill_color(*rgb)
    pdf.set_text_color(255, 255, 255)
    for w, h in zip(widths, headers):
        pdf.cell(w, 6.5, h, border=1, fill=True, align=Align.C)
    pdf.ln()


def _data_row(pdf: ReportPDF, widths: list[float], cells: list[str], fill: tuple[int, int, int] | None = None, bold: bool = False) -> None:
    pdf.set_font("Arial", "B" if bold else "", 7.5)
    if fill:
        pdf.set_fill_color(*fill)
    pdf.set_text_color(30, 30, 30)
    for w, c in zip(widths, cells):
        pdf.cell(w, 6.5, c, border=1, fill=bool(fill), align=Align.C)
    pdf.ln()


def build_pdf() -> Path:
    d = _compute()

    pdf = ReportPDF(orientation="L", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_font("Arial", "", str(FONT_REG))
    pdf.add_font("Arial", "B", str(FONT_BOLD))
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    pdf.body(
        "Annahmen: VUSD verkauft (+48,20 EUR), SNDK bereits aus dem Depot, neues Cash +100 EUR, "
        f"Reserve 50 EUR, Positionslimit 100 EUR je Titel. Ist-Depot: 6 Aktien je ca. 71 EUR "
        f"(Summe { _eur(d['stocks_now']) } EUR). Orders nur manuell in Trading 212."
    )

    pdf.section("1. Gesamtbild")
    w = [55, 45, 120]
    _header_row(pdf, w, ["Posten", "Betrag EUR", "Anmerkung"], (40, 90, 60))
    rows = [
        ("6 Aktien (Ist)", _eur(d["stocks_now"]), "OXY, WDC, STX, INTC, MU, CIEN"),
        ("VUSD-Verkaufserloes", _eur(VUSD_PROCEEDS), "Angenommen: ausgefuehrt"),
        ("Neues Cash", _eur(NEW_CASH), "Vom Nutzer bereitgestellt"),
        ("Gesamt", _eur(d["total_after"]), "Vor Kaeufen"),
        ("Reserve (abziehen)", f"-{_eur(RESERVE)}", "Pilot-Mindestreserve"),
        ("Anlagebar in Aktien", _eur(d["deployable"]), "P16C-Referenzrahmen"),
    ]
    for i, row in enumerate(rows):
        _data_row(pdf, w, list(row), fill=(248, 248, 252) if i % 2 == 0 else None, bold=row[0] == "Anlagebar in Aktien")

    pdf.section("2. P16C-Ziel vs. Ist")
    w2 = [18, 20, 22, 22, 18, 18, 20, 20, 95]
    _header_row(pdf, w2, ["Symbol", "Ist EUR", "Ziel EUR", "Luecke", "Ziel %", "Ist %", "Aktion", "63T %", "21T %"])
    order = ["OXY", "WDC", "STX", "INTC", "MU", "CIEN"]
    for sym in order:
        gap = d["gaps"][sym]
        if gap > 5:
            action, fill = "NACHKAUFEN", (235, 248, 235)
        elif gap < -5:
            action, fill = "REDUZIEREN", (255, 240, 240)
        else:
            action, fill = "HALTEN", (248, 248, 252)
        _data_row(
            pdf,
            w2,
            [
                sym,
                _eur(CURRENT[sym]),
                _eur(d["targets"][sym]),
                f"{gap:+.2f}".replace(".", ","),
                _pct(100 * d["targets"][sym] / d["deployable"]),
                _pct(100 * CURRENT[sym] / d["deployable"]),
                action,
                f"{d['mom'][sym]['ret63']:+.1f}".replace(".", ","),
                f"{d['mom'][sym]['ret21']:+.1f}".replace(".", ","),
            ],
            fill=fill,
        )

    pdf.section("3. Positionslimit 100 EUR (Pilot-Regel)")
    pdf.body(
        "P16C wuerde OXY theoretisch auf ca. 134 EUR und WDC auf ca. 115 EUR setzen. "
        "Das Positionslimit von 100 EUR je Titel ist bindend. STX erreicht das volle P16C-Ziel "
        "innerhalb des Caps. Ueberschuss verbleibt sinnvollerweise als Cash/Reserve (~50 EUR)."
    )
    w3 = [22, 28, 28, 28, 28]
    _header_row(pdf, w3, ["Symbol", "P16C-Ziel EUR", "Cap-Maximum EUR", "Erreichbar EUR", "Status"])
    for sym in order:
        tgt = d["targets"][sym]
        cap = min(MAX_POS, tgt)
        status = "Cap bindend" if tgt > MAX_POS else "Ziel erreichbar"
        _data_row(pdf, w3, [sym, _eur(tgt), _eur(MAX_POS), _eur(cap), status], fill=(248, 250, 252))

    pdf.add_page()
    pdf.section("4. Konkreter 100-EUR-Nachkaufplan")
    w4 = [12, 22, 22, 22, 22, 22, 130]
    _header_row(pdf, w4, ["#", "Symbol", "Kauf EUR", "Danach EUR", "Vorher EUR", "Prioritaet", "Begruendung"])
    plan_rows = [
        ("1", "OXY", _eur(d["buy100"]["OXY"]), _eur(d["after100"]["OXY"]), _eur(CURRENT["OXY"]), "1", "Groesste P16C-Luecke; Positions-Cap voll"),
        ("2", "WDC", _eur(d["buy100"]["WDC"]), _eur(d["after100"]["WDC"]), _eur(CURRENT["WDC"]), "2", "Zweitgroesste Luecke; starkes Momentum"),
        ("3", "STX", _eur(d["buy100"]["STX"]), _eur(d["after100"]["STX"]), _eur(CURRENT["STX"]), "3", "P16C-Ziel fast erreicht; bestes Momentum-Paar"),
        ("4", "Reserve", _eur(d["reserve_after_100"]), "-", "-", "-", "Restbetrag + Puffer auf Konto"),
        ("-", "INTC", "0", _eur(d["after100"]["INTC"]), _eur(CURRENT["INTC"]), "-", "Leicht uebergewichtet; nicht nachkaufen"),
        ("-", "MU", "0", _eur(d["after100"]["MU"]), _eur(CURRENT["MU"]), "-", "Uebergewichtet; Doppelung Halbleiter mit INTC"),
        ("-", "CIEN", "0", _eur(d["after100"]["CIEN"]), _eur(CURRENT["CIEN"]), "-", "Uebergewichtet; schwaechstes relatives Momentum"),
    ]
    for row in plan_rows:
        fill = (235, 248, 235) if row[1] in ("OXY", "WDC", "STX") else None
        _data_row(pdf, w4, list(row), fill=fill)

    pdf.section("5. Ausfuehrungsreihenfolge Trading 212")
    w5 = [16, 22, 24, 24, 130]
    _header_row(pdf, w5, ["Schritt", "Aktion", "Symbol", "Betrag EUR", "Hinweis"], (40, 90, 60))
    steps = [
        ("1", "Kauf", "OXY", _eur(d["buy100"]["OXY"]), "Limit-Order wenn moeglich"),
        ("2", "Kauf", "WDC", _eur(d["buy100"]["WDC"]), "Limit-Order wenn moeglich"),
        ("3", "Kauf", "STX", _eur(d["buy100"]["STX"]), "Limit-Order wenn moeglich"),
        ("4", "—", "Cash", _eur(d["reserve_after_100"]), "Als Reserve belassen"),
    ]
    for row in steps:
        _data_row(pdf, w5, list(row), fill=(240, 255, 240) if row[1] == "Kauf" else (248, 248, 252))

    pdf.section("6. Ranking — beste Optionen im validierten 6er-Universum")
    pdf.body(
        "Ausserhalb von OXY, WDC, STX, INTC, MU, CIEN sind neue Titel nicht Teil des "
        "validierten Pilot-Portfolios (PROVISIONAL_EXECUTABLE_PORTFOLIO_6_POSITION)."
    )
    w6 = [18, 22, 22, 22, 22, 130]
    _header_row(pdf, w6, ["Rang", "Symbol", "63T %", "21T %", "Empfehlung", "Kommentar"])
    ranking = [
        ("1", "WDC", f"{d['mom']['WDC']['ret63']:+.1f}", f"{d['mom']['WDC']['ret21']:+.1f}", "BESTE WAHL", "P16C + Momentum; Nachkauf empfohlen"),
        ("2", "STX", f"{d['mom']['STX']['ret63']:+.1f}", f"{d['mom']['STX']['ret21']:+.1f}", "SEHR GUT", "Staerkstes Momentum; Nachkauf empfohlen"),
        ("3", "OXY", f"{d['mom']['OXY']['ret63']:+.1f}", f"{d['mom']['OXY']['ret21']:+.1f}", "GUT (P16C)", "Groesstes Gewicht; schwaches 21T-Momentum"),
        ("4", "INTC", f"{d['mom']['INTC']['ret63']:+.1f}", f"{d['mom']['INTC']['ret21']:+.1f}", "HALTEN", "Nicht nachkaufen; leicht uebergewichtet"),
        ("5", "MU", f"{d['mom']['MU']['ret63']:+.1f}", f"{d['mom']['MU']['ret21']:+.1f}", "HALTEN", "Uebergewichtet; Halbleiber-Doppelung"),
        ("6", "CIEN", f"{d['mom']['CIEN']['ret63']:+.1f}", f"{d['mom']['CIEN']['ret21']:+.1f}", "HALTEN", "Uebergewichtet; schwaechstes Momentum"),
    ]
    for row in ranking:
        fill = (235, 248, 235) if row[0] in ("1", "2", "3") else None
        _data_row(pdf, w6, [r.replace(".", ",") for r in row], fill=fill)

    pdf.section("7. Bereits erledigt / nicht mehr noetig")
    w7 = [40, 40, 150]
    _header_row(pdf, w7, ["Thema", "Status", "Anmerkung"], (60, 60, 60))
    done = [
        ("SNDK verkauft", "ERLEDIGT", "Blockiertes Instrument; aus Depot entfernt"),
        ("VUSD verkauft", "ANGENOMMEN", "Offener Marktauftrag; Erloes ca. 48 EUR"),
        ("Gleichgewichtung 6 Titel", "ERLEDIGT", "Je ca. 71 EUR — solide Basis"),
        ("Weitere Verkaeufe", "NICHT NOETIG", "Optional: Feintuning INTC/MU/CIEN je ~7-13 EUR"),
        ("Intel nachkaufen", "NEIN", "Weder bestes Momentum noch bestes Gewicht"),
        ("Neue Titel (z.B. NVDA)", "NEIN", "Nicht im validierten Pilot-Universum"),
    ]
    for i, row in enumerate(done):
        _data_row(pdf, w7, list(row), fill=(248, 248, 252) if i % 2 == 0 else None)

    pdf.section("8. Zusammenfassung")
    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(30, 30, 30)
    summary = (
        f"Gesamtkapital nach Einzahlung: {_eur(d['total_after'])} EUR. "
        f"Anlagebar: {_eur(d['deployable'])} EUR. "
        f"100 EUR verteilen auf: OXY {_eur(d['buy100']['OXY'])} + WDC {_eur(d['buy100']['WDC'])} + "
        f"STX {_eur(d['buy100']['STX'])}; Reserve danach ca. {_eur(d['reserve_after_100'])} EUR. "
        "Beste Einzeloption: WDC. Kein Nachkauf bei INTC, MU, CIEN. "
        "16,67-Prozent-Gleichgewicht ist nicht das Systemziel — P16C favorisiert OXY/WDC/STX."
    )
    pdf.multi_cell(0, 5, summary)
    pdf.ln(3)

    pdf.section("9. Checkliste")
    pdf.set_font("Arial", "", 10)
    checks = [
        "[ ]  VUSD-Verkauf ausgefuehrt und Cash verbucht",
        f"[ ]  OXY ca. {_eur(d['buy100']['OXY'])} EUR gekauft",
        f"[ ]  WDC ca. {_eur(d['buy100']['WDC'])} EUR gekauft",
        f"[ ]  STX ca. {_eur(d['buy100']['STX'])} EUR gekauft",
        f"[ ]  Reserve ca. {_eur(d['reserve_after_100'])} EUR auf Konto",
        "[ ]  INTC / MU / CIEN nicht nachgekauft",
        "[ ]  Optional: Read-only API in Marktanalyse fuer Abgleich",
    ]
    for c in checks:
        pdf.cell(0, 6.5, c, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    return OUT


if __name__ == "__main__":
    print(build_pdf())
