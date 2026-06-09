@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"

echo ============================================================
echo Active Alpha Trading 212 - Paper Mark-to-Market
echo ============================================================
echo Arbeitsordner: %CD%
echo.
echo   Paper-Ordner:       !AA_PAPER_DIR!
echo   Benchmark:          !AA_BENCHMARK!
echo   Paper-Start-/Fallbackkapital: !AA_PAPER_CAPITAL! USD
echo   Execution Policy:   !AA_EXECUTION_POLICY_MODE!
echo   Trading-212 Policy: !AA_TRADING212_POLICY!
echo   Slippage-BPS:       !AA_SLIPPAGE_BPS!
echo   FX-BPS:             !AA_TRADING212_FX_BPS!
echo   Price Lookback:     !AA_PRICE_LOOKBACK_DAYS!
echo   Price Interval:     !AA_PRICE_INTERVAL!
echo.

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

set "PAPER_CASH="
set "PAPER_POSITIONS_VALUE="
set "PAPER_TOTAL_EQUITY="
for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL!') do (
  set "%%A=%%B"
)
echo.
echo [INFO] Aktuelles Paper-Ledger:
echo   Paper Cash:             !PAPER_CASH! USD
echo   Paper Positionswert:    !PAPER_POSITIONS_VALUE! USD
echo   Paper Total Equity:     !PAPER_TOTAL_EQUITY! USD

set "AA_EXECUTION_POLICY_FLAG="
if /I "!AA_EXECUTION_POLICY_MODE!"=="capital_curve" set "AA_EXECUTION_POLICY_FLAG=--capital-curve-policy"

echo.
echo [INFO] Starte Mark-to-Market ...
"!PYEXE!" paper_trading_engine.py ^
  --mode mark ^
  --paper-dir "!AA_PAPER_DIR!" ^
  --benchmark !AA_BENCHMARK! ^
  --capital !AA_PAPER_CAPITAL! ^
  --fee-model trading212_us ^
  --slippage-bps !AA_SLIPPAGE_BPS! ^
  --market-impact-bps !AA_MARKET_IMPACT_BPS! ^
  --trading212-sec-fee-rate !AA_TRADING212_SEC_FEE_RATE! ^
  --trading212-finra-taf-per-share !AA_TRADING212_FINRA_TAF_PER_SHARE! ^
  --trading212-fx-bps !AA_TRADING212_FX_BPS! ^
  --trading212-policy !AA_TRADING212_POLICY! ^
  !AA_EXECUTION_POLICY_FLAG! ^
  --max-gross-exposure !AA_MAX_GROSS_EXPOSURE! ^
  --price-lookback-days !AA_PRICE_LOOKBACK_DAYS! ^
  --price-interval !AA_PRICE_INTERVAL! ^
  --execute

if errorlevel 1 (
  echo [ERROR] Mark-to-Market fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo [OK] Mark-to-Market abgeschlossen. Ergebnisse in !AA_PAPER_DIR!
echo [OK] Danach pruefen: !AA_PAPER_DIR!\paper_dashboard.txt und !AA_PAPER_DIR!\next_rebalance_due.txt
if /I not "!AA_NONINTERACTIVE!"=="1" pause
endlocal
