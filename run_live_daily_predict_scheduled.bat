@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "AA_NONINTERACTIVE=1"
set "AA_PLAIN_PROGRESS=1"

call "%~dp0load_active_alpha_config.bat"
call "%~dp0active_alpha_marktanalyse_os.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1

set "PY=%~dp0.venv\Scripts\python.exe"
set "LOG=%~dp0evidence\live_trading_scheduled_run.log"

echo [%DATE% %TIME%] Signal-Update (predict) >> "%LOG%"

"%PY%" -u tools\run_tomorrow_prediction.py
set "RC=%ERRORLEVEL%"

"%PY%" -c "from pathlib import Path; from tools.preflight_live_daily_task import record_scheduled_run; record_scheduled_run(Path(r'%~dp0'), exit_code=%RC%, summary_de='EOD Signal-Update (predict)')"

if not "%RC%"=="0" (
  echo [FEHLER] Signal-Update fehlgeschlagen — siehe evidence\tomorrow_prediction\latest.json >> "%LOG%"
  exit /b %RC%
)
echo [OK] Signal-Update abgeschlossen. >> "%LOG%"
exit /b 0
