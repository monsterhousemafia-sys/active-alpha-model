"""Portfolio fees, offline prices, charts, PDF export for the result screen."""
from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

T212_MIN_ORDER_EUR = 1.0


def load_close_prices_from_cache(out_dir: Path, tickers: List[str]) -> Dict[str, float]:
    """Read last Close from out_dir/price_cache/ohlcv_panel.parquet (offline)."""
    panel_path = Path(out_dir) / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return {}
    try:
        panel = pd.read_parquet(panel_path)
        if panel.empty or "ticker" not in panel.columns:
            return {}
        if "date" in panel.columns:
            panel["date"] = pd.to_datetime(panel["date"])
        out: Dict[str, float] = {}
        want = {str(t).upper() for t in tickers}
        for tk, grp in panel.groupby("ticker"):
            key = str(tk).upper()
            if key not in want:
                continue
            if "Close" not in grp.columns:
                continue
            s = pd.to_numeric(grp["Close"], errors="coerce").dropna()
            if s.empty:
                continue
            if "date" in grp.columns:
                idx = grp["date"]
                val = s.loc[idx.idxmax()] if hasattr(idx, "max") else s.iloc[-1]
            else:
                val = s.iloc[-1]
            out[str(tk)] = float(val)
        return out
    except Exception:
        return {}


def resolve_prices_usd(
    out_dir: Path,
    tickers: List[str],
    *,
    online: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], str]:
    online = online or {}
    if online:
        return online, "live"
    cached = load_close_prices_from_cache(out_dir, tickers)
    if cached:
        return cached, "cache"
    return {}, "offline"


def synthesize_benchmark_returns(out_dir: Path, bench_ticker: str = "SPY") -> pd.Series:
    """Build daily benchmark returns from price cache if CSV missing."""
    cached = load_close_prices_from_cache(out_dir, [bench_ticker])
    px = cached.get(bench_ticker) or cached.get(bench_ticker.upper())
    if px is None and cached:
        px = next(iter(cached.values()), None)
    panel_path = Path(out_dir) / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return pd.Series(dtype=float)
    try:
        panel = pd.read_parquet(panel_path)
        tk = bench_ticker
        sub = panel[panel["ticker"].astype(str).str.upper() == tk.upper()].copy()
        if sub.empty:
            return pd.Series(dtype=float)
        sub["date"] = pd.to_datetime(sub["date"])
        sub = sub.sort_values("date")
        close = pd.to_numeric(sub["Close"], errors="coerce").dropna()
        close.index = pd.to_datetime(sub.loc[close.index, "date"])
        rets = close.pct_change().dropna()
        rets.name = "benchmark_return"
        return rets
    except Exception:
        return pd.Series(dtype=float)


def sector_weights(portfolio: pd.DataFrame) -> pd.Series:
    if portfolio.empty or "target_weight" not in portfolio.columns:
        return pd.Series(dtype=float)
    df = portfolio.copy()
    df["target_weight"] = pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0)
    if "sector" not in df.columns:
        df["sector"] = "Unbekannt"
    grouped = df.groupby(df["sector"].astype(str))["target_weight"].sum()
    total = float(grouped.sum())
    if total <= 0:
        return pd.Series(dtype=float)
    return (grouped / total).sort_values(ascending=False)


def estimate_portfolio_fees(
    rows: List[Dict[str, Any]],
    *,
    prices_usd: Dict[str, float],
    eurusd: Optional[float],
) -> Dict[str, float]:
    """Rough T212-style cost estimate for the displayed buy list."""
    from aa_config import BacktestConfig
    from aa_execution import estimate_backtest_trade_cost

    cfg = BacktestConfig()
    total = 0.0
    fx = float(eurusd) if eurusd and eurusd > 0 else 1.08
    for row in rows:
        ticker = str(row.get("ticker", ""))
        amount_eur = float(row.get("amount", 0.0))
        if amount_eur <= 0 or ticker.upper() in {"BARGELD", "CASH"}:
            continue
        px_usd = prices_usd.get(ticker) or prices_usd.get(ticker.upper())
        if not px_usd or px_usd <= 0:
            continue
        px_eur = px_usd / fx
        shares = amount_eur / px_eur
        cost = estimate_backtest_trade_cost(amount_eur, shares, "BUY", cfg)
        total += float(cost.get("total_cost", 0.0))
    return {"total_cost_eur": total, "n_orders": float(len(rows))}


def next_rebalance_hint(signal_date: str, rebalance_every: int = 5) -> str:
    if signal_date in {"", "n/a"}:
        return ""
    try:
        sig = pd.Timestamp(signal_date).date()
    except Exception:
        return ""
    nxt = sig + timedelta(days=int(max(rebalance_every, 1)))
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return f"Nächstes Rebalancing ca.: {nxt.isoformat()} (alle {rebalance_every} Handelstage)"


def render_sector_chart_png(sector: pd.Series, *, width_px: int = 480, height_px: int = 180) -> bytes:
    _ = width_px, height_px
    from aa_chart_render import render_sector_panel_png

    return render_sector_panel_png(sector)


