# Phase H — Operator Transparency

Generated: 2026-06-03T20:27:57+00:00
Status: COMPLETE

## H1 Modell-Vergleich (OK)

Modell-Vergleich (Research) — read-only
Champion (freigegeben): R3_w075_q065_noexit
Matrix-Sharpe-Führer: R0_LEGACY_ENSEMBLE
Champion Matrix-Rang: 4

Rangliste — Matrix embedded (~1860d):
   1. R0_LEGACY_ENSEMBLE (SIBLING_MATRIX) — Sharpe 0.9836
   2. M1_MOM_BLEND_MATCHED_CONTROLS (M1_CONTROL) — Sharpe 0.9834
   3. R2_MOM_BLEND_REPLACE (SIBLING_MATRIX) — Sharpe 0.9734
   4. R3_w075_q065_noexit (CHAMPION) — Sharpe 0.9228 [CHAMPION]
   5. R3_w070_q070_noexit (SIBLING_MATRIX) — Sharpe 0.9119
   6. R4_w070_q070_forceexit (SIBLING_MATRIX) — Sharpe 0.9055
   7. R1_GATE_BASE_ONLY (SIBLING_MATRIX) — Sharpe 0.8501

Rangliste — Aligned intersection (MOM/research CSVs):
   1. MOM_63_TOP12 (RESEARCH_CANDIDATE) — Sharpe 1.0311
   2. MOM_63_TOP12_STRICT (RESEARCH_CANDIDATE) — Sharpe 0.9983
   3. MOM_63_TOP15_RECONSTRUCTED (RESEARCH_CANDIDATE) — Sharpe 0.9938

WARNUNG: Matrix-embedded Sharpe ≠ MOM-Intersection-Sharpe vermischen.
Vollständig: evidence/canonical_model_comparison.md

## H2 Champion-Status (OK)

Produktiv-Champion: R3_w075_q065_noexit
Letztes Signal-Datum: 2026-06-02 (latest_target_portfolio.csv)
Auto-Promotion: DISABLED
Phase-E-Entscheidung: E1_RETAIN_R3 — R3_w075_q065_noexit

--- Charter (Auszug) ---
# Champion Decision Charter — R3_w075_q065_noexit

Stand: 2026-06-03 · Phase D (Governance)
Autoritative Quelle: `EXTERNAL_REVIEW_APPROVAL_FINAL.md`, `aa_evidence_schema.AUTHORITATIVE_CHAMPION`

## 1. Ökonomische Hypothese (warum R3 produktiv ist)

Der produktive Champion **R3_w075_q065_noexit** ist kein „max-Sharpe“-Modell, sondern ein **Risk-off-Momentum-Rescue**-Design:

| Parameter | Wert | Bedeutung |
|-----------|------|-----------|
| `risk_off_selection_mode` | `mom_blend_blend` | Momentum-Blend im Risk-off-Regime |
| `risk_off_momentum_weight` | 0.75 | Gewichtung Momentum vs. Basis |
| `risk_off_gate_mode` | `momentum_rescue` | Rettungs-Gate bei Stress |
| `risk_off_momentum_rescue_quantile` | 0.65 | Quantil für Rescue |
| `risk_off_force_exit_enabled` | false | Kein erzwungenes Voll-Exit |

**Hypothese:** In Risk-off-Phasen soll das Portfolio kontrolliert Momentum-Exposure halten und Drawdowns gegenüber naivem Ensemble / reinem Gate-Base begrenzen — nicht den höchsten historischen Sharpe auf der Matrix maximieren.

## 2. Bewusste Trade-offs vs. Referenzmodelle

Vergleichsrahmen: **Matrix embedded**, ~1860 Handelstage (siehe `evidence/canonical_model_comparison.md`).

| Referenz | Rolle | Typischer Trade-off vs. R3 |
|----------|-------|------------------------------|
| **R0_LEGACY_ENSEMBLE** | Primär-Benchmark | Höherer Matrix-Sharpe, weniger Risk-off-Spezialisierung |
| **M1_MOM_BLEND_MATCHED_CONTROLS** | Kontroll-Variante | Nahe R0-Sharpe, „matched controls“ ohne R3-Rescue-Logik |
| **R2 / R4** | Matrix-Geschwister | Leicht andere Risk-off-/Exit-Parameter |
… (gekürzt — vollständig in control/champion_decision_charter.md)

## H3 Rebalance-Vorcheck (WARN)

Rebalance-Vorcheck (read-only, keine T212-POSTs)
Planning-Cash: 34.34 EUR
Roh-Summe BUY (vor Welle): 32.62 EUR
Skaliert (nach Welle): 0.00 EUR
Scale-Faktor: 1.0
Quote-Coverage (geplante Käufe): 10/11 Kurse
Geplante BUY-Orders: 0
Blockiert (kein Live-BUY): SPY
Hinweis: Nur 10/11 Live-Kurse für geplante Käufe — Rebalance blockiert. Fehlend: SNDK. Bitte «Aktualisieren» (F5) oder US-Session warten.

Top-Positionen (nach Skalierung):

## H4 Pointer-Drift (PASS)

Locked Champion (Policy): R3_w075_q065_noexit
Pointer-Drift: nein

Beobachtete Pointer:
  control/challenger_report.json: R3_w075_q065_noexit
  model_output_sp500_pit_t212/challenger_report.json: R3_w075_q065_noexit
  model_output_sp500_pit_t212/latest_validated_run.json: R3_w075_q065_noexit

