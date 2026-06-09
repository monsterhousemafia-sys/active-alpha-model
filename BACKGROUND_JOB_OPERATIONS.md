# Background Job Operations

Stand: 2026-05-30 · Phase C Scaffold (standardmäßig deaktiviert)

## Jobs

| Job | Batch | Env-Variable | Default |
|-----|-------|--------------|---------|
| `realtime_collect` | `run_realtime_collector.bat` | `AA_JOB_REALTIME_COLLECT_ENABLED` | 0 |
| `eod_finalize` | `run_eod_finalize.bat` | `AA_JOB_EOD_FINALIZE_ENABLED` | 0 |
| `rebalance_signal` | `run_rebalance_signal.bat` | `AA_JOB_REBALANCE_SIGNAL_ENABLED` | 0 |
| `portfolio_review_live` | `run_portfolio_review_live.bat` | `AA_JOB_PORTFOLIO_REVIEW_LIVE_ENABLED` | 0 |
| `feedback_update` | `run_feedback_update.bat` | `AA_JOB_FEEDBACK_UPDATE_ENABLED` | 0 |
| `background_validate` | `run_background_validation.bat` | `AA_JOB_BACKGROUND_VALIDATE_ENABLED` + `AA_BACKGROUND_VALIDATE_ENABLED` | 0 |

CLI: `python tools/run_background_job.py <job>`

Status: `background_job_status.json` im Projektroot.

## Prozesslock

`.active_alpha_jobs/<job>.lock` — konkurrierende Instanz → Exitcode **3**, Status `LOCKED`.

## Windows Task Scheduler (manuell)

1. Task erstellen → Trigger nach Bedarf (z. B. `realtime_collect` alle 5 min während RTH).
2. Aktion: Batch-Datei mit `Start in` = Projektroot.
3. Env in `active_alpha_settings.bat` oder Task-Umgebung setzen.
4. **Nicht** automatisch registriert — bewusste manuelle Freigabe pro Job.

## Exitcodes

| Code | Bedeutung |
|------|-----------|
| 0 | OK, SKIPPED oder DISABLED |
| 1 | Unbehandelter Fehler |
| 2 | Fachlicher Fehler (z. B. kein validierter Champion) |
| 3 | Lock belegt |

## Abhängigkeiten

- `rebalance_signal` erfordert `latest_validated_run.json` mit Integrity PASS.
- `background_validate` startet nur mit `AA_BACKGROUND_VALIDATE_ENABLED=1` den Referenzlauf.
- Realtime-Jobs melden `REALTIME_PROVIDER_NOT_CONFIGURED` ohne Provider (Phase D).
