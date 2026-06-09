# Marktanalyse Invest — Live-Trading Start

| Start | Befehl |
|-------|--------|
| **Live-Trading (aktueller Code)** | `run_live_trading_start.bat` → Python Invest-UI |
| Alte EXE (nur nach Neu-Build) | `run_live_trading_start.bat --exe` → `Marktanalyse.exe` |
| Schnell ohne Preflight | `run_live_trading_dev_fast.bat` |
| Paper (virtuell) | `run_paper_trading.bat`, `1_daily_mark_to_market.bat`, `2_rebalance_when_due.bat` |
| Live (T212) | `1_live_daily_sync.bat`, `2_live_rebalance_when_due.bat` |

Legacy-Weiterleitung: `run_pilot_start.bat` / `run_pilot_dev_fast.bat` (gleiche Logik).

Preflight: `aa_live_trading_launch.py --preflight-only` (Champion + Signal-Frische)

Champion-Guard: Policy `control/learning_collection_policy.json` muss mit Code-Champion übereinstimmen.

**EXE/OS:** `active_alpha_marktanalyse_os.bat` setzt `AA_RUN_MODE=signal`. Dauerhaft: `powershell -File tools\setup_marktanalyse_windows_env.ps1`

Order: **Order ausführen** — Live-Rebalance / Einzelorder an Trading 212 (API mit Order-Rechten).
