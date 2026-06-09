@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Zentrale EXE — gleicher Einstieg wie run_pilot_start.bat
call "%~dp0run_pilot_start.bat"
exit /b %ERRORLEVEL%
