@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "INTERACTIVE=1"
if /I "%~1"=="--quiet" set "INTERACTIVE=0"

echo.
echo  Active Alpha - Komplett-Automatisierung
echo  =======================================
echo.
echo  Es werden zwei Windows-Aufgaben eingerichtet:
echo.
echo    1. Signal-Update     taeglich 22:15  (Modell + frische Kurse)
echo    2. Tages-Mark        Mo-Fr  15:25   (Konto, Vormerkung)
echo.
echo  Es werden KEINE Orders automatisch an Trading 212 gesendet.
echo.
if "%INTERACTIVE%"=="1" pause

call "%~dp0setup_live_daily_predict_task.bat" --quiet
call "%~dp0setup_live_daily_mark_task.bat" --quiet

echo.
echo  Fertig. Bitte Status pruefen:
echo    check_live_daily_setup.bat
echo.
if "%INTERACTIVE%"=="1" pause
exit /b 0
