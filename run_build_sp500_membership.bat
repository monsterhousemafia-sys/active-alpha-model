@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo Active Alpha Trading 212 - S&P-500-PIT-Membership
echo ============================================================
echo Arbeitsordner: %CD%
echo.

set "START_DATE=2012-01-01"
set /p "USER_START=Historisches Startdatum YYYY-MM-DD [2012-01-01]: "
if not "!USER_START!"=="" set "START_DATE=!USER_START!"

set "OUTPUT_FILE=ticker_membership.csv"
set /p "USER_OUTPUT=Output-Datei [ticker_membership.csv]: "
if not "!USER_OUTPUT!"=="" set "OUTPUT_FILE=!USER_OUTPUT!"

echo.
echo ============================================================
echo Konfiguration
echo ============================================================
echo   Startdatum:    !START_DATE!
echo   Output-Datei:  !OUTPUT_FILE!
echo.

call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)

set "PYEXE=%~dp0.venv\Scripts\python.exe"

echo.
echo [INFO] Baue Membership-Datei ...
"!PYEXE!" build_sp500_membership_wikipedia.py --start-date "!START_DATE!" --out "!OUTPUT_FILE!"
if errorlevel 1 (
  echo [ERROR] Membership-Build fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo [OK] Membership-Datei erstellt: !OUTPUT_FILE!
pause
endlocal
