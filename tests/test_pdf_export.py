"""Tests for vector PDF chart export."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def test_save_vector_charts_pdf_page(tmp_path: Path):
    pytest.importorskip("matplotlib")
    from matplotlib.backends.backend_pdf import PdfPages

    from aa_chart_render import save_vector_charts_pdf_page

    idx = pd.date_range("2018-01-01", periods=800, freq="B")
    strat = pd.Series(0.0004, index=idx)
    bench = pd.Series(0.0003, index=idx)
    sectors = pd.Series({"Tech": 0.6, "Health": 0.4})

    pdf_path = tmp_path / "charts.pdf"
    with PdfPages(str(pdf_path)) as pdf:
        save_vector_charts_pdf_page(pdf, strat, bench, sectors, bench_label="SPY")

    assert pdf_path.is_file()
    assert pdf_path.stat().st_size > 5000


def test_export_result_pdf_two_pages(tmp_path: Path):
    pytest.importorskip("matplotlib")
    import pandas as pd

    from aa_result_views import export_result_pdf

    idx = pd.date_range("2020-01-01", periods=400, freq="B")
    strat = pd.Series(0.0004, index=idx)
    bench = pd.Series(0.0003, index=idx)
    sectors = pd.Series({"Tech": 0.55, "Health": 0.45})
    rows = [
        {"ticker": "SPY", "weight_pct": 20.0, "amount": 2000.0, "shares": "10"},
        {"ticker": "AAPL", "weight_pct": 80.0, "amount": 8000.0, "shares": "40"},
    ]
    metrics = (
        "Ø Rendite p.a.: 26.5%\n"
        "Sharpe (Risiko/Rendite): 1.14\n"
        "Stärkster Rückgang: -27.0%\n"
        "Vergleichsindex: SPY"
    )
    path = export_result_pdf(
        tmp_path / "report.pdf",
        strategy_returns=strat,
        benchmark_returns=bench,
        sector_weights=sectors,
        bench_label="SPY",
        context_line="Zeitraum: 2010 – 2026 · Vergleich: SPY",
        metrics_summary=metrics,
        rows=rows,
        amount=10_000.0,
        fees={"total_cost_eur": 12.5},
        disclaimer="Keine Anlageberatung.",
    )
    assert path.is_file()
    assert path.stat().st_size > 12_000
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        assert len(reader.pages) == 2
    except ImportError:
        pass
