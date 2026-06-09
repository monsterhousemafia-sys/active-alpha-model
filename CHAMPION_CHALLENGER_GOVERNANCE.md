# Champion / Challenger Governance

Stand: 2026-06-03 (Phase D)

## Champion (produktiv)

**Authoritative variant:** `R3_w075_q065_noexit` (locked in `aa_evidence_schema`, sealed via `EXTERNAL_REVIEW_APPROVAL_FINAL.md`).

Manuell freigegebenes Modell mit:

- Integrity PASS (`integrity_report.json`)
- Data Quality nicht FAIL
- dokumentierter `variant_id` in `latest_validated_run.json` / `run_manifest.json`
- vollständigem Walk-forward-Backtest auf **Matrix-Kalender** (~1860 Tage), nicht verunreinigte 2450-Tage-`model_output`-Returns

Pointer: `latest_validated_run.json` (kanonischer `run_id` nach Phase B).

Geplant: `latest_validated_model.json`, `latest_validated_signal.json` (Phase G).

### Entscheidungscharter (Phase D)

| Dokument | Inhalt |
|----------|--------|
| `control/champion_decision_charter.md` | Ökonomische Hypothese R3, Trade-offs vs R0/M1, Zielfunktion, Nicht-Ziele |
| `control/champion_change_criteria.yaml` | Harte Kriterien für **manuellen** Champion-Wechsel |
| `evidence/canonical_model_comparison.json` | Kanonischer Modellvergleich (Phase C) |

**Cockpit:** Sektion `champion_governance_de` in `load_decision_cockpit()` — u. a. Freigabe-Status, Matrix-Sharpe-Rang, M1-Delta, Cost-Stress.

## Quarantined (nicht operativ)

| Variant | Status |
|---------|--------|
| `R5_rank_only_train5` | **QUARANTINED** — unauthorized operational champion claim; siehe `control/quarantine/` |

Kein Report, Registry-Eintrag oder Pointer darf R5 als produktiven Champion behaupten.

## Challenger (opt-in, deaktiviert)

| ID | Beschreibung | Status |
|----|--------------|--------|
| B0_DAILY_REFERENCE | Champion ohne Behavioral | geplant |
| B1_REALTIME_EXECUTION_ONLY | Alpha wie B0, Intraday nur Execution | geplant |
| B2_ATTENTION_CONTINUATION | + Attention/Continuation Features | geplant |
| B3_LIQUIDITY_STRESS | + Liquidity Stress | geplant |
| B4_CROWDING_OVERLAY | + Crowding Overlay | geplant |

Referenzvergleiche (Matrix + Research): R0, R3, **M1** (`mom_blend_matched_controls`), MOM_63_TOP12 / STRICT / TOP15_RECONSTRUCTED, SPY, QQQ, MTUM, SMH.

## Promotion Gate

Keine automatische Promotion. Kandidat nur bei Kriterien in `control/champion_change_criteria.yaml`, u. a.:

- Integrity PASS, Data Quality OK
- vollständiger / aligned Kalender (Phase C)
- dokumentierter Vorteil vs. Champion **und** M1 auf gleichem Vergleichsrahmen
- bestandenem Kostenstress mit **eigenem** Turnover (kein Champion-Proxy)
- DSR-Policy, Paper-/Shadow-Forward gemäß YAML
- neuem `EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_*.md`

Endgültige Freigabe: **manuell**.

## Verboten

- Automatischer Champion-Wechsel aus Driftwarnungen oder Challenger-Reports
- Online-Lernen auf unreifen Outcomes
- Echtgeldorders ohne manuelle Freigabe
- Nutzung verunreinigter Champion-Returns aus `model_output` (Phase B Archiv)

## Related

- `docs/CHAMPION_EVIDENCE_GOVERNANCE_IMPROVEMENT_PLAN.md` — Phasen A–I
- **Phase I (2026-06):** `codex_champion_evidence_remediation_review.zip` — externe Review **AWAITING**; Champion **unverändert** (`EXTERNAL_REVIEW_APPROVAL_CHAMPION_EVIDENCE_REMEDIATION.md`)
- `docs/governance/G1_COMPARISON_LOGIC.md` — G1-Vergleich (separate Freigabe)
