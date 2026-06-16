# Marktanalyse Decision Cockpit — Codex Project Rules

## Product goal

Build an auditable, read-only decision cockpit for quantitative research and later paper-evidence visualization in a Windows EXE.

## Global safety invariants

- Authoritative champion for governance/display: **`R3_w075_q065_noexit`** via `aa_evidence_schema.resolve_locked_champion()` and `control/authorization/champion_lineage_status.json`. Unsealed `R5_rank_only_train5` operational claims are quarantined under `control/quarantine/g0r_r5_unauthorized/` — not authoritative.
- Further champion changes require explicit external approval.
- `auto_research_enabled` must remain `false` until a later externally approved operational phase.
- `auto_promote_paper_enabled` must remain `false`.
- `auto_promote_signal_enabled` must remain `false`.
- `auto_execute_real_money_enabled` must remain `false`.
- Real-money execution is prohibited.
- Automatic promotion is prohibited.
- No economic model parameter or productive signal-weight changes without a new external approval.
- No EXE execution by Codex.
- No scheduled or background Codex automation unless separately approved after controller review.

## Phase execution rule

- Only the phase named in a genuine `EXTERNAL_REVIEW_APPROVAL_<PHASE>.md` may be executed.
- Files beginning with `TEMPLATE_` never authorize execution.
- Each phase must end with tests, a report, a review ZIP and status `AWAITING_EXTERNAL_REVIEW`.
- No subsequent phase may begin in the same run.

## Prohibited jobs unless explicitly approved in a future operational phase

- research jobs
- replay jobs
- shadow collection
- paper simulation
- promotion
- rollback
- backtests
- M1 validation or recalculation
- trading or broker connectivity
- EXE builds except a separately approved V5 build phase

## Safe engineering requirements

- Use atomic writes for control, evidence, experiment and controller artifacts.
- Use Git branches and backups before modifications.
- Treat missing evidence and conflicting evidence fail-closed.
- Never alter champion, pointer or promotion artifacts from evidence aggregation code.

---

# AGENTS.md — Active Alpha / Marktanalyse Decision Cockpit (project layout)

## Projektziel

Schrittweise ein **auditierbares Decision Cockpit** in der Windows-EXE `Marktanalyse.exe` aufbauen: Champion/Challenger-Evidenz, Gates, Pipeline, Safety und Blocker read-only sichtbar machen.

## Sektor-Lookup (Infrastruktur, Champion-neutral)

Lookup-Reihenfolge: `sector_reference.csv` (PIT) → `sector_yfinance_cache.json` → `SECTOR_MAP` → `"Unknown"`. Refresh: Universum-/`load_tickers`-Pipeline, `ensure_sector_reference_fresh`, Abdeckung: `python tools/verify_sector_reference_coverage.py`.

## Relevante Verzeichnisse

| Pfad | Zweck |
|------|--------|
| `model_output_sp500_pit_t212/` | Produktives Backtest-/Status-Output |
| `control/` | Pipeline-Pending, System-Health, LKG, Promotion-Status, Champion-Lineage |
| `control/champion_lineage_policy.json` | Champion R3→R5 Lineage, Resolver, Review-Baseline |
| `paper_output/` | Paper-Trading-Artefakte (read-only in frühen Phasen) |
| `validation_runs/` | Research-/Validierungsläufe |
| `tests/` | Unit-Tests |
| `tools/active_alpha_launcher.py` | PyInstaller-Einstieg → `Marktanalyse.exe` |
| `aa_dashboard_qt_window.py` | PySide6-GUI |
| `aa_auto_promotion.py` | Promotion-Gates (fail-closed) |
| `aa_pipeline_orchestration.py` | Pipeline JSON/YAML/Pending |
| `aa_safe_io.py` | Atomare Writes |

## R3 Exec Mirror (Daytrading-Oberfläche)

Architekturplan: [`docs/R3_EXEC_MIRROR_ARCHITECTURE.md`](docs/R3_EXEC_MIRROR_ARCHITECTURE.md) · Surface-Version: `exec_mirror_v14` (`analytics/r3_surface.py`).

| Modul | Rolle |
|-------|--------|
| `analytics/r3_t212_operator_api.py` | Domain SSoT — Operator-Zugangsdaten, Gates, Persistenz |
| `analytics/r3_t212_setup_ui.py` | Nur UI — T212-Formular auf `/r3` |
| `analytics/r3_t212_api_bond.py` | T212 Bond-Sync, Evidence, Bond-Lock |
| `analytics/r3_mirror_state.py` / `r3_mirror_view.py` | State → HTML (Exec-Spiegel) |
| `analytics/r3_mirror_capital.py` | Kapital/Trust für Mirror |
| `tools/preview_hub.py` | HTTP-Hub (`/r3`, `/api/r3/*`) |

