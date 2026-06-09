@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "TASK_NAME=Active Alpha Signal Update"
set "SCRIPT=%~dp0run_live_daily_predict_scheduled.bat"
set "SCHTIME=22:15"
set "INTERACTIVE=1"
if /I "%~1"=="--quiet" set "INTERACTIVE=0"

call "%~dp0setup_active_alpha_env.bat" >nul 2>&1
set "PY=%~dp0.venv\Scripts\python.exe"

echo.
echo  Active Alpha - Signal-Update planen
echo  ===================================
echo  Taeglich %SCHTIME%: Profil daily_alpha_h1, frische Kurse, Portfolio-CSV
echo.

if not exist "%SCRIPT%" (
  echo [FEHLER] %SCRIPT% fehlt
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo  Aktualisiere bestehende Aufgabe ...
  schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC DAILY /ST %SCHTIME% /RL LIMITED /F
if errorlevel 1 (
  echo  [FEHLER] Bitte als Administrator ausfuehren.
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

echo  [OK] Signal-Update registriert (taeglich %SCHTIME%).
schtasks /Query /TN "%TASK_NAME%" /FO LIST /V | findstr /I "Status Next Run Time"
echo.
if "%INTERACTIVE%"=="1" pause
exit /b 0
