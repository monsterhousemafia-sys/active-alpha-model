@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "TASK_NAME=Active Alpha Tages-Mark Mo-Fr"
set "SCRIPT=%~dp0run_live_daily_mark_scheduled.bat"
set "SCHTIME=15:25"
set "INTERACTIVE=1"
if /I "%~1"=="--quiet" set "INTERACTIVE=0"

call "%~dp0setup_active_alpha_env.bat" >nul 2>&1
set "PY=%~dp0.venv\Scripts\python.exe"

"%PY%" -c "from tools.live_daily_task_ui import format_setup_banner; print(format_setup_banner())"

if not exist "%SCRIPT%" (
  echo [FEHLER] Installationsdatei fehlt:
  echo          %SCRIPT%
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

echo  Systemcheck vor der Registrierung ...
echo.
"%PY%" tools\preflight_live_daily_task.py --scheduled --human
set "PF=%ERRORLEVEL%"
echo.

if not "%PF%"=="0" (
  echo  Hinweis: Die Aufgabe wird registriert, startet aber erst,
  echo           wenn alle Pflichtpunkte erfuellt sind.
  echo           Details: evidence\live_trading_daily_task_preflight_latest.txt
  echo.
)

schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if not errorlevel 1 (
  echo  Bestehende Windows-Aufgabe wird aktualisiert ...
  schtasks /Delete /TN "%TASK_NAME%" /F >nul
)
schtasks /Query /TN "Active Alpha Live Daily Mark" >nul 2>&1
if not errorlevel 1 schtasks /Delete /TN "Active Alpha Live Daily Mark" /F >nul

schtasks /Create /TN "%TASK_NAME%" /TR "\"%SCRIPT%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST %SCHTIME% /RL LIMITED /F
if errorlevel 1 (
  echo.
  echo  [FEHLER] Windows-Aufgabe konnte nicht erstellt werden.
  echo           Bitte diese Datei als Administrator ausfuehren:
  echo           Rechtsklick ^> Als Administrator ausfuehren
  echo.
  if "%INTERACTIVE%"=="1" pause
  exit /b 1
)

for /f "delims=" %%N in ('schtasks /Query /TN "%TASK_NAME%" /FO LIST /V ^| findstr /I "Next Run Time"') do set "NEXT_RUN=%%N"

"%PY%" -c "from tools.live_daily_task_ui import format_task_registered; print(format_task_registered('%TASK_NAME%', 'Montag-Freitag %SCHTIME% (lokal)', r'%NEXT_RUN%'.strip() or 'Taskplaner oeffnen'))"

echo  Empfohlen zusaetzlich:
echo    setup_live_daily_predict_task.bat  - Signal abends 22:15
echo    check_live_daily_setup.bat         - Status jederzeit pruefen
echo.

if "%INTERACTIVE%"=="1" pause
exit /b 0
