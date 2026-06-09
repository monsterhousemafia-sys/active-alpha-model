# R0-Migration — Master-Checkliste (M0–M12)

**Programm:** Langfristige Umstellung R3 → R0 (optional R0*)  
**Champion produktiv bis M9.2:** `R3_w075_q065_noexit`  
**Plan-Detail:** `docs/R0_LONG_TERM_MIGRATION_PLAN.md` · **Mandat:** `docs/R0_MIGRATION_MANDATE.md`

Legende: `[ ]` offen · `[~]` läuft · `[x]` erledigt · **BAT** = Windows-Starter im Repo-Root

---

## Übersicht (alle Phasen)

| Phase | Name | Dauer (Richtwert) | Champion produktiv? |
|-------|------|-------------------|---------------------|
| **M0** | Mandat & Zielfunktion | 1 Woche | R3 |
| **M1** | Evidenz-Baseline & Matrix | 1–2 Wochen + Rechnerzeit | R3 |
| **M2** | Einheitlicher Vergleich | 2–3 Wochen | R3 |
| **M3** | R0* Tuning (Research) | 4–8 Wochen | R3 |
| **M4** | MOM/Hybrid (optional) | 4–6 Wochen | R3 |
| **M5** | Gates (Kosten, DSR, Robustheit) | 3–4 Wochen | R3 |
| **M6** | Shadow-Monitoring | 6–8 Wochen | R3 |
| **M7** | Paper-Forward | 8–12 Wochen | R3 |
| **M8** | Ops-Vorbereitung (Signale, Config, Runbook) | 2–3 Wochen | R3 |
| **M9** | Externe Freigabe & Champion-Wechsel | 1–2 Wochen | **Wechsel → R0** |
| **M10** | Stabilisierung & Monitoring | 3 Monate | R0 |
| **M11** | EXE (Marktanalyse) Build & Abnahme | 1–2 Wochen | R0 |
| **M12** | OS / Desktop / Betriebs-Rollout | 1–3 Tage | R0 |

```text
M0 → M1 → M2 → (M3 ∥ M5) → M5 → M6 → M7 → M8 → M9 → M10
                                    ↘ M4? ↗
Nach M9:  M11 (EXE) ∥ M12 (OS)  — empfohlen als ein Release-Paket
```

---

## M0 — Mandat (ABGESCHLOSSEN)

| # | Aufgabe | Artefakt / Tool | Status |
|---|---------|-----------------|--------|
| M0.1 | Zielfunktion: Sharpe + CAGR primär | `docs/R0_MIGRATION_MANDATE.md` | [x] |
| M0.2 | Ziel: R0, Tuning R0* in M3 | `control/r0_migration/mandate.json` | [x] |
| M0.3 | Charter-Entwurf R0 | `control/champion_decision_charter_r0_target_draft.md` | [x] |
| M0.4 | Paper + Shadow Pflicht; EXE/OS nach M9 | Mandat | [x] |

**Tool:** `tools/run_r0_migration_phase_m0.py`

---

## M1 — Evidenz-Baseline & Validation Matrix **[AKTIVER SCOPE]**

**Fokus-Dokument:** `docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md` · Maschine: `control/r0_migration/m1_active_scope.json`

| # | Aufgabe | BAT / Befehl | Exit |
|---|---------|--------------|------|
| M1.0 | Programm-Fokus sync | auto (`r0_migration_active_scope`) | `control/r0_migration_program.json` |
| M1.1 | Pointer-Audit | auto via `run_r0_migration_m1_refresh.bat` | `pointer_audit.json` |
| M1.2 | Matrix R0 → R3 → M1 (Reihenfolge) | **`run_r0_migration_m1.bat`** | 3× PASS |
| M1.2a | Lock aktiv → **nicht** zweiter Start | `finish_push` / Commander HOLD | — |
| M1.2b | Status `X/3` | `run_r0_migration_m1_status.bat` | `m1_status_latest.txt` |
| M1.3 | Returns-Manifest | **`run_r0_migration_m1_refresh.bat`** | `all_m1_variants_integrity_pass: true` |
| M1.4 | Kein Champion-Read aus 2450d `model_output` | `calendar_mismatch_root_cause.md` | Regel dokumentiert |
| M1.5 | `AA_ALPHA_MODEL_MODE=ensemble` | `active_alpha_*.bat` | Env-Audit PASS |
| M1.6 | Seal M1 | `run_r0_migration_seal_phase.bat M1` | `m1_phase_seal.json` |

