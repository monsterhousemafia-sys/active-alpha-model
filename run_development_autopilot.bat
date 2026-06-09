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
set "AA_PROCESS_PRIORITY=high"

if /I "%~1"=="loop" (
  echo [%DATE% %TIME%] Development autopilot LOOP ^(Ctrl+C to stop^)
  "%PYEXE%" tools\run_pipeline_autopilot.py --loop --interval 300
  exit /b %ERRORLEVEL%
)

echo [%DATE% %TIME%] Development autopilot ONCE
"%PYEXE%" tools\run_pipeline_autopilot.py --once
exit /b %ERRORLEVEL%
