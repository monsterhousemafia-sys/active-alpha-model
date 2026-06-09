"""Champion portfolio rows for live trading UI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# SPY = benchmark filler; VUSD = LSE/GBP identity unresolved. SNDK tradable (user: SNDK = Sandisk @ T212).
BLOCKED_SYMBOLS = frozenset({"SPY", "VUSD"})


def _out_dir(root: Path) -> Path:
    return root / "model_output_sp500_pit_t212"


def _load_prognosis(root: Path) -> Dict[str, Any]:
    for name in ("pilot_today_prognosis_latest.json", "pilot_today_prognosis_20260601.json"):
        path = root / "evidence" / name
        if path.is_file():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                return doc if isinstance(doc, dict) else {}
            except (json.JSONDecodeError, OSError):
                continue
    return {}


def _load_portfolio_picks(root: Path, *, max_symbols: int = 50) -> List[Dict[str, Any]]:
    import pandas as pd

    path = _out_dir(root) / "latest_target_portfolio.csv"
    if not path.is_file():
        return []
    df = pd.read_csv(path)
    if df.empty or "ticker" not in df.columns:
        return []
    if "signal_date" in df.columns:
        df = df[df["ticker"].astype(str).str.upper() != "SPY"]
    if "eligible" in df.columns:
        df = df[df["eligible"].fillna(False).astype(bool)]
    if "target_weight" in df.columns:
        df = df[df["target_weight"].fillna(0).astype(float) > 0]
    sort_col = "alpha_lcb" if "alpha_lcb" in df.columns else "target_weight"
    df = df.sort_values(sort_col, ascending=False)
    picks: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        sym = str(row.get("ticker", "")).upper().strip()
        if not sym or sym in BLOCKED_SYMBOLS:
            continue
        weight = float(row.get("target_weight") or 0) * 100.0
        picks.append(
            {
                "symbol": sym,
                "model_weight_pct": round(weight, 2),
                "alpha_lcb": float(row.get("alpha_lcb") or 0),
                "signal_date": str(row.get("signal_date", ""))[:10],
            }
        )
        if len(picks) >= max(1, int(max_symbols)):
            break
    return picks


def load_today_pick(root: Path) -> Dict[str, Any]:
    """Best executable pick with optional EUR hint from prognosis."""
    root = Path(root)
    prognosis = _load_prognosis(root)
    picks = _load_portfolio_picks(root)
    if not picks and prognosis.get("top_executable_picks"):
        picks = list(prognosis["top_executable_picks"])

    top = picks[0] if picks else {}
    sym = str(top.get("symbol") or "").upper()
    eur_map = {
        str(p.get("symbol", "")).upper(): p.get("p16c_target_eur")
        for p in (prognosis.get("top_executable_picks") or [])
    }
    target_eur = eur_map.get(sym)
    if target_eur is None and sym:
        target_eur = round(500.0 * float(top.get("model_weight_pct") or 5) / 100.0 * 1.35, 2)

    signal_date = str(prognosis.get("signal_date") or top.get("signal_date") or "")[:10]
    regime = str(prognosis.get("regime") or "RISK_ON")

    from analytics.pilot_pick_rationale import explain_primary_pick, rationale_one_liner

    rationale = explain_primary_pick(root, symbol=sym, plan_row=top)
    reason = rationale_one_liner(rationale, max_len=200)

    return {
        "symbol": sym,
        "signal_date": signal_date,
        "regime": regime,
        "target_eur": target_eur,
        "model_weight_pct": top.get("model_weight_pct"),
        "reason_de": reason,
        "pick_rationale": rationale,
        "executable": bool(sym) and sym not in BLOCKED_SYMBOLS,
        "alternates": [p.get("symbol") for p in picks[1:4]],
    }
