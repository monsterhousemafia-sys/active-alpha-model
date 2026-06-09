# R0-M1 Autopilot — Übergabe (nur M1 bis Seal)

**Status:** `IN_PROGRESS` — M1 noch nicht SEALED.  
**Aktiver Scope:** `docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md` · `control/r0_migration/m1_active_scope.json`

**Selfcheck:** `python tools/run_r0_migration_autopilot_selfcheck.py` → `evidence/r0_migration/autopilot_selfcheck.json`

## Was jetzt läuft (Trading-Pfad Schritt 1)

| Komponente | Rolle |
|------------|--------|
| `run_r0_migration_m1.bat` | **Hauptsteuerung** — hält aktive Matrix, sonst Resume/Seal |
| `run_r0_migration_executive.bat` | **Executive** — 3-Min-Tick, eine Matrix, Auto-Resume |
| `run_r0_migration_m1_status.bat` | Fortschritt `X/3` Returns |
| `run_r0_migration_m1_scheduled_worker.bat` | Alle 30 Min (Task Scheduler): Refresh+Seal wenn fertig |
| `run_r0_migration_m1_finish.bat` | Nach 3/3 Returns / manuell |

**Nicht während M1:** `run_r0_migration_phase_orchestrator` / M2 — blockiert bis `evidence/r0_migration/m1_phase_seal.json`.

## Artefakte

- `control/r0_migration/autopilot_handoff.json` — letzter Lauf
- `control/r0_migration_program.json` — Fokus (`M1_IN_PROGRESS` / nach Seal `M2_READY`)
- `evidence/r0_migration/m1_health.json` — Stall/Blocker
- `evidence/r0_migration/commander_report.json` — Singularität Matrix

## Sie müssen nichts tun, wenn

- PC **an** bleibt (`run_r0_migration_prevent_sleep_on.bat` oder Strategic Setup)
- Watch-Loop oder Scheduler läuft
- Kein zweites Matrix/Commander parallel (`batch_active: true` → warten)

## Bei Abbruch / Reboot

```bat
run_r0_migration_m1.bat
```

Optional Status: `run_r0_migration_m1_status.bat`

## Nach M1-Seal

```bat
run_r0_migration_phase_orchestrator.bat
```

→ M2 (Vergleichsrahmen); M3+ stoppt mit `NOT_IMPLEMENTED` bis implementiert.
