# Evidence directory layout

This folder holds **session/build pipeline artefacts** (logs, screenshots, git patches from remediation runs). It is **not** the authoritative evidence gate plane.

## Authoritative gate evidence (do not archive here)

Use `control/evidence/` for fail-closed gate status consumed by the Decision Cockpit:

- `cost_stress_status.json`
- `robustness_status.json`
- `multiple_testing_status.json`
- `g1_*`, `g2_*`, `governance_drift_reconciliation.json`
- monitoring / forward readiness JSON

## Regenerable / historical run artefacts

`evidence/archive/` — dated pipeline outputs (V5R build, pytest diagnosis, git show patches). Safe to delete or regenerate; **gitignored** by default.

## Regenerate

```text
python tools/reconcile_governance_drift.py
python tools/finish_evidence_path_abcde.py   # if authorized phase artifacts needed
```

Do not manually edit `control/evidence/*` gate files except via export tools in `aa_*` / `tools/*`.
