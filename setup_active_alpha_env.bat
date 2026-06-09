@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ============================================================
echo Active Alpha Trading 212 - Python-Umgebung
echo ============================================================
echo Arbeitsordner: %CD%
echo.

set "REQ=requirements_active_alpha.txt"
set "STAMP=.venv\.active_alpha_requirements.stamp"
set "VENV_DIR=%~dp0.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%REQ%" (
  echo [ERROR] %REQ% fehlt.
  exit /b 1
)

echo [INFO] Pruefe lokale Python-Umgebung ...

set "PYLAUNCH="
for %%V in (3.12 3.13 3.11) do (
  if "!PYLAUNCH!"=="" (
    py -%%V -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
    if not errorlevel 1 set "PYLAUNCH=py -%%V"
  )
)

if "!PYLAUNCH!"=="" (
  python -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,11) and sys.maxsize > 2**32 else 1)" >nul 2>nul
  if not errorlevel 1 set "PYLAUNCH=python"
)

if "!PYLAUNCH!"=="" (
  echo [ERROR] Keine geeignete 64-bit Python-Version gefunden. Empfohlen: Python 3.12 x64.
  exit /b 1
)

set "RECREATE=0"
set "INSTALL_NEEDED=0"

if /I "%AA_RECREATE_ENV%"=="1" set "RECREATE=1"
if not exist "%VENV_PY%" set "RECREATE=1"

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.maxsize > 2**32 else 1)" >nul 2>nul
  if errorlevel 1 set "RECREATE=1"
)

if "!RECREATE!"=="1" (
  echo [INFO] Erstelle/Repariere lokale .venv ...
  if exist ".venv" rmdir /s /q ".venv"
  !PYLAUNCH! -m venv .venv
  if errorlevel 1 exit /b 1
  set "INSTALL_NEEDED=1"
)

rem Entfernt kaputte SciPy-Reste wie ~cipy, die pip-Warnungen verursachen koennen.
if exist ".venv\Lib\site-packages" (
  for /d %%D in (".venv\Lib\site-packages\~cipy*") do (
    echo [INFO] Entferne kaputten SciPy-Rest: %%~nxD
    rmdir /s /q "%%~fD" >nul 2>nul
  )
  del /f /q ".venv\Lib\site-packages\~cipy*" >nul 2>nul
)

if "!INSTALL_NEEDED!"=="0" (
  "%VENV_PY%" -c "import numpy, pandas, sklearn, scipy, yfinance, pyarrow, matplotlib" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] Abhaengigkeiten fehlen oder sind beschaedigt. Installation/Reparatur wird ausgefuehrt.
    set "INSTALL_NEEDED=1"
  )
)

if /I "%AA_FORCE_INSTALL%"=="1" (
  echo [INFO] AA_FORCE_INSTALL=1 gesetzt. Installation wird erzwungen.
  set "INSTALL_NEEDED=1"
)

if "!INSTALL_NEEDED!"=="0" if exist "%STAMP%" (
  "%VENV_PY%" -c "from pathlib import Path; req=Path(r'%REQ%'); stamp=Path(r'%STAMP%'); raise SystemExit(0 if stamp.exists() and stamp.stat().st_mtime >= req.stat().st_mtime else 1)" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] requirements_active_alpha.txt wurde seit der letzten Installation geaendert.
    set "INSTALL_NEEDED=1"
  )
)

if "!INSTALL_NEEDED!"=="1" (
  echo [INFO] Installiere/aktualisiere benoetigte Pakete. Kein Force-Reinstall, Pip-Cache bleibt aktiv.
  "%VENV_PY%" -m pip install --upgrade pip
  if errorlevel 1 exit /b 1

  "%VENV_PY%" -m pip install -r "%REQ%"
  if errorlevel 1 exit /b 1

  "%VENV_PY%" -c "import matplotlib" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] matplotlib fehlt nach requirements-Installation. Installiere matplotlib separat.
    "%VENV_PY%" -m pip install matplotlib
    if errorlevel 1 exit /b 1
  )

  "%VENV_PY%" -c "from pathlib import Path; Path(r'%STAMP%').write_text('ok\n', encoding='utf-8')"
  if errorlevel 1 exit /b 1
) else (
  if not exist "%STAMP%" (
    "%VENV_PY%" -c "from pathlib import Path; Path(r'%STAMP%').write_text('ok\n', encoding='utf-8')" >nul 2>nul
  )
  echo [OK] Lokale .venv ist bereit. Keine Paket-Neuinstallation notwendig.
)

"%VENV_PY%" -c "import numpy, pandas, sklearn, scipy, yfinance, pyarrow, matplotlib; print('[OK] Python environment ready:', numpy.__version__)"
if errorlevel 1 (
  echo [WARN] Import-Test fehlgeschlagen. Fuehre gezielte SciPy/Scikit-Learn-Reparatur aus.
  "%VENV_PY%" -m pip install --upgrade --force-reinstall scipy scikit-learn matplotlib
  if errorlevel 1 exit /b 1

  "%VENV_PY%" -c "import numpy, pandas, sklearn, scipy, yfinance, pyarrow, matplotlib; print('[OK] Python environment repaired:', numpy.__version__)"
  if errorlevel 1 exit /b 1
)

exit /b 0
