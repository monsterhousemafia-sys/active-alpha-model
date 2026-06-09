@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Active Alpha - Betriebsdaten periodisch aktualisieren
echo ============================================================

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" tools\run_ops_refresh.py
set "RC=%ERRORLEVEL%"

if %RC% EQU 0 (
  echo [OK] Betriebsdaten-Refresh abgeschlossen.
) else (
  echo [WARN] Betriebsdaten-Refresh mit Code %RC% beendet.
)

exit /b %RC%
