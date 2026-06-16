# External Review Approval — Neues Trading212-Konto + Zielportfolio

Review date: 2026-06-14

## Scope

**APPROVED** — Anbindung eines **neuen Trading212-Kontos** (Invest/ISA) per Live-API und
Umschichtung auf das Modell-**Zielportfolio** (`model_output_sp500_pit_t212/latest_target_portfolio.csv`)
ausschließlich über **R3 mit Operator-Bestätigung**.

## Decision

| Erlaubt | Verboten (ohne weitere Freigabe) |
|---------|----------------------------------|
| Broker-Connectivity, Read-only Sync, Live-Quotes | `auto_execute_real_money_enabled` |
| Zielportfolio-Berechnung (Plan, Reeval, Freigabe-Vorschau) | Stille Hintergrund-Orders |
| Bestätigte T212-Orders über R3 (`R3_DESKTOP`, `USER_CLICK`, …) | Champion-Wechsel |
| Core-Live-Pilot mit GUI-Bestätigung (max 500 €) | Auto-Rebalance ohne Klick |

## Preconditions

- Champion unverändert: **`R0_LEGACY_ENSEMBLE`** (Review-Baseline `R3_w075_q065_noexit`)
- API-Key mit Rechten: **Account-Daten + Orders**
- Neues Konto muss in R3 explizit bestätigt werden (`confirm_account=1`) — kein stiller Account-Wechsel
- Kill-Switch und Confirmed-Execution-Preflight bleiben aktiv

## Explicitly not authorized

- Automatic real-money execution without operator confirmation per wave
- Parameter or champion changes
- Orders from scheduler, engine, or headless sources

## Author

User explicit authorization — 2026-06-14
