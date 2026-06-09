@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "PYEXE=%~dp0.venv\Scripts\python.exe"
set "AA_JOB_FEEDBACK_UPDATE_ENABLED=0"
echo [%DATE% %TIME% UTC-local] feedback_update — outcome ledger sync (default disabled)
"%PYEXE%" tools\run_background_job.py feedback_update
exit /b %ERRORLEVEL%
