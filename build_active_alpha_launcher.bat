@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo Active Alpha - EXE Launcher bauen (onedir, schneller Start)
echo ============================================================

taskkill /IM Marktanalyse.exe /F >nul 2>&1
ping -n 2 127.0.0.1 >nul

if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

"%PY%" -m pip install --upgrade pip pyinstaller PySide6
if errorlevel 1 exit /b 1

set "ICON=%~dp0assets\marktanalyse_r5.ico"
if not exist "%~dp0tools\active_alpha_launcher.py" (
  echo [ERROR] tools\active_alpha_launcher.py fehlt.
  exit /b 1
)

echo [INFO] Erzeuge R5-Icon ...
"%PY%" "%~dp0tools\generate_r5_icon.py"
if errorlevel 1 exit /b 1
if not exist "%ICON%" (
  echo [ERROR] %ICON% fehlt.
  exit /b 1
)

echo [INFO] PyInstaller onedir (Marktanalyse.spec) ...
"%PY%" -m PyInstaller --noconfirm --clean --distpath . --workpath build\launcher build\launcher\Marktanalyse.spec
if errorlevel 1 (
  echo [ERROR] PyInstaller fehlgeschlagen.
  exit /b 1
)

echo [INFO] Post-Build: Root-Launcher + _internal Junction ...
"%PY%" "%~dp0tools\post_build_marktanalyse.py"
if errorlevel 1 (
  echo [ERROR] Post-Build fehlgeschlagen.
  exit /b 1
)

if not exist "%~dp0Marktanalyse.exe" (
  echo [ERROR] Marktanalyse.exe wurde nicht erzeugt.
  exit /b 1
)
if not exist "%~dp0Marktanalyse\_internal" (
  echo [ERROR] Marktanalyse\_internal fehlt.
  exit /b 1
)

echo [OK] Erstellt: %~dp0Marktanalyse.exe
echo [OK] Bundle:     %~dp0Marktanalyse\
echo.
echo [INFO] Smoke-Test ...
"%PY%" "%~dp0tools\smoke_test_launcher.py"
if errorlevel 1 (
  echo [WARN] Smoke-Test fehlgeschlagen — EXE manuell prüfen.
)
echo.
echo Hinweis: Marktanalyse.exe muss im Projektordner neben active_alpha_model.py liegen.
echo Onedir-Start: keine Entpackung bei jedem Aufruf (deutlich schneller als onefile).
exit /b 0
