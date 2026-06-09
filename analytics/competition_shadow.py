"""Shadow snapshot: model vs. mom_1 benchmark vs. live fills (observe-only)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from aa_safe_io import atomic_write_json

EVIDENCE_LATEST = Path("evidence/competition_shadow_latest.json")
EVIDENCE_HISTORY = Path("evidence/competition_shadow_history.jsonl")
PORTFOLIO_REL = Path("model_output_sp500_pit_t212/latest_target_portfolio.csv")
PRICE_PANEL_REL = Path("model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")
SUBMITTED_REL = Path("live_pilot/confirmed_execution/submitted_orders")
BENCHMARK_VARIANT = "mom_1_top12"
TOP_K = 12


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_portfolio_picks(root: Path) -> Dict[str, Any]:
    path = Path(root) / PORTFOLIO_REL
    if not path.is_file():
        return {"signal_date": None, "picks": []}
    df = pd.read_csv(path)
    if df.empty:
        return {"signal_date": None, "picks": []}
    signal_date = str(df["signal_date"].iloc[0])[:10] if "signal_date" in df.columns else None
    weight_col = "target_weight" if "target_weight" in df.columns else None
    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ticker = str(row.get("ticker") or "").upper()
        if not ticker or ticker == "SPY":
            continue
        w = float(row.get(weight_col) or 0) if weight_col else 0.0
        if w <= 0:
            continue
        rows.append(
            {
                "ticker": ticker,
                "target_weight": w,
                "mu_hat": float(row["mu_hat"]) if pd.notna(row.get("mu_hat")) else None,
                "rank_score": float(row["rank_score"]) if pd.notna(row.get("rank_score")) else None,
            }
        )
    rows.sort(key=lambda r: r["target_weight"], reverse=True)
    return {"signal_date": signal_date, "picks": rows}


def _normalize_ticker(raw: str) -> str:
    s = str(raw or "").upper().strip()
    if not s:
        return ""
    if "_US_EQ" in s:
        s = s.split("_US_EQ")[0]
    return s.split("_")[0] if s.endswith("_EQ") else s


def _load_eligible_universe(root: Path) -> Optional[Set[str]]:
    path = Path(root) / PORTFOLIO_REL
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path, usecols=lambda c: c in {"ticker", "in_universe", "eligible"})
    except Exception:
        return None
    if "eligible" in df.columns:
        mask = df["eligible"].astype(str).str.lower().isin({"true", "1", "yes"})
        tickers = {str(t).upper() for t in df.loc[mask, "ticker"].dropna()}
        if tickers:
            return tickers
    if "in_universe" in df.columns:
        mask = df["in_universe"].astype(str).str.lower().isin({"true", "1", "yes"})
        tickers = {str(t).upper() for t in df.loc[mask, "ticker"].dropna()}
        return tickers or None
    return None


def _mom1_top_picks(root: Path, signal_date: str, *, top_k: int = TOP_K) -> List[Dict[str, Any]]:
    panel_path = Path(root) / PRICE_PANEL_REL
    if not panel_path.is_file() or not signal_date:
        return []
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        return []
    if panel.empty:
        return []
    panel["date"] = pd.to_datetime(panel["date"], errors="coerce").dt.normalize()
    sig = pd.Timestamp(signal_date)
    window_start = sig - pd.Timedelta(days=21)
    panel = panel[(panel["date"] >= window_start) & (panel["date"] <= sig)].copy()
    if panel.empty:
        return []
    universe = _load_eligible_universe(root)
    if universe:
        panel = panel[panel["ticker"].astype(str).str.upper().isin(universe)]
    panel["Close"] = pd.to_numeric(panel["Close"], errors="coerce")
    panel = panel.sort_values(["ticker", "date"])
    panel["mom_1"] = panel.groupby("ticker", sort=False)["Close"].pct_change()
    last = panel.groupby("ticker", as_index=False).tail(1)
    last = last[last["mom_1"].notna() & (last["mom_1"] > 0) & (last["mom_1"] <= 0.5)]
    if last.empty:
        return []
    last = last.sort_values("mom_1", ascending=False).head(top_k)
    raw = last.set_index("ticker")["mom_1"].clip(lower=0) + 1e-6
    weights = (raw / raw.sum()).to_dict()
    return [
        {
            "ticker": str(row["ticker"]).upper(),
            "mom_1": float(row["mom_1"]),
            "target_weight": float(weights[str(row["ticker"]).upper()]),
        }
        for _, row in last.iterrows()
    ]


def _recent_live_orders(root: Path, *, limit: int = 20) -> List[Dict[str, Any]]:
    base = Path(root) / SUBMITTED_REL
    if not base.is_dir():
        return []
    files = sorted(base.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out: List[Dict[str, Any]] = []
    for path in files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        draft = doc.get("draft") or {}
        resp = doc.get("response") or {}
        raw_ticker = draft.get("instrument") or draft.get("ticker") or (resp.get("instrument") or {}).get("ticker") or ""
        out.append(
            {
                "draft_id": str(doc.get("draft_id") or path.stem),
                "ticker": _normalize_ticker(str(raw_ticker)),
                "side": str(draft.get("side") or ""),
                "status": str(resp.get("status") or resp.get("orderStatus") or "unknown"),
                "submitted_at_utc": doc.get("submitted_at_utc"),
            }
        )
    return out


def _overlap(a: Set[str], b: Set[str]) -> Dict[str, Any]:
    if not a and not b:
        return {"jaccard": None, "shared": [], "only_a": [], "only_b": []}
    shared = sorted(a & b)
    return {
        "jaccard": len(shared) / len(a | b) if (a | b) else None,
        "shared": shared,
        "only_a": sorted(a - b),
        "only_b": sorted(b - a),
    }


def build_competition_shadow_snapshot(root: Path) -> Dict[str, Any]:
    """Compare active model portfolio to mom_1_top12 and recent live orders."""
    root = Path(root)
    port = _load_portfolio_picks(root)
    signal_date = port.get("signal_date")
    model_tickers = {str(p["ticker"]).upper() for p in port.get("picks") or []}
    bench = _mom1_top_picks(root, str(signal_date or ""))
    bench_tickers = {str(p["ticker"]).upper() for p in bench}
    live = _recent_live_orders(root)
    live_tickers = {str(o["ticker"]).upper() for o in live if o.get("ticker")}
    model_bench = _overlap(model_tickers, bench_tickers)
    model_live = _overlap(model_tickers, live_tickers)

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "benchmark_variant": BENCHMARK_VARIANT,
        "benchmark_method_de": (
            "Unabhängiges mom_1_top12 auf eligible Universum (positive 1d-Returns, gleicher Preis-Stand) — "
            "informative only, nicht identisch mit Backtest-Pipeline."
        ),
        "signal_date": signal_date,
        "model": {
            "profile_ref": "control/prediction_operations.json",
            "n_picks": len(port.get("picks") or []),
            "top_picks": (port.get("picks") or [])[:TOP_K],
        },
        "benchmark_mom_1_top12": {
            "n_picks": len(bench),
            "top_picks": bench,
        },
        "live_orders_recent": live,
        "comparison": {
            "model_vs_benchmark": _overlap(model_tickers, bench_tickers),
            "model_vs_live": _overlap(model_tickers, live_tickers),
            "benchmark_vs_live": _overlap(bench_tickers, live_tickers),
        },
        "message_de": (
            f"Shadow: Modell {len(model_tickers)} | mom_1 {len(bench_tickers)} | "
            f"Overlap Modell/Benchmark {len(model_bench.get('shared') or [])} | "
            f"Modell/Live {len(model_live.get('shared') or [])} — Signal {signal_date or '—'}."
        ),
    }
    return doc


def write_competition_shadow_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    doc = build_competition_shadow_snapshot(root)
    atomic_write_json(root / EVIDENCE_LATEST, doc)
    hist_path = root / EVIDENCE_HISTORY
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    with hist_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    return doc