**Prüfung:**

```bat
run_r0_migration_m1_status.bat
```

Erwartung: **3/3** Returns (R0, R3, M1) mit `integrity_pass`.

**Tools:** `tools/run_r0_migration_phase_m1.py`, `tools/run_validation_matrix.py`, `tools/r0_migration_finish_push.py`, `tools/r0_migration_commander.py`

**Während M1 gesperrt:** M2-Orchestrator, Gates, Shadow, Champion-Wechsel (siehe `m1_active_scope.json`).

---

## M2 — Einheitlicher Vergleichsrahmen

| # | Aufgabe | Tool / Output | Exit |
|---|---------|---------------|------|
| M2.1 | Canonical Comparison rebuild | `tools/build_canonical_model_comparison.py` | `evidence/canonical_model_comparison.json` |
| M2.2 | Kalender A: Matrix 1860d | Report `.md` | R0 vs R3 Tabelle |
| M2.3 | Kalender B: Aligniert 2019–2026 | gemeinsame Returns | getrennt gelabelt |
| M2.4 | Subperioden R0 + R3 | im Canonical Report | Segment 2 nicht kollabiert |
| M2.5 | Risk-off-Episoden | `tools/build_risk_off_episode_comparison.py` (neu) | `risk_off_episode_attribution.csv` |

**Go:** R0 Sharpe ≥ R3 + 0,02; MaxDD ≤ R3 + 2 pp; schlägt M1 auf gleichem Kalender.

---

## M3 — R0* Optimierung (nur `validation_runs/`)

| # | Aufgabe | Output | Exit |
|---|---------|--------|------|
| M3.1 | Trial Ledger präregistriert | `research_evidence/r0_tuning_trial_ledger.json` | — |
| M3.2 | Grid-Runs (ensemble/top_k/train_years/…) | `validation_runs/R0_STAR_*` | — |
| M3.3 | Ein Sieger R0* oder Baseline R0 | Entscheidungsnotiz | ≥ R3, Segment 2 Sharpe > 0,5 |
| M3.4 | DSR für Grid | `multiple_testing_status.json` | PASS |

**Kein** produktives Default-Config-Change vor M9.

---

## M4 — MOM / Hybrid (optional)

| # | Aufgabe | Wann | Exit |
|---|---------|------|------|
| M4.1 | Nur wenn M3 CAGR-Lücke zu MOM > ~2 pp | Gate-Entscheid | Go/No-Go Hybrid |
| M4.2 | MOM_63_STRICT auf gleichem Kalender | `validation_runs/` | Vergleichs-CSV |
| M4.3 | Hybrid-Prototypen (Research) | `evidence/r0_migration/hybrid_research_summary.md` | externe Freigabe nötig für Produktiv |

---

## M5 — Statistische Gates (Champion-Change-Kriterien)

| Gate | Artefakt | PASS? |
|------|----------|-------|
| Cost-Stress +25 bps | `control/evidence/cost_stress_status.json` | [ ] |
| DSR ≥ 0,95 | `control/evidence/multiple_testing_status.json` | [ ] |
| Robustness Subperioden | `control/evidence/robustness_status.json` | [ ] |
| Turnover verifiziert (kein Proxy) | G1 / Matrix | [ ] |
| Zusammenfassung | `evidence/r0_migration/gate_matrix.json` | [ ] |

**Tools:** `tools/generate_research_evidence_reports.py`, `run_active_alpha_riskoff_followup.py`, `tools/chain_m1_then_cost_stress.py`

