@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Pilot Live Trading aktivieren (manuell bestätigt, kein Auto)
echo ============================================================
echo.
echo Aktivierungsphrase wird angezeigt — kopieren und bestaetigen:
echo.

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" tools\enable_pilot_live_trading.py --show-phrase
echo.
set /p PHRASE=Aktivierungsphrase exakt einfuegen: 
"%PY%" tools\enable_pilot_live_trading.py --risk-ack --phrase "%PHRASE%"
exit /b %ERRORLEVEL%
