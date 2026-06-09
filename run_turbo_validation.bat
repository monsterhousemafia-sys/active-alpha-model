@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 exit /b 1
set "AA_CPU_CORES=16"
set "AA_RESERVE_CPU_CORES=0"
set "AA_RUNTIME_PROFILE=turbo"
set "AA_PROCESS_PRIORITY=high"
set "AA_PARALLEL_PROFILE=high"
echo [TURBO] 16 Kerne, High-Priority, sequentiell: cost s5 -^> M1
"%~dp0.venv\Scripts\python.exe" tools\run_turbo_finish.py
exit /b %ERRORLEVEL%
