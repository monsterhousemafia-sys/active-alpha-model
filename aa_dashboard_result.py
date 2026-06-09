"""Load backtest outputs and build the Marktanalyse result view (chart + portfolio)."""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

DISCLAIMER_TEXT = (
    "Hinweis: Dieses Forschungsmodell ist keine Anlageberatung. "
    "Vergangene Performance ist kein verlässlicher Indikator für zukünftige Ergebnisse. "
    "Kurse, Wechselkurse und Gebühren können abweichen. "
    "Prüfen Sie Orders selbstständig bei Ihrem Broker."
)


METRIC_TOOLTIPS: Dict[str, str] = {
    "cagr": "Durchschnittliche jährliche Rendite über den Backtest-Zeitraum.",
    "sharpe_0rf": "Rendite pro Risiko-Einheit (höher = effizienter).",
    "max_drawdown": "Größter Peak-to-Trough-Verlust im Zeitraum.",
    "information_ratio": "Überrendite vs. Benchmark, bereinigt um Tracking Error.",
    "total_return": "Gesamtrendite über den gesamten Backtest.",
}


def _read_daily_returns_csv(path: Path, value_col: str) -> pd.Series:
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if df.empty:
        return pd.Series(dtype=float)
    col = value_col if value_col in df.columns else df.columns[0]
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def load_strategy_returns(out_dir: Path) -> pd.Series:
    path = Path(out_dir) / "strategy_daily_returns.csv"
    if not path.is_file():
        return pd.Series(dtype=float)
    return _read_daily_returns_csv(path, "strategy_return")


def load_benchmark_returns(out_dir: Path) -> pd.Series:
    path = Path(out_dir) / "benchmark_daily_returns.csv"
    if path.is_file():
        s = _read_daily_returns_csv(path, "benchmark_return")
        if not s.empty:
            return s
    bench = resolve_benchmark_label(out_dir)
    from aa_result_views import synthesize_benchmark_returns

    return synthesize_benchmark_returns(out_dir, bench)


def calendar_year_returns(daily: pd.Series) -> pd.Series:
    if daily.empty:
        return pd.Series(dtype=float)
    grouped = daily.groupby(daily.index.year)
    return grouped.apply(lambda x: float((1.0 + x).prod() - 1.0))


def resolve_benchmark_label(out_dir: Path, default: str = "Benchmark") -> str:
    cfg = parse_run_config_snapshot(out_dir)
    return cfg.get("benchmark") or default


def parse_run_config_snapshot(out_dir: Path) -> Dict[str, str]:
    snap = Path(out_dir) / "run_config_snapshot.txt"
    out: Dict[str, str] = {}
    if not snap.is_file():
        return out
    for line in snap.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        out[key.strip().lower()] = val.strip()
    return out


def build_context_line(
    out_dir: Path,
    *,
    signal_date: str = "n/a",
    portfolio_exposure: Optional[float] = None,
) -> str:
    cfg = parse_run_config_snapshot(out_dir)
    start = cfg.get("start", "")
    bench = cfg.get("benchmark", "SPY")
    strategy = load_strategy_returns(out_dir)
    end = ""
    if not strategy.empty:
        end = strategy.index.max().strftime("%Y-%m-%d")
    period = f"{start} – {end}" if start and end else (start or end or "Backtest-Zeitraum unbekannt")
    parts = [f"Zeitraum: {period}", f"Vergleich: {bench}"]
    if signal_date != "n/a":
        parts.append(f"Signal: {signal_date}")
    if portfolio_exposure is not None and portfolio_exposure < 0.999:
        parts.append(f"Modell-Exposure: {portfolio_exposure:.0%}")
    return " · ".join(parts)


def resolve_portfolio_exposure(portfolio: pd.DataFrame) -> float:
    if portfolio.empty:
        return 1.0
    if "portfolio_exposure" in portfolio.columns:
        val = pd.to_numeric(portfolio["portfolio_exposure"], errors="coerce").dropna()
        if not val.empty:
            exp = float(val.iloc[0])
            if 0.0 < exp <= 1.0:
                return exp
    total_w = float(portfolio["target_weight"].sum())
    if 0.0 < total_w < 1.0:
        return total_w
    return 1.0


