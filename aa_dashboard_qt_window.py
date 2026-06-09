from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from time import monotonic
from typing import Any, Dict, Optional, Tuple

from aa_dashboard_core import BACKTEST_PIPELINE, LAUNCHER_STEPS, DashboardCore
from aa_version import APP_TITLE


def _resolve_current_step(
    steps: tuple[tuple[str, str], ...],
    status_map: dict[str, str],
) -> tuple[int, int, str]:
    """Return (index, total, label) for the active or next pending step."""
    total = len(steps)
    if total == 0:
        return 0, 0, ""
    for i, (key, label) in enumerate(steps, start=1):
        if status_map.get(key) == "active":
            return i, total, label
    for i, (key, label) in enumerate(steps, start=1):
        if status_map.get(key, "pending") == "pending":
            return i, total, label
    _key, label = steps[-1]
    return total, total, label


def _fmt_seconds(seconds: float) -> str:
    seconds = max(int(seconds), 0)
    h, rem = divmod(seconds, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


class AppSession:
    """Shared Qt session for launcher + backtest in one window."""

    _instance: Optional["AppSession"] = None
    PAINT_INTERVAL_MS = 100

    def __init__(self) -> None:
        from PySide6.QtWidgets import QApplication

        self.app = QApplication.instance() or QApplication(sys.argv)
        from aa_dashboard_qt import configure_native_app

        configure_native_app(self.app)
        self._early_win = None
        self._splash = self._create_splash()
        if self._splash is not None:
            self.app.processEvents()
        from aa_qt_render import bootstrap_qt_native_windows

        bootstrap_qt_native_windows()
        from PySide6.QtCore import QTimer

        self.window = UnifiedMarktanalyseWindow()
        self._install_drag_pause_filter()
        self._process_events()
        self.timer = QTimer(self.window.widget)
        self.timer.setInterval(self.PAINT_INTERVAL_MS)
        self.timer.timeout.connect(self._tick)
        self._sync_fn = None
        self._dirty = True
        self._ui_sync_paused = False
        self._install_drag_pause_filter()

    def _install_drag_pause_filter(self) -> None:
        from PySide6.QtCore import QEvent, QObject, QTimer

        session = self

        class _DragPauseFilter(QObject):
            def __init__(self) -> None:
                super().__init__()
                self._resume = QTimer()
                self._resume.setSingleShot(True)
                self._resume.setInterval(180)
                self._resume.timeout.connect(session._resume_ui_sync)

            def eventFilter(self, watched, event) -> bool:  # noqa: N802
                t = event.type()
                if t in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.NonClientAreaMouseMove):
                    session._pause_ui_sync()
                elif t in (
                    QEvent.Type.MouseButtonRelease,
                    QEvent.Type.NonClientAreaMouseButtonRelease,
                    QEvent.Type.Leave,
                ):
                    self._resume.start()
                return False

        filt = _DragPauseFilter()
        self._win_filter = filt
        self.window._win.installEventFilter(filt)

    def _pause_ui_sync(self) -> None:
        self._ui_sync_paused = True

    def _resume_ui_sync(self) -> None:
        self._ui_sync_paused = False
        self.mark_dirty()

    @classmethod
    def get(cls) -> "AppSession":
        if cls._instance is None:
            cls._instance = AppSession()
        return cls._instance

    def mark_dirty(self) -> None:
        self._dirty = True

    def _process_events(self, *, light: bool = False) -> None:
        from PySide6.QtCore import QEventLoop

        flags = QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents if light else QEventLoop.ProcessEventsFlag.AllEvents
        self.app.processEvents(flags)

    @staticmethod
    def _create_splash():
        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QColor, QFont, QPixmap
            from PySide6.QtWidgets import QSplashScreen

            pix = QPixmap(520, 140)
            pix.fill(QColor("#0078d4"))
            splash = QSplashScreen(pix)
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            splash.setFont(font)
            splash.showMessage(
                f"{APP_TITLE} startet …\n\nBitte warten, Fenster wird vorbereitet.",
                Qt.AlignmentFlag.AlignCenter,
                QColor("#ffffff"),
            )
            splash.show()
            return splash
        except Exception:
            return None

    def start(self, sync_fn) -> None:
        self._sync_fn = sync_fn
        self._dirty = True
        self.window.show()
        self.timer.start()
        self.flush(force=True)
        self._process_events()
        if self._splash is not None:
            self._splash.finish(self.window.widget)
            self._splash = None
        self.window.show()
        self._process_events()

    def stop_timer(self) -> None:
        self.timer.stop()

    def flush(self, *, force: bool = False) -> None:
        if self._ui_sync_paused and not force:
            return
        if self._sync_fn is not None:
            self._sync_fn(force=force)
        self._process_events(light=not force)

    def _tick(self) -> None:
        if self._sync_fn is None or self._ui_sync_paused:
            return
        try:
            if self._dirty:
                self._sync_fn(force=False)
                self._dirty = False
            else:
                self._sync_fn(heartbeat=True)
        except Exception:
            pass
        try:
            self.window._animate_progress()
        except Exception:
            pass
        self._process_events(light=True)


