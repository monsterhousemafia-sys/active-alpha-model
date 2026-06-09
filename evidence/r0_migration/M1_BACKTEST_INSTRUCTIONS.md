# M1 — Backtest / Validation Matrix (Benutzeraktion)

## Brauchen Sie einen Backtest?

**Ja**, für vollständiges M1-Exit und für M2:

- `validation_runs/` ist leer oder ohne R0/R3/M1-Returns.
- Ohne Lauf gibt es keine frischen `strategy_daily_returns.csv` mit `integrity_pass`.

M1-Audits (Pointer, Env, Kalender-Regeln) sind **ohne** Backtest erledigt.

## Voraussetzungen

1. `AA_ALPHA_MODEL_MODE=ensemble` in `active_alpha_*.bat` (M1 hat ggf. bereits korrigiert).
2. Kein paralleler Marktanalyse.exe-Lauf (Batch-Lock).
3. **Authorization:** `control/authorization/current_authorization_status.json` darf
   `backtest_execution` / `matrix_rerun` **nicht** blockieren — sonst manuell nach G0/G1-Freigabe.

## Empfohlener Befehl (3 Varianten, ~Stunden Laufzeit)

```bat
.venv\Scripts\python.exe tools\run_validation_matrix.py --phase matrix --run-mode backtest --variant R0_LEGACY_ENSEMBLE --variant R3_w075_q065_noexit --variant M1_MOM_BLEND_MATCHED_CONTROLS --parallel-jobs 1 --runtime-profile turbo
```

Vollständige Matrix (alle R0–R4):

```bat
.venv\Scripts\python.exe tools\run_validation_matrix.py --phase matrix --run-mode backtest
```

Nach Abschluss:

```bat
.venv\Scripts\python.exe tools\run_r0_migration_phase_m1.py
```

**Authorization blocks backtest now:** False