---

## M6 — Shadow (≥ 30 Outcomes)

| # | Aufgabe | Exit |
|---|---------|------|
| M6.1 | `shadow_challenger_id` = R0 oder R0* | konfiguriert |
| M6.2 | ≥ 30 Tage/Outcomes parallel zu R3 | `shadow_monitor_status.json` PASS |
| M6.3 | Keine FAILSAFE-Drift 14d | dokumentiert |
| M6.4 | Cockpit-Panel Migration Shadow (read-only) | optional UI |

**Keine** Challenger-Orders.

---

## M7 — Paper-Forward (≥ 60 Tage)

| # | Aufgabe | Exit |
|---|---------|------|
| M7.1 | Paper auf R0-Config (Freigabe!) | `paper_monitor_status.json` PASS |
| M7.2 | Delta vs. R3-Paper | Report |
| M7.3 | Quote-Coverage, Gebühren-Spalte, Symbole | Ops-Checkliste |

**Tool:** `tools/run_p12c_forward_paper_trading.py` (nur mit Freigabe)

---

## M8 — Operative Vorbereitung (Signale & Config, **vor** Cutover)

| # | Aufgabe | Deliverable | Exit |
|---|---------|-------------|------|
| M8.1 | Runbook Signal-Cutover | `docs/R0_PRODUCTION_CUTOVER_RUNBOOK.md` | [ ] |
| M8.2 | Produktiv-Profil R0 | `config/champion_r0_production.json` | [ ] |
| M8.3 | Risk-off auf R0 in **Ziel**-`.bat` | `legacy`/`legacy` (erst ab M9 produktiv) | [ ] |
| M8.4 | Rollback R3 eingefroren | `control/rollback/r3_last_known_good/` | [ ] |
| M8.5 | Trockenlauf Signal | `latest_target_portfolio.csv` aus R0-Run | [ ] |
| M8.6 | Tests | `pytest` P0, Pilot-Refresh, Champion-Guard | grün |
| M8.7 | `champion_runtime_guard` / Cockpit-Strings | Code-Review | R0 angezeigt (read-only ok) |

**BAT (nach M9, für Signale):** `run_active_alpha_model.bat` mit geladenem R0-Profil — **nicht** vor M9 produktiv schalten.

---

## M9 — Externe Freigabe & Champion-Wechsel (ökonomisch produktiv)

| # | Schritt | Pflicht |
|---|---------|---------|
| M9.1 | Review-ZIP | Canonical, Gates, Shadow, Paper, ADR, Runbook |
| M9.2 | **`EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_<date>.md`** | kein TEMPLATE |
| M9.3 | Pointer | `latest_validated_run.json` → R0-`run_dir` |
| M9.4 | Lineage / Registry | `champion_lineage_policy.json` |
| M9.5 | Reports | `challenger_report` Champion = R0 |
| M9.6 | ADR | `CHAMPION_STRATEGIC_DECISION_RECORD.md` E3→R0 |
| M9.7 | Erstes produktives Signal-Fenster | dokumentiert |
| M9.8 | Charter aktivieren | `champion_decision_charter_r0_target_draft` → aktiv |

**Exit:** `champion_change_executed: true` · Auto-Promotion **bleibt false**.

---

## M10 — Stabilisierung (3 Monate nach M9)

| # | Aufgabe | Rhythmus |
|---|---------|----------|
| M10.1 | R3 als frozen sibling in Matrix | einmalig archiviert |
| M10.2 | Monatlicher Canonical-Refresh | monatlich |
| M10.3 | Live vs. Backtest Episode-Attribution | einmalig + Quartal |
| M10.4 | Spur B (MOM/Hybrid) abschließen | Programm-Entscheid |
| M10.5 | `run_r0_migration_m1_refresh.bat` nach jedem Re-Run | bei Bedarf |

---

## M11 — EXE (Marktanalyse Decision Cockpit)

