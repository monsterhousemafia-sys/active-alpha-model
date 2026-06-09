@echo off
rem ============================================================
rem Active Alpha Trading 212 - zentrale Standardkonfiguration
rem ============================================================
rem Diese Datei nicht zwingend bearbeiten. Eigene Werte werden durch
rem run_active_alpha_settings_wizard.bat in active_alpha_user_config.bat gespeichert.
rem ============================================================

rem Allgemein
set "AA_BENCHMARK=SPY"
set "AA_START_DATE=2012-01-01"
set "AA_SIGNAL_LOOKBACK_YEARS=9"
rem Kapitalwerte sind absichtlich getrennt:
rem AA_BACKTEST_CAPITAL = simuliertes Konto fuer Research-/Backtest-Laeufe.
rem AA_RESEARCH_BACKTEST_CAPITAL = Kapitalbasis fuer die Capital-Curve-Parameter im Backtest.
rem AA_PAPER_CAPITAL = Start-/Fallbackkapital fuer Paper-Depots; laufende Cashflows stehen im Paper-Ledger.
set "AA_BACKTEST_CAPITAL=100000"
set "AA_RESEARCH_BACKTEST_CAPITAL=100000"
set "AA_PAPER_CAPITAL=100"
set "AA_MAX_GROSS_EXPOSURE=1.0"

rem Universum / Daten
set "AA_BACKTEST_TICKER_SOURCE=sp500_pit"
rem Paper: sp500_auto = aktuelles Universum; sp500_pit = Point-in-Time wie Backtest (Paritaet).
set "AA_PAPER_TICKER_SOURCE=sp500_pit"
set "AA_TICKER_CACHE_DIR=universe_snapshots"
set "AA_TICKER_CACHE_MAX_AGE_DAYS=7"
set "AA_MEMBERSHIP_FILE=ticker_membership.csv"
set "AA_BACKTEST_MEMBERSHIP_MODE=strict"
set "AA_PAPER_MEMBERSHIP_MODE=auto"
set "AA_ASSET_MASTER_FILE=asset_master.csv"

rem Sektor-Referenz (Wikipedia GICS + yfinance-Fallback; siehe aa_sector_reference.py)
set "AA_SECTOR_REFERENCE_MODE=auto"
set "AA_SECTOR_REFERENCE_FILE=sector_reference.csv"
set "AA_SECTOR_REFERENCE_MAX_AGE_DAYS=7"
set "AA_SECTOR_YFINANCE_FALLBACK=1"
set "AA_SECTOR_YFINANCE_CACHE_FILE=sector_yfinance_cache.json"

set "AA_UNIVERSE_MODE=diy_pit_liquidity"
set "AA_UNIVERSE_TOP_N=100"
set "AA_UNIVERSE_ADV_LOOKBACK=63"
set "AA_UNIVERSE_MIN_ADV=10000000"
set "AA_UNIVERSE_MIN_PRICE=5"
set "AA_UNIVERSE_MIN_HISTORY_DAYS=252"

