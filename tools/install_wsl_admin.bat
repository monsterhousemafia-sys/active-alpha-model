@echo off
:: Double-click or: runas /user:Administrator (needs admin once)
cd /d E:\active_alpha_model
echo === WSL Install (Admin) ===
powershell -ExecutionPolicy Bypass -File tools\install_wsl_elevated.ps1
echo.
echo If successful: REBOOT then run post_reboot_wsl.ps1
pause
