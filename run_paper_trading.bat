@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0load_active_alpha_config.bat"

echo ============================================================
echo Active Alpha Trading 212 - Paper Trading Rebalance
echo ============================================================
echo Arbeitsordner: %CD%
echo.
echo Hinweis: Paper-Trading ist eine lokale virtuelle Buchhaltung; es werden keine echten Orders platziert.
echo.

echo [INFO] Verwende zentrale Konfiguration. Aendern mit: run_active_alpha_settings_wizard.bat
echo.
echo   Paper-Ordner:       !AA_PAPER_DIR!
echo   Paper-Tickerquelle: !AA_PAPER_TICKER_SOURCE!
echo   Universe Top-N:     !AA_UNIVERSE_TOP_N!
echo   Paper-Start-/Fallbackkapital: !AA_PAPER_CAPITAL! USD
echo   Policy:             !AA_TRADING212_POLICY!
echo   Slippage-BPS:       !AA_SLIPPAGE_BPS!
echo   FX-BPS:             !AA_TRADING212_FX_BPS!
echo   Risk-off:           mode=!AA_RISK_OFF_SELECTION_MODE! gate=!AA_RISK_OFF_GATE_MODE! mom_w=!AA_RISK_OFF_MOMENTUM_WEIGHT! q=!AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!
echo   Multi-Core:          n_jobs=!AA_N_JOBS! cores=!AA_CPU_CORES! backend=!AA_PARALLEL_BACKTEST_BACKEND! ram_gb=!AA_SYSTEM_RAM_GB!
echo   Caches:              feature=!AA_REUSE_FEATURE_CACHE! download=!AA_SKIP_DOWNLOAD_IF_CACHED! ttl_h=!AA_PRICE_CACHE_TTL_HOURS! shared=!AA_SHARED_CACHE_DIR!
echo   Signal-Lookback:     !AA_SIGNAL_LOOKBACK_YEARS! Jahre ^(Paper nutzt keinen Prediction-Cache^)
echo.

if /I not "!AA_NONINTERACTIVE!"=="1" (
  set /p "EDIT_CONFIG=Konfiguration vor Paper-Rebalance aendern? j/N [N]: "
  if /I "!EDIT_CONFIG!"=="J" (
    call "%~dp0run_active_alpha_settings_wizard.bat"
    call "%~dp0load_active_alpha_config.bat"
  )
)

set "RESET_FLAG="
set "STATE_EXISTS=0"
if exist "!AA_PAPER_DIR!\paper_state.json" set "STATE_EXISTS=1"

if "!STATE_EXISTS!"=="1" (
  echo [INFO] Bestehendes Paper-Depot gefunden: !AA_PAPER_DIR!\paper_state.json
  if /I not "!AA_NONINTERACTIVE!"=="1" (
    set /p "USER_RESET=Bestehendes Paper-Depot zuruecksetzen? N/j [N]: "
    if /I "!USER_RESET!"=="J" set "RESET_FLAG=--reset"
  )
)

set "FRACTIONAL_FLAG=--fractional"
if /I "!AA_FRACTIONAL!"=="N" set "FRACTIONAL_FLAG="


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

set "RISK_OFF_FLAGS="
if not "!AA_RISK_OFF_SELECTION_MODE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-selection-mode !AA_RISK_OFF_SELECTION_MODE!"
if not "!AA_RISK_OFF_MOMENTUM_VARIANT!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-variant !AA_RISK_OFF_MOMENTUM_VARIANT!"
if not "!AA_RISK_OFF_MOMENTUM_WEIGHT!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-weight !AA_RISK_OFF_MOMENTUM_WEIGHT!"
if not "!AA_RISK_OFF_GATE_MODE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-gate-mode !AA_RISK_OFF_GATE_MODE!"
if not "!AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!"=="" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-momentum-rescue-quantile !AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!"
if /I "!AA_RISK_OFF_FORCE_EXIT_ENABLED!"=="1" set "RISK_OFF_FLAGS=!RISK_OFF_FLAGS! --risk-off-force-exit-enabled"

if "!AA_PRICE_CACHE_TTL_HOURS!"=="" set "AA_PRICE_CACHE_TTL_HOURS=168"
set "PAPER_CACHE_FLAGS="
if /I "!AA_REUSE_FEATURE_CACHE!"=="1" set "PAPER_CACHE_FLAGS=!PAPER_CACHE_FLAGS! --reuse-feature-cache"
if /I "!AA_SKIP_DOWNLOAD_IF_CACHED!"=="1" set "PAPER_CACHE_FLAGS=!PAPER_CACHE_FLAGS! --skip-download-if-cached"
set "PAPER_SHARED_CACHE_FLAG="
if not "!AA_SHARED_CACHE_DIR!"=="" set "PAPER_SHARED_CACHE_FLAG=--shared-cache-dir "!AA_SHARED_CACHE_DIR!""
if "!AA_N_JOBS!"=="" set "AA_N_JOBS=auto"
if "!AA_CPU_CORES!"=="" set "AA_CPU_CORES=16"
if "!AA_PARALLEL_PROFILE!"=="" set "AA_PARALLEL_PROFILE=high"
if "!AA_SYSTEM_RAM_GB!"=="" set "AA_SYSTEM_RAM_GB=64"
if "!AA_PARALLEL_BACKTEST_BACKEND!"=="" set "AA_PARALLEL_BACKTEST_BACKEND=process"

