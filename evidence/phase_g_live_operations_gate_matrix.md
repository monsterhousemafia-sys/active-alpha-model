# Phase G — Live-Operations Gate Matrix

Generated: 2026-06-03T20:26:33+00:00

| Step | Status | Kurzbefund |
| --- | --- | --- |
| G1 Symbol STX -> STX_US_EQ | **PASS** | Orders/Reports: Feld symbol = Champion-Ticker (STX); T212 nur in t212_instrument_id. |
| G2 Planning-Cash / Welle | **PASS** | Skalierung raw→planning_cash; Evidence in phase_g_planning_cash_audit.json |
| G3 Quote N/N (+SNDK) | **PASS** | 14/14 Kurse OK |
| G4 Execution-Report | **PASS** | 1 Zeile/Symbol: executed vs NO_LIMIT_PRICE vs PREFLIGHT |
| G5 EXE + OS-BAT | **PASS** | EXE-Rebuild nur mit --build-exe; OS-BAT startet Marktanalyse read-only. |
| G6 Phase-5 Dry-Run Pflicht | **PASS** | validate_live_rebalance_phase5.py — Dry-Run vor Release |

## Acceptance

- Overall: **PASS**
- Dry-run quote: `14/14 Kurse OK`

Live US-Session-Run mit echten Credentials separat im Dashboard dokumentieren.

