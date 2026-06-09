@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0active_alpha_marktanalyse_os.bat"
set "AA_NONINTERACTIVE=1"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "PYEXE=%~dp0.venv\Scripts\python.exe"
echo ============================================================
echo Active Alpha - Live Trading Daily Sync (Paper: 1_daily mark)
echo ============================================================
"%PYEXE%" -m analytics.live_trading_operations --mode daily
if errorlevel 1 (
  echo [ERROR] Live daily sync fehlgeschlagen.
  pause
  exit /b 1
)
echo [OK] Mark + T212-Sync. Status: live_pilot\confirmed_execution\live_trading_next_rebalance.json
if /I not "!AA_NONINTERACTIVE!"=="1" pause
endlocal
