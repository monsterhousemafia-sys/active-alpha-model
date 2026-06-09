@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0load_active_alpha_config.bat"

echo ============================================================
echo Active Alpha Trading 212 - Backtest
echo ============================================================
echo Arbeitsordner: %CD%
echo.

echo [INFO] Verwende zentrale Konfiguration. Aendern mit: run_active_alpha_settings_wizard.bat
echo.
echo   Benchmark:          !AA_BENCHMARK!
echo   Startdatum:         !AA_START_DATE!
echo   Universe Top-N:     !AA_UNIVERSE_TOP_N!
echo   Backtest-Kapital:  !AA_BACKTEST_CAPITAL! USD
echo   Research-Kapital:  !AA_RESEARCH_BACKTEST_CAPITAL! USD
echo   Paper-Kapital:     !AA_PAPER_CAPITAL! USD
echo   Policy:             !AA_TRADING212_POLICY!
echo   Slippage-BPS:       !AA_SLIPPAGE_BPS!
echo   FX-BPS:             !AA_TRADING212_FX_BPS!
echo   Tail-Prune:         !AA_TAIL_PRUNE_ENABLED! floor=!AA_RESIDUAL_WEIGHT_FLOOR! soft=!AA_MAX_N_POSITIONS_SOFT! hard=!AA_MAX_N_POSITIONS_HARD!
echo   Alpha Model Mode:    !AA_ALPHA_MODEL_MODE!
echo   Extra Benchmarks:    !AA_EXTRA_BENCHMARKS!
echo   Naive Variants:      !AA_NAIVE_MOMENTUM_VARIANTS!
echo   Risk-Regime Mode:    !AA_RISK_REGIME_MODE!
echo   Exposure Controller: !AA_EXPOSURE_CONTROLLER!
echo   Cash Filler:         !AA_CASH_FILLER_MODE! max=!AA_CASH_FILLER_MAX_POSITION! completion=!AA_BENCHMARK_COMPLETION_TICKER! maxw=!AA_BENCHMARK_COMPLETION_MAX_WEIGHT!
echo   Cluster Mode:        !AA_CLUSTER_MODE! / !AA_CLUSTER_CONSTRAINT_MODE!
echo   Beta Cap Mode:       !AA_BETA_CAP_MODE! normal=!AA_DYNAMIC_BETA_NORMAL! riskon=!AA_DYNAMIC_BETA_RISK_ON! strong=!AA_DYNAMIC_BETA_STRONG!
echo   Bootstrap Iter.:     !AA_BOOTSTRAP_ITERATIONS!
echo   Multi-Core:          n_jobs=!AA_N_JOBS! cores=!AA_CPU_CORES! backend=!AA_PARALLEL_BACKTEST_BACKEND! ram_gb=!AA_SYSTEM_RAM_GB!
echo   Caches:              feature=!AA_REUSE_FEATURE_CACHE! prediction=!AA_REUSE_PREDICTION_CACHE! download=!AA_SKIP_DOWNLOAD_IF_CACHED! ttl_h=!AA_PRICE_CACHE_TTL_HOURS!
echo   Perf-Flags:          skip_naive=!AA_SKIP_NAIVE_MOMENTUM_BASELINE! skip_stats=!AA_SKIP_STATISTICAL_DIAGNOSTICS! skip_custom_bm=!AA_SKIP_CUSTOM_BENCHMARKS! skip_feat_pq=!AA_SKIP_FEATURE_PARQUET_WRITE! no_plot=!AA_NO_PLOT! no_naive_overlap=!AA_NO_NAIVE_OVERLAP!
echo   Risk-off Selektion:  mode=!AA_RISK_OFF_SELECTION_MODE! gate=!AA_RISK_OFF_GATE_MODE! mom_w=!AA_RISK_OFF_MOMENTUM_WEIGHT! q=!AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE! force_exit=!AA_RISK_OFF_FORCE_EXIT_ENABLED!
echo   Naive Diagnostics:   detailed=!AA_NAIVE_DETAILED_REPORTING! variants=!AA_NAIVE_DETAILED_VARIANTS!
echo.

if /I "!AA_LAUNCHER_READY!"=="1" (
  echo [INFO] Automatik-Modus ^(Marktanalyse.exe^): Konfiguration unveraendert, Backtest startet direkt.
) else (
  set /p "EDIT_CONFIG=Konfiguration vor dem Backtest aendern? j/N [N]: "
  if /I "!EDIT_CONFIG!"=="J" (
    call "%~dp0run_active_alpha_settings_wizard.bat"
    call "%~dp0load_active_alpha_config.bat"
  )
)