class UnifiedMarktanalyseWindow:
    """Single native window: setup, backtest progress, and results."""

    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QMainWindow,
            QPlainTextEdit,
            QProgressBar,
            QPushButton,
            QStackedWidget,
            QVBoxLayout,
            QWidget,
        )

        self._mode = "launcher"
        self._out_dir = ""
        self.tick = lambda: None

        self._win = QMainWindow()
        from aa_version import APP_SUBTITLE, APP_TITLE

        self._win.setWindowTitle(APP_TITLE)
        self._win.setMinimumSize(900, 620)
        self._win.resize(1040, 720)
        try:
            from PySide6.QtCore import Qt

            self._win.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        except Exception:
            pass

        from aa_qt_render import (
            WIN11_TEXT,
            WIN11_TEXT_SECONDARY,
            apply_win11_surface,
            apply_window_icon,
            style_native_button,
            style_native_groupbox,
            style_native_line_edit,
            style_native_table,
            style_native_progress_bar,
            style_time_panel,
            time_value_font,
            win11_ui_font,
        )

        apply_window_icon(self._win)

        central = QWidget()
        apply_win11_surface(central, kind="window")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(14)

        self._header = QLabel(APP_TITLE)
        header_font = win11_ui_font(size=28, semibold=True, display=True)
        if header_font is not None:
            self._header.setFont(header_font)
        outer.addWidget(self._header)

        self._subtitle = QLabel(APP_SUBTITLE)
        from aa_qt_render import apply_native_label_style

        sub_font = win11_ui_font(size=11)
        if sub_font is not None:
            self._subtitle.setFont(sub_font)
        apply_native_label_style(self._subtitle, color=WIN11_TEXT_SECONDARY)
        outer.addWidget(self._subtitle)

        self._health_badge = QLabel("")
        health_font = win11_ui_font(size=10, semibold=True)
        if health_font is not None:
            self._health_badge.setFont(health_font)
        apply_native_label_style(self._health_badge, color=WIN11_TEXT_SECONDARY)
        outer.addWidget(self._health_badge)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        outer.addWidget(line)

        self._stack = QStackedWidget()
        self._progress_page = QWidget()
        progress_layout = QVBoxLayout(self._progress_page)
        progress_layout.setContentsMargins(0, 0, 0, 0)

        step_box = QGroupBox("Fortschritt")
        apply_win11_surface(step_box, kind="card")
        style_native_groupbox(step_box)
        step_layout = QVBoxLayout(step_box)
        step_layout.setSpacing(8)

        self._step_counter = QLabel("Schritt 1 von 1")
        counter_font = win11_ui_font(size=9)
        if counter_font is not None:
            self._step_counter.setFont(counter_font)
        apply_native_label_style(self._step_counter, color=WIN11_TEXT_SECONDARY)
        step_layout.addWidget(self._step_counter)

        self._step_title = QLabel("Initialisierung …")
        title_font = win11_ui_font(size=14, semibold=True)
        if title_font is not None:
            self._step_title.setFont(title_font)
        apply_native_label_style(self._step_title, color=WIN11_TEXT, bold=False)
        self._step_title.setWordWrap(True)
        step_layout.addWidget(self._step_title)

        self._step_detail = QLabel("")
        detail_font = win11_ui_font(size=10)
        if detail_font is not None:
            self._step_detail.setFont(detail_font)
        self._step_detail.setWordWrap(True)
        apply_native_label_style(self._step_detail, color=WIN11_TEXT_SECONDARY)
        step_layout.addWidget(self._step_detail)

        progress_layout.addWidget(step_box)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        style_native_progress_bar(self._progress)
        progress_layout.addWidget(self._progress)

        time_frame = QFrame()
        time_frame.setObjectName("timePanel")
        style_time_panel(time_frame)
        time_layout = QHBoxLayout(time_frame)
        time_layout.setContentsMargins(10, 6, 10, 6)
        time_layout.setSpacing(12)

        def _time_pair(caption: str, *, align_end: bool = False) -> QLabel:
            row = QHBoxLayout()
            row.setSpacing(6)
            cap = QLabel(f"{caption}:")
            cap_font = win11_ui_font(size=9)
            if cap_font is not None:
                cap.setFont(cap_font)
            apply_native_label_style(cap, color=WIN11_TEXT_SECONDARY)
            val = QLabel("00:00:00")
            val_font = time_value_font(size=9)
            if val_font is not None:
                val.setFont(val_font)
            apply_native_label_style(val, color=WIN11_TEXT)
            if align_end:
                row.addStretch(1)
            row.addWidget(cap)
            row.addWidget(val)
            if not align_end:
                row.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(row)
            time_layout.addWidget(wrap, stretch=1)
            return val

        self._time_elapsed = _time_pair("Verstrichen")
        self._time_remaining = _time_pair("Verbleibend", align_end=True)
        progress_layout.addWidget(time_frame)

        log_box = QGroupBox("Meldungen")
        apply_win11_surface(log_box, kind="card")
        style_native_groupbox(log_box)
        log_layout = QVBoxLayout(log_box)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(500)
        apply_win11_surface(self._log, kind="log")
        log_font = win11_ui_font(size=10)
        if log_font is not None:
            self._log.setFont(log_font)
        log_layout.addWidget(self._log)
        progress_layout.addWidget(log_box, stretch=1)

        btn_row = QHBoxLayout()
        self._cancel_btn = QPushButton("Abbrechen")
        style_native_button(self._cancel_btn)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addStretch(1)
        btn_row.addWidget(self._cancel_btn)
        progress_layout.addLayout(btn_row)

        self._result_page = QWidget()
        result_layout = QVBoxLayout(self._result_page)
        result_layout.setSpacing(12)
        self._result_title = QLabel("Analyse abgeschlossen")
        result_font = win11_ui_font(size=16, semibold=True, display=True)
        if result_font is not None:
            self._result_title.setFont(result_font)
        result_layout.addWidget(self._result_title)

        self._result_context_label = QLabel("")
        ctx_font = win11_ui_font(size=10)
        if ctx_font is not None:
            self._result_context_label.setFont(ctx_font)
        self._result_context_label.setWordWrap(True)
        apply_native_label_style(self._result_context_label, color=WIN11_TEXT_SECONDARY)
        result_layout.addWidget(self._result_context_label)

        self._model_status_label = QLabel("")
        model_font = win11_ui_font(size=10)
        if model_font is not None:
            self._model_status_label.setFont(model_font)
        self._model_status_label.setWordWrap(True)
        apply_native_label_style(self._model_status_label, color=WIN11_TEXT_SECONDARY)
        result_layout.addWidget(self._model_status_label)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        metrics_box = QGroupBox("Kennzahlen")
        apply_win11_surface(metrics_box, kind="card")
        style_native_groupbox(metrics_box)
        metrics_layout = QVBoxLayout(metrics_box)
        from PySide6.QtWidgets import QTextBrowser

        self._result_metrics = QTextBrowser()
        self._result_metrics.setOpenExternalLinks(False)
        self._result_metrics.setFrameShape(QFrame.Shape.NoFrame)
        self._result_metrics.setMinimumHeight(160)
        self._result_metrics.setMaximumHeight(220)
        metrics_layout.addWidget(self._result_metrics)
        bottom_row.addWidget(metrics_box, stretch=2)

        invest_box = QGroupBox("Investition")
        apply_win11_surface(invest_box, kind="card")
        style_native_groupbox(invest_box)
        invest_layout = QVBoxLayout(invest_box)
        invest_layout.setSpacing(10)

        invest_hint = QLabel(
            "Betrag wird vollständig auf die Modell-Positionen verteilt "
            "(inkl. Benchmark-ETF, falls vom Modell vorgesehen)."
        )
        hint_font = win11_ui_font(size=10)
        if hint_font is not None:
            invest_hint.setFont(hint_font)
        invest_hint.setWordWrap(True)
        invest_layout.addWidget(invest_hint)

        amount_row = QHBoxLayout()
        amount_lbl = QLabel("Betrag (EUR)")
        if hint_font is not None:
            amount_lbl.setFont(hint_font)
        amount_row.addWidget(amount_lbl)
        from PySide6.QtGui import QDoubleValidator
        from PySide6.QtWidgets import QLineEdit

        self._invest_amount = QLineEdit("10000")
        self._invest_amount.setValidator(QDoubleValidator(0.0, 1e12, 2))
        self._invest_amount.setPlaceholderText("z. B. 10000")
        style_native_line_edit(self._invest_amount)
        self._invest_amount.editingFinished.connect(self._refresh_portfolio_table)
        amount_row.addWidget(self._invest_amount, stretch=1)
        invest_layout.addLayout(amount_row)

        self._fee_hint = QLabel("")
        if hint_font is not None:
            self._fee_hint.setFont(hint_font)
        self._fee_hint.setWordWrap(True)
        apply_native_label_style(self._fee_hint, color=WIN11_TEXT_SECONDARY)
        invest_layout.addWidget(self._fee_hint)

        self._portfolio_hint = QLabel("")
        if hint_font is not None:
            self._portfolio_hint.setFont(hint_font)
        self._portfolio_hint.setWordWrap(True)
        apply_native_label_style(self._portfolio_hint, color=WIN11_TEXT_SECONDARY)
        invest_layout.addWidget(self._portfolio_hint)

        self._portfolio_summary = QLabel("")
        if hint_font is not None:
            self._portfolio_summary.setFont(hint_font)
        self._portfolio_summary.setWordWrap(True)
        invest_layout.addWidget(self._portfolio_summary)
        invest_layout.addStretch(1)
        bottom_row.addWidget(invest_box, stretch=2)
        result_layout.addLayout(bottom_row)

        from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

        self._portfolio_table = QTableWidget(0, 5)
        self._portfolio_table.setHorizontalHeaderLabels(["Ticker", "Sektor", "Gewicht %", "Stück", "Betrag"])
        self._portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._portfolio_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        style_native_table(self._portfolio_table)
        self._portfolio_table.setMinimumHeight(200)
        result_layout.addWidget(self._portfolio_table, stretch=2)

        chart_box = QGroupBox("Ergebnisse")
        self._charts_box = chart_box
        apply_win11_surface(chart_box, kind="card")
        style_native_groupbox(chart_box)
        charts_row = QHBoxLayout(chart_box)
        charts_row.setContentsMargins(6, 10, 6, 6)
        charts_row.setSpacing(8)
        from aa_qt_charts import QtResultChartPanel

        self._chart_views: Dict[str, QtResultChartPanel] = {}
        panel_titles = {
            "equity": "Kumulierte Performance",
            "annual": "Jahresvergleich",
            "sector": "Sektor-Allokation",
        }

        def _add_chart_panel(key: str) -> None:
            panel = QWidget()
            panel.setStyleSheet("background-color: #ffffff; border-radius: 6px;")
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(2, 2, 2, 2)
            panel_layout.setSpacing(0)
            title_lbl = QLabel(panel_titles.get(key, key))
            tfont = win11_ui_font(size=10, semibold=True)
            if tfont is not None:
                title_lbl.setFont(tfont)
            apply_native_label_style(title_lbl, color=WIN11_TEXT)
            title_lbl.setContentsMargins(6, 4, 6, 2)
            panel_layout.addWidget(title_lbl)
            view = QtResultChartPanel(key)
            self._chart_views[key] = view
            panel_layout.addWidget(view.widget, stretch=1)
            charts_row.addWidget(panel, stretch=1)

        _add_chart_panel("equity")
        _add_chart_panel("annual")
        _add_chart_panel("sector")
        self._chart_view = self._chart_views["equity"]
        result_layout.addWidget(chart_box, stretch=4)

        self._result_ctx_data: Dict[str, Any] = {}
        self._deferred_startups: list = []
        self._result_portfolio = None
        self._portfolio_rows: list = []

        self._result_disclaimer = QLabel("")
        disc_font = win11_ui_font(size=9)
        if disc_font is not None:
            self._result_disclaimer.setFont(disc_font)
        self._result_disclaimer.setWordWrap(True)
        apply_native_label_style(self._result_disclaimer, color=WIN11_TEXT_SECONDARY)
        result_layout.addWidget(self._result_disclaimer)

        result_btn_row = QHBoxLayout()
        result_btn_row.setSpacing(10)
        self._export_btn = QPushButton("Portfolio als CSV speichern")
        self._export_btn.clicked.connect(self._export_portfolio_csv)
        self._pdf_btn = QPushButton("PDF-Report speichern")
        self._pdf_btn.clicked.connect(self._export_result_pdf)
        self._wizard_btn = QPushButton("Einstellungen …")
        self._wizard_btn.clicked.connect(self._open_settings_wizard)
        self._open_btn = QPushButton("Ausgabeordner öffnen")
        self._open_btn.clicked.connect(self._open_output_dir)
        self._close_btn = QPushButton("Schließen")
        style_native_button(self._close_btn, primary=True)
        self._close_btn.clicked.connect(self._win.close)
        for btn in (self._export_btn, self._pdf_btn, self._wizard_btn, self._open_btn):
            style_native_button(btn)
        result_btn_row.addWidget(self._export_btn)
        result_btn_row.addWidget(self._pdf_btn)
        result_btn_row.addWidget(self._wizard_btn)
        result_btn_row.addWidget(self._open_btn)
        self._cockpit_btn = QPushButton("Decision Cockpit (Read-Only)")
        style_native_button(self._cockpit_btn)
        self._cockpit_btn.clicked.connect(self._show_decision_cockpit)
        result_btn_row.insertWidget(0, self._cockpit_btn)
        result_btn_row.addStretch(1)
        result_btn_row.addWidget(self._close_btn)
        result_layout.addLayout(result_btn_row)

        self._stack.addWidget(self._progress_page)
        self._stack.addWidget(self._result_page)
        self._cockpit_page = QWidget()
        self._cockpit_layout = QVBoxLayout(self._cockpit_page)
        self._cockpit_layout.setContentsMargins(0, 0, 0, 0)
        cockpit_hdr = QHBoxLayout()
        self._cockpit_banner = QLabel("READ-ONLY DECISION COCKPIT — NO LIVE TRADING — NO AUTO PROMOTION")
        self._cockpit_banner.setWordWrap(True)
        cockpit_hdr.addWidget(self._cockpit_banner)
        self._cockpit_back_btn = QPushButton("Zurück zum Ergebnis")
        style_native_button(self._cockpit_back_btn)
        self._cockpit_back_btn.clicked.connect(lambda: self._stack.setCurrentWidget(self._result_page))
        cockpit_hdr.addWidget(self._cockpit_back_btn)
        self._cockpit_layout.addLayout(cockpit_hdr)
        self._cockpit_host = QWidget()
        self._cockpit_layout.addWidget(self._cockpit_host, stretch=1)
        self._stack.addWidget(self._cockpit_page)
        outer.addWidget(self._stack, stretch=1)

        self._win.setCentralWidget(central)
        self.widget = self._win
        self._steps_def = LAUNCHER_STEPS
        self._log_lines_shown = 0
        self._last_step_key = ""
        self._last_step_counter = ""
        self._last_step_title = ""
        self._last_step_detail = ""
        self._last_pct = -1
        self._target_pct = 0
        self._display_pct = 0.0
        self._last_progress_fmt = ""

    def _on_cancel(self) -> None:
        from aa_cancellation import request_cancel

        request_cancel()
        self._step_title.setText("Abbruch angefordert …")
        self._step_detail.setText("Der Lauf wird beendet, sobald der aktuelle Schritt fertig ist.")
        self._cancel_btn.setEnabled(False)

    def _show_decision_cockpit(self) -> None:
        from PySide6.QtWidgets import QVBoxLayout

        from aa_decision_cockpit_gui import create_decision_cockpit_widget

        host = self._cockpit_host
        old = host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(create_decision_cockpit_widget(Path.cwd(), parent=host))
        self._stack.setCurrentWidget(self._cockpit_page)

    def _open_output_dir(self) -> None:
        path = self._out_dir
        if not path:
            return
        p = Path(path)
        if not p.is_dir():
            return
        if sys.platform == "win32":
            os.startfile(str(p.resolve()))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p.resolve())], check=False)
        else:
            subprocess.run(["xdg-open", str(p.resolve())], check=False)

    def set_mode(self, mode: str) -> None:
        if self._mode == mode:
            return
        self._mode = mode
        self._last_step_key = ""
        if mode == "launcher":
            self._subtitle.setText("Setup — Umgebung & Analyse")
            self._steps_def = LAUNCHER_STEPS
        else:
            self._subtitle.setText("Walk-forward Analyse läuft")
            self._steps_def = BACKTEST_PIPELINE

    def show(self) -> None:
        from aa_qt_render import apply_native_taskbar_icon

        self._maybe_show_first_run_hint()
        self._win.show()
        apply_native_taskbar_icon(self._win)
        self._win.raise_()
        self._win.activateWindow()

    def _animate_progress(self) -> None:
        target = float(self._target_pct)
        if abs(self._display_pct - target) < 0.4:
            if self._display_pct != target:
                self._display_pct = target
                self._progress.setValue(int(round(target)))
            return
        step = max((target - self._display_pct) * 0.38, 0.6)
        if target < self._display_pct:
            step = min((target - self._display_pct) * 0.38, -0.6)
        self._display_pct = max(0.0, min(100.0, self._display_pct + step))
        shown = int(round(self._display_pct))
        if shown != self._progress.value():
            self._progress.setValue(shown)

    def set_health_status(self, health: str, message: str = "") -> None:
        from aa_qt_render import WIN11_ERROR, WIN11_SUCCESS, WIN11_TEXT_SECONDARY, apply_native_label_style
        from aa_system_status import health_label

        key = str(health or "").upper()
        color = WIN11_TEXT_SECONDARY
        prefix = "●"
        if key == "OK":
            color = WIN11_SUCCESS
        elif key == "WARN":
            color = WIN11_TEXT_SECONDARY
        elif key == "ERROR":
            color = WIN11_ERROR
        text = f"{prefix} System: {health_label(key)}"
        if message:
            text = f"{text} — {message[:120]}"
        self._health_badge.setText(text)
        apply_native_label_style(self._health_badge, color=color, bold=(key != "OK"))

    def sync_launcher(self, core, *, force: bool = False, heartbeat: bool = False) -> None:
        if heartbeat:
            self._sync_time(core.started_at, core.eta_seconds)
            return
        if self._mode != "launcher":
            self.set_mode("launcher")
        self._apply_progress_sync(
            pct=core.progress_pct(),
            progress_fmt="%p%",
            started_at=core.started_at,
            eta_fn=core.eta_seconds,
            logs=core.logs,
            step_map={key: core._status.get(key, "pending") for key, _ in LAUNCHER_STEPS},
            detail=core.activity_line().strip(),
            force=force,
        )

    def sync_backtest(self, core: DashboardCore, *, force: bool = False, heartbeat: bool = False) -> None:
        if heartbeat:
            self._sync_time(core.started_at, core.eta_seconds)
            return
        if self._mode != "backtest":
            self.set_mode("backtest")
        self._out_dir = core.out_dir
        fmt = f"%p%  ({core._sub_completed}/{core._sub_total})" if core._sub_total > 1 else "%p%"
        detail = core.activity_line().strip()
        self._apply_progress_sync(
            pct=core.progress_pct(),
            progress_fmt=fmt,
            started_at=core.started_at,
            eta_fn=core.eta_seconds,
            logs=core.logs,
            step_map=core._pipeline_status,
            detail=detail,
            force=force,
        )
        if core.last_error:
            from aa_qt_render import WIN11_ERROR, apply_native_label_style

            apply_native_label_style(self._step_title, color=WIN11_ERROR, bold=True)

    def _apply_progress_sync(
        self,
        *,
        pct: int,
        progress_fmt: str,
        started_at: float,
        eta_fn,
        logs,
        step_map: dict,
        detail: str,
        force: bool,
    ) -> None:
        if force or pct != self._last_pct:
            self._target_pct = max(0, min(100, int(pct)))
            self._last_pct = pct
            if force:
                self._display_pct = float(self._target_pct)
                self._progress.setValue(self._target_pct)
        if force or progress_fmt != self._last_progress_fmt:
            self._progress.setFormat(progress_fmt)
            self._last_progress_fmt = progress_fmt
        self._sync_current_step(step_map, detail=detail, force=force)
        self._sync_time(started_at, eta_fn)
        prev_logs = self._log_lines_shown
        self._sync_logs(logs, force=force)
        if force or len(logs) > prev_logs:
            try:
                from aa_ui_pump import pump_ui

                pump_ui(force=False)
            except Exception:
                pass

    def _sync_current_step(self, status_map: dict, *, detail: str, force: bool = False) -> None:
        idx, total, title = _resolve_current_step(self._steps_def, status_map)
        step_key = self._steps_def[idx - 1][0] if idx > 0 else ""
        counter = f"Schritt {idx} von {total}" if total else ""
        detail = detail.strip()
        if detail == title:
            detail = ""

        if not force and step_key == self._last_step_key and counter == self._last_step_counter:
            if title == self._last_step_title and detail == self._last_step_detail:
                return

        self._last_step_key = step_key
        if counter != self._last_step_counter:
            self._step_counter.setText(counter)
            self._last_step_counter = counter
        if title != self._last_step_title:
            self._step_title.setText(title)
            self._last_step_title = title
        if detail != self._last_step_detail:
            self._last_step_detail = detail
            if detail:
                self._step_detail.setText(detail)
            else:
                self._step_detail.clear()

    def _sync_time(self, started_at: float, eta_fn) -> None:
        elapsed = monotonic() - started_at
        remaining = eta_fn(elapsed)
        elapsed_txt = _fmt_seconds(elapsed)
        if remaining is not None and remaining >= 0:
            remain_txt = f"~{_fmt_seconds(remaining)}"
        else:
            remain_txt = "—"
        if self._time_elapsed.text() != elapsed_txt:
            self._time_elapsed.setText(elapsed_txt)
        if self._time_remaining.text() != remain_txt:
            self._time_remaining.setText(remain_txt)

    def _sync_logs(self, logs, *, force: bool = False) -> None:
        if force and len(logs) < self._log_lines_shown:
            self._log.clear()
            self._log_lines_shown = 0
        if len(logs) == self._log_lines_shown:
            return
        if force and self._log_lines_shown == 0 and len(logs) > 8:
            self._log.setPlainText("\n".join(logs))
            self._log_lines_shown = len(logs)
        else:
            while self._log_lines_shown < len(logs):
                self._log.appendPlainText(logs[self._log_lines_shown])
                self._log_lines_shown += 1
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def _maybe_show_first_run_hint(self) -> None:
        if os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return
        if os.environ.get("AA_NONINTERACTIVE", "").strip().lower() in {"1", "true", "yes"}:
            return
        from aa_paths import project_root

        root = project_root()
        flag = root / ".marktanalyse_setup_hint"
        if flag.is_file():
            return
        try:
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(
                self._win,
                f"{APP_TITLE} — Erster Start",
                "Der erste vollständige Lauf kann 20–60 Minuten dauern (Daten, Backtest, Signal).\n\n"
                "Folgeläufe sind deutlich schneller dank Cache.\n\n"
                "Internetverbindung erforderlich. Log: marktanalyse_last_run.log",
            )
            flag.write_text("ok\n", encoding="utf-8")
        except Exception:
            pass

    def _export_result_pdf(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from aa_result_views import export_result_pdf

        if not self._portfolio_rows:
            QMessageBox.information(self._win, "PDF", "Kein Portfolio für PDF vorhanden.")
            return
        out = Path(self._out_dir) if self._out_dir else Path(".")
        try:
            amount = float(str(self._invest_amount.text()).replace(",", "."))
        except ValueError:
            amount = 0.0
        ctx = self._result_ctx_data
        path = out / f"marktanalyse_report_{ctx.get('signal_date', 'export')}.pdf".replace(":", "-")
        try:
            export_result_pdf(
                path,
                strategy_returns=ctx.get("strategy_returns"),
                benchmark_returns=ctx.get("benchmark_returns"),
                sector_weights=ctx.get("sector_weights"),
                bench_label=str(ctx.get("bench_label") or "Benchmark"),
                chart_png=ctx.get("chart_png") or b"",
                sector_png=ctx.get("sector_png") or b"",
                equity_chart_png=ctx.get("equity_chart_png") or b"",
                annual_chart_png=ctx.get("annual_chart_png") or b"",
                sector_chart_png=ctx.get("sector_chart_png") or b"",
                context_line=str(ctx.get("context_line", "")),
                metrics_summary=str(ctx.get("metrics_summary", "")),
                rows=self._portfolio_rows,
                amount=amount,
                fees=ctx.get("fees_estimate") or {},
                disclaimer=str(ctx.get("disclaimer", "")),
                rebalance_hint=str(ctx.get("rebalance_hint", "")),
            )
            QMessageBox.information(self._win, "PDF", f"Report gespeichert:\n{path.resolve()}")
        except Exception as exc:
            QMessageBox.warning(self._win, "PDF", f"Export fehlgeschlagen:\n{exc}")

    def _open_settings_wizard(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from aa_paths import project_root

        root = project_root()
        bat = root / "run_active_alpha_settings_wizard.bat"
        if not bat.is_file():
            QMessageBox.warning(self._win, "Einstellungen", f"Wizard nicht gefunden:\n{bat}")
            return
        try:
            import subprocess

            subprocess.Popen(
                ["cmd", "/c", "start", "", str(bat)],
                cwd=str(root),
                shell=False,
            )
            QMessageBox.information(
                self._win,
                "Einstellungen",
                "Der Einstellungs-Assistent wurde in einem neuen Fenster gestartet.\n"
                "Änderungen gelten ab dem nächsten Lauf.",
            )
        except Exception as exc:
            QMessageBox.warning(self._win, "Einstellungen", str(exc))

    def _export_portfolio_csv(self) -> None:
        from PySide6.QtWidgets import QMessageBox

        from aa_dashboard_result import export_portfolio_csv

        if not self._portfolio_rows:
            QMessageBox.information(self._win, "Export", "Kein Portfolio zum Speichern vorhanden.")
            return
        out = Path(self._out_dir) if self._out_dir else Path(".")
        try:
            amount = float(str(self._invest_amount.text()).replace(",", "."))
        except ValueError:
            amount = 0.0
        stamp = self._result_ctx_data.get("signal_date", "export")
        if stamp == "n/a":
            stamp = "export"
        path = out / f"mein_portfolio_{stamp}.csv"
        export_portfolio_csv(
            path,
            self._portfolio_rows,
            amount=amount,
            context_line=str(self._result_ctx_data.get("context_line", "")),
        )
        QMessageBox.information(self._win, "Export", f"Portfolio gespeichert:\n{path.resolve()}")

    def _refresh_portfolio_table(self) -> None:
        from PySide6.QtWidgets import QTableWidgetItem

        from aa_dashboard_result import scale_portfolio_rows

        portfolio = self._result_portfolio
        if portfolio is None or getattr(portfolio, "empty", True):
            self._portfolio_table.setRowCount(0)
            self._portfolio_summary.setText("")
            self._portfolio_rows = []
            self._export_btn.setEnabled(False)
            return
        try:
            amount = float(str(self._invest_amount.text()).replace(",", "."))
        except ValueError:
            amount = 0.0
        ctx = self._result_ctx_data
        rows, invested, cash = scale_portfolio_rows(
            portfolio,
            amount,
            prices_usd=ctx.get("prices_usd"),
            eurusd=ctx.get("eurusd"),
        )
        self._portfolio_rows = rows
        self._portfolio_table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            self._portfolio_table.setItem(i, 0, QTableWidgetItem(str(row["ticker"])))
            self._portfolio_table.setItem(i, 1, QTableWidgetItem(str(row["sector"])))
            self._portfolio_table.setItem(i, 2, QTableWidgetItem(f"{row['weight_pct']:.1f}"))
            self._portfolio_table.setItem(i, 3, QTableWidgetItem(str(row.get("shares", "—"))))
            self._portfolio_table.setItem(i, 4, QTableWidgetItem(f"{row['amount']:,.2f} €"))
        if rows:
            from aa_result_views import T212_MIN_ORDER_EUR, estimate_portfolio_fees

            fees = estimate_portfolio_fees(rows, prices_usd=ctx.get("prices_usd") or {}, eurusd=ctx.get("eurusd"))
            self._result_ctx_data["fees_estimate"] = fees
            fx_note = ""
            psrc = str(ctx.get("price_source", ""))
            if psrc == "cache":
                fx_note = " · Kurse aus lokalem Cache"
            elif psrc == "live" and ctx.get("eurusd"):
                fx_note = f" · Live-Kurse, EUR/USD {float(ctx['eurusd']):.4f}"
            elif not ctx.get("prices_usd"):
                fx_note = " · Kurse offline (Stückzahl geschätzt/fehlt)"
            cash_note = f" · Cash: {cash:,.2f} €" if cash > 0.01 else ""
            self._portfolio_summary.setText(
                f"{len(rows)} Positionen · Investiert: {invested:,.2f} € · "
                f"Gesamt: {amount:,.2f} €{cash_note}{fx_note}"
            )
            self._fee_hint.setText(
                f"T212-Mindestorder ~{T212_MIN_ORDER_EUR:.0f} € · "
                f"geschätzte Kosten (Käufe): {fees.get('total_cost_eur', 0.0):,.2f} €"
            )
        else:
            self._portfolio_summary.setText("Kein Portfolio verfügbar.")
            self._fee_hint.setText("")
        self._export_btn.setEnabled(bool(rows))
        self._pdf_btn.setEnabled(bool(rows))

    def _prepare_result_presentation(self) -> None:
        """Maximize window and lay out result page before chart sizing."""
        from PySide6.QtWidgets import QApplication

        self._win.setMinimumSize(980, 720)
        if not self._win.isMaximized():
            self._win.showMaximized()
        self._win.raise_()
        self._win.activateWindow()
        QApplication.processEvents()

    def _apply_result_context(self, ctx: Dict[str, Any]) -> None:
        self._result_ctx_data = ctx
        self._result_portfolio = ctx.get("portfolio")
        from aa_qt_charts import update_result_chart_panels

        analytical_ok = str(ctx.get("analytical_validity", "PASS")).upper() == "PASS"
        if analytical_ok:
            update_result_chart_panels(self._chart_views, ctx)
        else:
            msg = str(ctx.get("analytical_error") or "Gespeicherte Analyse ungültig")
            for view in getattr(self, "_chart_views", {}).values():
                view.show_message(msg)

        summary = ctx.get("metrics_summary") or ""
        metrics_html = ctx.get("metrics_html") or ""
        if metrics_html and analytical_ok:
            self._result_metrics.setHtml(metrics_html)
        else:
            self._result_metrics.setPlainText(summary)
        ctx_lines = [str(ctx.get("context_line") or "")]
        if ctx.get("rebalance_hint"):
            ctx_lines.append(str(ctx["rebalance_hint"]))
        self._result_context_label.setText("\n".join(line for line in ctx_lines if line))
        self._result_disclaimer.setText(ctx.get("disclaimer") or "")
        status_text = str(ctx.get("model_status_text") or "")
        if status_text:
            self._model_status_label.setText(status_text)
            integrity_key = str((ctx.get("model_status") or {}).get("integrity_status", "")).upper()
            if integrity_key != "PASS":
                apply_native_label_style(self._model_status_label, color=WIN11_ERROR, bold=True)
            else:
                apply_native_label_style(self._model_status_label, color=WIN11_TEXT_SECONDARY)
        else:
            self._model_status_label.setText("")
        from aa_version import APP_TITLE
        from aa_qt_render import WIN11_ERROR, WIN11_SUCCESS, apply_native_label_style

        if ctx.get("app_title"):
            if analytical_ok:
                self._result_title.setText("Analyse abgeschlossen")
                apply_native_label_style(self._result_title, color=WIN11_SUCCESS, bold=True)
                self._win.setWindowTitle(f"{APP_TITLE} — Ergebnis")
            else:
                self._result_title.setText("Analyse ungültig")
                apply_native_label_style(self._result_title, color=WIN11_ERROR, bold=True)
                self._win.setWindowTitle(f"{APP_TITLE} — ungültig")
            self._header.setText(APP_TITLE)

        source = ctx.get("portfolio_source") or ""
        if self._result_portfolio is not None and not getattr(self._result_portfolio, "empty", True):
            n = len(self._result_portfolio)
            self._portfolio_hint.setText(f"Zielportfolio ({source}, {n} Titel)" if source else f"Zielportfolio ({n} Titel)")
        else:
            self._portfolio_hint.setText(
                "Kein Zielportfolio gefunden. Bitte Analyse erneut ausführen (Modus: Signal)."
            )
        self._refresh_portfolio_table()

    def register_deferred_startup(self, fn) -> None:
        """Run after the result UI is visible (e.g. paper MTM in background)."""
        self._deferred_startups.append(fn)

    def _run_deferred_startups(self) -> None:
        import threading

        for fn in self._deferred_startups:
            threading.Thread(target=fn, name="deferred-startup", daemon=True).start()
        self._deferred_startups.clear()

    def _refresh_live_prices_async(self) -> None:
        """Fetch live FX/prices after cache-first startup display."""
        import threading

        out_dir = Path(self._out_dir) if self._out_dir else None
        portfolio = self._result_portfolio
        if out_dir is None or portfolio is None or getattr(portfolio, "empty", True):
            return

        def _worker() -> None:
            try:
                from aa_dashboard_result import fetch_fx_eurusd, fetch_last_prices_usd
                from aa_result_views import resolve_prices_usd

                tickers = portfolio["ticker"].astype(str).tolist()
                online = fetch_last_prices_usd(tickers)
                prices_usd, price_source = resolve_prices_usd(out_dir, tickers, online=online)
                eurusd = fetch_fx_eurusd()
                self._result_ctx_data["prices_usd"] = prices_usd
                self._result_ctx_data["price_source"] = price_source
                self._result_ctx_data["eurusd"] = eurusd
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self._refresh_portfolio_table)
            except Exception:
                pass

        threading.Thread(target=_worker, name="live-prices", daemon=True).start()

    def show_result(
        self,
        *,
        success: bool,
        out_dir: str,
        metrics: Dict[str, Any],
        signal_date: str = "n/a",
        output_files: Optional[list] = None,
        error: str = "",
    ) -> None:
        self._out_dir = out_dir
        self._stack.setCurrentWidget(self._result_page)
        self._cancel_btn.setEnabled(False)
        if success:
            self._result_title.setText("Analyse abgeschlossen")
            from aa_qt_render import WIN11_SUCCESS, apply_native_label_style

            apply_native_label_style(self._result_title, color=WIN11_SUCCESS, bold=True)
            try:
                from aa_system_status import read_system_status

                st = read_system_status(Path.cwd())
                if st.health and st.health != "unknown":
                    self.set_health_status(st.health, st.message)
            except Exception:
                pass
            from aa_version import APP_TITLE

            self._win.setWindowTitle(f"{APP_TITLE} — Ergebnis")
            for view in getattr(self, "_chart_views", {}).values():
                view.show_message("Lade Ergebnisse …")
            self._result_context_label.setText("Daten werden geladen …")
            from aa_dashboard_qt import pump_ui

            pump_ui(force=True)
            try:
                from aa_dashboard_result import load_result_context

                skip_png = os.environ.get("AA_SKIP_PNG_CHARTS", "1").strip().lower() not in {
                    "0",
                    "false",
                    "no",
                    "off",
                }
                cache_prices = os.environ.get("AA_STARTUP_CACHE_PRICES", "1").strip().lower() not in {
                    "0",
                    "false",
                    "no",
                    "off",
                }
                paper_rel = os.environ.get("AA_PAPER_MODEL_OUT_DIR", "").strip()
                paper_path = None
                if paper_rel:
                    paper_path = Path(paper_rel)
                    if not paper_path.is_absolute():
                        paper_path = Path.cwd() / paper_path
                out_path = Path(out_dir)
                if not out_path.is_absolute():
                    out_path = Path.cwd() / out_path
                ctx = load_result_context(
                    out_path,
                    metrics=metrics,
                    paper_dir=paper_path,
                    skip_chart_png=skip_png,
                    online_prices=not cache_prices,
                )
                self._apply_result_context(ctx)
                self._prepare_result_presentation()
                from PySide6.QtCore import QTimer

                QTimer.singleShot(80, self._run_deferred_startups)
                if cache_prices:
                    QTimer.singleShot(200, self._refresh_live_prices_async)
            except Exception as exc:
                self._prepare_result_presentation()
                self._chart_view.show_message(f"Ergebnis konnte nicht geladen werden: {exc}")
                self._result_metrics.setPlainText(f"Ausgabe: {out_dir}")
        else:
            self._prepare_result_presentation()
            self._result_title.setText("Analyse fehlgeschlagen")
            from aa_qt_render import WIN11_ERROR, apply_native_label_style

            apply_native_label_style(self._result_title, color=WIN11_ERROR, bold=True)
            self._win.setWindowTitle(f"{APP_TITLE} — Fehler")
            lines = [error or "Unbekannter Fehler", "", f"Ausgabe: {out_dir}"]
            for view in getattr(self, "_chart_views", {}).values():
                view.show_message("Analyse fehlgeschlagen")
            self._result_metrics.setPlainText("\n".join(lines))
            self._portfolio_table.setRowCount(0)
            self._portfolio_hint.setText("")
            self._portfolio_summary.setText("")
            self._result_context_label.setText("")
            self._result_disclaimer.setText("")
            self._export_btn.setEnabled(False)
            self._pdf_btn.setEnabled(False)
            self._fee_hint.setText("")
            for view in getattr(self, "_chart_views", {}).values():
                view.show_message("")
        self._open_btn.setEnabled(bool(out_dir) and Path(out_dir).is_dir())


# Backward-compatible aliases
MarktanalyseWindow = UnifiedMarktanalyseWindow
LauncherWindow = UnifiedMarktanalyseWindow
