@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "TASK_NAME=Marktanalyse Learning EOD Catchup"
set "SCRIPT=%~dp0run_learning_eod_catchup.bat"
set "SCHTIME=22:15"

echo ============================================================
echo Windows-Aufgabe: taeglicher Learning EOD Catchup
echo ============================================================
echo Aufgabe: %TASK_NAME%
echo Skript:  %SCRIPT%
echo Uhrzeit: %SCHTIME% (lokal, nach US-Schluss)
echo.

if not exist "%SCRIPT%" (
  echo [ERROR] Skript fehlt: %SCRIPT%
  exit /b 1
)

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Entferne bestehende Aufgabe ...
  schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC DAILY /ST %SCHTIME% /RL LIMITED /F
if errorlevel 1 (
  echo [ERROR] Aufgabe konnte nicht erstellt werden.
  echo         Bitte PowerShell/CMD als Administrator ausfuehren.
  exit /b 1
)

echo [OK] Geplante Aufgabe erstellt.
echo      Taeglich um %SCHTIME%: EOD-Closes + Broker-Snapshot ^(headless^).
echo      Log: evidence\learning_eod_catchup_latest.json
echo.
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V | findstr /I "TaskName Next Run Time Status"
exit /b 0
