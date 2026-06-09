@echo off
rem Start Marktanalyse.exe mit OS-Profil (Signal/Rebalance via Projekt-.venv)
cd /d "%~dp0"
call "%~dp0load_active_alpha_config.bat" 2>nul
call "%~dp0active_alpha_marktanalyse_os.bat"
if not exist "%~dp0Marktanalyse.exe" (
  echo [FEHLER] Marktanalyse.exe fehlt.
  pause
  exit /b 1
)
start "" "%~dp0Marktanalyse.exe"
