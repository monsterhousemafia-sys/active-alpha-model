@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo Active Alpha Trading 212 - Robustheitstests
echo ============================================================
echo Arbeitsordner: %CD%
echo.

echo Der Runner testet FX, Slippage, alle Policies ^(conservative/balanced/active/threshold^) und Universe-Breite gegen die Balanced-FX0-Basis.
echo Shared Feature/Price-Cache: robustness_results_trading212\_shared_cache
echo Parallel: 2 Varianten gleichzeitig ^(Standard^). Dry-run: python run_robustness_tests.py --dry-run
echo Resume: python run_robustness_tests.py --skip-completed
echo Ergebnisse: robustness_results_trading212\robustness_summary.csv/.txt
echo.

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

call "%~dp0load_active_alpha_config.bat"

set "PYEXE=%~dp0.venv\Scripts\python.exe"

"!PYEXE!" check_active_alpha_core.py
if errorlevel 1 (
  pause
  exit /b 1
)

call "%~dp0load_active_alpha_config.bat"

echo.
echo [INFO] Starte Robustheitstests ...
set "ROBUSTNESS_ARGS="
if not "!AA_SHARED_CACHE_DIR!"=="" set "ROBUSTNESS_ARGS=!ROBUSTNESS_ARGS! --shared-cache-dir "!AA_SHARED_CACHE_DIR!""
if not "!AA_ROBUSTNESS_PARALLEL_JOBS!"=="" set "ROBUSTNESS_ARGS=!ROBUSTNESS_ARGS! --parallel-jobs !AA_ROBUSTNESS_PARALLEL_JOBS!"
"!PYEXE!" run_robustness_tests.py !ROBUSTNESS_ARGS!
if errorlevel 1 (
  echo [ERROR] Robustheitstests fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo [OK] Robustheitstests abgeschlossen.
pause
endlocal
