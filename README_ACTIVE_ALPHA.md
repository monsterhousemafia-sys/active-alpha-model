# Active Alpha Model Package

Dieses Paket enthält den bereinigten Projektordner für das Active-Alpha-Modell.

## Wichtige Dateien

Siehe auch [OPS.md](OPS.md) für Marktanalyse.exe, Fast-Path und Ops-Refresh.

- `active_alpha_model.py` – Modell, Backtest, Signal-Generator, Reporting.
- `paper_trading_engine.py` – Paper-Trading-Engine.
- `active_alpha_control_center.py` – operative Kontrollschicht mit Status und Preflight.
- `check_active_alpha_core.py` – Konsistenzprüfung der Projektdateien.
- `build_sp500_membership_wikipedia.py` – Builder für `ticker_membership.csv`.
- `requirements_active_alpha.txt` – Python-Abhängigkeiten für die lokale `.venv`.
- `run_active_alpha_model.bat` – Backtest-/Signal-Lauf.
- `run_paper_trading.bat` – Paper-Rebalance.
- `run_active_alpha_control_center.bat` – Control-Center.

## Kapitaltrennung

Die Kapitalwerte sind bewusst getrennt:

- `AA_BACKTEST_CAPITAL` – Konto-/Ausführungskapital im Backtest.
- `AA_RESEARCH_BACKTEST_CAPITAL` – Kapital für strategische Capital-Curve-Policy im Backtest.
- `AA_PAPER_CAPITAL` – Start-/Fallbackkapital für Paper-Trading.

## Erster Start

1. Ordner entpacken.
2. Bei Bedarf `run_build_sp500_membership.bat` ausführen, falls `ticker_membership.csv` lokal fehlt.
3. `run_active_alpha_model.bat` starten.
4. Bei Problemen zuerst `check_active_alpha_core.py` über die Batch-Datei oder direkt mit `.venv\Scripts\python.exe check_active_alpha_core.py` prüfen.

## Reporting-Hotfix

Die Version enthält den Duplicate-Column-Fix für `backtest_decisions` und eine robuste Reporting-Schicht:

- `reporting_progress.txt`
- `reporting_errors.txt`
- `reporting_errors.json`
- frühes `backtest_report.txt`
- frühes `run_manifest.json`
- isolierte optionale Diagnoseschritte

Damit sollen Core-Backtest-Dateien auch dann erhalten bleiben, wenn optionale Benchmarks oder Statistikmodule scheitern.

## Nicht enthalten

Nicht enthalten sind lokal erzeugte Daten-/Output-Dateien wie `features.parquet`, `backtest_decisions.csv`, `strategy_daily_returns.csv`, `.venv`, `model_output_*` und `paper_output`. Diese werden lokal erzeugt.

Falls `ticker_membership.csv` in deinem lokalen Ordner bereits vorhanden ist, behalte sie. Falls sie fehlt, muss sie über `run_build_sp500_membership.bat` erzeugt werden.


## Multi-Core Pipeline

The backtest now supports a parallel prediction/training pipeline. It parallelizes the state-independent walk-forward model fitting and prediction stage while keeping portfolio path simulation serial for correctness. Configure it in `active_alpha_settings.bat`:

```bat
set "AA_N_JOBS=auto"
set "AA_PARALLEL_BACKTEST_BACKEND=thread"
```

Use `thread` to avoid large DataFrame copies. Use `process` only when enough RAM is available and true multiprocessing is required.

See [PERFORMANCE.md](PERFORMANCE.md) for cache invalidation rules, `--shared-cache-dir`, `--dry-run`, `--cache-status`, and robustness-lab parallel execution.

See [ARCHITECTURE.md](ARCHITECTURE.md) for module layout and walk-forward phases A/B/C.

See [BASELINE.md](BASELINE.md) for reference-run metrics and comparison workflow.

Local CI-style verification: `run_quality_gate.bat` (pytest + `--self-test` + core check).
