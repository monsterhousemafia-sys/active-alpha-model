@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "PYEXE=%~dp0.venv\Scripts\python.exe"
set "AA_CPU_CORES=16"
set "AA_RESERVE_CPU_CORES=0"
set "AA_RUNTIME_PROFILE=turbo"
set "AA_JOB_EOD_FINALIZE_ENABLED=1"
set "AA_JOB_OPERATIONAL_REFINEMENT_ENABLED=1"
echo [%DATE% %TIME% UTC-local] eod_finalize + operational refinement
"%PYEXE%" tools\run_background_job.py eod_finalize
if errorlevel 1 exit /b %ERRORLEVEL%
"%PYEXE%" tools\run_background_job.py operational_refinement
exit /b %ERRORLEVEL%
