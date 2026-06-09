@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0.."
call "%~dp0..\setup_active_alpha_env.bat" >nul 2>&1
set "PY=%~dp0..\.venv\Scripts\python.exe"
set "ROOT=%~dp0.."
if /I "%~1"=="setup" goto setup
if /I "%~1"=="h1" goto h1
if /I "%~1"=="sync" goto sync
if /I "%~1"=="status" goto status
echo Usage: tools\linux_source_compute.bat [setup ^| h1 ^| sync ^| status]
exit /b 1
:status
"%PY%" -c "from pathlib import Path; from analytics.linux_compute_router import write_evidence,routing_doc; import json; r=Path(r'%ROOT%'); write_evidence(r); print(json.dumps(routing_doc(r),indent=2))"
exit /b 0
:setup
echo [INFO] WSL Setup ...
wsl bash -lc "cd /mnt/e/active_alpha_model && bash tools/wsl_conductor.sh setup"
"%PY%" -c "from pathlib import Path; from analytics.linux_compute_router import write_evidence; write_evidence(Path(r'%ROOT%'))"
exit /b %ERRORLEVEL%
:sync
wsl bash -lc "rsync -a --exclude .venv --exclude __pycache__ /mnt/e/active_alpha_model/ $HOME/active_alpha_model/"
exit /b %ERRORLEVEL%
:h1
"%PY%" tools\run_daily_alpha_h1_pipeline.py --restart --poll-seconds 120
exit /b %ERRORLEVEL%