echo.
echo ============================================================
echo Starte Backtest-Konfiguration
echo ============================================================
echo   Output-Ordner:       !AA_BACKTEST_OUT_DIR!
echo   Tickerquelle:        !AA_BACKTEST_TICKER_SOURCE!
echo   Membership Mode:     !AA_BACKTEST_MEMBERSHIP_MODE!
echo   Universe Top-N:      !AA_UNIVERSE_TOP_N!
echo   Backtest-Kapital:   !AA_BACKTEST_CAPITAL! USD
echo   Research-Kapital:   !AA_RESEARCH_BACKTEST_CAPITAL! USD
echo   Policy:              !AA_TRADING212_POLICY!
echo   Slippage-BPS:        !AA_SLIPPAGE_BPS!
echo   FX-BPS:              !AA_TRADING212_FX_BPS!
echo.


set "TAIL_PRUNE_FLAG="
if /I "!AA_TAIL_PRUNE_ENABLED!"=="J" set "TAIL_PRUNE_FLAG=--tail-prune-enabled"
set "TAIL_PRUNE_REALLOCATE_FLAG="
if /I "!AA_TAIL_PRUNE_REALLOCATE!"=="N" set "TAIL_PRUNE_REALLOCATE_FLAG=--no-tail-prune-reallocate"
if "!AA_RESIDUAL_WEIGHT_FLOOR!"=="" set "AA_RESIDUAL_WEIGHT_FLOOR=0.005"
if "!AA_RESIDUAL_SELL_MIN_VALUE!"=="" set "AA_RESIDUAL_SELL_MIN_VALUE=0.01"
if "!AA_ORDER_VALUE_ROUNDING!"=="" set "AA_ORDER_VALUE_ROUNDING=1.0"
if "!AA_BROKER_MIN_REMAINING_POSITION_VALUE!"=="" set "AA_BROKER_MIN_REMAINING_POSITION_VALUE=1.0"
if "!AA_MAX_N_POSITIONS_SOFT!"=="" set "AA_MAX_N_POSITIONS_SOFT=35"
if "!AA_MAX_N_POSITIONS_HARD!"=="" set "AA_MAX_N_POSITIONS_HARD=45"
if "!AA_MAX_TAIL_REALLOCATION_PER_NAME!"=="" set "AA_MAX_TAIL_REALLOCATION_PER_NAME=0.01"
if "!AA_TAIL_REALLOCATION_STEP!"=="" set "AA_TAIL_REALLOCATION_STEP=0.0025"
if "!AA_TAIL_REALLOCATION_ROUNDS!"=="" set "AA_TAIL_REALLOCATION_ROUNDS=10"
if "!AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER!"=="" set "AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER=0.02"

if "!AA_PRICE_CACHE_TTL_HOURS!"=="" set "AA_PRICE_CACHE_TTL_HOURS=168"
set "CACHE_FLAGS="
if /I "!AA_REUSE_FEATURE_CACHE!"=="1" set "CACHE_FLAGS=!CACHE_FLAGS! --reuse-feature-cache"
if /I "!AA_REUSE_PREDICTION_CACHE!"=="1" set "CACHE_FLAGS=!CACHE_FLAGS! --reuse-prediction-cache"
if /I "!AA_SKIP_DOWNLOAD_IF_CACHED!"=="1" set "CACHE_FLAGS=!CACHE_FLAGS! --skip-download-if-cached"
set "PERF_FLAGS="
if /I "!AA_SKIP_NAIVE_MOMENTUM_BASELINE!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --no-naive-momentum-baseline"
if /I "!AA_SKIP_STATISTICAL_DIAGNOSTICS!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --no-statistical-diagnostics"
if /I "!AA_SKIP_CUSTOM_BENCHMARKS!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --no-custom-benchmarks"
if /I "!AA_SKIP_FEATURE_PARQUET_WRITE!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --skip-feature-parquet-write"
if /I "!AA_NO_PLOT!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --no-plot"
if /I "!AA_NO_NAIVE_OVERLAP!"=="1" set "PERF_FLAGS=!PERF_FLAGS! --no-naive-overlap"
set "RISK_OFF_FLAGS="
if not "!AA_RISK_OFF_SELECTION_MODE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-selection-mode !AA_RISK_OFF_SELECTION_MODE!"
if not "!AA_RISK_OFF_MOMENTUM_VARIANT!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-variant !AA_RISK_OFF_MOMENTUM_VARIANT!"
if not "!AA_RISK_OFF_MOMENTUM_WEIGHT!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-weight !AA_RISK_OFF_MOMENTUM_WEIGHT!"
if not "!AA_RISK_OFF_GATE_MODE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-gate-mode !AA_RISK_OFF_GATE_MODE!"
if not "!AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-rescue-quantile !AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!"
if /I "!AA_RISK_OFF_FORCE_EXIT_ENABLED!"=="1" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-force-exit-enabled"
if /I "!AA_FORCE_REBUILD_PREDICTIONS!"=="1" set "CACHE_FLAGS=!CACHE_FLAGS! --force-rebuild-predictions"
if /I "!AA_NAIVE_DETAILED_REPORTING!"=="1" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --naive-detailed-reporting"
if /I "!AA_NAIVE_POSITION_CONTRIBUTIONS!"=="1" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --naive-position-contributions"
if not "!AA_NAIVE_DETAILED_VARIANTS!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --naive-detailed-variants "!AA_NAIVE_DETAILED_VARIANTS!""
set "SHARED_CACHE_FLAG="
if not "!AA_SHARED_CACHE_DIR!"=="" set "SHARED_CACHE_FLAG=--shared-cache-dir "!AA_SHARED_CACHE_DIR!""