set "ENGINE_POLICY_ARGS=--trading212-policy !AA_TRADING212_POLICY!"
if /I "!AA_EXECUTION_POLICY_MODE!"=="capital_curve" set "ENGINE_POLICY_ARGS=--capital-curve-policy --trading212-policy !AA_TRADING212_POLICY!"

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

if exist check_active_alpha_core.py (
  "!PYEXE!" check_active_alpha_core.py
  if errorlevel 1 (
    pause
    exit /b 1
  )
)

if not exist "!AA_PAPER_DIR!" mkdir "!AA_PAPER_DIR!"

echo.
echo [INFO] Lese aktuelle Paper-Equity ...
set "PAPER_CASH="
set "PAPER_POSITIONS_VALUE="
set "PAPER_TOTAL_EQUITY="
set "PAPER_STATE_EXISTS="
set "EFFECTIVE_CAPITAL="

for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL!') do (
  set "%%A=%%B"
)

if "!PAPER_TOTAL_EQUITY!"=="" set "PAPER_TOTAL_EQUITY=!AA_PAPER_CAPITAL!"
if "!PAPER_CASH!"=="" set "PAPER_CASH=!AA_PAPER_CAPITAL!"
if "!PAPER_POSITIONS_VALUE!"=="" set "PAPER_POSITIONS_VALUE=0.00"

if defined RESET_FLAG (
  set "EFFECTIVE_CAPITAL=!AA_PAPER_CAPITAL!"
  echo [INFO] Reset wurde gewaehlt; effektives Kapital wird auf Start-/Fallbackkapital gesetzt.
) else (
  set "EFFECTIVE_CAPITAL=!PAPER_TOTAL_EQUITY!"
)

echo [OK] Konfiguriertes Paper-Start-/Fallbackkapital: !AA_PAPER_CAPITAL! USD
echo [OK] Paper Cash:                            !PAPER_CASH! USD
echo [OK] Paper Positionswert:                   !PAPER_POSITIONS_VALUE! USD
echo [OK] Paper Total Equity:                    !PAPER_TOTAL_EQUITY! USD
echo [OK] Effektives Kapital fuer diesen Lauf:   !EFFECTIVE_CAPITAL! USD

echo.
echo [INFO] Berechne Trading-212-Policy ...
for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-policy --capital !EFFECTIVE_CAPITAL! --fee-model trading212_us --trading212-policy !AA_TRADING212_POLICY!') do set "%%A=%%B"

set "MIN_TRADE_VALUE=!POLICY_MIN_TRADE_VALUE!"
if "!MIN_TRADE_VALUE!"=="" set "MIN_TRADE_VALUE=10"

echo [OK] Policy: !POLICY_PROFILE! ^| RB !POLICY_REBALANCE_EVERY!d ^| Top-K !POLICY_TOP_K! ^| MaxPos !POLICY_MAX_POSITION! ^| MaxIssuer !POLICY_MAX_ISSUER! ^| TO !POLICY_MAX_TURNOVER! ^| Band !POLICY_NO_TRADE_BAND! ^| MinOrder !POLICY_MIN_TRADE_VALUE!

if not exist "!AA_PAPER_MODEL_OUT_DIR!" mkdir "!AA_PAPER_MODEL_OUT_DIR!"
(
  echo mode=paper_signal_and_rebalance
  echo benchmark=!AA_BENCHMARK!
  echo start=!AA_START_DATE!
  echo signal_lookback_years=!AA_SIGNAL_LOOKBACK_YEARS!
  echo ticker_source=!AA_PAPER_TICKER_SOURCE!
  echo membership_file=!AA_MEMBERSHIP_FILE!
  echo membership_mode=!AA_PAPER_MEMBERSHIP_MODE!
  echo universe_mode=!AA_UNIVERSE_MODE!
  echo universe_top_n=!AA_UNIVERSE_TOP_N!
  echo configured_paper_start_fallback_capital=!AA_PAPER_CAPITAL!
  echo paper_cash=!PAPER_CASH!
  echo paper_positions_value=!PAPER_POSITIONS_VALUE!
  echo paper_total_equity=!PAPER_TOTAL_EQUITY!
  echo effective_capital=!EFFECTIVE_CAPITAL!
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
  echo research_backtest_capital=!AA_RESEARCH_BACKTEST_CAPITAL!
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
  echo n_jobs=!AA_N_JOBS!
  echo cpu_cores=!AA_CPU_CORES!
  echo parallel_profile=!AA_PARALLEL_PROFILE!
  echo system_ram_gb=!AA_SYSTEM_RAM_GB!
  echo reuse_feature_cache=!AA_REUSE_FEATURE_CACHE!
  echo skip_download_if_cached=!AA_SKIP_DOWNLOAD_IF_CACHED!
  echo shared_cache_dir=!AA_SHARED_CACHE_DIR!
  echo price_cache_ttl_hours=!AA_PRICE_CACHE_TTL_HOURS!
) > "!AA_PAPER_MODEL_OUT_DIR!\paper_model_config_snapshot.txt"

