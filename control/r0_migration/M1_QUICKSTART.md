# M1 — ein Einstieg

**Executive (läuft im Hintergrund, 3-Min-Tick):** `run_r0_migration_executive.bat`

**Manuell einmal:** `run_r0_migration_executive_once.bat` oder `run_r0_migration_m1.bat`

**Status:** `run_r0_migration_m1_status.bat`  
**Nach 3/3:** `run_r0_migration_m1_finish.bat`  
**Rennen aktiv:** kein Watch-Loop/Scheduler — nur eine Matrix

**Blocker entfernen:** `run_r0_migration_eliminate_blockers.bat`

## Aliase (gleiche Logik, nicht extra starten)

- `run_r0_migration_finish_push.bat`
- `run_r0_migration_autopilot.bat`
- `run_r0_migration_m1_matrix_background.bat`

## Nur Debug (Vordergrund-Matrix)

- `run_r0_migration_m1_matrix.bat`

## Nicht parallel

Wenn `batch_active: true` → warten, kein zweiter Start.

Scope: `docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md`
