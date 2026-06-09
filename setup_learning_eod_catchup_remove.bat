@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "TASK_NAME=Marktanalyse Learning EOD Catchup"
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1 && echo [OK] Task entfernt || echo [INFO] Kein Task vorhanden
exit /b 0
