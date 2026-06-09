@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "LAUNCHER=%~dp0Marktanalyse_start.bat"
set "EXE=%~dp0Marktanalyse.exe"
set "WORKDIR=%~dp0"
if "%WORKDIR:~-1%"=="\" set "WORKDIR=%WORKDIR:~0,-1%"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\R3 Marktanalyse.lnk"
set "TASK=R3 Marktanalyse"
set "ICON=%~dp0Marktanalyse.ico"
if not exist "%ICON%" set "ICON=%~dp0assets\marktanalyse_r3.ico"

echo ============================================================
echo Windows-Autostart: Marktanalyse.exe bei Anmeldung
echo ============================================================

if not exist "%EXE%" (
  echo [ERROR] Marktanalyse.exe fehlt: %EXE%
  echo         Bitte zuerst tools\build_v5r_standalone_exe.py ausfuehren.
  exit /b 1
)
if not exist "%LAUNCHER%" (
  echo [WARN] Marktanalyse_start.bat fehlt — Autostart nutzt nur EXE ohne OS-Profil.
  set "LAUNCHER=%EXE%"
)

echo [INFO] Erstelle Autostart-Verknuepfung ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath='%LAUNCHER%';" ^
  "$s.WorkingDirectory='%WORKDIR%';" ^
  "$s.WindowStyle=1;" ^
  "$s.Description='R3 Marktanalyse Autostart';" ^
  "if (Test-Path '%ICON%') { $s.IconLocation='%ICON%,0' };" ^
  "$s.Save()"
if errorlevel 1 (
  echo [ERROR] Autostart-Verknuepfung fehlgeschlagen.
  exit /b 1
)
echo [OK] Verknuepfung: %LINK%

echo [INFO] Registriere zuverlaessigen Task-Scheduler-Eintrag (15s Verzoegerung) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\register_marktanalyse_autostart.ps1" -ExePath "%LAUNCHER%" -WorkDir "%WORKDIR%"
if errorlevel 1 (
  echo [WARN] Task-Scheduler fehlgeschlagen — nur Verknuepfung aktiv.
) else (
  echo [OK] Geplanter Task: %TASK% (Anmeldung + 15s)
)

echo.
echo [INFO] Pruefung ...
if exist "%LINK%" (echo   Verknuepfung: vorhanden) else (echo   Verknuepfung: FEHLT)
schtasks /Query /TN "%TASK%" >nul 2>&1 && echo   Task-Scheduler: registriert || echo   Task-Scheduler: nicht registriert
echo.
echo Marktanalyse.exe startet bei Windows-Anmeldung.
echo Hinweis: Unter Einstellungen ^> Apps ^> Autostart muss der Eintrag aktiv sein.
echo Entfernen: setup_active_alpha_startup_remove.bat
exit /b 0
