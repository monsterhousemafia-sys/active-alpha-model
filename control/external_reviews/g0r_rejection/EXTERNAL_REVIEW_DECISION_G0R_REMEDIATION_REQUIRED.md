# External Review Decision — G0R Authorization and Champion-Lineage Remediation Resubmission

Review date/time (UTC): `2026-05-31T21:28:23+00:00`  
Review basis: static inspection of the submitted ZIP and byte/hash comparison against the included V5R external baseline materials and previously received final approval materials. No source file, test suite, batch file, EXE, backtest, model job, or operational function was executed.

## Reviewed artifact

| Field | Value |
|---|---|
| Phase submitted | `G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION` |
| Artifact | `codex_g0r_authorization_champion_lineage_remediation_review.zip` |
| Observed external SHA-256 | `2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679` |
| ZIP entries | `47` |
| ZIP integrity test | `PASS` |
| Duplicate entry paths | `NONE` |
| Unsafe/traversal paths | `NONE` |

## External review decision

```text
G0R_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0R_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

The submission remedies several substantive issues from the rejected G0 package, but it cannot be externally sealed because the proof of a clean, reviewable remediation checkpoint and the protected-state restoration evidence remain incomplete and internally inconsistent.

## Confirmed positive remediation findings

1. The ZIP is readable and contains no duplicate or unsafe paths.
2. `VISION_PROGRESS.json` now declares itself informational only, sets `operational_authorization` to `NONE`, and records all operative safety flags as `NO`.
3. `control/authorization/current_authorization_status.json` records `R3_w075_q065_noexit` as authoritative Champion, blocks operations, and keeps G1 unauthorized.
4. `control/review_snapshot/g0r_decision_cockpit_snapshot.json` displays:
   - `active_champion = R3_w075_q065_noexit`;
   - `promotion_eligible_display = NO`;
   - `paper_eligible_display = NO`;
   - `real_money_eligible_display = NO`.
5. `control/vision_automation/automation_state.json` is included and records manual read-only state with no operational, EXE, or real-money authorization.
6. The Phase Catalog now includes `G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION`; the Registry records that phase as `AWAITING_EXTERNAL_REVIEW` with `external_sealed = false` and `review_zip_sha256 = PENDING_EXTERNAL_SEAL`.
7. For the 12 protected artefacts whose actual bytes are included in the ZIP, the included file contents match the submitted `CODEX_G0R_PROTECTED_HASHES_AFTER.json` values.
8. The submitted `CODEX_G0R_PROTECTED_HASHES_AFTER.json` hash list matches the included V5R protected baseline hash list across its 18 declared entries.

## Material blockers preventing external seal

### 1. No isolated Git remediation checkpoint exists

`CODEX_G0R_PREFLIGHT.md` and `CODEX_G0R_GIT_STATUS.txt` both report:

```text
Start HEAD       = 13c6e5cae3f7a238a50700bf481bb55b9b9fe897
Remediation HEAD = 13c6e5cae3f7a238a50700bf481bb55b9b9fe897
```

The two values are identical. The package therefore contains no commit binding the submitted G0R remediation content to a reviewable source checkpoint.

At the same time, `CODEX_G0R_GIT_STATUS.txt` reports a very large uncommitted worktree containing deletions, modifications and new files across governance, Evidence, controller, build, test and tool paths. This includes modified or removed safety-relevant and historical-review artefacts.

This directly fails the required condition of an isolated, externally traceable G0R remediation checkpoint.

**Finding:** `G0R_CLEAN_ISOLATED_GIT_CHECKPOINT_NOT_ESTABLISHED`.

### 2. The remediation report incorrectly states that no pre-remediation protected drift existed

`CODEX_G0R_EXTERNAL_REJECTION_REMEDIATION_REPORT.md` states:

```text
Drift before remediation: 0
```

However, the package's own `CODEX_G0R_PROTECTED_HASHES_BEFORE.json` and `CODEX_G0R_PROTECTED_HASHES_AFTER.json` show two changed protected paths:

| Protected path | G0R Before SHA-256 | G0R After SHA-256 |
|---|---|---|
| `model_output_sp500_pit_t212/background_research_status.json` | `93b3f6523e04322cbe8f5baabdf29e1c9c1004e59a98c7db5d53c835d18de55f` | `2401c9cd2340d186c98eced96356315cd0c03dab41607c94c60c1df9b5a53d70` |
| `model_output_sp500_pit_t212/latest_validated_run.json` | `bd8fba0f972984292864562cc13668d5cbb7ff26d7d5edd08e269f07dd927482` | `e5a821da3cae03952cc0bbbad9c43d9f813fa60fb48d58d60fe6947314a9a58d` |

The `After` hashes equal the submitted V5R baseline hashes, so a restoration is claimed; nevertheless, the statement that no drift existed before remediation is materially inaccurate.

**Finding:** `G0R_REPORT_MISSTATES_PRE_REMEDIATION_PROTECTED_DRIFT`.

### 3. Restored protected output files are not included for byte-level verification

The two protected paths reported as restored to the V5R baseline are not present as file contents in the ZIP:

- `model_output_sp500_pit_t212/background_research_status.json`
- `model_output_sp500_pit_t212/latest_validated_run.json`

The ZIP provides only declared hashes for these restored files. Because these are the exact files whose prior drift represented the unauthorized Champion-lineage problem, their corrected file contents must be externally inspectable in the resubmission.

In addition, four other protected files enumerated in the submitted hash set are omitted from the ZIP:

- `DEVELOPMENT_PIPELINE.json`
- `DEVELOPMENT_PIPELINE.yaml`
- `control/evidence/forward_monitoring_data_requirements.json`
- `control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml`
- `model_output_sp500_pit_t212/background_research_status.json`
- `model_output_sp500_pit_t212/latest_validated_run.json`

**Finding:** `G0R_RESTORED_PROTECTED_ARTEFACTS_NOT_EXTERNALLY_INSPECTABLE`.

### 4. Claimed detached sidecar hash does not match the submitted ZIP

`NEXT_CURSOR_PROMPT.md` claims:

```text
Detached sidecar SHA-256 = 5cbdec0f11b348895ecc9a68b2478eab67a9c27449d4e5e98c402c46c8154ee2
```

The externally observed SHA-256 of the submitted ZIP is:

```text
Observed ZIP SHA-256      = 2a008e6eadee94d0a6e2b7faa772c8f3f1c35c7bab89e13078174c32bb41c679
```

These hashes differ. No separately supplied sidecar for this G0R ZIP accompanied the submission.

The Registry correctly leaves the review ZIP hash as `PENDING_EXTERNAL_SEAL`; however, the submitted package still contains a concrete, incorrect sidecar claim.

**Finding:** `G0R_SUBMITTED_SIDECAR_HASH_MISMATCH`.

### 5. The local PASS assertion is unsupported under the submitted gate conditions

The package declares:

```text
G0R_LOCAL_REMEDIATION_STATUS = PASS
```

Yet the submitted materials themselves demonstrate:
- no Remediation commit;
- extensive uncontrolled/uncommitted worktree changes;
- an inaccurate pre-remediation drift statement;
- omitted restored protected artefacts;
- an incorrect concrete detached-sidecar hash.

Under the fail-closed standard defined by the remediation scope, these conditions require local status to be `BLOCKED_PENDING_CLEAN_ISOLATED_CHECKPOINT` or equivalent, not `PASS`.

**Finding:** `G0R_LOCAL_PASS_ASSERTION_NOT_SUPPORTED`.

## Required remediation before another G0R submission

A replacement G0R submission must:

1. Create a clean isolated remediation checkpoint commit containing exactly the authorized G0R scope; the submitted Git report must show a different committed remediation HEAD from the starting HEAD and no unexplained G0R-relevant working-tree drift.
2. Correct the remediation report to state explicitly that two protected output pointers were drifted before remediation and were restored to the V5R hash baseline.
3. Include the actual corrected bytes of:
   - `model_output_sp500_pit_t212/background_research_status.json`;
   - `model_output_sp500_pit_t212/latest_validated_run.json`;
   together with hashes matching the V5R baseline.
4. Include all other protected files enumerated as reviewed, or narrow the hash claim to files whose actual content is included and explain any baseline-only references.
5. Regenerate the final ZIP only after all in-package files are final. Provide its detached sidecar as a separately submitted artifact, with a SHA-256 matching the actual submitted ZIP.
6. Set the local status to `AWAITING_EXTERNAL_REVIEW` only after the clean commit and coherent review package exist; do not claim `PASS` while required seal prerequisites are unmet.
7. Keep all current R3/read-only/fail-closed corrections in place.
8. Keep G1 unauthorized and do not generate Turnover, Cost-Stress, statistical, Shadow, Paper, Promotion, EXE or real-money outputs.

## Prohibited pending a corrected external seal

```text
NO G1 APPROVAL OR EXECUTION
NO TURNOVER ARTEFACT GENERATION
NO BACKTEST OR MATRIX RE-RUN
NO COST-STRESS / DSR / PBO / CSCV / ROBUSTNESS EXECUTION
NO SHADOW OR PAPER ACTIVATION
NO PROMOTION OR CHAMPION CHANGE
NO REAL-MONEY EXECUTION
NO EXE BUILD OR EXECUTION
```
