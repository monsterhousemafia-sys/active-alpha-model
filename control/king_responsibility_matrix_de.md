# Verantwortungs-Matrix — vier geschlossene Schichten

**SSoT:** Jede Schicht hat genau einen Aufgabenbereich. Sie liest nur die Evidence der darunterliegenden Schichten und verstärkt sie — keine Doppelarbeit, keine Überschneidung.

**Netzwerk-Takt:** `control/king_network.json` (Topologie) · `evidence/king_network_pulse_latest.json` (live: `beat`, `phase`, `active_layer`, `handoff_to`). Sync: `bash tools/king_ops.sh network`.

**Hardware-Takt:** `control/king_hardware_policy.json` · `evidence/king_hardware_latest.json` (GPU, VRAM, NVMe, ETA). In jedem Pulse eingebettet.


```
Operator
   │
   ▼
┌──────────────┐  /bau · r3-bau  ┌──────────────┐
│ 3 · KÖNIG    │────────────────►│ build-kernel │
│ 32B Urteil   │  autonom bauen  │ 128 Schritte │
└──────┬───────┘                 └──────────────┘
       │ king_ops
       ▼
┌──────────────┐  ruft auf   ┌──────────────┐
│ 1 · BASH     │────────────►│ 2 · PYTHON   │
│ king_ops     │  h1-watch   │ ai_kernel    │
└──────────────┘             └──────────────┘

Schicht 4 Cursor: Notfall-Fallback (selten) — kein Standard-Bau
```

---

## Schicht 1 — Bash (Ausführen)

| | |
|---|---|
| **Wer** | `tools/king_*.sh`, Einstieg `bash tools/king_ops.sh` |
| **Manifest** | `control/king_bash_manifest.json` |
| **Tut** | PID, flock, wait, clean, verify, status, h1-seal, watch-bg, safety-Flags |
| **Tut nicht** | Sharpe berechnen, Seal behaupten, Code schreiben, Operator-Prosa |
| **Evidence** | `evidence/king_status_latest.json`, `king_verify_*`, `king_clean_*`, `king_tune_*` |
| **Nächster Schritt** | Feld `next_action_de` + `next_layer` in `king_status_latest.json` |

**Regel:** Immer `king_ops status` vor jeder Entscheidung. Ein Benchmark-Job, flock-geschützt.

---

## Schicht 2 — Python (Beweisen)

| | |
|---|---|
| **Wer** | `tools/ai_kernel.py`, `analytics/h1_*.py`, `analytics/king_sovereignty.py` |
| **Tut** | Evaluate, Seal-Prüfung, Governance-JSON, Sharpe/MDD, `pass_full_seal` |
| **Tut nicht** | Shell-Orchestrierung, parallele Benchmarks, LLM-Prosa |
| **Evidence** | `evidence/daily_alpha_h1_evaluation_latest.json`, `control/h1_governance_status.json`, `evidence/king_sovereignty_latest.json` |
| **Aufgerufen von** | Bash (`h1-watch` in `king_h1_seal.sh`), König (`/h1-watch`, `/könig-puls`) |

**Regel:** Seal nur wenn `pass_full_seal: true` in frischer Evaluation — nie aus Chat-Prosa.

---

## Schicht 3 — König 32B (Entscheiden)

| | |
|---|---|
| **Wer** | `alpha-model-agent`, Modell `qwen2.5-coder:32b` |
| **Config** | `control/alpha_model_agent_home.json`, `control/local_llm.json` |
| **Tut** | Evidence lesen → nächsten `king_ops`-Befehl wählen; PASS/FAIL erklären; **autonom bauen** via `/bau`, `r3-bau`, `build-kernel`; nach Seal `/learn` `/evolve` |
| **Bau-Policy** | `control/king_32b_autonomous_build.json` — 32B ist Standard-Bauer |
| **Tut nicht** | Manuelle 65-Min-Shell-Jobs; zweiten Benchmark starten; Champion ändern; Seal ohne Evaluation |
| **Liest zuerst** | `evidence/king_status_latest.json` → `next_action_de` / `next_layer` |
| **Dann** | H1-Evaluation, Sovereignty, Bridge |

**Regel:** Operative Jobs per Bash/Slash — nicht per freier Shell-Prosa im Chat.

---