if /I not "!AA_LAUNCHER_READY!"=="1" (
  call "%~dp0setup_active_alpha_env.bat"
  if errorlevel 1 (
    echo [ERROR] Abhaengigkeiten fehlgeschlagen.
    if /I not "!AA_LAUNCHER_READY!"=="1" pause
    exit /b 1
  )
) else (
  echo [INFO] Launcher hat .venv und Bibliotheken bereits vorbereitet.
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

if /I not "!AA_LAUNCHER_READY!"=="1" (
  "!PYEXE!" check_active_alpha_core.py
  if errorlevel 1 (
    if /I not "!AA_LAUNCHER_READY!"=="1" pause
    exit /b 1
  )
) else (
  echo [INFO] Core-Check wurde bereits vom Launcher ausgefuehrt.
)

if not exist "!AA_BACKTEST_OUT_DIR!" mkdir "!AA_BACKTEST_OUT_DIR!"
(
  echo mode=backtest
  echo benchmark=!AA_BENCHMARK!
  echo start=!AA_START_DATE!
  echo ticker_source=!AA_BACKTEST_TICKER_SOURCE!
  echo membership_file=!AA_MEMBERSHIP_FILE!
  echo membership_mode=!AA_BACKTEST_MEMBERSHIP_MODE!
  echo universe_mode=!AA_UNIVERSE_MODE!
  echo universe_top_n=!AA_UNIVERSE_TOP_N!
  echo backtest_capital=!AA_BACKTEST_CAPITAL!
  echo research_backtest_capital=!AA_RESEARCH_BACKTEST_CAPITAL!
  echo paper_capital=!AA_PAPER_CAPITAL!
  echo execution_policy_mode=!AA_EXECUTION_POLICY_MODE!
  echo trading212_policy=!AA_TRADING212_POLICY!
  echo slippage_bps=!AA_SLIPPAGE_BPS!
  echo market_impact_bps=!AA_MARKET_IMPACT_BPS!
  echo trading212_fx_bps=!AA_TRADING212_FX_BPS!
  echo tail_prune_enabled=!AA_TAIL_PRUNE_ENABLED!
  echo residual_weight_floor=!AA_RESIDUAL_WEIGHT_FLOOR!
  echo residual_sell_min_value=!AA_RESIDUAL_SELL_MIN_VALUE!
  echo order_value_rounding=!AA_ORDER_VALUE_ROUNDING!
  echo broker_min_remaining_position_value=!AA_BROKER_MIN_REMAINING_POSITION_VALUE!
  echo max_n_positions_soft=!AA_MAX_N_POSITIONS_SOFT!
  echo max_n_positions_hard=!AA_MAX_N_POSITIONS_HARD!
  echo max_tail_reallocation_per_name=!AA_MAX_TAIL_REALLOCATION_PER_NAME!
  echo beta_cap_mode=!AA_BETA_CAP_MODE!
  echo dynamic_beta_risk_off=!AA_DYNAMIC_BETA_RISK_OFF!
  echo dynamic_beta_normal=!AA_DYNAMIC_BETA_NORMAL!
  echo dynamic_beta_risk_on=!AA_DYNAMIC_BETA_RISK_ON!
  echo dynamic_beta_strong=!AA_DYNAMIC_BETA_STRONG!
  echo static_cluster_cap=!AA_STATIC_CLUSTER_CAP!
  echo dynamic_cluster_cap=!AA_DYNAMIC_CLUSTER_CAP!
  echo cluster_constraint_mode=!AA_CLUSTER_CONSTRAINT_MODE!
  echo tail_reallocation_step=!AA_TAIL_REALLOCATION_STEP!
  echo tail_reallocation_rounds=!AA_TAIL_REALLOCATION_ROUNDS!
  echo tail_prune_min_exposure_buffer=!AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER!
  echo alpha_model_mode=!AA_ALPHA_MODEL_MODE!
  echo extra_benchmarks=!AA_EXTRA_BENCHMARKS!
  echo naive_momentum_variants=!AA_NAIVE_MOMENTUM_VARIANTS!
  echo bootstrap_iterations=!AA_BOOTSTRAP_ITERATIONS!
  echo random_seed=!AA_RANDOM_SEED!
  echo n_jobs=!AA_N_JOBS!
  echo cpu_cores=!AA_CPU_CORES!
  echo parallel_backtest_backend=!AA_PARALLEL_BACKTEST_BACKEND!
  echo system_ram_gb=!AA_SYSTEM_RAM_GB!
  echo parallel_profile=!AA_PARALLEL_PROFILE!
  echo risk_regime_mode=!AA_RISK_REGIME_MODE!
  echo exposure_controller=!AA_EXPOSURE_CONTROLLER!
  echo cash_filler_mode=!AA_CASH_FILLER_MODE!
  echo cash_filler_max_position=!AA_CASH_FILLER_MAX_POSITION!
  echo cash_filler_min_score=!AA_CASH_FILLER_MIN_SCORE!
  echo benchmark_completion_ticker=!AA_BENCHMARK_COMPLETION_TICKER!
  echo benchmark_completion_max_weight=!AA_BENCHMARK_COMPLETION_MAX_WEIGHT!
  echo low_beta_filler_max_position=!AA_LOW_BETA_FILLER_MAX_POSITION!
  echo low_beta_filler_beta_max=!AA_LOW_BETA_FILLER_BETA_MAX!
  echo low_beta_filler_min_score=!AA_LOW_BETA_FILLER_MIN_SCORE!
  echo low_beta_filler_max_vol_63=!AA_LOW_BETA_FILLER_MAX_VOL_63!
  echo exposure_recovery_policy=!AA_EXPOSURE_RECOVERY_POLICY!
  echo cluster_mode=!AA_CLUSTER_MODE!
  echo dynamic_cluster_window_short=!AA_DYNAMIC_CLUSTER_WINDOW_SHORT!
  echo dynamic_cluster_window_long=!AA_DYNAMIC_CLUSTER_WINDOW_LONG!
  echo dynamic_cluster_corr_threshold=!AA_DYNAMIC_CLUSTER_CORR_THRESHOLD!
  echo dynamic_cluster_min_overlap=!AA_DYNAMIC_CLUSTER_MIN_OVERLAP!
  echo reproducibility_mode=!AA_REPRODUCIBILITY_MODE!
  echo skip_naive_momentum_baseline=!AA_SKIP_NAIVE_MOMENTUM_BASELINE!
  echo skip_statistical_diagnostics=!AA_SKIP_STATISTICAL_DIAGNOSTICS!
  echo no_naive_overlap=!AA_NO_NAIVE_OVERLAP!
  echo skip_feature_parquet_write=!AA_SKIP_FEATURE_PARQUET_WRITE!
  echo no_plot=!AA_NO_PLOT!
  echo reuse_feature_cache=!AA_REUSE_FEATURE_CACHE!
  echo reuse_prediction_cache=!AA_REUSE_PREDICTION_CACHE!
  echo skip_download_if_cached=!AA_SKIP_DOWNLOAD_IF_CACHED!
  echo shared_cache_dir=!AA_SHARED_CACHE_DIR!
  echo price_cache_ttl_hours=!AA_PRICE_CACHE_TTL_HOURS!
) > "!AA_BACKTEST_OUT_DIR!\run_config_snapshot.txt"

echo.
echo [INFO] Starte Backtest ...
REM Dieser Backtest-Launcher darf kein --mode both verwenden.
REM Signal-/Paper-Zielportfolios gehoeren in AA_PAPER_MODEL_OUT_DIR und werden durch den Signal/Paper-Lauf erzeugt.
"!PYEXE!" active_alpha_model.py ^
  --mode backtest ^
  --ticker-source !AA_BACKTEST_TICKER_SOURCE! ^
  --ticker-cache-dir "!AA_TICKER_CACHE_DIR!" ^
  --ticker-cache-max-age-days !AA_TICKER_CACHE_MAX_AGE_DAYS! ^
  --membership-file "!AA_MEMBERSHIP_FILE!" ^
  --membership-mode !AA_BACKTEST_MEMBERSHIP_MODE! ^
  --asset-master-file "!AA_ASSET_MASTER_FILE!" ^
  --benchmark !AA_BENCHMARK! ^
  --start !AA_START_DATE! ^
  --signal-lookback-years !AA_SIGNAL_LOOKBACK_YEARS! ^
  --horizon !AA_HORIZON! ^
  --rebalance-every !AA_REBALANCE_EVERY! ^
  --top-k !AA_TOP_K! ^
  --max-position !AA_MAX_POSITION! ^
  --good-regime-exposure !AA_GOOD_REGIME_EXPOSURE! ^
  --bad-regime-exposure !AA_BAD_REGIME_EXPOSURE! ^
  --risk-on-exposure-floor !AA_RISK_ON_EXPOSURE_FLOOR! ^
  --min-edge !AA_MIN_EDGE! ^
  --lcb-z !AA_LCB_Z! ^
  --lcb-scale !AA_LCB_SCALE! ^
  --cost-bps !AA_COST_BPS! ^
  --universe-mode !AA_UNIVERSE_MODE! ^
  --universe-top-n !AA_UNIVERSE_TOP_N! ^
  --universe-adv-lookback !AA_UNIVERSE_ADV_LOOKBACK! ^
  --universe-min-adv !AA_UNIVERSE_MIN_ADV! ^
  --universe-min-price !AA_UNIVERSE_MIN_PRICE! ^
  --universe-min-history-days !AA_UNIVERSE_MIN_HISTORY_DAYS! ^
  --min-adv !AA_UNIVERSE_MIN_ADV! ^
  --max-ann-vol !AA_MAX_ANN_VOL! ^
  --max-sector !AA_MAX_SECTOR! ^
  --max-issuer !AA_MAX_ISSUER! ^
  --max-correlation-cluster !AA_MAX_CORRELATION_CLUSTER! ^
  --max-portfolio-beta !AA_MAX_PORTFOLIO_BETA! ^
  --beta-cap-mode !AA_BETA_CAP_MODE! ^
  --dynamic-beta-risk-off !AA_DYNAMIC_BETA_RISK_OFF! ^
  --dynamic-beta-normal !AA_DYNAMIC_BETA_NORMAL! ^
  --dynamic-beta-risk-on !AA_DYNAMIC_BETA_RISK_ON! ^
  --dynamic-beta-strong !AA_DYNAMIC_BETA_STRONG! ^
  --static-cluster-cap !AA_STATIC_CLUSTER_CAP! ^
  --dynamic-cluster-cap !AA_DYNAMIC_CLUSTER_CAP! ^
  --cluster-constraint-mode !AA_CLUSTER_CONSTRAINT_MODE! ^
  --no-trade-band !AA_NO_TRADE_BAND! ^
  --weight-smoothing !AA_WEIGHT_SMOOTHING! ^
  --max-turnover !AA_MAX_TURNOVER! ^
  !TAIL_PRUNE_FLAG! ^
  --residual-weight-floor !AA_RESIDUAL_WEIGHT_FLOOR! ^
  --residual-sell-min-value !AA_RESIDUAL_SELL_MIN_VALUE! ^
  --order-value-rounding !AA_ORDER_VALUE_ROUNDING! ^
  --broker-min-remaining-position-value !AA_BROKER_MIN_REMAINING_POSITION_VALUE! ^
  --max-n-positions-soft !AA_MAX_N_POSITIONS_SOFT! ^
  --max-n-positions-hard !AA_MAX_N_POSITIONS_HARD! ^
  !TAIL_PRUNE_REALLOCATE_FLAG! ^
  --max-tail-reallocation-per-name !AA_MAX_TAIL_REALLOCATION_PER_NAME! ^
  --tail-reallocation-step !AA_TAIL_REALLOCATION_STEP! ^
  --tail-reallocation-rounds !AA_TAIL_REALLOCATION_ROUNDS! ^
  --tail-prune-min-exposure-buffer !AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER! ^
  --fee-model trading212_us ^
  --backtest-capital !AA_BACKTEST_CAPITAL! ^
  --research-backtest-capital !AA_RESEARCH_BACKTEST_CAPITAL! ^
  --execution-policy-mode !AA_EXECUTION_POLICY_MODE! ^
  --trading212-policy !AA_TRADING212_POLICY! ^
  --slippage-bps !AA_SLIPPAGE_BPS! ^
  --market-impact-bps !AA_MARKET_IMPACT_BPS! ^
  --trading212-sec-fee-rate !AA_TRADING212_SEC_FEE_RATE! ^
  --trading212-finra-taf-per-share !AA_TRADING212_FINRA_TAF_PER_SHARE! ^
  --trading212-fx-bps !AA_TRADING212_FX_BPS! ^
  --max-gross-exposure !AA_MAX_GROSS_EXPOSURE! ^
  --train-years !AA_TRAIN_YEARS! ^
  --min-train-rows !AA_MIN_TRAIN_ROWS! ^
  --alpha-model-mode !AA_ALPHA_MODEL_MODE! ^
  --extra-benchmarks "!AA_EXTRA_BENCHMARKS!" ^
  --naive-momentum-variants "!AA_NAIVE_MOMENTUM_VARIANTS!" ^
  --bootstrap-iterations !AA_BOOTSTRAP_ITERATIONS! ^
  --random-seed !AA_RANDOM_SEED! ^
  --n-jobs !AA_N_JOBS! ^
  --cpu-cores !AA_CPU_CORES! ^
  --parallel-backtest-backend !AA_PARALLEL_BACKTEST_BACKEND! ^
  --system-ram-gb !AA_SYSTEM_RAM_GB! ^
  --parallel-profile !AA_PARALLEL_PROFILE! ^
  --price-cache-ttl-hours !AA_PRICE_CACHE_TTL_HOURS! ^
  !CACHE_FLAGS! ^
  !SHARED_CACHE_FLAG! ^
  !PERF_FLAGS! ^
  !RISK_OFF_FLAGS! ^
  --risk-regime-mode !AA_RISK_REGIME_MODE! ^
  --exposure-controller !AA_EXPOSURE_CONTROLLER! ^
  --cash-filler-mode !AA_CASH_FILLER_MODE! ^
  --cash-filler-max-position !AA_CASH_FILLER_MAX_POSITION! ^
  --cash-filler-min-score !AA_CASH_FILLER_MIN_SCORE! ^
  --benchmark-completion-ticker !AA_BENCHMARK_COMPLETION_TICKER! ^
  --benchmark-completion-max-weight !AA_BENCHMARK_COMPLETION_MAX_WEIGHT! ^
  --low-beta-filler-max-position !AA_LOW_BETA_FILLER_MAX_POSITION! ^
  --low-beta-filler-beta-max !AA_LOW_BETA_FILLER_BETA_MAX! ^
  --low-beta-filler-min-score !AA_LOW_BETA_FILLER_MIN_SCORE! ^
  --low-beta-filler-max-vol-63 !AA_LOW_BETA_FILLER_MAX_VOL_63! ^
  --exposure-recovery-policy !AA_EXPOSURE_RECOVERY_POLICY! ^
  --cluster-mode !AA_CLUSTER_MODE! ^
  --dynamic-cluster-window-short !AA_DYNAMIC_CLUSTER_WINDOW_SHORT! ^
  --dynamic-cluster-window-long !AA_DYNAMIC_CLUSTER_WINDOW_LONG! ^
  --dynamic-cluster-corr-threshold !AA_DYNAMIC_CLUSTER_CORR_THRESHOLD! ^
  --dynamic-cluster-min-overlap !AA_DYNAMIC_CLUSTER_MIN_OVERLAP! ^
  --reproducibility-mode !AA_REPRODUCIBILITY_MODE! ^
  --out-dir "!AA_BACKTEST_OUT_DIR!" ^
  !AA_ADDITIONAL_MODEL_ARGS!

if errorlevel 1 (
  echo [ERROR] Modelllauf fehlgeschlagen.
  if /I not "!AA_LAUNCHER_READY!"=="1" pause
  exit /b 1
)

echo.
echo [OK] Backtest abgeschlossen. Ergebnisse in !AA_BACKTEST_OUT_DIR!
if /I not "!AA_LAUNCHER_READY!"=="1" pause
exit /b 0
