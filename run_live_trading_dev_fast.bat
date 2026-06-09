@echo off
rem Live-Trading — schneller Start ohne Preflight
call "%~dp0run_pilot_dev_fast.bat" %*
exit /b %ERRORLEVEL%
