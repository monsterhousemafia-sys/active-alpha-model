@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0load_active_alpha_config.bat"

call "%~dp0run_paper_status.bat"
if errorlevel 1 (
  echo [ERROR] Paper-Status konnte nicht aktualisiert werden.
  pause
  exit /b 1
)

set "NEXT_REBALANCE_FILE=%~dp0!AA_PAPER_DIR!\next_rebalance_due.txt"
set "NEXT_REBALANCE_RECOMMENDATION="
if exist "!NEXT_REBALANCE_FILE!" (
  for /f "tokens=1,* delims=:" %%A in ('findstr /B /C:"recommendation:" "!NEXT_REBALANCE_FILE!" 2^>nul') do set "NEXT_REBALANCE_RECOMMENDATION=%%B"
  set "NEXT_REBALANCE_RECOMMENDATION=!NEXT_REBALANCE_RECOMMENDATION: =!"
)

if /I not "!NEXT_REBALANCE_RECOMMENDATION!"=="REBALANCE_DUE" (
  echo.
  echo [INFO] Kein Rebalance faellig. Empfehlung: !NEXT_REBALANCE_RECOMMENDATION!
  echo [INFO] Fuehre stattdessen nur run_paper_mark_to_market.bat aus.
  call "%~dp0run_paper_mark_to_market.bat"
  if errorlevel 1 (
    echo [ERROR] Mark-to-Market fehlgeschlagen.
    pause
    exit /b 1
  )
  pause
  exit /b 0
)

echo.
set "START_REBALANCE=J"
set /p "START_REBALANCE=Rebalance ist faellig. Jetzt Rebalance starten? J/n [J]: "
if /I "!START_REBALANCE!"=="N" (
  echo [INFO] Rebalance abgebrochen.
  pause
  exit /b 0
)

call "%~dp0run_paper_trading.bat"
endlocal