if not exist "!AA_PAPER_DIR!" mkdir "!AA_PAPER_DIR!"
copy /y "!AA_PAPER_MODEL_OUT_DIR!\paper_model_config_snapshot.txt" "!AA_PAPER_DIR!\paper_model_config_snapshot.txt" >nul

echo.
echo [INFO] Aktualisiere aktuelle Signale mit derselben Modellkonfiguration ...
"!PYEXE!" active_alpha_model.py ^
  --mode signal ^
  --ticker-source !AA_PAPER_TICKER_SOURCE! ^
  --ticker-cache-dir "!AA_TICKER_CACHE_DIR!" ^
  --ticker-cache-max-age-days !AA_TICKER_CACHE_MAX_AGE_DAYS! ^
  --membership-file "!AA_MEMBERSHIP_FILE!" ^
  --membership-mode !AA_PAPER_MEMBERSHIP_MODE! ^
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
  --backtest-capital !EFFECTIVE_CAPITAL! ^
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
  !RISK_OFF_FLAGS! ^
  --out-dir "!AA_PAPER_MODEL_OUT_DIR!" ^
  --price-cache-ttl-hours !AA_PRICE_CACHE_TTL_HOURS! ^
  --n-jobs !AA_N_JOBS! ^
  --cpu-cores !AA_CPU_CORES! ^
  --parallel-backtest-backend !AA_PARALLEL_BACKTEST_BACKEND! ^
  --system-ram-gb !AA_SYSTEM_RAM_GB! ^
  --parallel-profile !AA_PARALLEL_PROFILE! ^
  !PAPER_CACHE_FLAGS! ^
  !PAPER_SHARED_CACHE_FLAG! ^
  !AA_ADDITIONAL_MODEL_ARGS!

if errorlevel 1 (
  echo [ERROR] Signal-Lauf fehlgeschlagen.
  pause
  exit /b 1
)

if not exist "!AA_PAPER_MODEL_OUT_DIR!\latest_target_portfolio.csv" (
  echo [ERROR] !AA_PAPER_MODEL_OUT_DIR!\latest_target_portfolio.csv wurde nicht erzeugt.
  pause
  exit /b 1
)

if exist active_alpha_control_center.py (
  "!PYEXE!" active_alpha_control_center.py --mode preflight --scope rebalance
  if errorlevel 1 (
    echo [ERROR] Paper-Preflight nach Signal-Lauf fehlgeschlagen. Rebalance wird nicht gestartet.
    echo [INFO] Details: control_output\preflight_report.txt
    pause
    exit /b 1
  )
)

echo.
echo [INFO] Fuehre Paper-Trading-Rebalance aus ...
"!PYEXE!" paper_trading_engine.py ^
  --mode rebalance ^
  --target-file "!AA_PAPER_MODEL_OUT_DIR!\latest_target_portfolio.csv" ^
  --paper-dir "!AA_PAPER_DIR!" ^
  --benchmark !AA_BENCHMARK! ^
  --capital !EFFECTIVE_CAPITAL! ^
  --fee-model trading212_us ^
  --slippage-bps !AA_SLIPPAGE_BPS! ^
  --market-impact-bps !AA_MARKET_IMPACT_BPS! ^
  --trading212-sec-fee-rate !AA_TRADING212_SEC_FEE_RATE! ^
  --trading212-finra-taf-per-share !AA_TRADING212_FINRA_TAF_PER_SHARE! ^
  --trading212-fx-bps !AA_TRADING212_FX_BPS! ^
  --min-trade-value !MIN_TRADE_VALUE! ^
  --residual-weight-floor !AA_RESIDUAL_WEIGHT_FLOOR! ^
  --residual-sell-min-value !AA_RESIDUAL_SELL_MIN_VALUE! ^
  --order-value-rounding !AA_ORDER_VALUE_ROUNDING! ^
  --broker-min-remaining-position-value !AA_BROKER_MIN_REMAINING_POSITION_VALUE! ^
  !ENGINE_POLICY_ARGS! ^
  --max-gross-exposure !AA_MAX_GROSS_EXPOSURE! ^
  --price-lookback-days !AA_PRICE_LOOKBACK_DAYS! ^
  --price-interval !AA_PRICE_INTERVAL! ^
  !RESET_FLAG! ^
  !FRACTIONAL_FLAG! ^
  --execute

if errorlevel 1 (
  echo [ERROR] Paper-Trading-Lauf fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo [OK] Paper-Trading abgeschlossen. Ergebnisse in !AA_PAPER_DIR!
echo [OK] Danach pruefen: !AA_PAPER_DIR!\paper_dashboard.txt und !AA_PAPER_DIR!\paper_action_sheet.csv
if /I not "!AA_NONINTERACTIVE!"=="1" pause
endlocal