def fetch_fx_eurusd() -> Optional[float]:
    """USD per 1 EUR (yfinance EURUSD=X)."""
    try:
        import yfinance as yf

        hist = yf.Ticker("EURUSD=X").history(period="5d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception:
        return None


def fetch_last_prices_usd(tickers: List[str]) -> Dict[str, float]:
    tickers = [t for t in tickers if t and str(t).upper() not in {"CASH", "BARGELD"}]
    if not tickers:
        return {}

    from aa_fictive_daily_data import fetch_fictive_last_prices_usd, is_fictive_price_source

    if is_fictive_price_source(None, os.environ):
        return fetch_fictive_last_prices_usd(tickers)

    try:
        import yfinance as yf

        data = yf.download(
            tickers,
            period="5d",
            progress=False,
            threads=False,
            auto_adjust=True,
        )
        out: Dict[str, float] = {}
        if len(tickers) == 1:
            tk = tickers[0]
            if not data.empty and "Close" in data.columns:
                out[tk] = float(data["Close"].iloc[-1])
            return out
        if data.empty:
            return out
        close = data.get("Close")
        if close is None:
            return out
        if isinstance(close, pd.Series):
            tk = tickers[0]
            val = close.iloc[-1]
            if pd.notna(val):
                out[tk] = float(val)
            return out
        for tk in tickers:
            if tk not in close.columns:
                continue
            val = close[tk].iloc[-1]
            if pd.notna(val):
                out[tk] = float(val)
        return out
    except Exception:
        return {}


def stock_only_portfolio(portfolio: pd.DataFrame) -> pd.DataFrame:
    """Drop benchmark/cash filler rows — show investable stocks only."""
    if portfolio.empty:
        return portfolio
    df = portfolio.copy()
    if "sector" in df.columns:
        df = df[df["sector"].astype(str).str.lower() != "benchmark"]
    if "correlation_cluster" in df.columns:
        df = df[~df["correlation_cluster"].astype(str).str.contains("Benchmark", case=False, na=False)]
    if "ticker" in df.columns:
        df = df[~df["ticker"].astype(str).str.upper().isin({"BARGELD", "CASH"})]
    return df


def exemplar_stock_portfolio(portfolio: pd.DataFrame) -> pd.DataFrame:
    """Stock-only sleeve renormalized to 100% — no cash / benchmark completion residual."""
    df = stock_only_portfolio(portfolio)
    if df.empty or "target_weight" not in df.columns:
        return df
    total_w = float(pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0).sum())
    if total_w <= 0:
        return df
    out = df.copy()
    out["target_weight"] = pd.to_numeric(out["target_weight"], errors="coerce").fillna(0.0) / total_w
    return out


def load_target_portfolio(out_dir: Path, *, paper_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, str]:
    """Return (portfolio_df, source_description)."""
    out_dir = Path(out_dir)
    candidates: List[Tuple[Path, str]] = [
        (out_dir / "latest_target_portfolio.csv", "aktuelles Modell-Signal"),
    ]
    if paper_dir is not None:
        candidates.append((Path(paper_dir) / "latest_target_portfolio.csv", "Paper-Modell"))

    for path, label in candidates:
        if not path.is_file():
            continue
        df = pd.read_csv(path)
        if df.empty or "target_weight" not in df.columns:
            continue
        df = df.copy()
        df["target_weight"] = pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0)
        df = df[df["target_weight"] > 0].copy()
        if df.empty:
            continue
        if "ticker" not in df.columns:
            continue
        return df, label

    weights_path = out_dir / "backtest_weights.csv"
    if weights_path.is_file():
        wh = pd.read_csv(weights_path)
        if not wh.empty and {"ticker", "weight", "rebalance_date"}.issubset(wh.columns):
            wh["rebalance_date"] = pd.to_datetime(wh["rebalance_date"], errors="coerce")
            last = wh["rebalance_date"].max()
            snap = wh[wh["rebalance_date"] == last].copy()
            snap["target_weight"] = pd.to_numeric(snap["weight"], errors="coerce").fillna(0.0)
            snap = snap[snap["target_weight"] > 0]
            if not snap.empty:
                return snap, f"letzte Backtest-Gewichtung ({last.date() if pd.notna(last) else 'n/a'})"

    return pd.DataFrame(), ""