def _pdf_plain_lines(*blocks: str) -> List[str]:
    """Flatten optional text blocks into non-empty lines for PDF layout."""
    lines: List[str] = []
    for block in blocks:
        if not block:
            continue
        for part in str(block).splitlines():
            text = part.strip()
            if text:
                lines.append(text)
    return lines


def save_pdf_report_page(
    pdf,
    *,
    context_line: str,
    metrics_summary: str,
    rows: List[Dict[str, Any]],
    amount: float,
    fees: Dict[str, float],
    disclaimer: str,
    rebalance_hint: str = "",
) -> None:
    """Render page 2 (report text) with fixed A4 margins — no fig.text drift."""
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(8.27, 11.69), dpi=300, facecolor="white")
    ax = fig.add_axes([0.08, 0.07, 0.84, 0.86])
    ax.set_axis_off()
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)

    y = 1.0
    body_gap = 0.032
    small_gap = 0.026

    def put(
        text: str,
        *,
        size: int = 9,
        weight: str = "normal",
        family: str = "sans-serif",
        gap: float = body_gap,
    ) -> None:
        nonlocal y
        if y < 0.12:
            return
        ax.text(
            0.0,
            y,
            text,
            transform=ax.transAxes,
            va="top",
            ha="left",
            fontsize=size,
            fontweight=weight,
            family=family,
            color="#202020",
        )
        y -= gap

    put("Marktanalyse — Portfolio-Report", size=14, weight="bold", gap=0.05)
    y -= 0.01
    for line in _pdf_plain_lines(context_line, rebalance_hint):
        put(line)
    if _pdf_plain_lines(context_line, rebalance_hint):
        y -= 0.012
    for line in _pdf_plain_lines(metrics_summary):
        put(line)
    y -= 0.018
    put(f"Investitionsbetrag: {amount:,.2f} EUR".replace(",", " "), size=10)
    put(
        f"Geschätzte T212-Kosten (Käufe): {fees.get('total_cost_eur', 0.0):,.2f} EUR".replace(",", " "),
        gap=small_gap,
    )
    y -= 0.02
    put("Positionen", size=10, weight="bold", gap=0.034)
    put(
        f"{'Ticker':<8} {'Gew.%':>6}  {'Betrag EUR':>12}  {'Stück':>8}",
        size=8,
        family="monospace",
        gap=0.028,
    )
    for row in rows[:20]:
        ticker = str(row.get("ticker", ""))[:8]
        line = (
            f"{ticker:<8} {float(row.get('weight_pct', 0.0)):>5.1f}%  "
            f"{float(row.get('amount', 0.0)):>11,.2f}  {str(row.get('shares', '—')):>8}".replace(",", " ")
        )
        put(line, size=8, family="monospace", gap=0.024)
        if y < 0.14:
            break

    ax.text(
        0.0,
        0.0,
        disclaimer,
        transform=ax.transAxes,
        va="bottom",
        ha="left",
        fontsize=7,
        color="#605e5c",
        wrap=True,
    )
    pdf.savefig(fig, dpi=300, facecolor="white")
    plt.close(fig)


def export_result_pdf(
    path: Path,
    *,
    chart_png: bytes = b"",
    sector_png: bytes = b"",
    context_line: str,
    metrics_summary: str,
    rows: List[Dict[str, Any]],
    amount: float,
    fees: Dict[str, float],
    disclaimer: str,
    rebalance_hint: str = "",
    equity_chart_png: bytes = b"",
    annual_chart_png: bytes = b"",
    sector_chart_png: bytes = b"",
    strategy_returns: Optional[pd.Series] = None,
    benchmark_returns: Optional[pd.Series] = None,
    sector_weights: Optional[pd.Series] = None,
    bench_label: str = "Benchmark",
) -> Path:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError as exc:
        raise RuntimeError("matplotlib fehlt für PDF-Export") from exc

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(path)) as pdf:
        if strategy_returns is not None and not getattr(strategy_returns, "empty", True):
            from aa_chart_render import save_vector_charts_pdf_page

            sectors = sector_weights if sector_weights is not None else pd.Series(dtype=float)
            save_vector_charts_pdf_page(
                pdf,
                strategy_returns,
                benchmark_returns,
                sectors,
                bench_label=bench_label,
            )
        else:
            images = [
                equity_chart_png or chart_png,
                annual_chart_png,
                sector_chart_png or sector_png,
            ]
            if any(images):
                fig = plt.figure(figsize=(11.69, 4.2), dpi=300, facecolor="white")
                slots = [i for i, img in enumerate(images) if img]
                n = len(slots)
                for j, idx in enumerate(slots):
                    ax = fig.add_axes([0.02 + j * (0.96 / max(n, 1)), 0.08, 0.96 / max(n, 1) - 0.02, 0.84])
                    ax.imshow(plt.imread(io.BytesIO(images[idx]), format="png"), interpolation="nearest")
                    ax.axis("off")
                pdf.savefig(fig, dpi=300)
                plt.close(fig)
        save_pdf_report_page(
            pdf,
            context_line=context_line,
            metrics_summary=metrics_summary,
            rows=rows,
            amount=amount,
            fees=fees,
            disclaimer=disclaimer,
            rebalance_hint=rebalance_hint,
        )
    return path
