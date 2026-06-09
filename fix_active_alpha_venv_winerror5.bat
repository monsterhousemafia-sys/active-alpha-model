@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo Active Alpha - Reparatur fuer pip WinError 5 / gesperrte .pyd

echo Projektordner: %CD%
echo ============================================================
echo.

echo [1/5] Stoppe Python-/pip-Prozesse, die aus diesem Projektordner laufen ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '.').Path.ToLowerInvariant(); Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant().StartsWith($root) -and $_.Name -match '^(python|pythonw|pip|py)\.exe$' } | ForEach-Object { Write-Host ('Stoppe PID ' + $_.ProcessId + '  ' + $_.ExecutablePath); Stop-Process -Id $_.ProcessId -Force }"

echo.
echo [2/5] Entferne ggf. gesperrte/defekte websockets-Binaerdatei ...
if exist ".venv\Lib\site-packages\websockets\speedups.cp314-win_amd64.pyd" (
  attrib -R ".venv\Lib\site-packages\websockets\speedups.cp314-win_amd64.pyd" 2>nul
  del /F /Q ".venv\Lib\site-packages\websockets\speedups.cp314-win_amd64.pyd" 2>nul
)

if not exist ".venv\Scripts\python.exe" goto RECREATE_VENV

echo.
echo [3/5] Repariere pip/wheel und installiere websockets ohne Cache neu ...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto RECREATE_VENV
".venv\Scripts\python.exe" -m pip install --force-reinstall --no-cache-dir websockets
if errorlevel 1 goto RECREATE_VENV

goto INSTALL_DEPS

:RECREATE_VENV
echo.
echo [INFO] Direkte Reparatur nicht ausreichend. Die lokale .venv wird sauber neu aufgebaut.
if exist ".venv" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'; Rename-Item -Path '.venv' -NewName ('.venv_broken_' + $stamp) -Force"
)

echo [3/5] Erstelle neue virtuelle Umgebung. Bevorzugt Python 3.12, dann 3.13, dann Standard-python ...
py -3.12 -m venv .venv
if errorlevel 1 py -3.13 -m venv .venv
if errorlevel 1 python -m venv .venv
if errorlevel 1 (
  echo [ERROR] Konnte keine neue .venv erstellen. Installiere Python 3.12 oder 3.13 und starte erneut.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] pip-Basisinstallation fehlgeschlagen.
  pause
  exit /b 1
)

:INSTALL_DEPS
echo.
echo [4/5] Installiere Projekt-Abhaengigkeiten ...
if exist "requirements.txt" (
  ".venv\Scripts\python.exe" -m pip install --upgrade --no-cache-dir -r requirements.txt
) else (
  echo [WARN] requirements.txt nicht gefunden. Installiere Kernpakete fuer Active Alpha.
  ".venv\Scripts\python.exe" -m pip install --upgrade --no-cache-dir numpy pandas scikit-learn yfinance pyarrow matplotlib rich websockets
)
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten konnten nicht installiert werden.
  echo         Falls weiterhin WinError 5 erscheint: Explorer, VS Code, Jupyter, Terminalfenster und Virenscanner-Zugriff auf .venv schliessen/pausieren und erneut starten.
  pause
  exit /b 1
)

echo.
echo [5/5] Import-Test ...
".venv\Scripts\python.exe" -c "import sys; print('Python:', sys.version); import websockets; print('websockets OK:', websockets.__version__); import numpy, pandas, sklearn, yfinance; print('Core packages OK')"
if errorlevel 1 (
  echo [ERROR] Import-Test fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo [OK] .venv repariert. Starte danach dein normales run_active_alpha_model.bat erneut.
pause
exit /b 0