rem Modell / Portfolio
rem Hinweis: Diese Werte sind manuelle Fallbacks. Bei AA_EXECUTION_POLICY_MODE=capital_curve
rem ueberschreibt die Trading-212-Policy diese Parameter kapitalabhaengig.
set "AA_HORIZON=10"
set "AA_REBALANCE_EVERY=5"
set "AA_TOP_K=15"
set "AA_MAX_POSITION=0.14"
set "AA_GOOD_REGIME_EXPOSURE=1.0"
set "AA_BAD_REGIME_EXPOSURE=0.65"
set "AA_RISK_ON_EXPOSURE_FLOOR=1.0"
set "AA_MIN_EDGE=0.0010"
set "AA_LCB_Z=0.10"
set "AA_LCB_SCALE=0.10"
set "AA_COST_BPS=10.0"
set "AA_MAX_ANN_VOL=1.25"
set "AA_MAX_SECTOR=0.55"
set "AA_MAX_ISSUER=0.15"
set "AA_MAX_CORRELATION_CLUSTER=0.40"
set "AA_MAX_PORTFOLIO_BETA=1.35"
set "AA_BETA_CAP_MODE=dynamic"
set "AA_DYNAMIC_BETA_RISK_OFF=1.10"
set "AA_DYNAMIC_BETA_NORMAL=1.30"
set "AA_DYNAMIC_BETA_RISK_ON=1.45"
set "AA_DYNAMIC_BETA_STRONG=1.55"
set "AA_STATIC_CLUSTER_CAP=0.40"
set "AA_DYNAMIC_CLUSTER_CAP=0.50"
set "AA_CLUSTER_CONSTRAINT_MODE=static_only"
set "AA_NO_TRADE_BAND=0.008"
set "AA_WEIGHT_SMOOTHING=0.50"
set "AA_MAX_TURNOVER=0.40"
set "AA_TRAIN_YEARS=5"
set "AA_ML_RETRAIN_EVERY=2"
set "AA_MIN_TRAIN_ROWS=2500"
set "AA_ALPHA_MODEL_MODE=ensemble"
set "AA_EXTRA_BENCHMARKS=QQQ,RSP,MTUM,QUAL,VUG,VLUE,USMV,SMH"
set "AA_NAIVE_MOMENTUM_VARIANTS=mom_63_top12,mom_126_top12,mom_252_21_top12,mom_blend_top12,sector_neutral_momentum,cluster_neutral_momentum"
set "AA_BOOTSTRAP_ITERATIONS=0"
set "AA_RANDOM_SEED=42"
rem Laufzeit-Optimierung (strategieneutral): weniger Report-/Diagnostik-Overhead im Backtest.
set "AA_SKIP_NAIVE_MOMENTUM_BASELINE=1"
set "AA_SKIP_STATISTICAL_DIAGNOSTICS=1"
set "AA_SKIP_CUSTOM_BENCHMARKS=1"
set "AA_SKIP_FEATURE_PARQUET_WRITE=1"
set "AA_NO_PLOT=1"
rem Risk-off-Selektion (R4 Return-Max: Momentum Rescue, mom_blend_blend 75/25, q=0.60)
set "AA_RISK_OFF_SELECTION_MODE=mom_blend_blend"
set "AA_RISK_OFF_MOMENTUM_VARIANT=mom_blend_top12"
set "AA_RISK_OFF_MOMENTUM_WEIGHT=0.75"
set "AA_RISK_OFF_GATE_MODE=momentum_rescue"
set "AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE=0.65"
set "AA_RISK_OFF_FORCE_EXIT_ENABLED=0"
set "AA_NAIVE_DETAILED_REPORTING=0"
set "AA_NAIVE_DETAILED_VARIANTS=mom_blend_top12,mom_63_top12"
set "AA_NAIVE_POSITION_CONTRIBUTIONS=0"
set "AA_FORCE_REBUILD_PREDICTIONS=0"
set "AA_PRICE_CACHE_TTL_HOURS=168"
rem Multi-Core-Pipeline: parallelisiert ML-Training/Vorhersage je Rebalance; Portfolio-Pfad bleibt seriell.
rem Ryzen 9 3950X: 16 physische Kerne / 32 Threads -> auto nutzt 16 Worker (nicht 32).
rem Windows x64, 64 GB RAM (Worker-Sizing + float32-Feature-Tabellen).
set "AA_N_JOBS=auto"
set "AA_CPU_CORES=16"
set "AA_PARALLEL_BACKTEST_BACKEND=process"
set "AA_SYSTEM_RAM_GB=64"
set "AA_PARALLEL_PROFILE=high"
rem Runtime-Profil: research | validation | background | exe (EXE setzt exe automatisch)
set "AA_RUNTIME_PROFILE=research"
rem Kerne fuer GUI/OS/EXE freihalten (Batch nutzt cpu_cores - reserve)
set "AA_RESERVE_CPU_CORES=2"
rem Validierungs-Matrix: parallele Varianten (Orchestrator)
set "AA_VALIDATION_PARALLEL_JOBS=3"
set "AA_REUSE_FEATURE_CACHE=1"
set "AA_REUSE_PREDICTION_CACHE=1"
set "AA_SKIP_DOWNLOAD_IF_CACHED=1"
set "AA_AUTO_OPS_REFRESH=1"
set "AA_OPS_REFRESH_INTERVAL_HOURS=24"
set "AA_FAST_PATH=1"
set "AA_SIGNAL_REFRESH_ON_STALE_DATA=1"
set "AA_FROZEN_LIGHT_ENV=1"
set "AA_SINGLE_INSTANCE=1"
set "AA_SKIP_PNG_CHARTS=1"
set "AA_STARTUP_CACHE_PRICES=1"
set "AA_DEFER_PAPER_ON_FAST_PATH=1"
set "AA_SKIP_VENV_PROBE=1"
rem Shared cache optional — leer lassen = Caches in AA_BACKTEST_OUT_DIR
set "AA_SHARED_CACHE_DIR="
set "AA_ROBUSTNESS_PARALLEL_JOBS=2"
rem Naive-Baselines parallel zu Phase B (0=Overlap an, 1=seriell danach). Nur relevant wenn AA_SKIP_NAIVE_MOMENTUM_BASELINE=0.
set "AA_NO_NAIVE_OVERLAP=0"
set "AA_RISK_REGIME_MODE=normal"
set "AA_EXPOSURE_CONTROLLER=gradual_alpha"
set "AA_CASH_FILLER_MODE=benchmark_completion"
set "AA_CASH_FILLER_MAX_POSITION=0.03"
set "AA_CASH_FILLER_MIN_SCORE=0.0"
set "AA_BENCHMARK_COMPLETION_TICKER=SPY"
set "AA_BENCHMARK_COMPLETION_MAX_WEIGHT=0.25"
set "AA_LOW_BETA_FILLER_MAX_POSITION=0.015"
set "AA_LOW_BETA_FILLER_BETA_MAX=0.90"
set "AA_LOW_BETA_FILLER_MIN_SCORE=-0.05"
set "AA_LOW_BETA_FILLER_MAX_VOL_63=0.75"
set "AA_EXPOSURE_RECOVERY_POLICY=cause_aware"
rem static = kein Rolling-Cluster-Overlay (~5 min schneller bei cluster_constraint_mode=static_only).
set "AA_CLUSTER_MODE=static"
set "AA_DYNAMIC_CLUSTER_WINDOW_SHORT=126"
set "AA_DYNAMIC_CLUSTER_WINDOW_LONG=252"
set "AA_DYNAMIC_CLUSTER_CORR_THRESHOLD=0.65"
set "AA_DYNAMIC_CLUSTER_MIN_OVERLAP=0.50"
set "AA_REPRODUCIBILITY_MODE=normal"

