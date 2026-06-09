@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0load_active_alpha_config.bat"
if errorlevel 1 (
  echo [FEHLER] Konfiguration konnte nicht geladen werden.
  pause
  exit /b 1
)
call "%~dp0active_alpha_marktanalyse_os.bat"

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

rem Standard: Marktanalyse.exe wenn vorhanden (Phasen 0-5). --python erzwingt .venv-UI.
set "USE_EXE=1"
if /I "%~1"=="--python" set "USE_EXE=0"
if /I "%~1"=="python" set "USE_EXE=0"
if /I "%~1"=="--exe" set "USE_EXE=1"
if /I "%~1"=="exe" set "USE_EXE=1"
if not exist "%~dp0Marktanalyse.exe" set "USE_EXE=0"

echo ============================================================
echo Live-Trading Dashboard (wie Paper) — Start
echo ============================================================
echo Paper-Rhythmus: 1_live_daily_sync / 2_live_rebalance_when_due
echo.
echo Modus: !USE_EXE!  ^(0=Python .venv, 1=Marktanalyse.exe + .venv fuer Signal^)
echo AA_RUN_MODE=!AA_RUN_MODE!
echo.

"%PY%" "%~dp0aa_live_trading_launch.py" --preflight-only
if errorlevel 1 (
  echo.
  echo [FEHLER] Preflight fehlgeschlagen — UI wird nicht gestartet.
  echo Tipp: Log oben lesen; alternativ run_live_trading_dev_fast.bat --skip-preflight
  pause
  exit /b 1
)

if "!USE_EXE!"=="1" (
  if not exist "%~dp0Marktanalyse.exe" (
    echo [FEHLER] Marktanalyse.exe fehlt. Build: .venv\Scripts\python.exe tools\build_v5r_standalone_exe.py
    pause
    exit /b 1
  )
  if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [FEHLER] .venv fehlt — Signal/Rebalance in der EXE brauchen den Projekt-.venv.
    echo        Bitte setup_active_alpha_env.bat ausfuehren.
    pause
    exit /b 1
  )
  echo [INFO] Starte Marktanalyse.exe ^(Projektordner + .venv fuer Signal ②/③^).
  start "" "%~dp0Marktanalyse.exe"
  exit /b 0
)

echo [INFO] Starte Live-Trading-UI ^(Python / aa_live_trading_launch.py^).
start "" "%PY%" "%~dp0aa_live_trading_launch.py" --skip-preflight
exit /b 0
