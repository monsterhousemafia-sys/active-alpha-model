# Vision: Marktanalyse Decision Cockpit — Umsetzungsplan (V0–V5)

Stand: **2026-05-30T18:58Z**

## Zielarchitektur

```
┌─────────────────────────────────────────────────────────────┐
│                    Marktanalyse.exe (PySide6)               │
│  Executive │ Compare │ Evidence │ Cost/Rob │ Shadow │ Safety│
└──────────────────────────┬──────────────────────────────────┘
                           │ read-only view models
┌──────────────────────────┴──────────────────────────────────┐
│ aa_dashboard_result / aa_model_status / aa_result_views     │
│ aa_evidence_status (V1) │ aa_experiment_registry (V1)       │
│ cost_stress engine (V2) │ shadow_paper_monitor (V3)         │
└──────────────────────────┬──────────────────────────────────┘
                           │ atomic reads
┌──────────────────────────┴──────────────────────────────────┐
│ model_output_sp500_pit_t212/  control/  validation_runs/     │
│ Ledger │ Shadow │ Research │ Promotion gates │ Pipeline      │
└─────────────────────────────────────────────────────────────┘
```

**Prinzipien:** Champion unverändert bis manuelle Freigabe; Promotion fail-closed; fehlende Evidenz sichtbar; keine Echtgeldorders; atomare Statuswrites; jede Phase endet mit Review-ZIP + externer Freigabe.

---

## PHASE V0 — Safety und Reproduzierbarkeit ✅ (dieser Lauf)

### Ziel
Bestehende Sicherheits-, Pipeline-, Status- und Promotion-Probleme beheben/verifizieren ohne operative Läufe.

### Dateien
| Aktion | Datei |
|--------|-------|
| Reparatur/Verifikation | `aa_auto_promotion.py`, `aa_ops_refresh.py`, `aa_pipeline_autopilot.py`, `aa_pipeline_orchestration.py`, `aa_control_plane.py`, `aa_acceptance_audit.py`, `aa_safe_io.py` |
| Pipeline | `DEVELOPMENT_PIPELINE.json`, `.yaml`, `control/pipeline_pending.json`, `NEXT_CURSOR_PROMPT.md` |
| Governance (neu) | `AGENTS.md`, `VISION_DECISION_COCKPIT_EXECPLAN.md`, `VISION_PROGRESS.json` |
| Tests | `tests/test_p7_auto_promotion.py`, `test_pipeline_*`, `test_control_plane.py`, `test_p8_*`, `test_p0_*` |

### Definition of Done
- Auto-Promotion fail-closed inkl. `COST_STRESS_GATE` und Data-Quality-Evidenz
- Autopilot out_dir fail-closed → `model_output_sp500_pit_t212/`
- P7→P9 in JSON/YAML konsistent
- Atomare Writes auf Steuerdateien
- Cursor-Hooks deaktiviert (leere `hooks.json`)
- `auto_research_enabled: false` in Entwicklungsphasen V0R–V2
- 66+ Unit-Tests PASS
- `codex_v0r_safety_review.zip` erzeugt
- `VISION_PROGRESS.json` → `V0_EXTERNAL_REVIEW_REQUIRED`

### Review-Artefakte
`CODEX_V0_PREFLIGHT.md`, `CODEX_V0_REPAIR_REPORT.md`, `CODEX_V0_TEST_OUTPUT.txt`, `codex_v0_safety_review.zip`

### Abbruchbedingungen
Champion geändert; Promotion ausgeführt; verbotener Job gestartet; Tests FAIL ohne Reparatur.

---

## PHASE V1 — Evidence Data Contracts und Experiment Registry (NUR PLAN)

### Ziel
Versionierte Read-only-Datenmodelle für GUI und Audit.

### Neue Module (geplant)
| Modul | Zweck |
|-------|--------|
| `aa_evidence_schema.py` | JSON-Schema / Typen für Evidence Ladder Stufen |
| `aa_experiment_registry.py` | Experiment-Manifest (ID, Hypothese, Cutoff, Versionen) |
| `aa_evidence_status.py` | Aggregation Gate-Resultate → Ladder-Stufe (fail-closed) |
| `tests/test_evidence_schema.py` | Schema-Validierung |
| `tests/test_experiment_registry.py` | Registry CRUD read-only |

### Datenmodelle (Entwurf)
```yaml
EvidenceStage: IDEA | BACKTESTED | ROBUSTNESS_CHECKED | SHADOW_RUNNING | SHADOW_PASSED | PAPER_RUNNING | PAPER_CANDIDATE | REJECTED
ExperimentManifest:
  experiment_id, hypothesis, candidate_variant, champion_ref, control_ref,
  data_cutoff_utc, feature_version, cost_model_version, eval_protocol_version,
  result_status, decision_reason
```

### GUI-Ziel (read-only, V4)
Experiment Registry Tab — Liste + Detail ohne Aktionen.

### Tests (geplant)
Schema round-trip; Ladder darf Stufe nicht überspringen; fehlendes Gate → max Stufe BACKTESTED.

### DoD (V1)
Registry schreibt nur unter `control/experiments/`; keine Shadow/Paper-Jobs; **auto_research bleibt disabled**; Review-ZIP; `EXTERNAL_REVIEW_APPROVAL_V1.md` erforderlich für V2.

