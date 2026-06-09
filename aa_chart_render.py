"""Matplotlib result charts — identical plot areas, full white-canvas usage."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

# Supersample 2× then downscale → crisp Segoe UI text on HiDPI displays.
CHART_DPI = 144
RENDER_SCALE = 2
# No in-chart titles (Qt shows captions above each panel).
PLOT_AXES = [0.11, 0.11, 0.87, 0.88]
PLOT_AXES_EXPANDED = [0.08, 0.08, 0.91, 0.91]
MIN_INK_RATIO = 0.055
PDF_DPI = 300

_WIN11_FONT = ["Segoe UI", "Tahoma", "DejaVu Sans", "sans-serif"]


@dataclass
class ChartFillReport:
    panel: str
    ok: bool
    ink_ratio: float
    width_px: int
    height_px: int
    message: str


def _apply_mpl_style() -> bool:
    try:
        import logging

        logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plt.rcParams.update(
            {
                "font.family": "sans-serif",
                "font.sans-serif": _WIN11_FONT,
                "font.size": 9,
                "axes.labelsize": 9,
                "axes.titlesize": 9,
                "legend.fontsize": 8,
                "xtick.labelsize": 8,
                "ytick.labelsize": 8,
                "text.antialiased": True,
                "axes.unicode_minus": False,
                "figure.dpi": CHART_DPI,
                "savefig.dpi": CHART_DPI,
                "lines.antialiased": True,
                "patch.antialiased": True,
                "axes.edgecolor": "#d1d1d1",
                "axes.linewidth": 0.75,
                "grid.color": "#ebebeb",
                "grid.linewidth": 0.55,
                "text.color": "#202020",
                "axes.labelcolor": "#202020",
                "xtick.color": "#605e5c",
                "ytick.color": "#605e5c",
            }
        )
        return True
    except ImportError:
        return False


def _style_axes(ax) -> None:
    ax.tick_params(axis="both", which="major", labelsize=8, width=0.75, length=3, colors="#605e5c")
    for spine in ax.spines.values():
        spine.set_linewidth(0.75)
        spine.set_color("#d1d1d1")


def measure_ink_ratio(png_bytes: bytes, *, white_threshold: int = 248) -> float:
    if not png_bytes:
        return 0.0
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        pixels = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())
        total = max(len(pixels), 1)
        ink = sum(1 for r, g, b in pixels if r < white_threshold or g < white_threshold or b < white_threshold)
        return ink / total
    except Exception:
        return 0.0


def png_dimensions(png_bytes: bytes) -> Tuple[int, int]:
    if not png_bytes:
        return 0, 0
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes))
        return int(img.size[0]), int(img.size[1])
    except Exception:
        return 0, 0


def validate_chart_png(
    panel: str,
    png_bytes: bytes,
    *,
    target_w: int,
    target_h: int,
    min_ink: float = MIN_INK_RATIO,
) -> ChartFillReport:
    w, h = png_dimensions(png_bytes)
    ink = measure_ink_ratio(png_bytes)
    if not png_bytes:
        return ChartFillReport(panel, False, 0.0, w, h, "leer")
    if w <= 0 or h <= 0:
        return ChartFillReport(panel, False, ink, w, h, "PNG unlesbar")
    if ink < min_ink:
        return ChartFillReport(panel, False, ink, w, h, f"Zeichenfläche zu leer ({ink:.1%})")
    if abs(w - target_w) > 8 or abs(h - target_h) > 8:
        return ChartFillReport(panel, False, ink, w, h, f"Größe {w}x{h} ≠ Ziel {target_w}x{target_h}")
    return ChartFillReport(panel, True, ink, w, h, "ok")


def _figure_bytes(fig, *, width_px: int, height_px: int) -> bytes:
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=CHART_DPI,
        facecolor="white",
        edgecolor="white",
        pad_inches=0.01,
    )
    plt.close(fig)
    data = buf.getvalue()
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        if img.size != (width_px, height_px):
            img = img.resize((width_px, height_px), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, format="PNG", optimize=False)
            return out.getvalue()
    except Exception:
        pass
    return data


def _make_figure(width_px: int, height_px: int, axes_rect: List[float]):
    import matplotlib.pyplot as plt

    render_w = max(width_px * RENDER_SCALE, 480)
    render_h = max(height_px * RENDER_SCALE, 440)
    w_in = render_w / CHART_DPI
    h_in = render_h / CHART_DPI
    fig = plt.figure(figsize=(w_in, h_in), dpi=CHART_DPI, facecolor="white")
    ax = fig.add_axes(axes_rect)
    return fig, ax


def _blank_panel(message: str, *, width_px: int, height_px: int, axes_rect: List[float]) -> bytes:
    if not _apply_mpl_style():
        return b""
    fig, ax = _make_figure(width_px, height_px, axes_rect)
    ax.set_axis_off()
    ax.text(
        0.5,
        0.5,
        message,
        ha="center",
        va="center",
        fontsize=9,
        color="#605e5c",
        transform=ax.transAxes,
        family=_WIN11_FONT[0],
    )
    return _figure_bytes(fig, width_px=width_px, height_px=height_px)


def _render_panel(
    width_px: int,
    height_px: int,
    draw_fn: Callable,
    *,
    axes_rect: Optional[List[float]] = None,
) -> bytes:
    if not _apply_mpl_style():
        return b""
    rect = axes_rect or PLOT_AXES
    fig, ax = _make_figure(width_px, height_px, rect)
    draw_fn(ax)
    _style_axes(ax)
    return _figure_bytes(fig, width_px=width_px, height_px=height_px)


def _render_with_qc(
    panel: str,
    width_px: int,
    height_px: int,
    draw_fn: Callable,
) -> Tuple[bytes, ChartFillReport]:
    width_px = max(int(width_px), 240)
    height_px = max(int(height_px), 220)
    png = _render_panel(width_px, height_px, draw_fn, axes_rect=PLOT_AXES)
    report = validate_chart_png(panel, png, target_w=width_px, target_h=height_px)
    if report.ok:
        return png, report
    png = _render_panel(width_px, height_px, draw_fn, axes_rect=PLOT_AXES_EXPANDED)
    report = validate_chart_png(panel, png, target_w=width_px, target_h=height_px, min_ink=MIN_INK_RATIO * 0.85)
    return png, report


def draw_equity_on_axes(
    ax,
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
) -> bool:
    """Draw equity curves on an existing matplotlib axes (vector-safe for PDF)."""
    common = strategy.dropna().index
    if benchmark is not None and not benchmark.empty:
        common = common.intersection(benchmark.dropna().index)
    if len(common) < 2:
        return False
    eq_s = (1.0 + strategy.reindex(common).fillna(0.0)).cumprod()
    ax.plot(eq_s.index, eq_s.values, label="Strategie", color="#0067c0", linewidth=1.65, antialiased=True)
    if benchmark is not None and not benchmark.empty:
        eq_b = (1.0 + benchmark.reindex(common).fillna(0.0)).cumprod()
        ax.plot(eq_b.index, eq_b.values, label=bench_label, color="#8a8886", linewidth=1.25, alpha=0.95, antialiased=True)
    ax.set_ylabel("Wachstum")
    ax.legend(loc="upper left", frameon=False, prop={"size": 8, "family": _WIN11_FONT[0]})
    ax.grid(True, alpha=0.95)
    _style_axes(ax)
    return True


def draw_annual_on_axes(
    ax,
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
    calendar_year_returns_fn=None,
) -> bool:
    if calendar_year_returns_fn is None:
        from aa_dashboard_result import calendar_year_returns

        calendar_year_returns_fn = calendar_year_returns

    strat_years = calendar_year_returns_fn(strategy)
    bench_years = (
        calendar_year_returns_fn(benchmark)
        if benchmark is not None and not benchmark.empty
        else pd.Series(dtype=float)
    )
    years = sorted(set(strat_years.index.astype(int).tolist()) | set(bench_years.index.astype(int).tolist()))
    if not years:
        return False
    x = list(range(len(years)))
    bar_w = 0.36
    s_vals = [float(strat_years.get(y, float("nan"))) * 100 for y in years]
    ax.bar([i - bar_w / 2 for i in x], s_vals, width=bar_w, label="Strategie", color="#0067c0", linewidth=0)
    if not bench_years.empty:
        b_vals = [float(bench_years.get(y, float("nan"))) * 100 for y in years]
        ax.bar([i + bar_w / 2 for i in x], b_vals, width=bar_w, label=bench_label, color="#a19f9d", linewidth=0)
    ax.set_xticks(x)
    ax.set_xticklabels([str(y) for y in years], rotation=45, ha="right")
    ax.set_ylabel("Rendite %")
    ax.axhline(0, color="#323130", linewidth=0.55)
    ax.legend(loc="upper left", frameon=False, prop={"size": 8, "family": _WIN11_FONT[0]})
    ax.grid(True, axis="y", alpha=0.95)
    _style_axes(ax)
    return True


def draw_sector_on_axes(ax, sector: pd.Series) -> bool:
    if sector.empty:
        return False
    top = sector.head(8)
    labels = [str(x)[:22] for x in reversed(top.index.tolist())]
    ax.barh(labels, (top.values[::-1] * 100.0), color="#0067c0", height=0.68, linewidth=0)
    ax.set_xlabel("Gewicht %")
    ax.grid(True, axis="x", alpha=0.95)
    _style_axes(ax)
    return True


def save_vector_charts_pdf_page(
    pdf,
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    sector: pd.Series,
    *,
    bench_label: str = "Benchmark",
) -> None:
    """Render sharp vector charts directly into a PDF page (300 DPI)."""
    if not _apply_mpl_style():
        return
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(11.69, 4.0), dpi=PDF_DPI, facecolor="white")
    panels = [
        ("Kumulierte Performance", draw_equity_on_axes, (strategy, benchmark), {"bench_label": bench_label}),
        ("Jahresvergleich", draw_annual_on_axes, (strategy, benchmark), {"bench_label": bench_label}),
        ("Sektor-Allokation", draw_sector_on_axes, (sector,), {}),
    ]
    for idx, (title, draw_fn, args, kwargs) in enumerate(panels, start=1):
        ax = fig.add_subplot(1, 3, idx)
        ax.set_facecolor("white")
        ok = draw_fn(ax, *args, **kwargs)
        if ok:
            ax.set_title(title, fontsize=9, color="#202020", pad=6, family=_WIN11_FONT[0])
        else:
            ax.set_axis_off()
            ax.text(0.5, 0.5, "Keine Daten", ha="center", va="center", fontsize=9, color="#605e5c")
    fig.tight_layout(pad=0.8, w_pad=1.0)
    pdf.savefig(fig, dpi=PDF_DPI, facecolor="white")
    plt.close(fig)


def render_equity_chart_png(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
    width_px: int = 462,
    height_px: int = 320,
) -> bytes:
    def _draw(ax) -> None:
        draw_equity_on_axes(ax, strategy, benchmark, bench_label=bench_label)

    if strategy.empty:
        return _blank_panel("Keine Daten", width_px=width_px, height_px=height_px, axes_rect=PLOT_AXES)
    common = strategy.dropna().index
    if benchmark is not None and not benchmark.empty:
        common = common.intersection(benchmark.dropna().index)
    if len(common) < 10:
        return _blank_panel("Zu wenig Daten", width_px=width_px, height_px=height_px, axes_rect=PLOT_AXES)
    png, _ = _render_with_qc("equity", width_px, height_px, _draw)
    return png


def render_annual_chart_png(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
    calendar_year_returns_fn=None,
    width_px: int = 462,
    height_px: int = 320,
) -> bytes:
    if calendar_year_returns_fn is None:
        from aa_dashboard_result import calendar_year_returns

        calendar_year_returns_fn = calendar_year_returns

    if strategy.empty:
        return _blank_panel("Keine Daten", width_px=width_px, height_px=height_px, axes_rect=PLOT_AXES)

    strat_years = calendar_year_returns_fn(strategy)
    bench_years = (
        calendar_year_returns_fn(benchmark)
        if benchmark is not None and not benchmark.empty
        else pd.Series(dtype=float)
    )
    years = sorted(set(strat_years.index.astype(int).tolist()) | set(bench_years.index.astype(int).tolist()))
    if not years:
        return _blank_panel("Keine Jahresrenditen", width_px=width_px, height_px=height_px, axes_rect=PLOT_AXES)

    def _draw(ax) -> None:
        draw_annual_on_axes(ax, strategy, benchmark, bench_label=bench_label, calendar_year_returns_fn=calendar_year_returns_fn)

    png, _ = _render_with_qc("annual", width_px, height_px, _draw)
    return png


def render_sector_panel_png(sector: pd.Series, *, width_px: int = 462, height_px: int = 320) -> bytes:
    if sector.empty:
        return _blank_panel("Keine Sektordaten", width_px=width_px, height_px=height_px, axes_rect=PLOT_AXES)

    def _draw(ax) -> None:
        draw_sector_on_axes(ax, sector)

    png, _ = _render_with_qc("sector", width_px, height_px, _draw)
    return png


def render_result_panels_sized(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    sector: pd.Series,
    panel_sizes: Dict[str, Tuple[int, int]],
    *,
    bench_label: str = "Benchmark",
) -> Tuple[Dict[str, bytes], List[ChartFillReport]]:
    from aa_dashboard_result import calendar_year_returns

    def _size(key: str) -> Tuple[int, int]:
        w, h = panel_sizes.get(key, (462, 320))
        return max(int(w), 240), max(int(h), 220)

    reports: List[ChartFillReport] = []
    w, h = _size("equity")
    equity = render_equity_chart_png(strategy, benchmark, bench_label=bench_label, width_px=w, height_px=h)
    reports.append(validate_chart_png("equity", equity, target_w=w, target_h=h))

    w, h = _size("annual")
    annual = render_annual_chart_png(
        strategy,
        benchmark,
        bench_label=bench_label,
        calendar_year_returns_fn=calendar_year_returns,
        width_px=w,
        height_px=h,
    )
    reports.append(validate_chart_png("annual", annual, target_w=w, target_h=h))

    w, h = _size("sector")
    sector_png = render_sector_panel_png(sector, width_px=w, height_px=h)
    reports.append(validate_chart_png("sector", sector_png, target_w=w, target_h=h))

    return {
        "equity_chart_png": equity,
        "annual_chart_png": annual,
        "sector_chart_png": sector_png,
        "chart_png": equity,
    }, reports
