# R3 Exec Mirror — Architekturplan

**Stand:** 2026-06-10 · **Surface:** `exec_mirror_v14` (`analytics/r3_surface.py`)

Operative Oberfläche für Daytrading-Freigabe: eine Seite (`/r3`), read-only Evidence, fail-closed Gates. Kein Auto-Execute, kein stiller Champion-Wechsel.

---

## 1. Schichtenmodell

```text
┌─────────────────────────────────────────────────────────────┐
│  Hub     tools/preview_hub.py                               │
│          GET /r3 · GET/POST /api/r3/*                       │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  View     analytics/r3_mirror_view.py                       │
│           HTML/CSS/JS — Poll, Freigabe-Button, T212-Formular│
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│  State    analytics/r3_mirror_state.py                      │
│           Evidence-JSON → ein Mirror-Dict                   │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
  r3_mirror_capital   r3_freigabe        r3_one_click_start
  (Kapital/Trust)     (Paket ready)      (Start-Kette)
        │                   │                   │
        └───────────────────┼───────────────────┘
                            ▼
              r3_t212_operator_api  ← Domain SSoT (Zugangsdaten)
                            │
                            ▼
              r3_t212_api_bond      ← Live-Sync, Bond-Lock
                            │
                            ▼
              integrations/trading212/*  ← Read-only Broker
```

**Public API:** `analytics/r3_exec_mirror.py` re-exportiert State + View.

---

## 2. T212 Operator-API (Domain)

| Modul | Verantwortung |
|-------|----------------|
| `analytics/r3_t212_operator_api.py` | **SSoT** — Setup-State, `.env`-Persistenz, Gates, `save_t212_credentials_from_web` |
| `analytics/r3_t212_setup_ui.py` | **Nur UI** — Key/Secret-Formular (HTML/CSS/JS), Re-Exports aus Domain |
| `analytics/r3_operator_surface_text.py` | Minimale Operator-Texte (`OPERATOR_API_ENTER`, …) |
| `analytics/r3_t212_api_bond.py` | Bond-Sync, Evidence `evidence/r3_t212_api_bond_latest.json`, `merge_operator_api_fields`, `ensure_operator_bond_lock` |
| `analytics/r3_mirror_capital.py` | Autoritatives Kapital für Mirror — investierbar nur bei Trust **und** `operator_api_ready` |

### Marker & Persistenz

| Artefakt | Zweck |
|----------|--------|
| `control/r3_t212_operator_setup.json` | `web_setup_complete: true` nach einmaliger Web-Eingabe |
| `root/.env` | `TRADING212_API_KEY` / `TRADING212_API_SECRET` (atomar) |
| `control/r3_t212_api_bond.json` | Bond-Lock (`bonded`, Fingerprints) |
| `evidence/r3_t212_api_bond_latest.json` | Live-Kontostand, Trust, Confirmation-Text |

**Regel:** Stille `.env` ohne Web-Setup-Marker → `needs_api_setup: true` (fail-closed).

### Operator-Flow

1. Operator öffnet `/r3` → Formular sichtbar wenn `needs_operator_api_setup()`.
2. `POST /api/r3/t212/credentials` → `save_t212_credentials_from_web()`.
3. Persistenz: GUI-Controller + `.env` + Setup-Marker + Bond (`ensure_r3_t212_api_bond`).
4. Gates prüfen `operator_api_ready()` — nicht erst nach vollem Live-Sync.

### Zentrale Gate-Helfer

```python
operator_api_gate_block(root, **extra)      # generisch — returns None oder fail-dict
operator_api_account_block(root)            # Closed-Loop / Account-Engine
merge_operator_api_fields(doc, root, ...)   # Bond-Evidence anreichern
ensure_operator_bond_lock(root, bond, api_state)
```

**Consumer (Auszug):** `r3_one_click_start`, `r3_prognosis_pipeline`, `r3_order_execution_gate`, `r3_live_capital`, `r3_closed_loop`, `king_plan_integration`, `t212_trust_gate`.

---

## 3. Surface-Cache

`SURFACE_RENDER_VERSION` in `analytics/r3_surface.py` invalidiert gerendertes HTML bei strukturellen UI-Änderungen.

| Version | Anlass |
|---------|--------|
| `exec_mirror_v13` | Vor Operator-API-Refactoring |
| `exec_mirror_v14` | Domain/UI-Trennung (`r3_t212_operator_api` + dünnes `setup_ui`) |

Prüfung: `surface_cache_valid()` — Version, `exec_mirror_only`, `surface_path` müssen passen.

---

## 4. HTTP-Endpunkte (Allowlist)

Registriert in `analytics/local_apps_registry.py` (Exec-Mirror-Modus):

| Route | Rolle |
|-------|--------|
| `GET /r3` | Exec-Spiegel-Seite |
| `GET /api/r3/mirror` | State-Payload (Poll) |
| `GET /api/r3/t212` | Bond + Operator-State |
| `POST /api/r3/t212/credentials` | Einmalige Zugangsdaten |
| `POST /api/r3/start` | One-Click-Start (nach Gates) |

---

## 5. Tests (ohne operative Jobs)

```bash
.venv/bin/python -m pytest \
  tests/test_r3_t212_setup_ui.py \
  tests/test_r3_t212_api_bond.py \
  tests/test_r3_one_click_start.py \
  tests/test_r3_mirror_capital.py \
  tests/test_r3_exec_mirror.py \
  tests/test_r3_closed_loop.py \
  tests/test_r3_trading_functions.py \
  tests/test_r3_surface.py \
  -q
```

Domain-Logik testen gegen `analytics.r3_t212_operator_api`; UI nur über `r3_t212_setup_ui.render_t212_setup_panel`.

---

## 6. Governance (unverändert)

- Champion locked: `R3_w075_q065_noexit` (Review) / Runtime laut `control/operational_champion.json`.
- `auto_execute_real_money_enabled` = `false` — keine Echtgeldorders ohne separate Freigabe.
- Fehlende Evidenz = fail-closed.

Siehe auch: `AGENTS.md`, `control/r3_operational_checklist_de.md`, `VISION_DECISION_COCKPIT_EXECPLAN.md`.
