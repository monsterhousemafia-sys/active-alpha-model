# External Review Decision — G0R2 Clean Checkpoint and Evidence Completeness Remediation

Review date/time (UTC): `2026-05-31T21:48:53+00:00`  
Review basis: static inspection of the submitted ZIP and detached SHA-256 sidecar; byte/hash comparison of submitted protected artefacts against the submitted V5R baseline and previously received final approval materials; static inspection of submitted governance and packaging code. No bundled source file, test suite, batch file, EXE, backtest, model job or operational function was executed.

## Reviewed artefacts

| Field | Value |
|---|---|
| Phase submitted | `G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION` |
| Review ZIP | `codex_g0r2_clean_checkpoint_evidence_completeness_review.zip` |
| Observed external SHA-256 | `93f730b75593fae4a7f1eec9c4b31bc089d997abb3da45ee8559467feecfc537` |
| Submitted sidecar | `codex_g0r2_clean_checkpoint_evidence_completeness_review.zip.sha256` |
| Sidecar verification | `PASS` |
| ZIP entries | `58` |
| ZIP integrity/readability | `PASS` |
| Duplicate ZIP paths | `NONE` |
| Unsafe/traversal ZIP paths | `NONE` |

## External review decision

```text
G0R2_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0R2_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

G0R2 remedies the substantive R3/Protected-State/Sidecar deficiencies identified in the rejected G0R package. It cannot yet be externally sealed because the submitted package does not provide a clean and complete commit-bound review checkpoint for its own final contents, and a modified safety-relevant snapshot is omitted from the submission.

## Confirmed positive remediation findings

1. The detached sidecar SHA-256 matches the externally calculated ZIP hash exactly:
   ```text
   93f730b75593fae4a7f1eec9c4b31bc089d997abb3da45ee8559467feecfc537
   ```
2. The ZIP is structurally readable and contains no duplicate or unsafe archive paths.
3. `R3_w075_q065_noexit` is shown as authoritative Champion in the submitted current authorization, champion-lineage and G0R2 snapshot artefacts.
4. `VISION_PROGRESS.json` is marked informational-only, records `operational_authorization = NONE`, and sets all listed operative safety flags to `NO`.
5. The G0R2 read-only cockpit snapshot shows:
   ```text
   promotion_eligible_display = NO
   paper_eligible_display = NO
   real_money_eligible_display = NO
   ```
6. `control/vision_automation/automation_state.json` is included and preserves a non-operational, manual-review-only state.
7. The Phase Catalog includes G0R2 and prohibits G1 execution, turnover generation, backtest/matrix execution, statistical validation, Robustness, Shadow, Paper, Promotion, Champion change, real-money execution, EXE build and EXE execution.
8. The Review Registry represents G0R2 as `AWAITING_EXTERNAL_REVIEW`, with `external_sealed = false`, `g1_authorized = false`, `next_phase_authorized = false` and `review_zip_sha256 = PENDING_EXTERNAL_SEAL`.
9. All 18 protected-scope artefacts listed in `CODEX_G0R2_PROTECTED_HASHES_AFTER.json` are included as actual file contents in the ZIP. Their computed byte hashes match the declared After values and the submitted V5R protected baseline.
10. The previously misreported drift has been corrected: the submission now identifies the two pre-G0R drifted paths and classifies their current contents as restored to the V5R baseline:
    - `model_output_sp500_pit_t212/background_research_status.json`
    - `model_output_sp500_pit_t212/latest_validated_run.json`
11. The included bytes of `EXTERNAL_REVIEW_APPROVAL_FINAL.md`, `V5R_EXTERNAL_ACCEPTANCE_REPORT.md` and the V5R protected-hash baseline match the previously received review materials.

## Material blockers preventing external seal

### 1. The submitted final ZIP contents are not fully bound to the reported Git checkpoint

`CODEX_G0R2_GIT_STATUS.txt` reports a new clean checkpoint:

```text
start_head           = c5a0fd45c366faf61f2337e02f39b92d12813040
g0r2_remediation_head = da08c5ff98e7ce68893e68d6dc49ed1bb32ce042
head_changed          = true
```

This is an improvement over G0R. However, the submitted packaging script `tools/complete_g0r2_remediation.py` statically shows the following order:

1. create the first G0R2 commit;
2. write or refresh Git-status and report artefacts;
3. build the review ZIP and detached sidecar;
4. perform an additional `git add -A` and a second commit after ZIP creation.

Consequently, the final report/status/ZIP generation stage is not shown as part of the `g0r2_remediation_head` reported inside the ZIP. The submitted evidence therefore does not establish that all final in-ZIP review contents are committed in, or reproducibly tied to, the checkpoint it presents for external review.

**Finding:** `G0R2_FINAL_PACKAGE_NOT_BOUND_TO_REPORTED_CHECKPOINT`.

### 2. The packaging script stages files using unrestricted `git add -A`

The included `tools/complete_g0r2_remediation.py` stages repository contents using:

```text
git add -A
```

both for the remediation commit and for the later post-ZIP commit. The authorized remediation requirement was an isolated commit containing only explicitly permitted G0R2 files. An unrestricted staging command is not fail-closed: in a non-clean worktree it can absorb unrelated, operational or unreviewed artefacts.

The submitted Git report lists only a bounded set of committed G0R2 files and reports a clean worktree, but the submitted remediation tool itself does not technically enforce that isolation.

**Finding:** `G0R2_UNRESTRICTED_GIT_STAGING_NOT_FAIL_CLOSED`.

### 3. A modified safety-relevant snapshot listed in the commit report is omitted from the ZIP

`CODEX_G0R2_GIT_STATUS.txt` lists the following file among committed G0R2 changes:

```text
control/review_snapshot/v5r_decision_cockpit_snapshot.json
```

This file is not included in the submitted ZIP. It is safety-relevant because the preceding reviews identified fail-open read-only cockpit display claims as a material blocker. External review cannot verify the content of a modified V5R cockpit snapshot that is omitted from the review package.

**Finding:** `G0R2_MODIFIED_SAFETY_SNAPSHOT_OMITTED`.

### 4. The backup manifest contradicts the submitted commit evidence

`G0R2-BACKUP_MANIFEST.json` states:

```text
G0R2 uses read-only verification; no file mutations.
```

The same package's Git report lists multiple modified and newly created files committed in G0R2, including authorization-state artefacts, phase catalog, review registry and cockpit snapshots. These are permissible categories of remediation changes when controlled, but they are file mutations. The manifest therefore does not accurately describe the remediation activity.

**Finding:** `G0R2_BACKUP_MANIFEST_MISSTATES_FILE_MUTATIONS`.

## Required remediation before a replacement submission

A replacement submission may be limited to packaging/checkpoint completeness corrections while preserving all validated R3/read-only/protected-state corrections. It must:

1. Remove unrestricted staging from the submitted remediation path. Stage only an explicit allowlist of authorized G0R2/G0R3 files and fail if any unrelated worktree change exists.
2. Produce one final commit-bound submission state, or otherwise provide a verifiable final commit manifest after all report and package-input files have been finalized. The review ZIP should contain a Git report referencing the commit that contains all submitted source/status/report inputs, excluding only the external detached ZIP sidecar and the archive file itself where appropriate.
3. Include `control/review_snapshot/v5r_decision_cockpit_snapshot.json`, since it is listed as modified and is directly relevant to the previously identified display-safety defect.
4. Correct `G0R2-BACKUP_MANIFEST.json` to enumerate actual modified/new remediation files and any backed-up or quarantined originals, or state precisely that no protected artefacts were modified during G0R2 while governance/report files were changed.
5. Retain the now verified facts:
   - authoritative Champion `R3_w075_q065_noexit`;
   - manual read-only usage only;
   - all operative capabilities blocked;
   - G1 unauthorized;
   - 18 protected artefacts present and matching the V5R baseline;
   - two prior G0R drifted pointers accurately documented as restored;
   - correct separate detached-sidecar method.
6. Submit a new ZIP and detached `.sha256` sidecar for external review. No in-package document may claim external sealing before that review.

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
