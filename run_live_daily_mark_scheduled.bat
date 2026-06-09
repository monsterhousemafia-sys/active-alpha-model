@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "AA_NONINTERACTIVE=1"
set "AA_SCHEDULED_LIVE_TASK=1"
set "AA_PLAIN_PROGRESS=1"

call "%~dp0load_active_alpha_config.bat"
call "%~dp0active_alpha_marktanalyse_os.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1

set "PY=%~dp0.venv\Scripts\python.exe"
set "LOG=%~dp0evidence\live_trading_scheduled_run.log"

echo [%DATE% %TIME%] Tages-Mark (enqueue only) >> "%LOG%"

"%PY%" -c "from pathlib import Path; from analytics.prediction_operations import ensure_prediction_before_orders, orders_config; r=Path(r'%~dp0'); o=orders_config(r); import sys; g=ensure_prediction_before_orders(r, auto_run=bool(o.get('auto_run_predict_on_scheduled_mark', True))) if o.get('require_prediction_ready', True) else {'ok': True}; sys.exit(0 if g.get('ok') or g.get('skipped') else 3)" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [BLOCKIERT] Predict nicht bereit — zuerst Signal-Update ^(22:15^) oder manuell run_tomorrow_prediction.py >> "%LOG%"
  "%PY%" -c "from pathlib import Path; from tools.preflight_live_daily_task import record_scheduled_run; record_scheduled_run(Path(r'%~dp0'), exit_code=3, summary_de='Blockiert: Predict fehlt')"
  exit /b 3
)

"%PY%" tools\preflight_live_daily_task.py --scheduled --enforce --human >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [BLOCKIERT] Checkliste nicht erfuellt — siehe evidence\live_trading_daily_task_preflight_latest.txt >> "%LOG%"
  "%PY%" -c "from pathlib import Path; from tools.preflight_live_daily_task import record_scheduled_run; record_scheduled_run(Path(r'%~dp0'), exit_code=2, summary_de='Blockiert: Checkliste nicht erfuellt')"
  exit /b 2
)

"%PY%" -m analytics.live_trading_operations --mode daily >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  set "SUMMARY=Mark + Sync OK, Vormerkung wenn faellig"
  "%PY%" tools\run_competition_shadow_snapshot.py >> "%LOG%" 2>&1
  "%PY%" tools\build_competition_readiness.py >> "%LOG%" 2>&1
) else (
  set "SUMMARY=Tages-Mark fehlgeschlagen"
)

"%PY%" -c "from pathlib import Path; from tools.preflight_live_daily_task import record_scheduled_run; record_scheduled_run(Path(r'%~dp0'), exit_code=%RC%, summary_de=r'%SUMMARY%')"

if not "%RC%"=="0" exit /b %RC%
echo [OK] %SUMMARY% >> "%LOG%"
exit /b 0
