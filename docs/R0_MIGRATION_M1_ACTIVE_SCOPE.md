# R0-Migration — Aktiver Scope: nur M1 (Trading-Pfad Schritt 1)

**Stand:** Ausführung fokussiert auf **M1** bis `evidence/r0_migration/m1_phase_seal.json` existiert.  
**Champion produktiv:** `R3_w075_q065_noexit` (unverändert).  
**Maschinenlesbar:** `control/r0_migration/m1_active_scope.json`

---

## Was jetzt gilt (identisch Trading-Mandat Schritt 1)

| Element | Inhalt |
|---------|--------|
| Varianten | `R0_LEGACY_ENSEMBLE`, `R3_w075_q065_noexit`, `M1_MOM_BLEND_MATCHED_CONTROLS` |
| Kalender | Ein alignierter Schnitt (Matrix), gleiche Kosten/Rahmen |
| Risk-off R0/M1 | `legacy` / `legacy` |
| Ziel | 3× `strategy_daily_returns.csv` mit `integrity_pass` |
| Seal | `run_r0_migration_seal_phase.bat M1` (oder Auto nach 3/3) |

**Nicht** Teil von M1: Episoden-Attribution (M2), Gates (M5), Shadow/Paper (M6–M7), Champion-Wechsel (M9).

---

## Erlaubte Befehle (M1)

| Befehl | Zweck |
|--------|--------|
| `run_r0_migration_m1.bat` | **Hauptsteuerung** (= finish_push: hold / resume / seal) |
| `run_r0_migration_m1_status.bat` | Fortschritt `X/3` (optional) |
| `run_r0_migration_watch_loop.bat` | Automation (5-Min-Tick) |
| `run_r0_migration_m1_finish.bat` | Nach 3/3 Returns |
| `run_r0_migration_prevent_sleep_on.bat` | PC wach |

**Nicht starten:** `run_r0_migration_phase_m2` / Orchestrator für M2 — erst **nach** M1-Seal.

---

## Nach M1-Seal (Trading-Pfad Schritt 2+)

```text
M1 SEALED → M2 (Vergleichsrahmen) → M3/M5 (Research + Gates) → M6/M7 (Shadow/Paper) → M8 → M9 (Freigabe) → M10–M12
```

M4 (MOM/Hybrid) nur bei CAGR-Lücke nach M2/M3 — siehe Mandat.

---

## Verboten bis M9 (unverändert)

Champion-Wechsel, Auto-Promotion, Echtgeld, produktive R0-Parameter ohne Freigabe.
