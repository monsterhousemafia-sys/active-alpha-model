@echo off
setlocal EnableExtensions
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\R3 Marktanalyse.lnk"
set "TASK=R3 Marktanalyse"

echo Entferne Autostart ...
if exist "%LINK%" del /F /Q "%LINK%" && echo [OK] Verknuepfung geloescht
schtasks /Delete /TN "%TASK%" /F >nul 2>&1 && echo [OK] Task-Scheduler entfernt || echo [INFO] Kein Task vorhanden
powershell -NoProfile -ExecutionPolicy Bypass -Command "Unregister-ScheduledTask -TaskName '%TASK%' -Confirm:$false -ErrorAction SilentlyContinue" >nul 2>&1
exit /b 0