def load_stock_portfolio(out_dir: Path, *, paper_dir: Optional[Path] = None) -> Tuple[pd.DataFrame, str]:
    """Portfolio without benchmark/cash filler rows (legacy sector views)."""
    portfolio, source = load_target_portfolio(out_dir, paper_dir=paper_dir)
    return stock_only_portfolio(portfolio), source


def scale_portfolio_rows(
    portfolio: pd.DataFrame,
    amount: float,
    *,
    prices_usd: Optional[Dict[str, float]] = None,
    eurusd: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], float, float]:
    """Allocate capital by portfolio-level target_weight (no silent 100% normalization).

    ``target_weight`` is the share of total portfolio capital. Uninvested capital is cash:
    ``cash = max(0, amount - sum(amount * target_weight))``.
    Returns (rows, invested_eur, cash_eur).
    """
    if portfolio.empty or amount <= 0:
        return [], 0.0, 0.0

    total_w = float(portfolio["target_weight"].sum())
    if total_w <= 0:
        return [], 0.0, float(amount)

    rows: List[Dict[str, Any]] = []
    allocated = 0.0
    for _, rec in portfolio.sort_values("target_weight", ascending=False).iterrows():
        w = float(rec["target_weight"])
        line_amount = round(amount * w, 2)
        allocated += line_amount
        ticker = str(rec.get("ticker", ""))
        shares_txt = "—"
        if prices_usd and ticker in prices_usd and eurusd and eurusd > 0:
            price_eur = prices_usd[ticker] / eurusd
            if price_eur > 0:
                shares = line_amount / price_eur
                shares_txt = f"{shares:.4f}".rstrip("0").rstrip(".")
        rows.append(
            {
                "ticker": ticker,
                "sector": str(rec.get("sector", "") or "—"),
                "weight_pct": w * 100.0,
                "sleeve_weight_pct": (w / total_w * 100.0) if total_w > 0 else 0.0,
                "amount": line_amount,
                "shares": shares_txt,
            }
        )
    invested = round(sum(float(r["amount"]) for r in rows), 2)
    cash = round(max(0.0, amount - invested), 2)
    if rows and abs(invested + cash - amount) > 0.02:
        rows[0]["amount"] = round(float(rows[0]["amount"]) + (amount - invested - cash), 2)
        invested = round(sum(float(r["amount"]) for r in rows), 2)
        cash = round(max(0.0, amount - invested), 2)

    return rows, invested, cash


