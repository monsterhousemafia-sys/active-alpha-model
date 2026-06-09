@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "TASK_NAME=ActiveAlpha Betriebsdaten Refresh"
set "SCRIPT=%~dp0refresh_active_alpha_ops.bat"
set "SCHTIME=22:00"

echo ============================================================
echo Windows-Aufgabe: taeglicher Betriebsdaten-Refresh
echo ============================================================
echo Aufgabe: %TASK_NAME%
echo Skript:  %SCRIPT%
echo Uhrzeit: %SCHTIME% (lokal)
echo.

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo [INFO] Entferne bestehende Aufgabe ...
  schtasks /Delete /TN "%TASK_NAME%" /F >nul
)

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC DAILY /ST %SCHTIME% /RL LIMITED /F
if errorlevel 1 (
  echo [ERROR] Aufgabe konnte nicht erstellt werden. Bitte als Administrator ausfuehren.
  exit /b 1
)

echo [OK] Geplante Aufgabe erstellt.
echo      Taeglich um %SCHTIME% werden Kurse, Universum, Signal und Paper-MTM aktualisiert.
echo      Marktanalyse.exe kann danach direkt auf frische Caches zugreifen.
exit /b 0
