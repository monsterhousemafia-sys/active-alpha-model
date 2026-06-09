@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"

rem Read current paper ledger equity if the Python environment already exists.
set "PAPER_CASH="
set "PAPER_POSITIONS_VALUE="
set "PAPER_TOTAL_EQUITY="
set "PAPER_STATE_EXISTS="
if exist "%~dp0.venv\Scripts\python.exe" if exist "%~dp0paper_trading_engine.py" (
  for /f "tokens=1,* delims==" %%A in ('"%~dp0.venv\Scripts\python.exe" "%~dp0paper_trading_engine.py" --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL! 2^>nul') do (
    set "%%A=%%B"
  )
)

set "POLICY_CAPITAL=!AA_PAPER_CAPITAL!"
if not "!PAPER_TOTAL_EQUITY!"=="" set "POLICY_CAPITAL=!PAPER_TOTAL_EQUITY!"
set "POLICY_PROFILE="
set "POLICY_REBALANCE_EVERY="
set "POLICY_TOP_K="
set "POLICY_MAX_POSITION="
set "POLICY_MAX_ISSUER="
set "POLICY_MAX_TURNOVER="
set "POLICY_NO_TRADE_BAND="
set "POLICY_MIN_TRADE_VALUE="
if exist "%~dp0.venv\Scripts\python.exe" if exist "%~dp0paper_trading_engine.py" (
  for /f "tokens=1,* delims==" %%A in ('"%~dp0.venv\Scripts\python.exe" "%~dp0paper_trading_engine.py" --print-policy --capital !POLICY_CAPITAL! --fee-model trading212_us --trading212-policy !AA_TRADING212_POLICY! 2^>nul') do (
    set "%%A=%%B"
  )
)