---

## PHASE V2 — Cost Stress und Robustness Engine (NUR PLAN)

### Ziel
Ökonomische Validierung implementieren; `COST_STRESS_GATE` befüllen.

### Neue Module (geplant)
| Modul | Zweck |
|-------|--------|
| `aa_cost_stress.py` | Baseline, +10/+25/+50 bps, Slippage/Turnover-Stress |
| `aa_robustness_metrics.py` | Deflated Sharpe, Regime-/Teilperioden-Stabilität |
| `tests/test_cost_stress.py` | Gate PASS/FAIL deterministisch |

### Zwingende Regel
`COST_STRESS_GATE`, `ECONOMIC_VALUE_GATE`, `RISK_GATE` müssen `pass: true` liefern, bevor Paper-Kandidat möglich (Promotion weiterhin manuell deaktiviert bis extern freigegeben).

### GUI-Ziel (V4)
Cost-Stress-Tabelle mit PASS/FAIL und Begründung pro Szenario.

### Abbruch
Kandidat ohne Cost-Stress als promotion-eligible markiert.

---

## PHASE V3 — Kontrolliertes Shadow-/Paper-Monitoring (NUR PLAN)

### Ziel
Forward-Beobachtung nach externer Freigabe; P9-Infrastruktur operationalisieren.

### Module (geplant)
| Modul | Erweiterung |
|-------|-------------|
| `aa_p9_shadow_paper_prep.py` | → Forward-Monitor (bereits Prep-Gates) |
| `aa_shadow_paper_monitor.py` | Prognosen, reife Outcomes, simulierte Nettoergebnisse |

### Regeln
- Champion `R3_w075_q065_noexit` Referenz
- Challenger `MOM_63_TOP12`; M1 Kontrolle
- Shadow vor Paper; keine Promotion; keine Echtgeldorders
- Mindestbeobachtungsregeln konfigurierbar in `promotion_gate_config.yaml` (read-only Anzeige)

### DoD (V3)
Monitor-Status in EXE sichtbar (read-only); Review-ZIP; externe Freigabe für V4.

---

## PHASE V4 — Decision Cockpit GUI (NUR PLAN)

### Ziel
PySide6-GUI um read-only Entscheidungsansichten erweitern.

### Zu prüfende Dateien
`aa_dashboard_qt_window.py`, `aa_dashboard_result.py`, `aa_model_status.py`, `aa_qt_charts.py`, `aa_result_views.py`, `tools/active_alpha_launcher.py`

### Ziel-Tabs
1. **Executive Overview** — Champion, Phase, Integrity, Blocker, Safety-Flags
2. **Champion vs Challenger** — Metriken nebeneinander, Evidenz-Typ-Kennzeichnung
3. **Evidence Ladder** — Stufen pro Kandidat
4. **Cost / Robustness** — Stress-Szenarien
5. **Shadow / Paper** — Forward-Monitor
6. **Experiments** — Registry
7. **Safety / Audit** — Flags, Incidents, Tests, Promotion-Blockgründe
8. **Export** — bestehende PDF/CSV + Audit-Report (später)

### Tests (geplant)
`tests/test_dashboard_gui.py`, `tests/test_dashboard_result.py` — keine Buttons für Promotion/Echtgeld/Parameter.

### DoD (V4)
Alle Tabs read-only; Smoke-Tests PASS; Screenshot-Set; Review-ZIP.

---

## PHASE V5 — Finaler Windows-Build (NUR PLAN)

### Build-Pfad
```
build_active_alpha_launcher.bat
  → PyInstaller build/launcher/Marktanalyse.spec
  → dist/Marktanalyse/ oder Marktanalyse.exe (Projektroot)
tools/verify_exe_integration.py
```

### Lieferobjekte
- `Marktanalyse.exe` + SHA-256
- Build-Log
- Vollständige Testausgabe
- Screenshot-Set aller Cockpit-Ansichten
- `FINAL_EXE_REVIEW.zip`

### DoD (V5)
GUI-Smoke PASS; Hash dokumentiert; keine aktivierte Promotion/Echtgeld-Automation in gebundener EXE.

---

## Phasenübergänge

| Von | Nach | Voraussetzung |
|-----|------|---------------|
| V0 | V1 | `EXTERNAL_REVIEW_APPROVAL_V1.md` |
| V1 | V2 | `EXTERNAL_REVIEW_APPROVAL_V2.md` |
| V2 | V3 | `EXTERNAL_REVIEW_APPROVAL_V3.md` |
| V3 | V4 | `EXTERNAL_REVIEW_APPROVAL_V4.md` |
| V4 | V5 | `EXTERNAL_REVIEW_APPROVAL_V5.md` |

`VISION_PROGRESS.json` wird pro Phase atomar aktualisiert; `authorized_phase` nur gesetzt nach externer Freigabe.

---

## Gemeinsame Abbruchbedingungen (alle Phasen)

Champion geändert ohne Freigabe; Automation-Flags aktiviert; Echtgeldorder; Löschung von Ledger/Shadow/Registry; nicht-atomare Steuerwrites; EXE/Batch-Pipeline in nicht autorisierten Phasen.
