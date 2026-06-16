"""Ganztägiger Fall-Wächter — erkennt Portfolio-Abwärtsbewegung mit Begründung."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_daily_postmortem_policy.json")
_EVIDENCE_REL = Path("evidence/prognosis_fall_watch_latest.json")
_PORTFOLIO_REL = Path("model_output_sp500_pit_t212/latest_target_portfolio.csv")
_PANEL_REL = Path("model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")


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


def _load_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(root / _POLICY_REL)
    return doc or {
        "bad_day_underperform_bps": 50,
        "bad_day_portfolio_pct": -0.01,
        "benchmark_ticker": "SPY",
    }


def _load_signal_picks(root: Path) -> List[Dict[str, Any]]:
    import pandas as pd

    path = root / _PORTFOLIO_REL
    if not path.is_file():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    wsum = float(df["target_weight"].sum()) or 1.0
    picks = []
    for _, r in df.iterrows():
        w = float(r["target_weight"]) / wsum
        if w <= 0:
            continue
        picks.append(
            {
                "ticker": str(r["ticker"]).upper(),
                "weight": w,
                "mu_hat": float(r.get("mu_hat") or 0),
            }
        )
    return picks


def _prior_closes(root: Path, tickers: List[str], bench: str) -> Dict[str, float]:
    import pandas as pd

    panel_path = root / _PANEL_REL
    if not panel_path.is_file():
        return {}
    panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    panel["date"] = pd.to_datetime(panel["date"])
    panel["ticker"] = panel["ticker"].astype(str).str.upper()
    latest = panel["date"].max()
    sub = panel[panel["date"] == latest]
    out: Dict[str, float] = {}
    for t in tickers + [bench]:
        row = sub[sub["ticker"] == t]
        if not row.empty:
            out[t] = float(row["Close"].iloc[-1])
    out["_as_of_date"] = str(latest.date()) if not pd.isna(latest) else ""
    return out


def _fetch_live_usd(tickers: List[str]) -> Dict[str, Tuple[float, str]]:
    """Read-only Yahoo last price (USD)."""
    out: Dict[str, Tuple[float, str]] = {}
    try:
        import yfinance as yf
    except ImportError:
        return out
    uniq = sorted({t for t in tickers if t})
    if not uniq:
        return out
    try:
        data = yf.download(
            " ".join(uniq),
            period="1d",
            interval="1m",
            progress=False,
            threads=True,
            auto_adjust=True,
        )
    except Exception:
        return out
    if data is None or data.empty:
        return out
    import pandas as pd

    now = _utc_now()
    if isinstance(data.columns, pd.MultiIndex):
        for t in uniq:
            try:
                col = data["Close"][t].dropna()
                if not col.empty:
                    out[t] = (float(col.iloc[-1]), now)
            except (KeyError, TypeError, ValueError):
                pass
    else:
        col = data["Close"].dropna()
        if len(uniq) == 1 and not col.empty:
            out[uniq[0]] = (float(col.iloc[-1]), now)
    return out


def _justify_fall(
    *,
    port_ret: float,
    bench_ret: Optional[float],
    mu_hat_port: float,
    picks_detail: List[Dict[str, Any]],
    policy: Dict[str, Any],
    prior_date: str,
) -> Dict[str, Any]:
    from scipy import stats

    bad_abs = float(policy.get("bad_day_portfolio_pct") or -0.01)
    under_bps = float(policy.get("bad_day_underperform_bps") or 50) / 10000.0
    n_down = sum(1 for p in picks_detail if (p.get("intraday_return_pct") or 0) < 0)
    n_up = sum(1 for p in picks_detail if (p.get("intraday_return_pct") or 0) > 0)
    n_total = len(picks_detail)
    delta = (port_ret - bench_ret) if bench_ret is not None else None

    triggers: List[str] = []
    if port_ret < 0:
        triggers.append(f"Portfolio negativ ({port_ret*100:+.2f} %)")
    if port_ret < bad_abs:
        triggers.append(f"Portfolio unter Schwelle {bad_abs*100:.1f} %")
    if delta is not None and delta < -under_bps:
        triggers.append(f"Underperformance vs SPY ({delta*100:+.2f} %, Schwelle −{under_bps*100:.2f} %)")
    if n_total and n_down > n_up:
        triggers.append(f"Mehrheit fallend ({n_down}/{n_total} Titel rot)")
    if port_ret < mu_hat_port:
        triggers.append(f"Unter Modell-Erwartung μ̂={mu_hat_port*100:+.2f} %")

    # Binomial: ist heutiger Fall ungewöhnlich vs. H1 hit-rate?
    h1 = _load_json(Path(__file__).resolve().parents[1] / "evidence/daily_alpha_h1_evaluation_latest.json")
    hit = float((h1.get("metrics_strategy") or {}).get("daily_hit_rate") or 0.5466)
    p_down_hist = 1.0 - hit

    reasons_de: List[str] = []
    if triggers:
        reasons_de.append("Auslöser: " + "; ".join(triggers))
    if delta is not None:
        reasons_de.append(f"Gewichtetes Plan-Portfolio {port_ret*100:+.2f} % vs. SPY {bench_ret*100:+.2f} % (Δ {delta*100:+.2f} %).")
    else:
        reasons_de.append(f"Gewichtetes Plan-Portfolio {port_ret*100:+.2f} % (Benchmark fehlt).")
    reasons_de.append(
        f"Modell erwartete +{mu_hat_port*100:.2f} % — realisierte Abweichung {(port_ret - mu_hat_port)*100:+.2f} Prozentpunkte."
    )
    if n_total:
        reasons_de.append(f"Einzelwerte: {n_down} fallend, {n_up} steigend (Basis Vortag {prior_date}).")
    worst = min(picks_detail, key=lambda x: float(x.get("intraday_return_pct") or 0), default=None)
    best = max(picks_detail, key=lambda x: float(x.get("intraday_return_pct") or 0), default=None)
    if worst:
        reasons_de.append(f"Schwächster: {worst['ticker']} {worst['intraday_return_pct']:+.2f} %.")
    if best:
        reasons_de.append(f"Stärkster: {best['ticker']} {best['intraday_return_pct']:+.2f} %.")

    # Bestätigter Fall nur bei Postmortem-Schwellen (−1 % oder −50 bp vs. SPY)
    fall_detected = port_ret < bad_abs
    if delta is not None and delta < -under_bps:
        fall_detected = True

    return {
        "fall_detected": fall_detected,
        "thresholds": {
            "bad_day_portfolio_pct": bad_abs,
            "underperform_spy_bps": int(under_bps * 10000),
        },
        "triggers": triggers,
        "reasons_de": reasons_de,
        "n_down": n_down,
        "n_up": n_up,
        "delta_vs_spy_pct": round(delta * 100, 3) if delta is not None else None,
        "vs_model_mu_hat_pp": round((port_ret - mu_hat_port) * 100, 3),
        "historical_p_down_h1": round(p_down_hist, 4),
    }


def run_fall_watch(root: Path, *, persist: bool = True, fetch_live: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = _load_policy(root)
    bench = str(policy.get("benchmark_ticker") or "SPY").upper()
    picks = _load_signal_picks(root)
    if not picks:
        doc = {"ok": False, "fall_detected": False, "message_de": "Keine Signal-Picks", "updated_at_utc": _utc_now()}
        if persist:
            atomic_write_json(root / _EVIDENCE_REL, doc)
        return doc

    tickers = [p["ticker"] for p in picks]
    priors = _prior_closes(root, tickers, bench)
    prior_date = str(priors.pop("_as_of_date", "") or "")

    live: Dict[str, Tuple[float, str]] = {}
    if fetch_live:
        live = _fetch_live_usd(tickers + [bench])

    lines: List[Dict[str, Any]] = []
    w_sum = 0.0
    ret_sum = 0.0
    mu_sum = 0.0
    missing: List[str] = []

    for p in picks:
        t = p["ticker"]
        w = p["weight"]
        p0 = priors.get(t)
        live_row = live.get(t)
        if p0 is None or not live_row:
            missing.append(t)
            continue
        p1 = live_row[0]
        ret = p1 / p0 - 1.0
        lines.append(
            {
                "ticker": t,
                "weight_pct": round(w * 100, 2),
                "mu_hat_pct": round(p["mu_hat"] * 100, 3),
                "prior_close": round(p0, 4),
                "live_price": round(p1, 4),
                "intraday_return_pct": round(ret * 100, 3),
                "quote_utc": live_row[1],
            }
        )
        w_sum += w
        ret_sum += w * ret
        mu_sum += w * p["mu_hat"]

    port_ret = ret_sum / w_sum if w_sum > 0 else None
    mu_hat_port = mu_sum / w_sum if w_sum > 0 else 0.0

    bench_ret = None
    if bench in priors and bench in live and priors[bench] > 0:
        bench_ret = live[bench][0] / priors[bench] - 1.0

    justification: Dict[str, Any] = {}
    fall_detected = False
    if port_ret is not None:
        justification = _justify_fall(
            port_ret=port_ret,
            bench_ret=bench_ret,
            mu_hat_port=mu_hat_port,
            picks_detail=lines,
            policy=policy,
            prior_date=prior_date,
        )
        fall_detected = bool(justification.get("fall_detected"))

    if fall_detected and port_ret is not None:
        headline = f"✓ Fall erkannt — Portfolio {port_ret*100:+.2f} %"
    elif port_ret is not None and port_ret < 0:
        headline = f"Schwäche (noch kein bestätigter Fall) — Portfolio {port_ret*100:+.2f} %"
    elif port_ret is not None:
        headline = f"Kein Fall — Portfolio {port_ret*100:+.2f} % (überwachen)"
    else:
        headline = "Warten auf Live-Kurse"

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": port_ret is not None,
        "fall_detected": fall_detected,
        "headline_de": headline,
        "prior_close_date": prior_date,
        "portfolio_return_pct": round(port_ret * 100, 3) if port_ret is not None else None,
        "benchmark_return_pct": round(bench_ret * 100, 3) if bench_ret is not None else None,
        "mu_hat_portfolio_pct": round(mu_hat_port * 100, 3),
        "missing_tickers": missing,
        "picks": sorted(lines, key=lambda x: x["intraday_return_pct"]),
        "justification": justification,
        "monitoring_de": "Read-only — kein Order-Impact",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
