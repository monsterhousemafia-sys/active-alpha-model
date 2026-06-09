@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem Live-Trading Start (Python-UI; --exe fuer alte Marktanalyse.exe)
call "%~dp0run_live_trading_start.bat" %*
exit /b %ERRORLEVEL%
