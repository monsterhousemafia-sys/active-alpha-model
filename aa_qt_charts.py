"""Native Qt Charts for the Marktanalyse result screen (HiDPI, zoom, tooltips)."""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

import pandas as pd

COLOR_STRATEGY = "#0067c0"
COLOR_BENCH_LINE = "#8a8886"
COLOR_BENCH_BAR = "#a19f9d"
COLOR_GRID = "#ebebeb"
COLOR_AXIS = "#605e5c"
COLOR_TEXT = "#202020"
COLOR_ZERO = "#323130"


def qt_charts_available() -> bool:
    try:
        from PySide6.QtCharts import QChart  # noqa: F401

        return True
    except ImportError:
        return False


def _chart_font(*, size: int = 9, semibold: bool = False):
    from aa_qt_render import win11_ui_font

    return win11_ui_font(size=size, semibold=semibold)


def _style_chart(chart) -> None:
    from PySide6.QtCore import QMargins, Qt
    from PySide6.QtGui import QBrush, QColor

    chart.setBackgroundVisible(True)
    chart.setBackgroundBrush(QBrush(QColor("#ffffff")))
    chart.setPlotAreaBackgroundVisible(True)
    chart.setPlotAreaBackgroundBrush(QBrush(QColor("#ffffff")))
    chart.setMargins(QMargins(4, 4, 4, 4))
    legend = chart.legend()
    legend.setVisible(True)
    legend.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    font = _chart_font(size=8)
    if font is not None:
        chart.setFont(font)
        legend.setFont(font)
    chart.setAnimationOptions(chart.AnimationOption.NoAnimation)


def _style_value_axis(axis, *, title: str = "") -> None:
    from PySide6.QtGui import QBrush, QColor, QPen

    if title:
        axis.setTitleText(title)
    axis.setLabelsColor(COLOR_AXIS)
    axis.setTitleBrush(QBrush(QColor(COLOR_TEXT)))
    axis.setGridLinePen(QPen(QColor(COLOR_GRID), 0.55))
    axis.setMinorGridLineVisible(False)
    font = _chart_font(size=8)
    if font is not None:
        axis.setLabelsFont(font)
        axis.setTitleFont(font)


def _style_category_axis(axis) -> None:
    from PySide6.QtGui import QPen

    axis.setLabelsColor(COLOR_AXIS)
    axis.setGridLineVisible(False)
    font = _chart_font(size=8)
    if font is not None:
        axis.setLabelsFont(font)


def _ms(ts) -> float:
    return float(pd.Timestamp(ts).timestamp() * 1000.0)


def build_equity_chart(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
):
    from PySide6.QtCharts import QChart, QDateTimeAxis, QLineSeries, QValueAxis
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPen

    chart = QChart()
    _style_chart(chart)

    common = strategy.dropna().index
    if benchmark is not None and not benchmark.empty:
        common = common.intersection(benchmark.dropna().index)
    if len(common) < 2:
        return chart

    eq_s = (1.0 + strategy.reindex(common).fillna(0.0)).cumprod()
    s_series = QLineSeries()
    s_series.setName("Strategie")
    s_series.setPen(QPen(QColor(COLOR_STRATEGY), 2.0))
    for ts, val in eq_s.items():
        s_series.append(_ms(ts), float(val))
    chart.addSeries(s_series)

    if benchmark is not None and not benchmark.empty:
        eq_b = (1.0 + benchmark.reindex(common).fillna(0.0)).cumprod()
        b_series = QLineSeries()
        b_series.setName(bench_label)
        b_series.setPen(QPen(QColor(COLOR_BENCH_LINE), 1.5))
        for ts, val in eq_b.items():
            b_series.append(_ms(ts), float(val))
        chart.addSeries(b_series)

    axis_x = QDateTimeAxis()
    span_years = (pd.Timestamp(common.max()) - pd.Timestamp(common.min())).days / 365.25
    axis_x.setFormat("yyyy" if span_years > 3 else "MMM yy")
    axis_x.setTickCount(min(8, max(3, int(span_years) + 1)))
    _style_category_axis(axis_x)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

    axis_y = QValueAxis()
    axis_y.setTitleText("Wachstum")
    axis_y.setLabelFormat("%.2f")
    _style_value_axis(axis_y, title="Wachstum")
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

    for series in chart.series():
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

    from PySide6.QtCore import QDateTime

    axis_x.setRange(
        QDateTime.fromMSecsSinceEpoch(int(_ms(common.min()))),
        QDateTime.fromMSecsSinceEpoch(int(_ms(common.max()))),
    )
    vals = list(eq_s.values)
    if benchmark is not None and not benchmark.empty:
        vals += list((1.0 + benchmark.reindex(common).fillna(0.0)).cumprod().values)
    y_min = min(vals)
    y_max = max(vals)
    pad = (y_max - y_min) * 0.06 or 0.05
    axis_y.setRange(y_min - pad, y_max + pad)
    return chart


