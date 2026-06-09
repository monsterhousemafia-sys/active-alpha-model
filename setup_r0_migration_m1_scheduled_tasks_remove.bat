@echo off
setlocal
cd /d "%~dp0"
for %%T in ("R0 Migration M1 Monitor" "R0 Migration M1 On Logon") do (
  schtasks /Delete /TN %%~T /F >nul 2>&1 && echo [OK] Entfernt: %%~T || echo [INFO] Nicht vorhanden: %%~T
)
exit /b 0
