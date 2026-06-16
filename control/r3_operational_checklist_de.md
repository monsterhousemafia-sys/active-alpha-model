# R3 Betriebs-Checkliste — Active Alpha Model

**SSoT (maschinenlesbar):** `control/r3_operational_checklist.json`  
**Basis:** Trading-Kreislauf, Order-Trennung, Safety-Invarianten aus `AGENTS.md`, Serienreife-Gates.

> R3 ist die **einzige Order-Oberfläche**. Active Alpha Model liefert Signal, Plan und Reevaluation — führt **keine** Broker-Orders aus.

---

## Schnellprüfung (Operator)

```bash
bash tools/king_ops.sh verify          # Safety
bash tools/king_ops.sh r3-sync --repair
bash tools/king_ops.sh series-ready    # Serienreife-Gates
bash tools/king_ops.sh r3-checklist    # Checkliste A–G (Evidence-Scan)
bash tools/king_ops.sh r3-cycle        # Kreislauf
bash tools/king_ops.sh cockpit-update  # R3 ↔ Decision-Cockpit-Vision
```

Browser: `http://127.0.0.1:17890/r3`  
Evidence: `evidence/r3_operational_checklist_latest.json` · `evidence/series_readiness_latest.json` · `evidence/decision_cockpit_update_latest.json`

---

## A — Safety & Governance (muss, fail-closed)

| # | Muss funktionieren | Prüfung |
|---|-------------------|---------|
| A1 | `auto_research_enabled` = false | `promotion_gate_config.yaml` |
| A2 | `auto_promote_*` = false | `promotion_gate_config.yaml` |
| A3 | `auto_execute_real_money_enabled` = false | `promotion_gate_config.yaml` |
| A4 | Champion gesperrt — kein stiller Wechsel | `control/champion_lineage_policy.json` |
| A5 | Orders **nur** aus R3-Quellen (`R3_DESKTOP`, `USER_CLICK`, …) | `control/r3_order_execution_policy.json` |
| A6 | Hintergrund/Scheduler/Engine **blockiert** für Live-Orders | `forbidden_order_sources` in Policy |
| A7 | Live-Submit nur nach GUI-Bestätigung + Gates | `resolve_submission_mode()` → Dry-Run wenn offen |

**Befehl:** `bash tools/king_ops.sh verify`

---

## B — Laufzeit & Autostart (muss)

| # | Muss funktionieren | Prüfung |
|---|-------------------|---------|
| B1 | Preview-Hub `127.0.0.1:17890` | `/api/health` → 200 |
| B2 | R3 Mirror API | `/api/r3/mirror` → JSON |
| B3 | Qt-Cockpit optional | `bash tools/r3_cockpit.sh` |
| B4 | Login-Autostart + `R3.desktop` | `bash tools/king_ops.sh r3-detach` |
| B5 | Stack intakt (Hub + Mirror + Cache) | `evidence/stack_integrity_latest.json` → `stack_ok` |
| B6 | `~/.local` Besitz = Benutzer | `evidence/r3_home_ownership_latest.json` |

**Befehl:** `bash tools/king_ops.sh r3-sync --repair`

---

## C — Trading-Kreislauf — 7 Stufen (muss)

Quelle: `control/r3_trading_cycle_policy.json`

| Stufe | Active Alpha / R3 | Evidence | Feld (berechnet) |
|-------|-------------------|----------|------------------|
| 1 Internet | Beide | `evidence/r3_internet_latest.json` | `internet_ok` |
| 2 Konto | R3 T212-Bond | `evidence/r3_t212_api_bond_latest.json` | `connected`, `cash_eur` |
| 3 Kurse | R3 Ingest | `evidence/r3_browser_ingest_latest.json` | `ok`, `price_latest` |
| 4 Modell | Alpha Engine | `evidence/alpha_model_background_engine_latest.json` | `ok`, Rebalance |
| 5 Plan | Champion-Skalierung | `evidence/pilot_investment_plan_latest.json` | `investable_eur`, `allocations` |
| 6 Anzeige | R3 Mirror | `/r3` read-only | Mirror-State aus Evidence |
| 7 Orders | **nur R3** + Bestätigung | `control/r3_order_execution_policy.json` | `AUTHORITATIVE` |

**Befehl:** `bash tools/king_ops.sh r3-cycle`  
**Anzeige:** Kreislauf-Faktenzeilen in `/r3` — Werte nur aus `r3_evidence_metrics` (kein `or 0`)

---

## E — Neues T212-Konto + Zielportfolio (Operator)

Freigabe: [`EXTERNAL_REVIEW_APPROVAL_T212_NEW_ACCOUNT_20260614.md`](../EXTERNAL_REVIEW_APPROVAL_T212_NEW_ACCOUNT_20260614.md)  
Scope: [`control/authorization/t212_new_account_scope.json`](authorization/t212_new_account_scope.json)