def export_portfolio_csv(
    path: Path,
    rows: List[Dict[str, Any]],
    *,
    amount: float,
    context_line: str = "",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Marktanalyse Portfolio"])
        writer.writerow(["Gesamtbetrag_EUR", f"{amount:.2f}"])
        if context_line:
            writer.writerow(["Kontext", context_line])
        writer.writerow([])
        writer.writerow(["Ticker", "Sektor", "Gewicht_Prozent", "Betrag_EUR", "Stueck"])
        for row in rows:
            writer.writerow(
                [
                    row.get("ticker", ""),
                    row.get("sector", ""),
                    f"{float(row.get('weight_pct', 0.0)):.2f}",
                    f"{float(row.get('amount', 0.0)):.2f}",
                    row.get("shares", "—"),
                ]
            )
    return path


def format_metrics_summary(metrics: Dict[str, Any], bench_label: str) -> str:
    lines: List[str] = []
    labels = {
        "cagr": "Ø Rendite p.a.",
        "sharpe_0rf": "Sharpe (Risiko/Rendite)",
        "max_drawdown": "Stärkster Rückgang",
        "information_ratio": "Überrendite vs. Index",
        "total_return": "Gesamtrendite",
    }
    for key, label in labels.items():
        if key not in metrics:
            continue
        val = metrics[key]
        if isinstance(val, (float, int)):
            if key in {"cagr", "max_drawdown", "total_return"}:
                lines.append(f"{label}: {float(val):.1%}")
            else:
                lines.append(f"{label}: {float(val):.2f}")
        else:
            lines.append(f"{label}: {val}")
    if lines:
        lines.append(f"Vergleichsindex: {bench_label}")
    return "\n".join(lines)


def format_metrics_html(metrics: Dict[str, Any], bench_label: str) -> str:
    """Readable HTML block for the result panel (Segoe-friendly spacing)."""
    labels = {
        "cagr": "Ø Rendite p.a.",
        "sharpe_0rf": "Sharpe",
        "max_drawdown": "Max. Rückgang",
        "information_ratio": "Info-Ratio",
        "total_return": "Gesamtrendite",
    }
    rows: List[str] = []
    for key, label in labels.items():
        if key not in metrics:
            continue
        val = metrics[key]
        if isinstance(val, (float, int)):
            if key in {"cagr", "max_drawdown", "total_return"}:
                display = f"{float(val):.1%}"
            else:
                display = f"{float(val):.2f}"
        else:
            display = str(val)
        rows.append(
            f'<tr>'
            f'<td style="color:#605e5c;padding:4px 12px 4px 0;white-space:nowrap;font-size:9pt;">{label}</td>'
            f'<td style="color:#202020;padding:4px 0;font-size:9pt;">{display}</td>'
            f"</tr>"
        )
    if not rows:
        return ""
    return (
        '<table cellspacing="0" cellpadding="0" style="font-family:\'Segoe UI Variable Text\',\'Segoe UI\';'
        'font-size:9pt;line-height:1.4;">'
        + "".join(rows)
        + f'</table><p style="color:#605e5c;margin:10px 0 0 0;font-size:9pt;">Index: {bench_label}</p>'
    )


def render_performance_chart_png(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
    width_px: int = 720,
    height_px: int = 420,
) -> bytes:
    """Legacy combined chart (PDF fallback). Prefer split panels in the UI."""
    from aa_chart_render import render_annual_chart_png, render_equity_chart_png

    _ = width_px, height_px
    eq = render_equity_chart_png(strategy, benchmark, bench_label=bench_label)
    if not eq:
        return b""
    return eq


def render_result_charts(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    sector: pd.Series,
    *,
    bench_label: str = "Benchmark",
) -> Dict[str, bytes]:
    from aa_chart_render import render_annual_chart_png, render_equity_chart_png, render_sector_panel_png

    equity = render_equity_chart_png(strategy, benchmark, bench_label=bench_label)
    annual = render_annual_chart_png(
        strategy, benchmark, bench_label=bench_label, calendar_year_returns_fn=calendar_year_returns
    )
    sector_png = render_sector_panel_png(sector)
    combined = equity  # backward-compatible single blob
    return {
        "equity_chart_png": equity,
        "annual_chart_png": annual,
        "sector_chart_png": sector_png,
        "chart_png": combined,
    }


def load_result_context(
    out_dir: Path,
    *,
    metrics: Optional[Dict[str, Any]] = None,
    paper_dir: Optional[Path] = None,
    skip_chart_png: bool = False,
    online_prices: bool = True,
) -> Dict[str, Any]:
    from aa_result_views import (
        estimate_portfolio_fees,
        next_rebalance_hint,
        resolve_prices_usd,
        sector_weights,
    )
    from aa_version import APP_TITLE, APP_VERSION, MODEL_PROFILE
    from aa_ops_validation import assess_analytical_status, INVALID_ANALYSIS_USER_MESSAGE
    from aa_run_provenance import load_validated_run_dir, resolve_canonical_variant_id_from_manifest
    from aa_variant_id import normalize_variant_label
    from aa_model_status import format_model_status_block, read_model_status, write_model_status

    out_dir = Path(out_dir)
    analytical_validity, validated_run_id = assess_analytical_status(out_dir)
    analytical_ok = analytical_validity == "PASS"
    variant_id = ""
    run_dir = load_validated_run_dir(out_dir)
    if run_dir is not None:
        variant_id = resolve_canonical_variant_id_from_manifest(run_dir) or ""
    if not variant_id:
        variant_id = normalize_variant_label(MODEL_PROFILE)

    strategy = load_strategy_returns(out_dir) if analytical_ok else pd.Series(dtype=float)
    benchmark = load_benchmark_returns(out_dir) if analytical_ok else pd.Series(dtype=float)
    bench_label = resolve_benchmark_label(out_dir)
    portfolio, portfolio_source = load_target_portfolio(out_dir, paper_dir=paper_dir)
    exposure = resolve_portfolio_exposure(portfolio) if not portfolio.empty else 1.0
    signal_date = "n/a"
    if not portfolio.empty and "signal_date" in portfolio.columns:
        signal_date = str(portfolio["signal_date"].iloc[0])
    cfg = parse_run_config_snapshot(out_dir)
    rebalance_every = int(cfg.get("rebalance_every", "5") or "5")
    prices_usd: Dict[str, float] = {}
    price_source = "offline"
    eurusd: Optional[float] = None
    if not portfolio.empty:
        tickers = portfolio["ticker"].astype(str).tolist()
        online = fetch_last_prices_usd(tickers) if online_prices else {}
        prices_usd, price_source = resolve_prices_usd(out_dir, tickers, online=online or None)
        if online_prices:
            eurusd = fetch_fx_eurusd()
    sectors = sector_weights(portfolio) if analytical_ok else {}
    if skip_chart_png or not analytical_ok:
        charts = {
            "equity_chart_png": b"",
            "annual_chart_png": b"",
            "sector_chart_png": b"",
            "chart_png": b"",
        }
    else:
        charts = render_result_charts(strategy, benchmark, sectors, bench_label=bench_label)
    context_line = build_context_line(out_dir, signal_date=signal_date, portfolio_exposure=exposure)
    if not analytical_ok:
        context_line = f"{INVALID_ANALYSIS_USER_MESSAGE} | {context_line}"
    rebalance_hint = next_rebalance_hint(signal_date, rebalance_every=rebalance_every)
    fees = estimate_portfolio_fees([], prices_usd=prices_usd, eurusd=eurusd)
    safe_metrics = metrics if analytical_ok else {}
    model_status = read_model_status(out_dir)
    if analytical_ok:
        write_model_status(out_dir, variant_id=variant_id)
    return {
        "strategy_returns": strategy,
        "benchmark_returns": benchmark,
        "bench_label": bench_label,
        "portfolio": portfolio,
        "portfolio_source": portfolio_source,
        "portfolio_exposure": exposure,
        "prices_usd": prices_usd,
        "price_source": price_source,
        "eurusd": eurusd,
        "chart_png": charts["chart_png"],
        "equity_chart_png": charts["equity_chart_png"],
        "annual_chart_png": charts["annual_chart_png"],
        "sector_chart_png": charts["sector_chart_png"],
        "sector_png": charts["sector_chart_png"],
        "sector_weights": sectors,
        "metrics_summary": format_metrics_summary(safe_metrics, bench_label) if analytical_ok else INVALID_ANALYSIS_USER_MESSAGE,
        "metrics_html": format_metrics_html(safe_metrics, bench_label) if analytical_ok else f"<p>{INVALID_ANALYSIS_USER_MESSAGE}</p>",
        "metric_tooltips": METRIC_TOOLTIPS,
        "signal_date": signal_date,
        "context_line": context_line,
        "rebalance_hint": rebalance_hint,
        "rebalance_every": rebalance_every,
        "disclaimer": DISCLAIMER_TEXT,
        "app_title": APP_TITLE,
        "app_version": APP_VERSION,
        "model_profile": variant_id or MODEL_PROFILE,
        "fees_estimate": fees,
        "min_order_eur": 1.0,
        "analytical_validity": analytical_validity if analytical_validity in {"PASS", "INVALID"} else "NOT_VALIDATED",
        "analytical_error": "" if analytical_ok else INVALID_ANALYSIS_USER_MESSAGE,
        "validated_run_id": validated_run_id,
        "model_status": model_status,
        "model_status_text": format_model_status_block(model_status),
        "ai_development_text": model_status.get("ai_development_text") or "",
    }
