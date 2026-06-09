@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"

echo ============================================================
echo Active Alpha Trading 212 - Paper Cashflow
echo ============================================================
echo Arbeitsordner: %CD%
echo.
echo Hinweis: Cashflows sind Paper-Buchungen. Sie platzieren keine echten Bank- oder Brokertransaktionen.
echo.

echo Cashflow-Typ:
echo   deposit  = Einzahlung in Paper-Cash
echo   withdraw = Auszahlung aus Paper-Cash
echo.
set "CASHFLOW_TYPE=deposit"
set /p "USER_TYPE=Cashflow-Typ deposit/withdraw [deposit]: "
if not "!USER_TYPE!"=="" set "CASHFLOW_TYPE=!USER_TYPE!"

set "AMOUNT="
set /p "AMOUNT=Betrag in USD, positiv eingeben: "
set "AMOUNT=!AMOUNT:,=.!"

if "!AMOUNT!"=="" (
  echo [ERROR] Kein Betrag eingegeben.
  pause
  exit /b 1
)

set "NOTE="
set /p "NOTE=Notiz fuer paper_cashflows.csv [optional]: "

echo.
echo ============================================================
echo Konfiguration
echo ============================================================
echo   Paper-Ordner:             !AA_PAPER_DIR!
echo   Typ:                      !CASHFLOW_TYPE!
echo   Betrag:                   !AMOUNT! USD
echo   Policy:                   !AA_TRADING212_POLICY!
echo.

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"
set "AA_EXECUTION_POLICY_FLAG="
if /I "!AA_EXECUTION_POLICY_MODE!"=="capital_curve" set "AA_EXECUTION_POLICY_FLAG=--capital-curve-policy"

rem Current paper ledger before cashflow. AA_PAPER_CAPITAL is only fallback when no state exists.
set "PAPER_CASH_BEFORE="
set "PAPER_POSITIONS_VALUE_BEFORE="
set "PAPER_TOTAL_EQUITY_BEFORE="
for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL!') do (
  if "%%A"=="PAPER_CASH" set "PAPER_CASH_BEFORE=%%B"
  if "%%A"=="PAPER_POSITIONS_VALUE" set "PAPER_POSITIONS_VALUE_BEFORE=%%B"
  if "%%A"=="PAPER_TOTAL_EQUITY" set "PAPER_TOTAL_EQUITY_BEFORE=%%B"
)
echo.
echo [INFO] Paper-Ledger vor Cashflow:
echo   Paper-Start-/Fallbackkapital: !AA_PAPER_CAPITAL! USD
echo   Paper Cash:             !PAPER_CASH_BEFORE! USD
echo   Paper Positionswert:    !PAPER_POSITIONS_VALUE_BEFORE! USD
echo   Paper Total Equity:     !PAPER_TOTAL_EQUITY_BEFORE! USD
echo.

"!PYEXE!" paper_trading_engine.py ^
  --mode cashflow ^
  --paper-dir "!AA_PAPER_DIR!" ^
  --benchmark !AA_BENCHMARK! ^
  --capital !AA_PAPER_CAPITAL! ^
  --cashflow-type !CASHFLOW_TYPE! ^
  --amount !AMOUNT! ^
  --note "!NOTE!" ^
  --trading212-policy !AA_TRADING212_POLICY! ^
  !AA_EXECUTION_POLICY_FLAG! ^
  --execute

if errorlevel 1 (
  echo [ERROR] Cashflow-Buchung fehlgeschlagen.
  pause
  exit /b 1
)


set "PAPER_CASH_AFTER="
set "PAPER_POSITIONS_VALUE_AFTER="
set "PAPER_TOTAL_EQUITY_AFTER="
for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL!') do (
  if "%%A"=="PAPER_CASH" set "PAPER_CASH_AFTER=%%B"
  if "%%A"=="PAPER_POSITIONS_VALUE" set "PAPER_POSITIONS_VALUE_AFTER=%%B"
  if "%%A"=="PAPER_TOTAL_EQUITY" set "PAPER_TOTAL_EQUITY_AFTER=%%B"
)
echo.
echo [OK] Paper-Ledger nach Cashflow:
echo   Paper Cash:             !PAPER_CASH_AFTER! USD
echo   Paper Positionswert:    !PAPER_POSITIONS_VALUE_AFTER! USD
echo   Paper Total Equity:     !PAPER_TOTAL_EQUITY_AFTER! USD
echo.
echo [OK] Cashflow abgeschlossen. Danach pruefen:
echo   !AA_PAPER_DIR!\paper_cashflows.csv
echo   !AA_PAPER_DIR!\paper_dashboard.txt
echo   !AA_PAPER_DIR!\paper_report.txt
echo.
pause
endlocal