| # | Schritt | Befehl / Aktion |
|---|---------|-----------------|
| E1 | API-Key (Account + Orders) in T212 erzeugen | T212 App → Settings → API |
| E2 | Credentials speichern | R3 Broker-Setup oder `.env` (siehe `control/broker/TRADING212_SETUP.md`) |
| E3 | Verbindung testen | `python tools/setup_trading212_connection.py` |
| E4 | Bond sync | `curl 'http://127.0.0.1:17890/api/r3/t212?sync=1'` |
| E5 | **Neues Konto bestätigen** (fail-closed) | `curl 'http://127.0.0.1:17890/api/r3/t212?confirm_account=1'` |
| E6 | Zielportfolio-Kette | `bash tools/king_ops.sh alpha-engine` → R3 **Jetzt starten** |
| E7 | Paket ausführen | R3: Zielportfolio bestätigen (Confirmed Execution, kein Auto-Execute) |

**Evidence:** `evidence/r3_t212_api_bond_latest.json` (`account_label`, `account_fingerprint`) · `control/r3_t212_confirmed_account.json` · `evidence/r3_freigabe_latest.json` (`package_ready`)

**Hinweis:** Bei Konto-Wechsel blockiert Freigabe bis E5 erneut ausgeführt wurde.

---

## D — Anzeige `/r3` (muss)

| # | Muss funktionieren | Quelle |
|---|-------------------|--------|
| D1 | Plan-Panel: € + % aus Plan-Allocations | `pilot_investment_plan_latest.json` |
| D2 | T212-Panel: **Verkauf** und **Kauf** getrennt | `r3_stock_orders_latest.json` |
| D3 | Fakten-Stapel (System, Kreislauf, Pipeline) — nur Zahlen | `fields_de` je Metrik |
| D4 | Fehlende Evidence → `—` (nicht erfunden) | `analytics/r3_evidence_metrics.py` |
| D5 | Kompakt-Status: T212 · Paket · Kurse | Mirror-State |
| D6 | Live-Poll aktualisiert ohne Reload | `r3PollMirror` |
| D7 | Runtime-Upgrade: **Übernehmen / Später** — kein Auto-Apply | Operator-Freigabe |

---

## E — Handel Kauf + Verkauf (muss)

Quelle: `control/r3_trading_functions_policy.json` · `r3_stock_orders.py`

| # | Funktion | Verhalten |
|---|----------|-----------|
| E1 | **Einzel-Kauf** | Button → `confirm` → `POST /api/r3/order` → T212 |
| E2 | **Einzel-Verkauf** | Button (rot) → gleicher Pfad mit `side=SELL` |
| E3 | Verkauf-Quelle | Plan `side:SELL` **oder** Reeval `REDUZIEREN` (nur gehaltene Positionen) |
| E4 | **Gesamtpaket** | Nur BUY-Zeilen, Button `… € → T212`, `r3FreigabeSubmit` |
| E5 | Mindest-Trade | ≥ `min_trade_eur` (12 €) |
| E6 | Kein All-in | `max_single_buy_pct` eingehalten |
| E7 | Drei Meldungen | Initial · Verkauf · Umschichtung (`r3_trading_functions_latest.json`) |

**UI:** Immer zwei Blöcke sichtbar: **Verkauf** · **Kauf** (leer = `—`)

---

## F — Active Alpha Hintergrund (muss für korrekte R3-Daten)

| # | Muss liefern | Evidence |
|---|-------------|----------|
| F1 | Champion-Signal → Plan | `pilot_investment_plan_latest.json` |
| F2 | Reevaluation Kauf/Verkauf | `pilot_portfolio_reevaluation_latest.json` |
| F3 | Closed Loop Konto→investierbar | `r3_closed_loop_latest.json` |
| F4 | Kurse/Snapshot | `pilot_day_trading_snapshot_latest.json` |
| F5 | `order_gate_ok` | `control/prediction_readiness.json` |
| F6 | H1/Benchmark | König — **kein** R3-Blocker für Anzeige |

**Trennung:** Engine schreibt Pläne — R3 führt Orders aus.

---

## G — Operator & König (soll)

| # | Befehl | Zweck |
|---|--------|-------|
| G1 | `bash tools/king_ops.sh status` | Snapshot |
| G2 | `bash tools/king_ops.sh r3-apply` | UI sichtbar |
| G3 | `bash tools/king_ops.sh r3-detach` | Ohne Cursor |
| G4 | `bash tools/alpha_model_agent.sh` | König 32B |
| G5 | `bash tools/king_ops.sh series-ready` | Serienreife % |

---

## Automatisierte Tests (Regression)

```bash
.venv/bin/python3 -m pytest tests/test_r3_exec_mirror.py tests/test_r3_stock_orders.py \
  tests/test_r3_trading_cycle.py tests/test_r3_evidence_metrics.py \
  tests/test_r3_trading_functions.py tests/test_r3_order_execution_gate.py -q
```

---

## Was explizit **nicht** in R3 gehört

- Auto-Promote / Champion-Wechsel ohne externe Freigabe  
- H1-Backtest / Benchmark starten (König)  
- Orders aus Scheduler, Session, `sync_r3_flow`, Headless  
- Erfundene Anzeigezahlen ohne Evidence-Feld  
- Stiller Runtime-Apply ohne Operator (Übernehmen/Später)

---

*Checkliste abgeleitet aus dem produktiven Active-Alpha-Stack — bei Policy-Änderung JSON + MD gemeinsam aktualisieren.*