def build_annual_chart(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    *,
    bench_label: str = "Benchmark",
    calendar_year_returns_fn: Optional[Callable[[pd.Series], pd.Series]] = None,
):
    from PySide6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QValueAxis
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    if calendar_year_returns_fn is None:
        from aa_dashboard_result import calendar_year_returns

        calendar_year_returns_fn = calendar_year_returns

    chart = QChart()
    _style_chart(chart)

    strat_years = calendar_year_returns_fn(strategy)
    bench_years = (
        calendar_year_returns_fn(benchmark)
        if benchmark is not None and not benchmark.empty
        else pd.Series(dtype=float)
    )
    years = sorted(set(strat_years.index.astype(int).tolist()) | set(bench_years.index.astype(int).tolist()))
    if not years:
        return chart

    strat_set = QBarSet("Strategie")
    strat_set.setColor(QColor(COLOR_STRATEGY))
    bench_set = QBarSet(bench_label)
    bench_set.setColor(QColor(COLOR_BENCH_BAR))
    for year in years:
        strat_set.append(float(strat_years.get(year, float("nan"))) * 100.0)
        if not bench_years.empty:
            bench_set.append(float(bench_years.get(year, float("nan"))) * 100.0)

    series = QBarSeries()
    series.append(strat_set)
    if not bench_years.empty:
        series.append(bench_set)
    chart.addSeries(series)

    axis_x = QBarCategoryAxis()
    axis_x.append([str(y) for y in years])
    _style_category_axis(axis_x)
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)

    axis_y = QValueAxis()
    axis_y.setTitleText("Rendite %")
    axis_y.setLabelFormat("%.0f")
    _style_value_axis(axis_y, title="Rendite %")
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_y)

    all_vals = [float(strat_years.get(y, 0.0)) * 100.0 for y in years]
    if not bench_years.empty:
        all_vals += [float(bench_years.get(y, 0.0)) * 100.0 for y in years]
    y_min = min(all_vals + [0.0])
    y_max = max(all_vals + [0.0])
    pad = max((y_max - y_min) * 0.12, 2.0)
    axis_y.setRange(y_min - pad, y_max + pad)
    return chart


def build_sector_chart(sector: pd.Series):
    from PySide6.QtCharts import QBarCategoryAxis, QBarSet, QChart, QHorizontalBarSeries, QValueAxis
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    chart = QChart()
    _style_chart(chart)
    if sector.empty:
        return chart

    top = sector.head(8)
    labels = [str(x)[:22] for x in reversed(top.index.tolist())]
    values = (top.values[::-1] * 100.0).tolist()

    bar_set = QBarSet("Gewicht")
    bar_set.setColor(QColor(COLOR_STRATEGY))
    for v in values:
        bar_set.append(float(v))

    series = QHorizontalBarSeries()
    series.append(bar_set)
    chart.addSeries(series)

    axis_y = QBarCategoryAxis()
    axis_y.append(labels)
    _style_category_axis(axis_y)
    chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(axis_y)

    axis_x = QValueAxis()
    axis_x.setTitleText("Gewicht %")
    axis_x.setLabelFormat("%.0f")
    _style_value_axis(axis_x, title="Gewicht %")
    chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(axis_x)

    x_max = max(values) if values else 1.0
    axis_x.setRange(0.0, x_max * 1.12)
    return chart


class _ChartZoomFilter:
    """Double-click resets chart zoom."""

    def __init__(self, chart_view) -> None:
        from PySide6.QtCore import QObject

        class _Filter(QObject):
            def __init__(self, view) -> None:
                super().__init__()
                self._view = view

            def eventFilter(self, watched, event) -> bool:
                from PySide6.QtCore import QEvent

                if event.type() == QEvent.Type.MouseButtonDblClick:
                    chart = self._view.chart()
                    if chart is not None:
                        chart.zoomReset()
                    return True
                return False

        self._filter = _Filter(chart_view)
        chart_view.viewport().installEventFilter(self._filter)


