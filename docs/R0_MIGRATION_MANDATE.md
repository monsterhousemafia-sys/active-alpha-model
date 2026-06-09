# R0-Migrations-Mandat (Phase M0)

**Status:** EXECUTED — M0 abgeschlossen  
**Erstellt:** 2026-05-31 (UTC)  
**Programm:** `docs/R0_LONG_TERM_MIGRATION_PLAN.md`  
**Produktiver Champion (unverändert bis M9):** `R3_w075_q065_noexit`

---

## 1. Zweck

Dieses Mandat legt die **Zielfunktion** und **Programmentscheidungen** für die langfristige Umstellung von R3 auf **R0_LEGACY_ENSEMBLE** fest. Es autorisiert **keinen** produktiven Champion-Wechsel und **keine** Änderung an Signal-Gewichten oder Risk-off-Parametern in Produktion.

Maschinenlesbar: `control/r0_migration/mandate.json`

---

## 2. Zielfunktion (M0.1)

| Priorität | Kriterium | Schwelle / Quelle |
|-----------|-----------|-------------------|
| **Primär** | Sharpe (0 rf) auf **aligniertem** Kalender | Δ ≥ **+0,02** vs. `R3_w075_q065_noexit` (`control/champion_change_criteria.yaml`) |
| **Primär** | CAGR auf gleichem Kalender | Höher als R3; kein zusätzlicher YAML-Schwellenwert |
| **Sekundär** | Max Drawdown | Nicht schlechter als R3 + **2 Prozentpunkte** (relativ zum Kriterium YAML) |
| **Sekundär** | M1-Kontrolle | Ziel-Kandidat muss **M1** auf gleichem Kalender schlagen (`require_beat_m1_control`) |
| **Optional / Stabilität** | Subperioden | Segment 2 Sharpe **> 0,5** für Ziel-Kandidat (R0*); Segment 3 dokumentiert |
| **Pflicht (Gates)** | Cost +25 bps, DSR, Robustness, Shadow, Paper | `control/champion_change_criteria.yaml` — alle PASS vor M9 |

**Explizit nicht mehr #1-Ziel:** Risk-off-Momentum-Rescue als alleinige Begründung für schlechteren Gesamt-Sharpe (bisherige R3-Charter-Logik).

**Stop-Regel:** Wenn M2 (Episode-Attribution) zeigt, dass R0 in **risk_off**-Episoden katastrophal schlechter ist (MaxDD >> +2 pp vs. R3) **und** kein R0* das behebt → Programm stoppen oder nur Shadow ohne Cutover.

---

## 3. Ziel-Variante (M0.2)

| Entscheidung | Wahl |
|--------------|------|
| **Primärziel** | `R0_LEGACY_ENSEMBLE` (Baseline: `legacy` / `legacy`, `alpha_model_mode=ensemble`) |
| **Forschungsspur A** | **R0\*** — getunte Parameter **nur** in `validation_runs/`, gleiche Risk-off-Philosophie |
| **Forschungsspur B** | **MOM / Hybrid** — **zurückgestellt** bis M4; nur wenn Spur A CAGR-Lücke zu MOM nicht schließt |
| **Ausgeschlossen** | `R5_rank_only_train5`, produktives `rank_only` |

**Cutover-Kandidat an M9:** `R0_LEGACY_ENSEMBLE` oder ein einzelner nachgewiesener **R0\***-Lauf — nicht beide parallel produktiv.

---

## 4. Risiko-Appetit (M0.4)

| Frage | Antwort |
|-------|---------|
| Akzeptanz schlechterer Performance in Risk-off-Episoden zugunsten höherem Gesamt-Sharpe/CAGR? | **Ja, bedingt** — nur wenn Episode-Analyse (M2) kein katastrophales R0-Verhalten zeigt und Gates PASS |
| Akzeptanz höherer Volatilität vs. R3? | **Ja**, wenn Sharpe/CAGR und DD-Gates erfüllt |
| Akzeptanz Strategiewechsel zu MOM_63? | **Nein** in M0–M3; erst nach M4-Entscheid + **breitere** externe Freigabe |

---

## 5. Operative Programmparameter (offene Punkte aus Plan — entschieden)

| Thema | Entscheidung M0 |
|-------|-----------------|
| Paper-Forward (M7) | **Pflicht** (`paper_forward_min_days: 60` in Criteria-YAML) |
| Shadow (M6) | **Pflicht** (`shadow_min_outcomes: 30`) |
| EXE / OS-Rollout | **Nach M9** — **M11** (Marktanalyse.exe Build/Verify), **M12** (BAT/Startup/Desktop); keine frühe EXE-Umstellung |
| Auto-Promotion | **Bleibt DISABLED** |

---

## 6. Charter (M0.3)

- **Aktiv (unverändert):** `control/champion_decision_charter.md` (R3-Hypothese) — gilt bis M9.
- **Entwurf Zielzustand:** `control/champion_decision_charter_r0_target_draft.md` — wird bei erfolgreichem M9 zur aktiven Charter.

---

## 7. Governance & Freigabe

| Regel | Status |
|-------|--------|
| Produktiver Champion | **R3** bis `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md` + M9 |
| Änderung produktiver Parameter | **Verboten** in M1–M8 (nur Research-Runs) |
| Nächste Phase | **M1** — Evidenz-Baseline (`evidence/r0_migration/`) |

---

## 8. Genehmigung (Programm-Owner)

| Feld | Wert |
|------|------|
| `approval_mode` | `PROGRAM_MANDATE_CURSOR_SESSION` |
| `approved_at_utc` | siehe `control/r0_migration/mandate.json` |
| `authoritative_until` | Widerruf nur durch neues Mandat oder externes Revoke |

---

## 9. Referenzen

- `docs/R0_LONG_TERM_MIGRATION_PLAN.md`
- `evidence/canonical_model_comparison.json`
- `control/champion_change_criteria.yaml`
- `docs/CHAMPION_STRATEGIC_DECISION_RECORD.md` (E1 — wird nach M9 ggf. ersetzt)
