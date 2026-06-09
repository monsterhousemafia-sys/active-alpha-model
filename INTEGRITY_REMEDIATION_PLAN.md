# Integrity Remediation Plan — Active Alpha Model (R3)

Stand: 2025-05-29 · Profil R3 · Ziel: Backtest-Validität vor weiteren Modelloptimierungen.

## A. Bestandsaufnahme (Kontrollflüsse)

| Thema | Ort | Beschreibung |
|-------|-----|--------------|
| Rebalance-Termine | `aa_backtest.run_walkforward_pipeline` | `rebalance_dates = [d for idx,d in enumerate(dates) if d >= first_possible and idx % rebalance_every == 0]` |
| `ml_retrain_every` | `aa_backtest_ml.precompute_backtest_predictions` | Fit nur an Terminen mit `n % retrain_every == 0`; Zwischentermine per Forwarding |
| Prediction Cache | `aa_features._try_load_prediction_cache` / `_save_prediction_cache` | Pickle + Meta; Schema v3 mit Coverage-Metadaten |
| Pfadsimulation | `aa_backtest._simulate_walkforward_portfolio_path` | Phase B; nutzt Cache oder serielles ML; forwarded → Re-Selektion auf aktuellem Snapshot |
| Strategie-Tagesrenditen | `_simulate_walkforward_portfolio_path` → `strategy_daily_returns.csv` via `write_backtest_core_outputs` | Vektorisierte Periodenrenditen zwischen Rebalances |
| `backtest_decisions` / `backtest_weights` | `_simulate_walkforward_portfolio_path` decision_rows / weight_rows | Pro Rebalance; finale Diagnosen in `dec_extra` |
| `constraint_binding_history` | `aa_portfolio.write_constraint_binding_history` | Dedup pro `rebalance_date`; nutzt finale Exposure-Felder |
| Fast-Path-Gültigkeit | `aa_ops.validate_persisted_analysis` | Liest `latest_validated_run.json` + `integrity_report.json` (status PASS) |
| GUI-Allokation | `aa_dashboard_result.scale_portfolio_rows` | `amount × target_weight`; Cash = Rest |
| Batch-Returncodes | `run_active_alpha_launcher.bat` → `exit /b %ERRORLEVEL%` | Python-Exitcode wird durchgereicht |

## B. Sicherungsregeln

- Neue Validierungsläufe: `validation_runs/<timestamp>_<variant>/`
- Produktive Outputs (`model_output_sp500_pit_t212/`) werden nicht überschrieben ohne expliziten Lauf
- Ungültige Runs bleiben unter `runs/<run_id>/` mit `status=INVALID`
- Nur PASS-Runs aktualisieren `latest_validated_run.json`

## C. Bestätigte Probleme und geplante Änderungen

### 1. Backtest-Kalender / `ml_retrain_every` (Phase 1)
- **Problem:** `n_jobs <= 1` lieferte leeren Prediction-Cache; Phase B übersprang Rebalances bei `status != ok` (inkl. `forwarded_ml_retrain`).
- **Fix:** Serielle Phase A; `resolve_forwarded_ml_prediction` re-selektiert auf aktuellem Snapshot; `validate_backtest_calendar_integrity`.
- **Tests:** ml_retrain_every 1/2/3 gleiche Periodenanzahl; fehlende Cache-Termine → INVALID.

### 2. Finale Portfoliodiagnostik (Phase 2)
- **Problem:** `rec = dict(dec_extra); rec.update(row_dict)` überschrieb finale Exposure/Beta.
- **Fix:** Merge umgekehrt; `final_*`-Felder aus finalen Gewichten; `portfolio_exposure` = finale Exposure.

### 3. Run-Provenienz (Phase 3)
- **Problem:** Gemischte Artefakte aus verschiedenen Läufen im selben Output-Ordner.
- **Fix:** `runs/<run_id>/`, `run_manifest.json`, Code-/Config-Fingerprint; atomarer Pointer `latest_validated_run.json`.

