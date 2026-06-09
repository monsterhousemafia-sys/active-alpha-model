@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set "PY=.venv\Scripts\python.exe") else (set "PY=python")
"%PY%" "%~dp0aa_live_trading_launch.py" --skip-preflight %*
exit /b %ERRORLEVEL%
