"""Evidence-based pick rationale from frozen champion CSV — no invented stories."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

CHAMPION_ID = "R3_w075_q065_noexit"

METHODOLOGY_DE = (
    f"Champion {CHAMPION_ID} (eingefrorenes Signal, read-only). "
    "Messgrößen: alpha_lcb (untere Konfidenzgrenze der erwarteten Überrendite), "
    "rank_score (Rang im Universum), target_weight (Zielgewicht), eligible (handelbar ja/nein), "
    "risk_on / target_exposure (Marktregime & Ziel-Investitionsgrad). "
    "Die App rechnet das Modell nicht neu — fehlende CSV-Felder → keine Begründung."
)


def _fmt_num(val: Any, *, decimals: int = 4) -> str:
    try:
        return f"{float(val):.{decimals}f}"
    except (TypeError, ValueError):
        return "—"


def explain_symbol_from_model_row(
    symbol_row: Optional[Dict[str, Any]],
    meta: Optional[Dict[str, Any]],
    *,
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Build pick rationale only from champion CSV fields present on the row.
    status: OK | INCOMPLETE | MISSING
    """
    sym = str(symbol or (symbol_row or {}).get("symbol") or "").upper()
    meta = meta or {}
    if not symbol_row:
        return {
            "status": "MISSING",
            "symbol": sym,
            "summary_de": "Keine Modellzeile — Champion-CSV fehlt oder Symbol nicht im Signal.",
            "factors_de": [],
            "signal_date": str(meta.get("signal_date") or "")[:10],
            "champion_id": CHAMPION_ID,
        }

    factors: List[str] = []
    signal_date = str(meta.get("signal_date") or "")[:10]
    if signal_date:
        factors.append(f"Signal-Datum (eingefroren): {signal_date}")

    eligible = symbol_row.get("eligible")
    if eligible is False:
        factors.append("eligible=false — nicht für neue Käufe vorgesehen")
    elif eligible is True:
        factors.append("eligible=true — im Champion-Universum")

    tw = symbol_row.get("target_weight")
    if tw is not None:
        try:
            factors.append(f"Zielgewicht im Modell: {_fmt_num(float(tw) * 100, decimals=2)} %")
        except (TypeError, ValueError):
            pass

    alcb = symbol_row.get("alpha_lcb")
    if alcb is not None:
        factors.append(f"alpha_lcb: {_fmt_num(alcb)} (höher = stärkeres Signal)")

    rs = symbol_row.get("rank_score")
    if rs is not None:
        factors.append(f"rank_score: {_fmt_num(rs)} (Portfolio-Rang)")

    mu = symbol_row.get("mu_hat")
    if mu is not None:
        factors.append(f"mu_hat: {_fmt_num(mu)} (erwartete Überrendite-Schätzung)")

    sel = symbol_row.get("selection_score")
    if sel is not None:
        factors.append(f"selection_score: {_fmt_num(sel)}")

    sector = str(symbol_row.get("sector") or "").strip()
    if sector:
        factors.append(f"Sektor (Modell): {sector}")

    risk_on = meta.get("risk_on")
    if risk_on is not None:
        factors.append(
            "Risk-on — Nachkäufe erlaubt"
            if bool(risk_on)
            else "Risk-off — Modell empfiehlt keine neuen Nachkäufe"
        )
    texp = meta.get("target_exposure")
    if texp is not None:
        factors.append(f"Ziel-Exposure Modell: {_fmt_num(float(texp) * 100, decimals=1)} %")

    if not factors:
        return {
            "status": "INCOMPLETE",
            "symbol": sym,
            "summary_de": f"{sym}: CSV-Zeile ohne auswertbare Kennzahlen.",
            "factors_de": [],
            "signal_date": signal_date,
            "champion_id": CHAMPION_ID,
        }

    headline_parts: List[str] = []
    if alcb is not None:
        headline_parts.append(f"Alpha LCB {_fmt_num(alcb)}")
    if rs is not None:
        headline_parts.append(f"Rang {_fmt_num(rs)}")
    if tw is not None:
        try:
            headline_parts.append(f"Gewicht {_fmt_num(float(tw) * 100, decimals=1)} %")
        except (TypeError, ValueError):
            pass
    headline = " · ".join(headline_parts) if headline_parts else "Champion-Zeile"

    return {
        "status": "OK",
        "symbol": sym,
        "summary_de": f"{sym}: {headline}",
        "factors_de": factors,
        "signal_date": signal_date,
        "champion_id": CHAMPION_ID,
    }


def explain_primary_pick(
    root: Any,
    *,
    symbol: str,
    plan_row: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Rationale for today's primary symbol from champion CSV."""
    from pathlib import Path

    from analytics.pilot_portfolio_reevaluation import load_champion_portfolio_model

    champion = load_champion_portfolio_model(Path(root))
    if champion.get("status") != "OK":
        return {
            "status": "MISSING",
            "symbol": str(symbol).upper(),
            "summary_de": "Champion-Portfolio nicht lesbar — keine Pick-Begründung.",
            "factors_de": [f"CSV-Status: {champion.get('status')}"],
            "signal_date": "",
            "champion_id": CHAMPION_ID,
        }
    sym = str(symbol).upper()
    row = (champion.get("symbols") or {}).get(sym) or plan_row or {}
    out = explain_symbol_from_model_row(row, champion.get("meta"), symbol=sym)
    if plan_row and plan_row.get("target_eur"):
        out["factors_de"] = list(out.get("factors_de") or [])
        out["factors_de"].append(
            f"Live-Ziel (Cash-Skalierung): {float(plan_row['target_eur']):.2f} € netto nach Gebührenpuffer"
        )
    return out


def rationale_one_liner(doc: Dict[str, Any], *, max_len: int = 120) -> str:
    line = str(doc.get("summary_de") or "")
    if doc.get("status") != "OK":
        return line[:max_len]
    factors = doc.get("factors_de") or []
    if factors and len(line) < 40:
        line = f"{line} — {factors[0]}"
    return line[:max_len] + ("…" if len(line) > max_len else "")
