"""Portfolio comparison view — charts, timeline, equity, PDF (R1)."""

from __future__ import annotations



from typing import TYPE_CHECKING



from PySide6.QtCore import Qt

from PySide6.QtGui import QPixmap

from PySide6.QtWidgets import (

    QHBoxLayout,

    QLabel,

    QPushButton,

    QScrollArea,

    QTableWidget,

    QTableWidgetItem,

    QVBoxLayout,

    QWidget,

)



from analytics.human_vs_base_comparison import (

    compare_human_vs_base,

    export_comparison_pdf,

    render_comparison_dashboard_png,

    write_comparison_evidence,

)

from ui.interactive_cockpit.button_roles import ROLE_PRIMARY, ROLE_SECONDARY, set_button_role

from ui.interactive_cockpit.cockpit_theme import INFO_PANEL



if TYPE_CHECKING:

    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow





def build_portfolio_comparison_view(win: "InteractiveCockpitWindow") -> QWidget:

    outer = QWidget()

    outer_lay = QVBoxLayout(outer)

    outer_lay.setContentsMargins(0, 0, 0, 0)



    scroll = QScrollArea()

    scroll.setWidgetResizable(True)

    scroll.setFrameShape(QScrollArea.Shape.NoFrame)

    content = QWidget()

    lay = QVBoxLayout(content)



    lay.addWidget(QLabel("<h2>Portfolio-Vergleich</h2>"))

    lay.addWidget(

        QLabel(

            "Vergleicht Ihr echtes Trading-212-Portfolio mit dem vorgeschlagenen Basisportfolio "

            "(Champion-Referenz, 500-EUR-Konfiguration). Allokation, Drift, Wertkurve und "

            "Ereignis-Timeline — read-only, keine Orders."

        )

    )



    win._comparison_summary = QLabel()

    win._comparison_summary.setWordWrap(True)

    win._comparison_summary.setStyleSheet(INFO_PANEL)

    lay.addWidget(win._comparison_summary)



    btn_row = QHBoxLayout()

    refresh = QPushButton("Vergleich aktualisieren")

    set_button_role(refresh, ROLE_PRIMARY)

    refresh.clicked.connect(lambda: refresh_portfolio_comparison(win, force_sync=True))

    export_btn = QPushButton("JSON-Report speichern")

    set_button_role(export_btn, ROLE_SECONDARY)

    export_btn.clicked.connect(lambda: refresh_portfolio_comparison(win, force_sync=True, save_report=True))

    pdf_btn = QPushButton("PDF exportieren")

    set_button_role(pdf_btn, ROLE_SECONDARY)

    pdf_btn.clicked.connect(lambda: refresh_portfolio_comparison(win, force_sync=True, export_pdf=True))

    btn_row.addWidget(refresh)

    btn_row.addWidget(export_btn)

    btn_row.addWidget(pdf_btn)

    btn_row.addStretch()

    lay.addLayout(btn_row)



    win._comparison_chart = QLabel("Dashboard wird nach Aktualisierung geladen …")

    win._comparison_chart.setAlignment(Qt.AlignmentFlag.AlignCenter)

    win._comparison_chart.setMinimumHeight(520)

    lay.addWidget(win._comparison_chart)



    lay.addWidget(QLabel("<b>Symbol-Drift</b>"))

    win._comparison_table = QTableWidget(0, 5)

    win._comparison_table.setHorizontalHeaderLabels(

        ["Symbol", "Basis %", "Ihr %", "Drift %", "Hinweis"]

    )

    lay.addWidget(win._comparison_table)



    lay.addWidget(QLabel("<b>Ereignisse (Historie + Positionen)</b>"))

    win._comparison_trades_table = QTableWidget(0, 4)

    win._comparison_trades_table.setHorizontalHeaderLabels(["Datum", "Symbol", "Art", "Quelle"])

    lay.addWidget(win._comparison_trades_table)



    scroll.setWidget(content)

    outer_lay.addWidget(scroll)

    return outer





def refresh_portfolio_comparison(

    win: "InteractiveCockpitWindow",

    *,

    force_sync: bool = False,

    save_report: bool = False,

    export_pdf: bool = False,

) -> None:

    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

    from integrations.trading212.t212_readonly_trade_history_sync import sync_live_readonly_trade_history



    if force_sync:

        try:

            sync_readonly_account(win.root, force=True)

            sync_live_readonly_trade_history(win.root)

            win.refresh_state(full=False)

        except Exception as exc:

            win._comparison_summary.setText(f"Sync fehlgeschlagen: {exc}")

            return



    broker = (win.state or {}).get("broker") or {}

    report = compare_human_vs_base(win.root, broker)

    chart_path = win.root / "evidence/portfolio_comparison_dashboard.png"

    ok_chart, chart_msg = render_comparison_dashboard_png(report, chart_path)



    if ok_chart and chart_path.is_file():

        pix = QPixmap(str(chart_path))

        if not pix.isNull():

            win._comparison_chart.setPixmap(

                pix.scaled(920, 500, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

            )

        else:

            win._comparison_chart.setText("Dashboard konnte nicht geladen werden.")

    else:

        win._comparison_chart.setText(f"Kein Dashboard: {chart_msg}")



    metrics = report.get("metrics") or {}

    if report.get("status") != "OK":

        win._comparison_summary.setText(str(report.get("reason") or report.get("status")))

        win._comparison_table.setRowCount(0)

        win._comparison_trades_table.setRowCount(0)

        return



    equity_n = metrics.get("equity_point_count", 0)

    trade_n = metrics.get("trade_event_count", 0)

    win._comparison_summary.setText(

        f"{metrics.get('interpretation_de', '')}\n\n"

        f"Drift (L1): {metrics.get('allocation_drift_l1_pct')} % | "

        f"Cash: {metrics.get('cash_weight_human_pct')} % | "

        f"Kurvenpunkte: {equity_n} | Ereignisse: {trade_n} | "

        f"Basis nicht gehalten: {', '.join(metrics.get('symbols_in_base_not_held') or []) or '—'}"

    )



    rows = report.get("rows") or []

    win._comparison_table.setRowCount(len(rows))

    for r, row in enumerate(rows):

        hint = ""

        if row.get("in_base_only"):

            hint = "nur Basis"

        elif row.get("in_human_only"):

            hint = "nur Sie"

        for c, v in enumerate(

            [

                row.get("symbol"),

                f"{row.get('base_weight_pct', 0):.1f}",

                f"{row.get('human_weight_pct', 0):.1f}",

                f"{row.get('drift_pct', 0):+.1f}",

                hint,

            ]

        ):

            win._comparison_table.setItem(r, c, QTableWidgetItem(str(v)))



    events = (report.get("trade_timeline") or {}).get("events") or []

    win._comparison_trades_table.setRowCount(len(events))

    for r, ev in enumerate(events):

        for c, v in enumerate(

            [

                ev.get("date"),

                ev.get("symbol"),

                ev.get("side"),

                ev.get("note_de") or ev.get("source"),

            ]

        ):

            win._comparison_trades_table.setItem(r, c, QTableWidgetItem(str(v)))



    extra = ""

    if save_report:

        path = write_comparison_evidence(win.root, report)

        extra += f"\n\nJSON: {path}"

    if export_pdf:

        pdf_path = win.root / "evidence/portfolio_comparison_report.pdf"

        ok_pdf, pdf_msg = export_comparison_pdf(report, pdf_path)

        extra += f"\n\nPDF: {pdf_msg}" if ok_pdf else f"\n\nPDF fehlgeschlagen: {pdf_msg}"

    if extra:

        win._comparison_summary.setText(win._comparison_summary.text() + extra)