rem Tail-Pruning / Positionshygiene
set "AA_TAIL_PRUNE_ENABLED=J"
set "AA_RESIDUAL_WEIGHT_FLOOR=0.005"
set "AA_RESIDUAL_SELL_MIN_VALUE=0.01"
set "AA_ORDER_VALUE_ROUNDING=1.0"
set "AA_BROKER_MIN_REMAINING_POSITION_VALUE=1.0"
set "AA_MAX_N_POSITIONS_SOFT=35"
set "AA_MAX_N_POSITIONS_HARD=45"
set "AA_TAIL_PRUNE_REALLOCATE=J"
set "AA_MAX_TAIL_REALLOCATION_PER_NAME=0.01"
set "AA_TAIL_REALLOCATION_STEP=0.0025"
set "AA_TAIL_REALLOCATION_ROUNDS=10"
set "AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER=0.02"

rem Execution / Trading 212
set "AA_EXECUTION_POLICY_MODE=capital_curve"
set "AA_TRADING212_POLICY=threshold"
set "AA_SLIPPAGE_BPS=2"
set "AA_MARKET_IMPACT_BPS=0"
set "AA_TRADING212_FX_BPS=0"
set "AA_TRADING212_SEC_FEE_RATE=0.0000278"
set "AA_TRADING212_FINRA_TAF_PER_SHARE=0.000195"
set "AA_FRACTIONAL=J"

rem Paper-Engine-Preise
set "AA_PRICE_LOOKBACK_DAYS=10"
set "AA_PRICE_INTERVAL=1d"

rem Outputs
set "AA_BACKTEST_OUT_DIR=model_output_sp500_pit_t212"
set "AA_PAPER_MODEL_OUT_DIR=model_output_sp500_pit_t212"
set "AA_PAPER_DIR=paper_output"

rem Expertenfeld: zusätzliche active_alpha_model.py Flags, normalerweise leer lassen.
set "AA_ADDITIONAL_MODEL_ARGS="
