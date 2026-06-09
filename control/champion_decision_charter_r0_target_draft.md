# Champion Decision Charter — Zielzustand R0 (ENTWURF, nicht aktiv)

**Status:** DRAFT — ersetzt `control/champion_decision_charter.md` erst nach M9 + externem Champion-Change-Seal  
**Mandat:** `docs/R0_MIGRATION_MANDATE.md` · M0 abgeschlossen  
**Aktueller produktiver Champion bis Cutover:** `R3_w075_q065_noexit`

---

## 1. Ökonomische Hypothese (warum R0 produktiv sein soll)

Der Ziel-Champion **R0_LEGACY_ENSEMBLE** (oder ein dokumentiertes **R0\***) ist ein **ML-Ensemble-Maximierungs**-Design:

| Parameter | Wert | Bedeutung |
|-----------|------|-----------|
| `alpha_model_mode` | `ensemble` | 40 % Elastic + 40 % GBM + 20 % Rank-Score |
| `risk_off_selection_mode` | `legacy` | Gleicher Ensemble-Score in risk-on und risk-off |
| `risk_off_gate_mode` | `legacy` | Trends + `alpha_lcb > -min_edge` |
| `risk_off_force_exit_enabled` | false | Kein erzwungenes Exit |

**Hypothese:** Auf einem **fairen, alignierten** Kalender liefert konsistentes ML-Ranking mit klassischen Risk-off-Gates **höheren** risk-adjusted Return und **flacheren** Drawdown als R3 — ohne Risk-off-Momentum-Rescue-Overlay.

---

## 2. Bewusste Trade-offs vs. Referenzmodelle

| Referenz | Rolle | Erwarteter Trade-off vs. R0 |
|----------|-------|-----------------------------|
| **R3_w075_q065_noexit** | Vorgänger-Champion | Besser in dokumentierter Rescue-Story; **schlechter** auf Matrix-Sharpe/CAGR (Phase C) |
| **M1_MOM_BLEND_MATCHED_CONTROLS** | Kontrolle | Nahezu gleiches Verhalten; M1 muss auf Cutover-Kalender geschlagen werden |
| **R2** | Sibling | Mehr Momentum in risk-off; Matrix-Sharpe unter R0 |
| **MOM_63_*** | Challenger | Höherer CAGR auf 2019–2026-Schnitt; anderer Strategietyp — nicht Default-Cutover |

---

## 3. Zielfunktion (nach Umstellung)

1. **Aligned calendar:** Sharpe-Delta vs. R3 ≥ Kriterien-YAML; CAGR höher.
2. **Risiko:** MaxDD nicht schlechter als R3 + Degradationsschwelle.
3. **Kosten / Statistik / Forward:** Gates in `control/champion_change_criteria.yaml` — weiterhin PASS-Pflicht für Wechsel **zu** R0; danach für **weitere** Wechsel.
4. **Kein Auto-Promotion** aus Backtest-Rang allein.

---

## 4. Explizite Nicht-Ziele

- Rückkehr zu R3 ohne neues externes Review.
- R5 / `rank_only` operativ.
- Verunreinigte `model_output`-Returns für Champion-Metriken.
- Stiller Parameter-Drift ohne Research-Run und Gate-Paket.

---

## 5. Aktivierung

Dieser Entwurf wird **nur** aktiv, wenn:

- `docs/R0_MIGRATION_MANDATE.md` vollständig umgesetzt (M1–M9),
- `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md` existiert,
- Pointer und `champion_strategic_decision.json` den Cutover dokumentieren.

Bis dahin gilt ausschließlich die R3-Charter in `control/champion_decision_charter.md`.
