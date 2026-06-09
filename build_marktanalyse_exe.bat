@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Marktanalyse.exe bauen (V5R onefile)
echo ============================================================
echo Ordner: %CD%
echo.

if exist "%~dp0Marktanalyse.exe" (
  echo [HINWEIS] Schliessen Sie alle laufenden Marktanalyse-Fenster
  echo         und beenden Sie Marktanalyse.exe im Task-Manager, falls der Build haengt.
  echo.
)

if not exist "%~dp0.venv\Scripts\python.exe" (
  echo [FEHLER] .venv fehlt hier:
  echo   %~dp0.venv\Scripts\python.exe
  echo.
  echo Bitte zuerst ausfuehren: setup_active_alpha_env.bat
  echo.
  pause
  exit /b 1
)

echo [INFO] Schritt 1/1: PyInstaller (Live-Ausgabe unten, 2-5 Minuten normal)
echo [INFO] Start: %DATE% %TIME%
echo.

set "PYTHONUNBUFFERED=1"
"%~dp0.venv\Scripts\python.exe" -u "%~dp0tools\build_v5r_standalone_exe.py"
set "RC=%ERRORLEVEL%"
echo.
echo [INFO] Ende: %DATE% %TIME%
echo.

if "%RC%"=="0" (
  if exist "%~dp0Marktanalyse.exe" (
    echo [OK] Marktanalyse.exe erstellt:
    dir "%~dp0Marktanalyse.exe" | findstr /i Marktanalyse
  ) else (
    echo [FEHLER] Build meldete OK, aber Marktanalyse.exe fehlt.
    set "RC=1"
  )
  if exist "%~dp0Marktanalyse.exe.sha256" (
    echo.
    type "%~dp0Marktanalyse.exe.sha256"
  )
) else (
  echo [FEHLER] Build exit code %RC%
  echo.
  echo Log-Datei suchen:
  if exist "%~dp0docs\integrity\session_logs\V5R\CODEX_V5R_BUILD_LOG.txt" (
    echo   %~dp0docs\integrity\session_logs\V5R\CODEX_V5R_BUILD_LOG.txt
  )
  for %%F in ("%CD%\CODEX_V5R_BUILD_LOG.txt") do if exist %%F echo   %%F
)

echo.
pause
exit /b %RC%