**Start:** nach **M9.2** (empfohlen parallel zu M12). Separates Build-Gate (V5R/V6) falls erforderlich.

| # | Aufgabe | Tool / Pfad | Exit |
|---|---------|-------------|------|
| M11.1 | Review-Snapshot R0-Champion | `control/review_snapshot/` | konsistent mit R0 |
| M11.2 | Cockpit-Viewmodel / Governance-DE | `aa_decision_cockpit_viewmodel.py` | zeigt R0, Trade-offs |
| M11.3 | PyInstaller Build | `tools/build_v5r_standalone_exe.py` | `Marktanalyse.exe` |
| M11.4 | Static Verify | `tools/static_verify_v5r_standalone_exe.py` | PASS |
| M11.5 | Runtime Smoke (fail-closed, read-only) | `tools/v5r_runtime_smoke_test.py` | PASS |
| M11.6 | SHA256 + Provenance | `Marktanalyse.exe.sha256`, `v5r_build_provenance.json` | dokumentiert |
| M11.7 | Review-ZIP EXE | `codex_v5r_*_review.zip` | externe EXE-Freigabe |
| M11.8 | Kein Champion aus verunreinigtem Output | Tests grün | fail-closed |

**Nicht:** EXE berechnet keine neuen Champion-Signale — nur **Anzeige** von `control/` + Snapshots.

---

## M12 — OS / Windows / Betriebs-Umgebung

**Start:** nach **M9** (idealerweise zusammen mit M11 als **ein** Rollout-Fenster).

| # | Aufgabe | Datei / Aktion | Exit |
|---|---------|----------------|------|
| M12.1 | Runbook OS-Rollout | `docs/R0_OS_ROLLOUT_RUNBOOK.md` | [ ] |
| M12.2 | `active_alpha_user_config.bat` / `settings.bat` | `ensemble`, R0 risk-off `legacy` | [ ] |
| M12.3 | `load_active_alpha_config.bat` Kette prüfen | alle Signal-Jobs | [ ] |
| M12.4 | `setup_active_alpha_startup.bat` | Desktop/Autostart-Pfade | [ ] |
| M12.5 | `run_v5r_decision_cockpit.bat` / `run_pilot_start.bat` | startet neue EXE | [ ] |
| M12.6 | Ops-Refresh / Sector S7 | `tools/run_ops_refresh.py` | PASS |
| M12.7 | T212-Pfad / Gebühren-Spalte | `live_trading_operations` | UI-Check |
| M12.8 | Alte EXE / `_internal` entfernen | nur nach Backup | sauberer Desktop |
| M12.9 | Kopie `Marktanalyse.exe` + SHA256 prüfen | User-Desktop | Match |
| M12.10 | Rollback-Paket OS (R3-.bat + alte EXE) | `control/rollback/r3_last_known_good/` | [ ] |

**BAT-Übersicht produktiv (Zielzustand):**

| Zweck | BAT |
|-------|-----|
| M1 Steuerung | `run_r0_migration_m1.bat` |
| Matrix Vordergrund (Debug) | `run_r0_migration_m1_matrix.bat` |
| M1 Refresh | `run_r0_migration_m1_refresh.bat` |
| Signale / Backtest produktiv | `run_active_alpha_model.bat` |
| Decision Cockpit | `run_v5r_decision_cockpit.bat` / `run_pilot_start.bat` |
| Ops Refresh | `tools/run_ops_refresh.py` (via bestehende Ops-BATs) |

---

## Nach Matrix-Ende / aktueller M1-Pfad

| Schritt | BAT |
|---------|-----|
| 1 | Matrix laufen lassen **oder** `run_r0_migration_m1.bat` |
| 2 | `run_r0_migration_m1_status.bat` → **3/3** |
| 3 | `run_r0_migration_m1_refresh.bat` oder `run_r0_migration_m1_finish.bat` |
| 4 | Seal: `run_r0_migration_seal_phase.bat M1` (oft automatisch) |
| 5 | **Erst danach** M2: `run_r0_migration_phase_orchestrator.bat` |

