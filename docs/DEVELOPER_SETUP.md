# Developer Setup — Active Alpha / R3

Read-only research cockpit. **Fail-closed** by default — no auto-orders, no champion changes.

## Quick start (Ubuntu)

```bash
cd ~/active_alpha_model
python3 -m venv .venv
.venv/bin/pip install -r requirements_active_alpha.txt

# Stack + R3 Desktop stabilisieren
bash tools/developer_bootstrap.sh

# R3 Fenster (falls nicht schon offen)
bash tools/r3_cockpit.sh
```

Hub: `http://127.0.0.1:17890` · Surface: `/r3`

## Allowed tests (no operative jobs)

```bash
.venv/bin/python -m pytest tests/test_p0_safety_control_plane.py -q
.venv/bin/python -m pytest tests/test_r3_ubuntu_stability.py -q
```

See `AGENTS.md` for the full allowed test list.

## Safety flags (do not enable without external approval)

| Flag | Required value |
|------|----------------|
| `auto_execute_real_money_enabled` | `false` |
| `auto_promote_*` | `false` |
| `auto_research_enabled` | `false` |

## Trading 212 — „nicht vertrauenswürdig“

**Das ist kein Werturteil über den Broker.** Es ist ein **Trust Gate** (`integrations/trading212/t212_trust_gate.py`):

Live-Cash, Plan-Skalierung und Orders sind blockiert, bis **frischer, gültiger API-Sync** vorliegt.

### Wann `trusted: false`?

| Code | Bedeutung |
|------|-----------|
| `NOT_CONFIGURED` | Kein API-Key hinterlegt |
| `RATE_LIMITED_SHOWING_CACHED_DATA` | T212 Rate-Limit — nur Cache, kein Live |
| `CONNECTION_FAILED_RETRY_AVAILABLE` | Verbindung fehlgeschlagen / Wartezeit (Throttle) |
| `STALE_SYNC` | Letzter Sync älter als 15 Min (`max_stale_sync_s`) |
| `CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA` | API-Key ungültig |
| `NO_SYNC` | Noch kein erfolgreicher Sync |

### Aktuell prüfen

```bash
.venv/bin/python3 -c "
from pathlib import Path
from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root
import json
print(json.dumps(assess_t212_trust_from_root(Path('.')), indent=2, ensure_ascii=False))
"
```

Evidence: `evidence/t212_trust_latest.json` · Policy: `control/t212_trust_policy.json`

### T212 vertrauenswürdig machen (Entwickler)

1. API-Key in GUI / Credential-Portal setzen (nicht in Git committen).
2. Rate-Limit abwarten (~2 Min zwischen Bulk-Syncs).
3. Manuell syncen: `bash tools/king_ops.sh r3-aktuell` oder Hub → T212 aktualisieren.
4. Erfolg wenn: `trusted: true`, `cash_eur` gesetzt, `last_sync_utc` frisch.

Orders bleiben **read-only / GUI-Bestätigung** — auch bei `trusted: true` kein Auto-Execute.

## Git publish

`bash tools/publish_public_git.sh` — siehe `docs/PUBLIC_GIT_PUBLISH.md`

## Projekt absichern

```bash
bash tools/project_security_lockdown.sh
```

Prüft: `promotion_gate_config.yaml`, Safety-Flags, `.cursor/hooks.json`, Secret-Rechte (chmod 600/700), Leak-Hinweis für Public-Git.

Evidence: `control/project_security_lock.json`, `evidence/project_security_lock_latest.json`

## Repair

```bash
bash tools/r3_ubuntu_stabilize.sh
bash tools/stack_integrity.sh --repair --launch
```
