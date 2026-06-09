@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "TASK_NAME=Active Alpha Evolution Woechentlich"
set "SCRIPT=%~dp0run_live_weekly_learning_scheduled.bat"
set "SCHTIME=10:00"
set "INTERACTIVE=1"
if /I "%~1"=="--quiet" set "INTERACTIVE=0"

call "%~dp0setup_active_alpha_env.bat" >nul 2>&1
set "PY=%~dp0.venv\Scripts\python.exe"

echo ============================================================
echo   Evolution Sportwagen -^> Rennwagen
echo   Woechentlich: Feedback + Live-Ledger + Auto-Apply (safe)
echo ============================================================
echo.

if not exist "%SCRIPT%" (
  echo [FEHLER] %SCRIPT% fehlt
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo Bestehende Aufgabe wird aktualisiert ...
  schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC WEEKLY /D SUN /ST %SCHTIME% /RL LIMITED /F
if errorlevel 1 (
  echo [FEHLER] Task konnte nicht erstellt werden — als Administrator ausfuehren.
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

echo [OK] %TASK_NAME% — Sonntag %SCHTIME% (lokal)
echo  Bericht: evidence\learning_cycle_audit_latest.json
echo  Auto-Apply: evidence\evolution_auto_apply_latest.json
echo.

if "%INTERACTIVE%"=="1" pause
exit /b 0