Siehe auch: `docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md`

---

## Verboten bis M9.2

- Champion-Pointer produktiv auf R0
- `AA_RISK_OFF_*` produktiv auf R0 ohne Freigabe
- Auto-Promotion
- Echtgeld-Orders
- R5 / `rank_only` produktiv
- EXE als „neuer Champion“ ohne M11-Verify

---

## Phasen absichern (Pflicht nach jeder Phase)

Jede Phase endet mit **Verify** und **Seal** (fail-closed). Ohne Seal der Vorphase startet die nächste nicht.

| Schritt | BAT / Befehl |
|---------|----------------|
| Prüfen | `run_r0_migration_verify_phase.bat M1` |
| Absichern | `run_r0_migration_seal_phase.bat M1` |

Artefakte:

| Datei | Bedeutung |
|-------|-----------|
| `control/r0_migration/phase_gates.json` | Exit-Kriterien M0–M12 |
| `evidence/r0_migration/m{N}_phase_seal.json` | Hash + Prüfliste, Status `SEALED` |
| `evidence/r0_migration/m{N}_completion_summary.json` | Kurzsummary |

**Automatisch:** M1-Refresh versucht Seal, wenn Returns + Env PASS und M0 sealed.

**Ausfall / Defekt / Hänger:**

| Schritt | BAT / Datei |
|---------|-------------|
| Stall-Erkennung + Lock-Reparatur | `run_r0_migration_outage_check.bat` |
| Health-Snapshot | `evidence/r0_migration/m1_health.json` |
| Sleep aus (während Matrix) | `run_r0_migration_prevent_sleep_on.bat` |
| Sleep zurück | `run_r0_migration_prevent_sleep_off.bat` |
| Config Schwellen | `control/r0_migration/outage_guard_config.json` |

Automatisch in: Matrix-BAT, Refresh, M1-Python, Scheduled-Worker.

**Strategisches Setup (empfohlen, einmal):**

```bat
run_r0_migration_strategic_setup.bat
```

→ Sleep an, **`finish_push`** (HOLD/Restart/Seal), Task Scheduler (PowerShell/Admin). Scope: nur M1.

**Nach Matrix-Ende:**

```bat
run_r0_migration_m1_finish.bat
```

**Windows Task Scheduler (PC macht M1 ohne Cursor):**

| Schritt | BAT |
|---------|-----|
| Aufgaben registrieren (als **Administrator**) | `setup_r0_migration_m1_scheduled_tasks.bat` |
| Entfernen | `setup_r0_migration_m1_scheduled_tasks_remove.bat` |
| Manuell testen | `run_r0_migration_m1_scheduled_worker.bat` |

- **Alle 30 Min:** Recovery → Matrix starten (wenn frei) oder Refresh+Seal (wenn Returns da)
- **Bei Anmeldung:** einmal Worker
- Log: `evidence/r0_migration/scheduled_worker.log`
- PC muss **wach** sein (kein Dauer-Sleep während Matrix)

**Absturz / PC-Aus / stale Lock:**

| Schritt | BAT |
|---------|-----|
| Recovery (Lock, Status, Snapshot) | `run_r0_migration_recover.bat` |
| Matrix neu | `run_r0_migration_m1.bat` |

Snapshot: `evidence/r0_migration/crash_recovery.json` · Matrix-Log wird **angehängt**, nicht überschrieben.

**Manuell M0 nachziehen:** `run_r0_migration_seal_phase.bat M0`

---

## Status-Tracking

| Datei | Inhalt |
|-------|--------|
| `control/r0_migration/phase_status.json` | Phasen M0–M12 (`SEALED` = freigegeben) |
| `control/r0_migration_program.json` | aktuelle Phase |
| `evidence/r0_migration/m1_completion_summary.json` | M1-Blocker |

---

*Stand wird bei Phasen-**Seal** in `phase_status.json` aktualisiert.*