class QtResultChartPanel:
    """One result chart panel: native QChartView with message fallback."""

    def __init__(self, panel_key: str, parent=None) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

        self.panel_key = panel_key
        self._root = QWidget(parent)
        layout = QVBoxLayout(self._root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._message = QLabel("Lade …")
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._message.setStyleSheet("background-color: #ffffff; color: #605e5c;")
        self._message.setMinimumHeight(300)
        self._stack.addWidget(self._message)

        self._chart_view = None
        if qt_charts_available():
            from PySide6.QtCharts import QChartView
            from PySide6.QtGui import QPainter

            self._chart_view = QChartView()
            self._chart_view.setMinimumHeight(300)
            self._chart_view.setStyleSheet("background-color: #ffffff; border: none;")
            self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._chart_view.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            self._chart_view.setRubberBand(QChartView.RubberBand.RectangleRubberBand)
            _ChartZoomFilter(self._chart_view)
            self._stack.addWidget(self._chart_view)

        layout.addWidget(self._stack)
        self.last_fill_ok = True

    @property
    def widget(self):
        return self._root

    def show_message(self, text: str) -> None:
        self._message.setText(text)
        self._stack.setCurrentWidget(self._message)
        self.last_fill_ok = False

    def _present_chart(self, chart) -> bool:
        if self._chart_view is None:
            self.show_message("Qt Charts nicht verfügbar.")
            return False
        self._chart_view.setChart(chart)
        self._stack.setCurrentWidget(self._chart_view)
        self.last_fill_ok = chart.series()
        return bool(self.last_fill_ok)

    def show_equity(
        self,
        strategy: pd.Series,
        benchmark: Optional[pd.Series],
        *,
        bench_label: str = "Benchmark",
    ) -> bool:
        if strategy.empty or len(strategy.dropna()) < 10:
            self.show_message("Zu wenig Performance-Daten.")
            return False
        return self._present_chart(build_equity_chart(strategy, benchmark, bench_label=bench_label))

    def show_annual(
        self,
        strategy: pd.Series,
        benchmark: Optional[pd.Series],
        *,
        bench_label: str = "Benchmark",
    ) -> bool:
        if strategy.empty:
            self.show_message("Keine Jahresrenditen.")
            return False
        return self._present_chart(build_annual_chart(strategy, benchmark, bench_label=bench_label))

    def show_sector(self, sector: pd.Series) -> bool:
        if sector.empty:
            self.show_message("Keine Sektordaten.")
            return False
        return self._present_chart(build_sector_chart(sector))

    def clear(self) -> None:
        self.show_message("")


def render_pdf_chart_pngs(
    strategy: pd.Series,
    benchmark: Optional[pd.Series],
    sector: pd.Series,
    *,
    bench_label: str = "Benchmark",
    width_px: int = 640,
    height_px: int = 420,
) -> Dict[str, bytes]:
    """High-res PNGs for PDF export (matplotlib, offline)."""
    from aa_chart_render import render_result_panels_sized

    sizes = {
        "equity": (width_px, height_px),
        "annual": (width_px, height_px),
        "sector": (width_px, height_px),
    }
    charts, _ = render_result_panels_sized(strategy, benchmark, sector, sizes, bench_label=bench_label)
    return charts


def update_result_chart_panels(
    panels: Dict[str, QtResultChartPanel],
    ctx: Dict[str, Any],
) -> None:
    """Push result context into native chart panels."""
    strategy = ctx.get("strategy_returns")
    benchmark = ctx.get("benchmark_returns")
    sectors = ctx.get("sector_weights")
    bench_label = str(ctx.get("bench_label") or "Benchmark")

    equity = panels.get("equity")
    if equity is not None:
        if strategy is not None and not getattr(strategy, "empty", True):
            equity.show_equity(strategy, benchmark, bench_label=bench_label)
        else:
            equity.show_message("Keine Performance-Daten.")

    annual = panels.get("annual")
    if annual is not None:
        if strategy is not None and not getattr(strategy, "empty", True):
            annual.show_annual(strategy, benchmark, bench_label=bench_label)
        else:
            annual.show_message("Keine Jahresrenditen.")

    sector_panel = panels.get("sector")
    if sector_panel is not None:
        if sectors is not None and not getattr(sectors, "empty", True):
            sector_panel.show_sector(sectors)
        else:
            sector_panel.show_message("Keine Sektordaten.")
