# Marktanalyse — Betrieb & Ops

Kurzreferenz für **Marktanalyse.exe**, Fast-Path und periodischen Daten-Refresh.

## Launcher-Flow

1. Single-Instance-Check
2. Preflight (Dateien, Speicher, Tagesdaten)
3. Laufplan: `results` | `refresh_analyze` | `analyze`
4. Ops-Refresh (Preise/Universe, optional Signal)
5. Paper Mark-to-Market (optional deferred)
6. Ergebnis-UI oder Voll-Backtest

## Wichtige Umgebungsvariablen

| Variable | Default (EXE) | Bedeutung |
|----------|---------------|-----------|
| `AA_FAST_PATH` | `1` | Gespeicherte Analyse anzeigen wenn Daten OK |
| `AA_AUTO_OPS_REFRESH` | `1` | Periodischer Refresh aktiver Caches |
| `AA_OPS_REFRESH_INTERVAL_HOURS` | `24` | Mindestabstand zwischen erfolgreichen Refreshes |
| `AA_SKIP_PNG_CHARTS` | `1` | Keine matplotlib-PNGs beim Start (Qt Charts) |
| `AA_STARTUP_CACHE_PRICES` | `1` | Cache-Preise zuerst, Live-Kurse im Hintergrund |
| `AA_DEFER_PAPER_ON_FAST_PATH` | `1` | Paper MTM nach UI-Anzeige |
| `AA_SKIP_VENV_PROBE` | `1` | Kein langsamer .venv-Import-Check in der EXE |
| `AA_FORCE_FULL_ANALYSIS` | `0` | Erzwingt Voll-Backtest |

## Ops-Refresh

- Meta-Datei: `{AA_BACKTEST_OUT_DIR}/ops_refresh_meta.json`
- `last_success_at_utc` wird nur bei `report.ok=True` gesetzt
- `last_attempt_at_utc` bei jedem Refresh-Versuch
- Lock-Datei: `.ops_refresh.lock` — parallele Läufe werden übersprungen (`ops_lock_contended` in `system_status.json`)

Preis-Refresh setzt via `aa_cache_coherence` u.a. `AA_FORCE_REBUILD_FEATURES=1`.

## Fast-Path Voraussetzungen

**Operativ** (Preise, Preflight):

- Tagesdaten OK (`assess_daily_data`)
- Preflight nicht blockierend

**Analytisch** (Backtest-Integrität):

- `latest_validated_run.json` mit `integrity_status: PASS`
- `runs/<run_id>/integrity_report.json` status PASS
- synchronisierte Artefakte: `strategy_daily_returns.csv`, `backtest_report.txt`, …

Ohne validierten Pointer: Fast-Path fällt auf Vollanalyse zurück. Die GUI zeigt keine Performance-Kennzahlen als gültig an (`analytical_validity != PASS`).

## Status

- `system_status.json` im Projektroot
- `health`: kombiniert aus `operational_health` und `analytical_validity`
- `operational_health`: `OK` | `WARN` | `ERROR` (Preflight, Daten, Exitcode)
- `analytical_validity`: `PASS` | `INVALID` | `UNKNOWN`
- WARN z.B. bei Ops-Lock, fehlgeschlagenem Paper-MTM, veralteten Daten

## Validierung / Phase 10

Schnell-Profil (Standard für `--phase matrix|cost|all`):

| Hebel | Effekt |
|-------|--------|
| `--no-naive-momentum-baseline` | ~12 min/Lauf (Phase C entfällt) |
| `--minimal-backtest-reporting` | Kein Factor/Benchmark/Bootstrap |
| `--backtest-scope path-only` (Kostenstress) | Phase A entfällt, nur Pfad+Kosten |
| `--parallel-jobs 2–3` | Varianten parallel (Kerne geteilt) |
| Warm-first | Erste Variante serial → Shared Feature-Cache |
| `--skip-complete` | R3-PASS wird übersprungen |
| Kostenstress | 9 statt 12 Läufe (`cost_s2_i0` = Basis) |

Grober Zeitplan (16 Kerne, R3 PASS): Matrix **~25–35 min**, Kostenstress **~25–35 min** → **~50–70 min**.

### Hardware-Profile (EXE nicht ausbremsen)

| Variable | BAT-Default | Bedeutung |
|----------|-------------|-----------|
| `AA_RUNTIME_PROFILE` | `research` | `exe` / `research` / `validation` / `background` |
| `AA_RESERVE_CPU_CORES` | `2` | Kerne für GUI/OS/EXE freihalten |
| `AA_VALIDATION_PARALLEL_JOBS` | `3` | Parallele Varianten in der Matrix |

Validierung erkennt eine laufende **Marktanalyse.exe** und wechselt automatisch auf `background` (1 Variante, idle-Priorität). Batch-Lock: `.active_alpha_batch.lock`.

```bat
.venv\Scripts\python.exe tools\run_validation_matrix.py --dry-run --phase all
.venv\Scripts\python.exe tools\run_validation_matrix.py --phase all --parallel-jobs 3
.venv\Scripts\python.exe tools\run_validation_matrix.py --phase cost --cost-mode path-only
.venv\Scripts\python.exe tools\run_validation_matrix.py --phase reference
.venv\Scripts\python.exe tools\backfill_validated_run.py --out-dir model_output_sp500_pit_t212 --dry-run
```

Outputs unter `validation_runs/<timestamp>_<variant>/` — produktive Ordner werden nicht überschrieben.

## Build & Autostart

```bat
build_active_alpha_launcher.bat
setup_active_alpha_startup.bat
tools\verify_exe_integration.py
```

Onedir-Bundle: `Marktanalyse/` + Root-Launcher `Marktanalyse.exe` (Junction `_internal`).

## Control Center vs. EXE

- **Marktanalyse.exe** nutzt `aa_ops`, `aa_preflight`, `aa_ops_refresh`
- **active_alpha_control_center.py** — separate CLI für Paper/Rebalance-Checks (`control_output/`)

Beide prüfen ähnliche Artefakte; operative Wahrheit für die GUI ist der EXE-Pfad.
