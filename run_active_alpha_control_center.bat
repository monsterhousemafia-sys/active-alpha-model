@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0load_active_alpha_config.bat"
if not exist "control_output" mkdir "control_output"

:MENU
cls
echo ============================================================
echo Active Alpha Trading 212 - Operational Control Center
echo ============================================================
echo Arbeitsordner: %CD%
echo.
echo Aktive Kernkonfiguration:
echo   Benchmark:          !AA_BENCHMARK!
echo   Paper-Ordner:       !AA_PAPER_DIR!
echo   Model-Output:       !AA_PAPER_MODEL_OUT_DIR!
echo   Backtest-Output:    !AA_BACKTEST_OUT_DIR!
echo   Risk-Regime:        !AA_RISK_REGIME_MODE!
echo   Exposure Controller:!AA_EXPOSURE_CONTROLLER!
echo   Cash Filler:        !AA_CASH_FILLER_MODE!
echo   Cluster Mode:       !AA_CLUSTER_MODE!
echo.
echo   1  = Operational Status anzeigen
echo   2  = Preflight fuer Paper-Rebalance pruefen
echo   3  = Rebalance pruefen und falls faellig ausfuehren
echo   4  = Taegliches Mark-to-Market ausfuehren
echo   5  = Paper Status / Dashboard anzeigen
echo   6  = Einzahlung / Auszahlung buchen
echo   7  = Backtest starten
echo   8  = Robustness-Matrix starten
echo   9  = Report-Zusammenfassung erzeugen
echo   10 = Konfiguration anzeigen
echo   11 = Konfiguration bearbeiten
echo   12 = Letzten Paper-Report oeffnen
echo   13 = Letzten Backtest-Report oeffnen
echo   0  = Beenden
echo.
set "CHOICE="
set /p "CHOICE=Auswahl [0-13]: "

if "!CHOICE!"=="1" goto STATUS
if "!CHOICE!"=="2" goto PREFLIGHT
if "!CHOICE!"=="3" goto REBALANCE_WHEN_DUE
if "!CHOICE!"=="4" call "%~dp0run_paper_mark_to_market.bat" & goto MENU
if "!CHOICE!"=="5" call "%~dp0run_paper_status.bat" & goto MENU
if "!CHOICE!"=="6" call "%~dp0run_paper_cashflow.bat" & goto MENU
if "!CHOICE!"=="7" call "%~dp0run_active_alpha_model.bat" & goto MENU
if "!CHOICE!"=="8" call "%~dp0run_robustness_tests.bat" & goto MENU
if "!CHOICE!"=="9" goto SUMMARY
if "!CHOICE!"=="10" goto CONFIG
if "!CHOICE!"=="11" call "%~dp0run_active_alpha_settings_wizard.bat" & call "%~dp0load_active_alpha_config.bat" & goto MENU
if "!CHOICE!"=="12" goto PAPER_REPORT
if "!CHOICE!"=="13" goto BACKTEST_REPORT
if "!CHOICE!"=="0" goto END

echo [ERROR] Ungueltige Auswahl.
pause
goto MENU

:ENSURE_ENV
call "%~dp0setup_active_alpha_env.bat"
if errorlevel 1 (
  echo [ERROR] Abhaengigkeiten fehlgeschlagen.
  pause
  exit /b 1
)
set "PYEXE=%~dp0.venv\Scripts\python.exe"
exit /b 0

:STATUS
call :ENSURE_ENV
if errorlevel 1 goto MENU
"!PYEXE!" active_alpha_control_center.py --mode status
pause
goto MENU

:PREFLIGHT
call :ENSURE_ENV
if errorlevel 1 goto MENU
"!PYEXE!" active_alpha_control_center.py --mode preflight --scope rebalance
if errorlevel 1 (
  echo.
  echo [WARN] Preflight meldet Fehler. Rebalance sollte nicht gestartet werden.
)
pause
goto MENU

:REBALANCE_WHEN_DUE
call :ENSURE_ENV
if errorlevel 1 goto MENU
"!PYEXE!" active_alpha_control_center.py --mode preflight --scope rebalance
if errorlevel 1 (
  echo.
  echo [ERROR] Preflight fehlgeschlagen. Rebalance wird nicht gestartet.
  echo [INFO] Details: control_output\preflight_report.txt
  pause
  goto MENU
)
call "%~dp02_rebalance_when_due.bat"
goto MENU

:SUMMARY
call :ENSURE_ENV
if errorlevel 1 goto MENU
"!PYEXE!" active_alpha_control_center.py --mode summary
echo.
echo [OK] Zusammenfassung geschrieben: control_output\control_summary.txt
pause
goto MENU

:CONFIG
call :ENSURE_ENV
if errorlevel 1 goto MENU
"!PYEXE!" active_alpha_control_center.py --mode config
echo.
echo [INFO] Vollstaendige Batch-Konfiguration:
echo ============================================================
call "%~dp0show_active_alpha_config.bat"
goto MENU

:PAPER_REPORT
call "%~dp0load_active_alpha_config.bat"
if exist "!AA_PAPER_DIR!\paper_report.txt" (
  notepad "!AA_PAPER_DIR!\paper_report.txt"
) else (
  echo [ERROR] !AA_PAPER_DIR!\paper_report.txt nicht gefunden.
  pause
)
goto MENU

:BACKTEST_REPORT
call "%~dp0load_active_alpha_config.bat"
if exist "!AA_BACKTEST_OUT_DIR!\backtest_report.txt" (
  notepad "!AA_BACKTEST_OUT_DIR!\backtest_report.txt"
) else (
  echo [ERROR] !AA_BACKTEST_OUT_DIR!\backtest_report.txt nicht gefunden.
  pause
)
goto MENU

:END
endlocal
exit /b 0
