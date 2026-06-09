@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat"

echo ============================================================
echo Active Alpha Trading 212 - Paper Status / Dashboard
echo ============================================================
echo Arbeitsordner: %CD%
echo.
echo   Paper-Ordner: !AA_PAPER_DIR!
echo   Paper-Start-/Fallbackkapital: !AA_PAPER_CAPITAL!
echo   Policy:       !AA_TRADING212_POLICY!
echo.

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

set "PAPER_CASH="
set "PAPER_POSITIONS_VALUE="
set "PAPER_TOTAL_EQUITY="
for /f "tokens=1,* delims==" %%A in ('"!PYEXE!" paper_trading_engine.py --print-current-equity --paper-dir "!AA_PAPER_DIR!" --capital !AA_PAPER_CAPITAL!') do (
  set "%%A=%%B"
)
echo.
echo [INFO] Aktuelles Paper-Ledger:
echo   Paper Cash:             !PAPER_CASH! USD
echo   Paper Positionswert:    !PAPER_POSITIONS_VALUE! USD
echo   Paper Total Equity:     !PAPER_TOTAL_EQUITY! USD

"!PYEXE!" paper_trading_engine.py ^
  --mode status ^
  --paper-dir "!AA_PAPER_DIR!" ^
  --benchmark !AA_BENCHMARK! ^
  --capital !AA_PAPER_CAPITAL! ^
  --trading212-policy !AA_TRADING212_POLICY!

if errorlevel 1 (
  echo [ERROR] Status-Lauf fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo Dashboard
echo ============================================================
if exist "!AA_PAPER_DIR!\paper_dashboard.txt" type "!AA_PAPER_DIR!\paper_dashboard.txt"
echo.
pause
endlocal
