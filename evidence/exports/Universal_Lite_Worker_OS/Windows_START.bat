@echo off
cd /d "%~dp0"
title Universal Lite Worker OS
echo Universal Lite Worker OS — Verbinde mit R3 ...
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
  echo Python 3 fehlt: https://www.python.org/downloads/
  pause
  exit / 1
)
%PY% worker.py
if errorlevel 1 pause
