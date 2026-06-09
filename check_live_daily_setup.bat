@echo off
setlocal EnableExtensions
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo.
call "%~dp0setup_active_alpha_env.bat" >nul 2>&1
set "PY=%~dp0.venv\Scripts\python.exe"

echo ============================================================
echo   Active Alpha - Automatisierung - Status
echo ============================================================
echo.
echo  --------------------------
schtasks /Query /TN "Active Alpha Tages-Mark Mo-Fr" >nul 2>&1
if errorlevel 1 (
  echo    Tages-Mark Mo-Fr 15:25   [nicht eingerichtet]
  echo                             -> setup_live_daily_mark_task.bat
) else (
  echo    Tages-Mark Mo-Fr 15:25   [aktiv]
  schtasks /Query /TN "Active Alpha Tages-Mark Mo-Fr" /FO LIST /V | findstr /I "Status Nächste Next Run"
)

schtasks /Query /TN "Active Alpha Signal Update" >nul 2>&1
if errorlevel 1 (
  echo    Signal Update 22:15      [nicht eingerichtet]
  echo                             -> setup_live_daily_predict_task.bat
) else (
  echo    Signal Update 22:15      [aktiv]
  schtasks /Query /TN "Active Alpha Signal Update" /FO LIST /V | findstr /I "Status Nächste Next Run"
)

schtasks /Query /TN "Active Alpha Evolution Woechentlich" >nul 2>&1
if errorlevel 1 (
  echo    Evolution So 10:00       [nicht eingerichtet]
  echo                             -> setup_live_weekly_evolution_task.bat
) else (
  echo    Evolution So 10:00       [aktiv]
)

echo.
echo  Systemcheck:
echo  --------------------------
"%PY%" tools\preflight_live_daily_task.py --scheduled --human
set "RC=%ERRORLEVEL%"

echo.
if exist "%~dp0evidence\live_trading_scheduled_run_latest.json" (
  echo  Letzter automatischer Lauf:
  echo  --------------------------
  "%PY%" -c "import json;from pathlib import Path;p=Path(r'%~dp0evidence/live_trading_scheduled_run_latest.json');d=json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {};print('  Zeit:',d.get('generated_at_utc','—'));print('  Code:',d.get('exit_code','—'));print('  Info:',d.get('summary_de','—')[:120])"
  echo.
)

if not "%RC%"=="0" (
  echo  Aktion noetig: Pflichtpunkte oben erfuellen, dann erneut pruefen.
) else (
  echo  Alles bereit fuer den automatischen Tages-Mark.
)

echo.
echo  Vollstaendiger Bericht:
echo    evidence\live_trading_daily_task_preflight_latest.txt
echo.
echo  Evolution (Sportwagen -^> Rennwagen):
echo  --------------------------
"%PY%" tools\run_learning_cycle_audit.py 2>nul
if exist "%~dp0evidence\learning_cycle_audit_latest.json" (
  "%PY%" -c "import json;from pathlib import Path;d=json.loads(Path(r'%~dp0evidence/learning_cycle_audit_latest.json').read_text(encoding='utf-8'));s=d.get('stage')or{};print('  Stufe:',s.get('stage_label_de','—'),'| Live reif:',(d.get('live_metrics')or{}).get('n_mature','—'))"
)
echo    evidence\learning_cycle_audit_latest.json
echo.
echo  Strategische Governance:
echo  --------------------------
"%PY%" tools\sync_strategic_governance.py --json 2>nul | "%PY%" -c "import sys,json;d=json.load(sys.stdin);print('  Governance:',d.get('governance_champion','—'));print('  Signal:',d.get('active_signal_variant','—'));print('  Orders-Profil:',d.get('effective_orders_profile','—'));print('  Kohaerenz:', 'OK' if d.get('coherence_ok') else d.get('coherence_issues'))"
echo    control\strategic_governance.json
echo.
echo  Wettkampf-Readiness:
echo  --------------------------
"%PY%" tools\build_competition_readiness.py 2>nul
if exist "%~dp0evidence\competition_readiness_latest.json" (
  "%PY%" -c "import json;from pathlib import Path;d=json.loads(Path(r'%~dp0evidence/competition_readiness_latest.json').read_text(encoding='utf-8'));print('  Cost-Stress:', 'PASS' if d.get('cost_stress_gate_pass') else 'OFFEN');print('  Sharpe-Leader:',d.get('aligned_sharpe_leader','—'));print('  Preis:',d.get('price_latest','—'),'(',d.get('price_stale_days','?'),'d)' if d.get('price_stale_days') is not None else '');print('  ',d.get('message_de','')[:100])"
)
echo    evidence\competition_shadow_latest.json
echo.
pause
exit /b %RC%
