"""Swing-Trading-Theorie — read-only Tagescheck (Momentum-Uptrend + Pullback)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/swing_trading_theory_latest.json")
_PORTFOLIO_REL = Path("model_output_sp500_pit_t212/latest_target_portfolio.csv")
_PANEL_REL = Path("model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")
_POLICY_REL = Path("control/swing_trading_theory_policy.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_swing_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    return doc or {
        "min_uptrend_share": 0.6,
        "min_pullback_in_uptrend_today": 3,
        "min_weighted_mom_63": 0.0,
        "orders_impact": "NONE",
    }


def run_swing_trading_theory_check(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Prüft ob Swing-Muster (mom_63-Uptrend + Pullback) heute im Plan-Portfolio sichtbar sind."""
    import numpy as np
    import pandas as pd
    from scipy import stats

    root = Path(root)
    policy = load_swing_policy(root)
    port_path = root / _PORTFOLIO_REL
    panel_path = root / _PANEL_REL
    if not port_path.is_file() or not panel_path.is_file():
        doc = {
            "ok": False,
            "shows_today": False,
            "headline_de": "Swing-Check — Portfolio/Panel fehlt",
            "updated_at_utc": _utc_now(),
        }
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    port = pd.read_csv(port_path)
    panel = pd.read_parquet(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    panel["ticker"] = panel["ticker"].astype(str).str.upper()
    panel = panel.sort_values(["ticker", "date"])
    panel["ret1d"] = panel.groupby("ticker")["Close"].pct_change()
    panel["ret5d"] = panel.groupby("ticker")["Close"].pct_change(5)
    latest = panel["date"].max()
    recent = panel[panel["date"] >= (latest - pd.Timedelta(days=30))]

    wsum = float(port["target_weight"].sum()) or 1.0
    port = port.copy()
    port["w"] = port["target_weight"] / wsum

    rows: List[Dict[str, Any]] = []
    for _, r in port.iterrows():
        t = str(r["ticker"]).upper()
        mom63 = float(r.get("mom_63_21") or 0)
        rev5 = float(r.get("rev_5") or 0)
        trend50 = float(r.get("trend_50") or 0)
        sub = recent[recent["ticker"] == t]
        ret1 = float(sub["ret1d"].iloc[-1]) if len(sub) and pd.notna(sub["ret1d"].iloc[-1]) else None
        ret5 = float(sub["ret5d"].iloc[-1]) if len(sub) and pd.notna(sub["ret5d"].iloc[-1]) else None
        uptrend = mom63 > 0 and trend50 >= 0.5
        pullback = rev5 < 0 or (ret1 is not None and ret1 < 0)
        swing_setup = uptrend and pullback
        manifest_today = None
        if uptrend and ret1 is not None:
            if ret1 < 0 and mom63 > 0:
                manifest_today = "pullback_in_uptrend"
            elif ret1 > 0:
                manifest_today = "continuation"
        rows.append(
            {
                "ticker": t,
                "weight_pct": round(float(r["w"]) * 100, 2),
                "mom_63": round(mom63, 4),
                "rev_5": round(rev5, 4),
                "uptrend": uptrend,
                "swing_setup": swing_setup,
                "ret1d_pct": round(ret1 * 100, 3) if ret1 is not None else None,
                "ret5d_pct": round(ret5 * 100, 3) if ret5 is not None else None,
                "manifest_today": manifest_today,
            }
        )

    df = pd.DataFrame(rows)
    n = len(df)
    n_uptrend = int(df["uptrend"].sum()) if n else 0
    n_swing_setup = int(df["swing_setup"].sum()) if n else 0
    n_pullback = int((df["manifest_today"] == "pullback_in_uptrend").sum()) if n else 0
    n_cont = int((df["manifest_today"] == "continuation").sum()) if n else 0

    def _wavg(col: str) -> Optional[float]:
        total = 0.0
        acc = 0.0
        for row in rows:
            v = row.get(col)
            if v is None:
                continue
            wt = row["weight_pct"] / 100.0
            acc += float(v) * wt
            total += wt
        return acc / total if total else None

    w_mom63 = _wavg("mom_63")
    w_rev5 = _wavg("rev_5")
    align = df[df["uptrend"] & df["ret5d_pct"].notna()]
    align_pct = float((np.sign(align["ret5d_pct"]) == np.sign(align["mom_63"])).mean()) if len(align) else None
    binom_p = float(stats.binomtest(n_swing_setup, n, 0.5, alternative="greater").pvalue) if n else None

    min_uptrend = float(policy.get("min_uptrend_share") or 0.6)
    min_pull = int(policy.get("min_pullback_in_uptrend_today") or 3)
    min_mom = float(policy.get("min_weighted_mom_63") or 0.0)

    shows = (
        n > 0
        and n_uptrend / n >= min_uptrend
        and n_pullback >= min_pull
        and w_mom63 is not None
        and w_mom63 > min_mom
    )

    fall = _load_json(root / "evidence/prognosis_fall_watch_latest.json")

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "ok": True,
        "updated_at_utc": _utc_now(),
        "as_of": str(latest.date()),
        "signal_date": str(port["signal_date"].iloc[0]),
        "shows_today": shows,
        "headline_de": (
            f"✓ Swing-Theorie sichtbar — {n_pullback} Pullbacks im Uptrend, {n_uptrend}/{n} Uptrends"
            if shows
            else f"○ Swing-Theorie heute schwach — {n_pullback} Pullbacks, {n_uptrend}/{n} Uptrends"
        ),
        "theory_de": (
            "Swing-Mapping: mom_63>0 + trend_50 (Uptrend) und rev_5<0 oder Tagesminus (Pullback) = "
            "mehr-Tage-Swing-Einstieg. Ergänzt h=1-Day-Alpha, ersetzt es nicht."
        ),
        "metrics": {
            "n_picks": n,
            "n_uptrend": n_uptrend,
            "n_swing_setup": n_swing_setup,
            "n_pullback_in_uptrend_today": n_pullback,
            "n_continuation_today": n_cont,
            "weighted_mom_63": round(w_mom63, 4) if w_mom63 is not None else None,
            "weighted_rev_5": round(w_rev5, 4) if w_rev5 is not None else None,
            "ret5d_mom63_alignment_pct": round(align_pct * 100, 1) if align_pct is not None else None,
            "portfolio_intraday_pct": fall.get("portfolio_return_pct"),
            "binom_swing_setup_p": round(binom_p, 4) if binom_p is not None else None,
        },
        "criteria_de": [
            f"Uptrend-Anteil ≥{min_uptrend:.0%}: {n_uptrend}/{n}",
            f"Pullback-im-Uptrend heute ≥{min_pull}: {n_pullback}",
            f"gewichtetes mom_63 > {min_mom}: {w_mom63:.4f}" if w_mom63 is not None else "mom_63 fehlt",
        ],
        "picks": sorted(rows, key=lambda x: (not x["swing_setup"], x.get("ret1d_pct") or 0)),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        "governance_de": "Read-only — kein Order-Impact, kein Champion-Wechsel",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
