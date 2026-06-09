@echo off

rem OS-Umgebung fuer Marktanalyse.exe und Live-Trading (Phasen 0-5 Rebalance-Pipeline).

rem Geladen von: Marktanalyse_start.bat, run_pilot_start.bat, run_live_trading_start.bat, 1_/2_live_*.bat

rem Stand: 2026-06-04 — T212-first Quotes, Cash-Welle, Kurs-Gate 14/14, auto Sektor-Referenz (Wikipedia+yfinance)



set "AA_RUN_MODE=signal"

set "AA_RUNTIME_PROFILE=exe"

set "AA_SIGNAL_REFRESH_ON_STALE_DATA=1"

rem Live prediction profile (daily_alpha_h1 — 1d horizon, EOD switch via prediction_operations.json)
if "%AA_PREDICTION_PROFILE%"=="" set "AA_PREDICTION_PROFILE=daily_alpha_h1"

set "AA_FAST_PATH=1"

set "AA_REUSE_FEATURE_CACHE=1"

set "AA_REUSE_PREDICTION_CACHE=1"

set "AA_SKIP_DOWNLOAD_IF_CACHED=1"

set "AA_SKIP_NAIVE_MOMENTUM_BASELINE=1"

set "AA_SKIP_STATISTICAL_DIAGNOSTICS=1"

set "AA_SKIP_CUSTOM_BENCHMARKS=1"

set "AA_SKIP_FEATURE_PARQUET_WRITE=1"

set "AA_NO_PLOT=1"

set "AA_PARALLEL_BACKTEST_BACKEND=thread"

set "AA_N_JOBS=auto"



rem Champion-Modell / Walk-Forward (Signal ③, Portfolio-Vergleich)

if "%AA_BACKTEST_OUT_DIR%"=="" set "AA_BACKTEST_OUT_DIR=model_output_sp500_pit_t212"

if "%AA_PAPER_MODEL_OUT_DIR%"=="" set "AA_PAPER_MODEL_OUT_DIR=%AA_BACKTEST_OUT_DIR%"



rem Sektor-Referenz (automatisch mit Universum-Refresh; yfinance fuer Champion-Randfaelle)
set "AA_SECTOR_REFERENCE_MODE=auto"
set "AA_SECTOR_REFERENCE_FILE=sector_reference.csv"
set "AA_SECTOR_REFERENCE_MAX_AGE_DAYS=7"
set "AA_SECTOR_YFINANCE_FALLBACK=1"
set "AA_SECTOR_YFINANCE_CACHE_FILE=sector_yfinance_cache.json"



rem Live-Kurse (T212-first + Yahoo validiert; Dashboard «Aktualisieren»)

set "AA_LIVE_QUOTE_MAX_AGE_S=120"

set "AA_LIVE_QUOTE_REFRESH_INTERVAL_S=60"

set "AA_OFFLINE_COCKPIT_TEST=0"



rem Live-Orders: echte T212-POSTs nur wenn KI-unterstuetzt + Credentials (nicht Dry-Run)

set "AA_EXECUTION_DRY_RUN=0"



rem P17: Netzwerk-Submission erlauben wenn Live-Trading freigeschaltet (Review-Mode separat in UI)

if "%AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION%"=="" set "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION=0"



exit /b 0

