@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0active_alpha_marktanalyse_os.bat"
set "AA_NONINTERACTIVE=1"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "PYEXE=%~dp0.venv\Scripts\python.exe"
set "STATUS_FILE=%~dp0live_pilot\confirmed_execution\live_trading_next_rebalance.json"
set "REC="
if exist "!STATUS_FILE!" (
  for /f "tokens=1,* delims=:" %%A in ('findstr /B /C:"recommendation:" "!STATUS_FILE!" 2^>nul') do set "REC=%%B"
  set "REC=!REC: =!"
)
if /I not "!REC!"=="REBALANCE_DUE" (
  if /I not "!REC!"=="REBALANCE_DUE_NO_HISTORY" (
    echo [INFO] Kein Rebalance faellig. Empfehlung: !REC!
    call "%~dp0\1_live_daily_sync.bat"
    exit /b 0
  )
)
echo.
set "START=J"
set /p "START=Rebalance faellig. Signal + Live-Orders starten? J/n [J]: "
if /I "!START!"=="N" (
  echo [INFO] Abgebrochen.
  pause
  exit /b 0
)
"%PYEXE%" -m analytics.live_trading_operations --mode rebalance
pause
endlocal
