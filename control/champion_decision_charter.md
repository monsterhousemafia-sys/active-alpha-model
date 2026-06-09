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
| **MOM_63_TOP12** | Research-Challenger | Höherer Sharpe auf eigenem Kalender; Turnover/Gates separat |

**Aktueller Befund (Phase C, read-only):** R3 liegt auf Matrix-Sharpe **hinter** R0 und M1; das ist **bekannt und akzeptiert**, solange die Risk-off-Hypothese und Governance-Stabilität Vorrang haben.

**Nicht vergleichen:** Matrix-embedded Sharpe (R0–R4) mit intersection-aligned MOM-Sharpe ohne gemeinsame Return-CSV — siehe Warnung im Canonical Report.

## 3. Was „besser“ bedeuten würde (Zielfunktion)

Ein Wechsel ist nur sinnvoll, wenn ein Kandidat **explizit** gegen diese Zielfunktion gewonnen hat (nicht implizit über Auto-Promotion):

1. **Matrix-fair:** Gleicher Kalender (≥200 überlappende Tage oder dokumentierte 1860-Tage-Matrix), Sharpe-Delta ≥ `min_sharpe_delta_vs_champion` in `control/champion_change_criteria.yaml`.
2. **Risiko:** Max Drawdown nicht schlechter als Champion + `max_drawdown_degradation_vs_champion`.
3. **Kosten:** Cost-Stress `PLUS_25_BPS` PASS mit **eigenem** Turnover (kein Champion-Proxy).
4. **Statistik:** DSR-Policy erfüllt (`control/evidence/multiple_testing_status.json`).
5. **Operationalisierung:** Paper-Forward und Shadow-Outcomes gemäß Criteria-YAML.
6. **Governance:** Neues `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md` (kein Template).

**Auto-Promotion bleibt DISABLED** — auch bei erfüllten Backtest-Kriterien.

## 4. Explizite Nicht-Ziele

- Höchster Matrix-Sharpe als alleinige Zielgröße.
- Automatischer Champion-Wechsel aus Drift, Cockpit-Warnungen oder Challenger-Reports.
- **R5_rank_only_train5** oder andere quarantinierte Claims als operativer Champion.
- Nutzung verunreinigter `model_output_sp500_pit_t212/strategy_daily_returns.csv` (2450-Tage-Mix) für Champion-Metriken.
- Echtgeld-, Paper- oder Shadow-Jobs ohne separate externe Freigabe.
- Änderung produktiver Signal-Gewichte / Risk-off-Parameter ohne neues externes Review.

## 5. Referenzen

| Artefakt | Zweck |
|----------|--------|
| `evidence/canonical_model_comparison.json` | Kanonischer Vergleich (Phase C) |
| `control/champion_change_criteria.yaml` | Harte Wechsel-Kriterien |
| `control/champion_lineage_policy.json` | Lineage, R5-Quarantäne, Phase-B-Hashes |
| `CHAMPION_CHALLENGER_GOVERNANCE.md` | Operative Champion/Challenger-Regeln |
| `docs/governance/G1_COMPARISON_LOGIC.md` | G1-Vergleichslogik (nicht autorisiert bis Freigabe) |
