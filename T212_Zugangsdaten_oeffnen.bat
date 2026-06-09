@echo off
setlocal EnableExtensions
cd /d "%~dp0"
start "" notepad.exe "%~dp0trading212_zugangsdaten.env"
echo Notepad geoeffnet: %~dp0trading212_zugangsdaten.env
exit /b 0