echo ============================================================
echo Active Alpha Trading 212 - Aktive Konfiguration
echo ============================================================
echo.
echo Allgemein
echo   Benchmark:                  !AA_BENCHMARK!
echo   Startdatum:                 !AA_START_DATE!
echo   Signal-Lookback-Jahre:      !AA_SIGNAL_LOOKBACK_YEARS!
echo   Backtest-Kapital:           !AA_BACKTEST_CAPITAL!
echo   Research-Kapital:           !AA_RESEARCH_BACKTEST_CAPITAL!
echo   Paper-Start-/Fallback:      !AA_PAPER_CAPITAL!
echo   Max Gross Exposure:         !AA_MAX_GROSS_EXPOSURE!
echo.
echo Universum / Daten
echo   Backtest-Tickerquelle:      !AA_BACKTEST_TICKER_SOURCE!
echo   Paper-Tickerquelle:         !AA_PAPER_TICKER_SOURCE!
echo   Universe Mode:              !AA_UNIVERSE_MODE!
echo   Universe Top-N:             !AA_UNIVERSE_TOP_N!
echo   Universe ADV Lookback:      !AA_UNIVERSE_ADV_LOOKBACK!
echo   Universe Min ADV:           !AA_UNIVERSE_MIN_ADV!
echo   Universe Min Price:         !AA_UNIVERSE_MIN_PRICE!
echo   Membership-Datei:           !AA_MEMBERSHIP_FILE!
echo   Backtest Membership Mode:   !AA_BACKTEST_MEMBERSHIP_MODE!
echo   Paper Membership Mode:      !AA_PAPER_MEMBERSHIP_MODE!
echo   Asset-Master-Datei:         !AA_ASSET_MASTER_FILE!
echo.
echo Modell / Portfolio
echo   Horizon:                    !AA_HORIZON!
echo   Rebalance Every:            !AA_REBALANCE_EVERY!
echo   Top-K:                      !AA_TOP_K!
echo   Max Position:               !AA_MAX_POSITION!
echo   Max Issuer:                 !AA_MAX_ISSUER!
echo   Max Sector:                 !AA_MAX_SECTOR!
echo   Max Correlation Cluster:    !AA_MAX_CORRELATION_CLUSTER!
echo   Max Portfolio Beta:         !AA_MAX_PORTFOLIO_BETA!
echo   Beta Cap Mode:              !AA_BETA_CAP_MODE!
echo   Dynamic Beta Caps:          off=!AA_DYNAMIC_BETA_RISK_OFF! normal=!AA_DYNAMIC_BETA_NORMAL! riskon=!AA_DYNAMIC_BETA_RISK_ON! strong=!AA_DYNAMIC_BETA_STRONG!
echo   Static/Dynamic Cluster Cap: !AA_STATIC_CLUSTER_CAP! / !AA_DYNAMIC_CLUSTER_CAP!
echo   Cluster Constraint Mode:    !AA_CLUSTER_CONSTRAINT_MODE!
echo   No-Trade-Band:              !AA_NO_TRADE_BAND!
echo   Weight Smoothing:           !AA_WEIGHT_SMOOTHING!
echo   Max Turnover:               !AA_MAX_TURNOVER!
echo   Alpha Model Mode:           !AA_ALPHA_MODEL_MODE!
echo   Extra Benchmarks:           !AA_EXTRA_BENCHMARKS!
echo   Naive Momentum Variants:    !AA_NAIVE_MOMENTUM_VARIANTS!
echo   Bootstrap Iterations:       !AA_BOOTSTRAP_ITERATIONS!
echo   Random Seed:                !AA_RANDOM_SEED!
echo   Risk-Regime Mode:           !AA_RISK_REGIME_MODE!
echo   Risk-off Selection:         mode=!AA_RISK_OFF_SELECTION_MODE! gate=!AA_RISK_OFF_GATE_MODE! mom_w=!AA_RISK_OFF_MOMENTUM_WEIGHT! q=!AA_RISK_OFF_MOMENTUM_RESCUE_QUANTILE!
echo   Exposure Controller:        !AA_EXPOSURE_CONTROLLER!
echo   Cash Filler Mode:           !AA_CASH_FILLER_MODE!
echo   Cash Filler Max Position:   !AA_CASH_FILLER_MAX_POSITION!
echo   Cash Filler Min Score:      !AA_CASH_FILLER_MIN_SCORE!
echo   Low-Beta Filler:            maxpos=!AA_LOW_BETA_FILLER_MAX_POSITION! beta_max=!AA_LOW_BETA_FILLER_BETA_MAX! min_score=!AA_LOW_BETA_FILLER_MIN_SCORE! max_vol63=!AA_LOW_BETA_FILLER_MAX_VOL_63!
echo   Exposure Recovery Policy:   !AA_EXPOSURE_RECOVERY_POLICY!
echo   Cluster Mode:               !AA_CLUSTER_MODE!
echo   Dynamic Cluster Short/Long: !AA_DYNAMIC_CLUSTER_WINDOW_SHORT! / !AA_DYNAMIC_CLUSTER_WINDOW_LONG!
echo   Dynamic Cluster Corr/Ovlp:  !AA_DYNAMIC_CLUSTER_CORR_THRESHOLD! / !AA_DYNAMIC_CLUSTER_MIN_OVERLAP!
echo   Reproducibility Mode:       !AA_REPRODUCIBILITY_MODE!
echo.
echo Tail-Pruning / Positionshygiene
echo   Tail-Prune aktiv:           !AA_TAIL_PRUNE_ENABLED!
echo   Residual Weight Floor:      !AA_RESIDUAL_WEIGHT_FLOOR!
echo   Residual Sell Min Value:    !AA_RESIDUAL_SELL_MIN_VALUE!
echo   Max Positions Soft/Hard:    !AA_MAX_N_POSITIONS_SOFT! / !AA_MAX_N_POSITIONS_HARD!
echo   Reallocate:                 !AA_TAIL_PRUNE_REALLOCATE!
echo   Max Reallocation per Name:  !AA_MAX_TAIL_REALLOCATION_PER_NAME!
echo   Reallocation Step/Rounds:   !AA_TAIL_REALLOCATION_STEP! / !AA_TAIL_REALLOCATION_ROUNDS!
echo   Min Exposure Buffer:        !AA_TAIL_PRUNE_MIN_EXPOSURE_BUFFER!
echo.
echo Execution / Kosten
echo   Execution Policy Mode:      !AA_EXECUTION_POLICY_MODE!
echo   Trading-212 Policy:         !AA_TRADING212_POLICY!
echo   Slippage BPS:               !AA_SLIPPAGE_BPS!
echo   Market Impact BPS:          !AA_MARKET_IMPACT_BPS!
echo   FX BPS:                     !AA_TRADING212_FX_BPS!
echo   SEC Fee Rate:               !AA_TRADING212_SEC_FEE_RATE!
echo   FINRA TAF per Share:        !AA_TRADING212_FINRA_TAF_PER_SHARE!
echo   Fractional Shares:          !AA_FRACTIONAL!
if not "!POLICY_PROFILE!"=="" (
  echo.
  echo Effektive Kapital-Policy
  echo   Policy-Kapital:            !POLICY_CAPITAL!
  echo   Profil:                    !POLICY_PROFILE!
  echo   Rebalance / Top-K:         !POLICY_REBALANCE_EVERY!d / !POLICY_TOP_K!
  echo   MaxPos / MaxIssuer:        !POLICY_MAX_POSITION! / !POLICY_MAX_ISSUER!
  echo   Turnover / Band:           !POLICY_MAX_TURNOVER! / !POLICY_NO_TRADE_BAND!
  echo   MinOrder:                  !POLICY_MIN_TRADE_VALUE!
) else (
  echo.
  echo Effektive Kapital-Policy:    nicht verfuegbar ^(.venv fehlt oder Paper Engine nicht lesbar^)
)
echo.
echo Paper-Ledger aktuell
echo   Paper-Ordner:               !AA_PAPER_DIR!
if "!PAPER_TOTAL_EQUITY!"=="" (
  echo   Aktuelle Paper-Equity:     nicht verfuegbar ^(.venv fehlt oder Paper Engine nicht lesbar^)
) else (
  echo   Paper Cash:                !PAPER_CASH! USD
  echo   Paper Positionswert:       !PAPER_POSITIONS_VALUE! USD
  echo   Paper Total Equity:        !PAPER_TOTAL_EQUITY! USD
  echo   Paper State vorhanden:     !PAPER_STATE_EXISTS!
)
echo   Hinweis: Backtest und Paper nutzen getrennte Kapitalwerte. Paper-Cashflows aendern das Ledger, nicht AA_PAPER_CAPITAL.
echo.
echo Outputs
echo   Backtest Output:            !AA_BACKTEST_OUT_DIR!
echo   Paper Model Output:         !AA_PAPER_MODEL_OUT_DIR!
echo   Paper Depot:                !AA_PAPER_DIR!
echo.
echo Performance / Cache
echo   N-Jobs / CPU Cores:         !AA_N_JOBS! / !AA_CPU_CORES!
echo   Backend / RAM / Profile:    !AA_PARALLEL_BACKTEST_BACKEND! / !AA_SYSTEM_RAM_GB! GB / !AA_PARALLEL_PROFILE!
echo   Reuse Feature Cache:        !AA_REUSE_FEATURE_CACHE!
echo   Reuse Prediction Cache:     !AA_REUSE_PREDICTION_CACHE!
echo   Skip Download if Cached:    !AA_SKIP_DOWNLOAD_IF_CACHED!
echo   Shared Cache Dir:           !AA_SHARED_CACHE_DIR!
echo   Robustness Parallel Jobs:   !AA_ROBUSTNESS_PARALLEL_JOBS!
if exist "%~dp0.venv\Scripts\python.exe" (
  echo.
  echo Cache-Status Backtest-Output:
  "%~dp0.venv\Scripts\python.exe" "%~dp0active_alpha_model.py" --cache-status --out-dir "!AA_BACKTEST_OUT_DIR!" --membership-mode !AA_BACKTEST_MEMBERSHIP_MODE! 2^>nul
) else (
  echo   Cache-Status:              .venv fehlt
)
echo.
if exist "%~dp0active_alpha_user_config.bat" (
  echo User-Override aktiv: active_alpha_user_config.bat
) else (
  echo User-Override aktiv: nein, Standardwerte aus active_alpha_settings.bat
)
echo.
pause
endlocal