Marker: `control/r3_t212_operator_setup.json` (`web_setup_complete`) — stille `.env` allein reicht nicht.

## Erlaubte Unit-Tests (ohne operative Jobs)

```text
.venv\Scripts\python.exe -m pytest tests/test_p0_safety_control_plane.py -q
.venv\Scripts\python.exe -m pytest tests/test_p7_auto_promotion.py -q
.venv\Scripts\python.exe -m pytest tests/test_p8_acceptance_audit.py -q
.venv\Scripts\python.exe -m pytest tests/test_pipeline_orchestration.py -q
.venv\Scripts\python.exe -m pytest tests/test_pipeline_autopilot.py -q
.venv\Scripts\python.exe -m pytest tests/test_control_plane.py -q
```

Phase-spezifische Tests nur in der autorisierten Phase ausführen.

## Verbotene operative Jobs (ohne externe Freigabe)

- `Marktanalyse.exe`, `run_active_alpha_model.bat`, `run_active_alpha_launcher.bat`
- `run_development_autopilot.bat`, `tools/run_pipeline_autopilot.py` (Session-Autopilot)
- Historische Validation Matrix, M1-Neuberechnung
- Research-, Replay-, Shadow-, Paper-, Promotion-, Rollback- oder Echtgeld-Trading-Jobs
- Champion-Wechsel, Änderung produktiver Signalgewichte oder ökonomischer Modellparameter

## Safety-Flags — nicht aktivieren

| Flag | Erlaubter Wert |
|------|----------------|
| `auto_promote_paper_enabled` | `false` |
| `auto_promote_signal_enabled` | `false` |
| `auto_execute_real_money_enabled` | `false` |
| `auto_research_enabled` | `false` (V0R–V2 Entwicklungsphasen; frühestens V3 nach externer Freigabe) |
| Aktiver Champion (runtime) | `R5_rank_only_train5` via `control/operational_champion.json` — **kein weiterer Wechsel** ohne externe Freigabe |
| Historischer Review-Champion | `R3_w075_q065_noexit` in sealed `EXTERNAL_REVIEW_APPROVAL_FINAL.md` |

Fehlende Evidenz = **fail-closed** (keine Promotion, keine höhere Evidence-Ladder-Stufe).

## Phasen-Governance

- Programmplan: `VISION_DECISION_COCKPIT_EXECPLAN.md`
- Fortschritt: `VISION_PROGRESS.json`
- **Jede Phase** erzeugt ein Review-ZIP und **stoppt danach**.
- **Keine nächste Phase** ohne `EXTERNAL_REVIEW_APPROVAL_<PHASE>.md` im Projektstamm.
- Steuerdateien (`DEVELOPMENT_PIPELINE.*`, `control/pipeline_pending.json`, `promotion_gate_config.yaml`, `NEXT_CURSOR_PROMPT.md`) nur **atomar** schreiben (`aa_safe_io`).

## Cursor-/Autopilot-Hooks

- Aktive `.cursor/hooks.json` muss leer sein (kein Session-Autopilot, kein pauschaler Shell-`allow`).
- Deaktivierte Hook-Konfiguration: `.cursor/hooks.disabled.json` (nur Archiv, nicht reaktivieren ohne Freigabe).

## Konfliktregel

Widerspricht eine ältere Anweisung diesen Regeln, **stoppe** die Aktion, dokumentiere den Konflikt im Phasenbericht, arbeite nur an nicht widersprechenden Teilen weiter.

## Ergänzung — Master-Task Evidenzregeln (2026-05)

- Keine Broker-, Order-, Paper-, Shadow- oder Real-Money-Ausführung ohne separate ausdrückliche Autorisierung.
- Decision Cockpit bleibt fail-closed und read-only.
- Research-Änderungen dürfen produktive Defaults nicht unbemerkt ändern (`risk_off_*` Standard = `legacy`).
- Jeder Status PASS muss durch reproduzierbare Evidence belegt sein.
- Jeder Backtestvergleich muss Inputs, Kosten, Varianten und Trial Ledger offenlegen.
- Kein stiller Download oder Austausch historischer Daten in eingefrorenen Vergleichsläufen.
- Alle Änderungen müssen getestet, gehasht und reportet werden.
- V5R-Runtime-Verifikation der finalen `dist/Marktanalyse.exe` ist für externe Abnahme erforderlich (widerspricht älterer „No EXE execution by Codex“-Regel nur in explizit autorisierten V5R-Phasen).