### 4. Fast-Path / GUI (Phase 4)
- **Problem:** Existenzprüfung ohne analytische Validität.
- **Fix:** Trennung `operational_health` / `analytical_validity`; GUI blockiert ungültige Performance-Anzeige.

### 5. Cash-/Exposure-Synchronisation (Phase 5)
- **Problem:** GUI normalisierte Gewichte auf 100 % des Betrags.
- **Fix:** `target_weight` = Anteil am Gesamtportfolio; explizites Cash.

### 6. Variantenidentität (Phase 6)
- **Problem:** „R3“ für unterschiedliche Parameter.
- **Fix:** `aa_variant_id.resolve_canonical_variant_id` → z. B. `R3_w070_q070_noexit`.

### 7. Prediction Cache (Phase 7)
- **Problem:** Fehlende Zwischenrebalances still akzeptiert; Schema ohne Coverage.
- **Fix:** Schema v3; Coverage-Prüfung; Risk-off-Parameter im Fingerprint (bereits vorhanden).

### 8. Launcher / Fonts (Phase 8)
- **Problem:** Font-Warnungsflut `Segoe UI Variable Text`; Batch-Quoting.
- **Fix:** Robuste Font-Fallbacks; Matplotlib-Warnfilter.

### 9. Datenqualität (Phase 9)
- **Problem:** DIY-PIT ohne explizites Gate vor Modellvergleichen.
- **Fix:** `aa_data_quality_gate`; Status `DATA_QUALITY_WARN` / `PASS` im Report.

## Testkriterien (Akzeptanz)

1. Vollständiger Backtest bei `rebalance_every=5`: alle erwarteten Handelstage in `strategy_daily_returns.csv`.
2. `ml_retrain_every=2` simuliert gleich viele Halteperioden wie `=1`.
3. `sum(weights) ≈ final_portfolio_exposure ≈ final_validated_exposure` pro Rebalance.
4. GUI: Summe Gewichte 0,65 → 650 EUR Positionen + 350 EUR Cash bei 1000 EUR.
5. Fast-Path nur bei `integrity_report.json` status PASS und konsistenter Run-ID.
6. Ungültiger Run überschreibt `latest_validated_run.json` nicht.
7. `pytest` grün (bestehend + neue Integrity-Tests).

## Spec-Abgleich (2026-05-30, Schritte 1–4)

| Spec-Abschnitt | Status |
|----------------|--------|
| A1 Kalender / `ml_retrain_every` | Implementiert; R3-Referenz 372/372 PASS |
| A2 Finale Exposure/Beta | Merge fix in `aa_backtest.py` |
| A3 Run-Provenienz | `aa_run_provenance.py`, `runs/<run_id>/` |
| A4 Fast-Path / GUI | `aa_ops_validation.py`, `aa_system_status.py` |
| A5 Cash-Sync | `aa_dashboard_result.scale_portfolio_rows` |
| B–L Realtime/Behavioral | **Nicht gestartet** — siehe `REALTIME_BEHAVIORAL_ARCHITECTURE.md` |

**Referenzdokumente:** `IMPLEMENTATION_STATUS.md`, `REALTIME_BEHAVIORAL_ARCHITECTURE.md`

**Offene Testlücken (nicht Gate-blockierend):** Integration `ml_retrain_every` 1/2/3 im Walk-forward; M1-Kalender-Parität; Exposure-Invariant aus CSV-Fixtures.

## Offene Risiken (nach Reparatur)

- DIY-PIT-Universum: Delisting-/Corporate-Action-Lücken bleiben.
- `ml_retrain_every > 1`: Modell wird nicht neu gefittet, nur Predictions wiederverwendet + Re-Selektion — ökonomisch beabsichtigt, aber nicht identisch zu täglichem Refit.
- Vollständige Validierungsläufe (Phase 10) erfordern separaten manuellen/CI-Lauf in `validation_runs/`.
