@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "PYEXE=%~dp0.venv\Scripts\python.exe"
set "AA_JOB_REALTIME_COLLECT_ENABLED=0"
echo [%DATE% %TIME% UTC-local] realtime_collect (default disabled)
"%PYEXE%" tools\run_background_job.py realtime_collect
exit /b %ERRORLEVEL%
