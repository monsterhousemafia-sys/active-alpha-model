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
set "LOG=%~dp0evidence\live_learning_weekly.log"

echo [%DATE% %TIME%] Weekly live learning sync >> "%LOG%"

"%PY%" tools\run_feedback_update.py >> "%LOG%" 2>&1
"%PY%" tools\sync_live_execution_outcomes.py >> "%LOG%" 2>&1
"%PY%" tools\run_competition_shadow_snapshot.py >> "%LOG%" 2>&1
"%PY%" tools\evaluate_daily_alpha_h1.py --seal-on-pass >> "%LOG%" 2>&1
"%PY%" tools\run_learning_cycle_audit.py --apply-safe >> "%LOG%" 2>&1

echo [OK] Weekly feedback + live sync + evolution audit >> "%LOG%"
exit /b 0