## Schicht 4 — Cursor (Notfall-Fallback, kein Standard-Bau)

| | |
|---|---|
| **Wer** | Cursor IDE (diese Session) — **nicht** im Bau-Takt |
| **Rolle** | `control/cursor_vasall_role_de.md` — nur wenn 32B blockiert |
| **Tut** | Selten: fokussierter Diff wenn Bridge `cursor_fallback_required` |
| **Tut nicht** | Standard-Bau, H1-Backtest, Benchmark, Seal, R3-Laufzeit |
| **Standard-Bauer** | König 32B — `/bau`, `bash tools/king_ops.sh r3-bau` |

**Regel:** Bau-Takt gehört Schicht 3. Cursor nur auf expliziten Notfall-Hinweis.

---

## Netzwerk-Takt (Phasen)

| Phase | Owner | Handoff an | Trigger |
|-------|-------|------------|---------|
| `sync` | bash | bash | `king_ops tune` |
| `observe` | bash | python | Benchmark läuft |
| `execute` | bash | python | h1-seal starten |
| `prove` | python | koenig | CSV da → h1-watch |
| `decide` | koenig | koenig | Evaluation da — ggf. /bau |
| `build` | koenig | bash | 32B /bau · r3-bau · build-kernel |
| `verify` | bash | koenig | nach 32B-Bau |
| `ready` | koenig | koenig | H1 sealed |

`beat` inkrementiert bei Phasenwechsel — alle Schichten lesen denselben Puls.

## Verstärkungs-Schleife (geschlossen)

| Phase | Schicht | Aktion |
|-------|---------|--------|
| Start | Bash | `king_ops tune` → verify, clean, status, watch-bg, **pulse** |
| Laufend | Bash | status + watch-bg; pulse `phase=observe` |
| CSV da | Bash | `king_ops h1-seal` → Python `h1-watch`; pulse `phase=prove` |
| Evaluate | Python | `pass_full_seal` in Evidence; pulse `phase=decide` |
| Urteil | König | Operator-Briefing; bei FAIL Forschungspfad, kein Auto-Champion |
| Code-Lücke | König | `/bau` oder `king_ops r3-bau`; pulse `phase=build` |
| Bau | König 32B | build-kernel (read/write/grep/pytest, bis 128 Schritte) |
| Abschluss | Bash | `r3_sync` · `king_ops verify` → pulse `phase=verify` |
| Notfall | Cursor | Nur `cursor_fallback_required` in Bridge |

---

## Monitoring-Governance (read-only, fail-closed)

| Komponente | Policy | Evidence | Wirkung |
|------------|--------|----------|---------|
| **T212 Trust Gate** | `control/t212_trust_policy.json` | `evidence/t212_trust_latest.json` | Blockiert Orders/Plan-Skalierung ohne Live-Sync |
| **Fall-Wächter** | `control/r3_fall_watch_policy.json` | `evidence/prognosis_fall_watch_latest.json` | R3-Panel `r3-fall-watch` — **kein** Order-Trigger |
| **Security-Lock** | `control/project_security_lock.json` | `evidence/project_security_lock_latest.json` | Safety-Flags, Hooks, Secret-Rechte |
| **SSoT** | `control/r3_monitoring_governance.json` | — | Kein Champion-Wechsel über Monitoring |

```bash
bash tools/king_ops.sh t212-trust-report
bash tools/prognosis_fall_watch.sh status
bash tools/project_security_lockdown.sh
```

---

## Verbotene Quer-Eingriffe

| Von | Nicht tun |
|-----|-----------|
| Bash | Sharpe/Seal ohne Python |
| Python | Benchmark ohne Bash flock |
| König | Shell-Jobs die Bash bereits hat |
| Cursor | H1/Benchmark/Seal ohne Bridge-Anfrage |

---

## Schnellreferenz

```bash
bash tools/king_ops.sh status    # Schicht 1 — immer zuerst
bash tools/king_ops.sh h1-seal    # Schicht 1 → ruft Schicht 2
.venv/bin/python tools/ai_kernel.py h1-watch   # Schicht 2 direkt
.venv/bin/python tools/ai_kernel.py king-pulse # Schicht 2 + 3 Autonomie
```

König-Chat: `alpha-model-agent` · Cursor: nur Bridge `request_de` abarbeiten.
