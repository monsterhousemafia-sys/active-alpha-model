# External Review Decision — G0 Authorization Source Conflict Remediation

Review date/time (UTC): `2026-05-31T21:12:43+00:00`  
Review basis: static inspection of the submitted archive and comparison against previously supplied sealed V5R baseline evidence. No bundled program, test suite, EXE, batch file, or repository script was executed.

## Reviewed artifact

| Field | Value |
|---|---|
| Phase submitted | `G0_AUTHORIZATION_SOURCE_CONFLICT_REMEDIATION` |
| Artifact | `codex_g0_authorization_conflict_remediation_review.zip` |
| Observed external SHA-256 | `09adac3cef01ef61faa716c39f751c39cab39ef5289ed5523d81af831b132130` |
| Archive entries | `27` |
| ZIP readability | `PASS` |
| Duplicate ZIP paths | `NONE` |
| Unsafe ZIP paths | `NONE` |

## Review decision

```text
G0_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0_EXTERNAL_SEALED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

G0 is **not sealed**. The package contains material state and traceability conflicts that prevent acceptance as a fail-closed governance remediation.

## Confirmed positive findings

1. The ZIP is structurally readable; no duplicate or traversal paths were identified.
2. `VISION_PROGRESS.json` within the package has been changed to informational-only with operational authorization `NONE`.
3. `control/operational_safety_flags.json` within the package sets automation and operative flags to disabled/false.
4. `control/authorization/current_authorization_status.json` asserts manual read-only status and blocks operative actions.
5. The submitted G0 internal before/after protected-hash files are equal across their 14 enumerated paths (`0` internal differences).
6. The package reports `102 passed`; this is recorded as submitted evidence only and was not independently executed in this external review.

## Material rejection findings

### 1. Unauthorized champion-lineage replacement is embedded in the G0 package

The final sealed external approval states that the Champion remains `R3_w075_q065_noexit` and expressly does not authorize a Champion change.

The G0 package nevertheless asserts a runtime/operational champion `R5_rank_only_train5` in multiple included artifacts, including:

- `IMPLEMENTATION_STATUS.md`
- `NEXT_CURSOR_PROMPT.md`
- `control/champion_lineage_policy.json`
- `control/CHAMPION_LINEAGE.md`
- `control/evidence/governance_drift_reconciliation.json`
- `control/review_snapshot/v5r_decision_cockpit_snapshot.json`

No externally sealed approval authorizing this Champion change is included. A G0 governance remediation cannot normalize or preserve an unapproved operative Champion replacement.

**Finding:** `UNAUTHORIZED_CHAMPION_LINEAGE_STATE_PRESENT`.

### 2. Submitted G0 ZIP hash does not match its review-registry entry

The package's `control/vision_automation/review_registry/review_registry.json` records for G0:

```text
review_zip_sha256 = ba094b521b9d964ad119b6763d5e53bccdfb7af6a51e0a3d1557e6bb359a4d54
```

The externally observed submitted ZIP hash is:

```text
observed_sha256 = 09adac3cef01ef61faa716c39f751c39cab39ef5289ed5523d81af831b132130
```

These values do not match.

**Finding:** `G0_REVIEW_ZIP_HASH_REGISTRY_MISMATCH`.

### 3. Protected-state preservation is not established against the sealed V5R baseline

The G0 package proves only that its own captured before/after set is unchanged during the reported G0 interval. It does not preserve the previously supplied sealed V5R protected baseline.

Across the 14 overlapping protected paths, `13` differ between `CODEX_V5R_PROTECTED_HASHES_AFTER.json` and the G0 `CODEX_G0_PROTECTED_HASHES_BEFORE.json`:

| Protected path | Sealed V5R baseline SHA-256 | G0 submitted “before” SHA-256 |
|---|---|---|
| `control/auto_promotion_status.json` | `e2901234d1f4bceb3606a55095da804c6baacc1a454c3342f394626dbff100e7` | `8b4c636b27ac8af582eac55ff9dc86329f44c21f595931a082820f2bf517996b` |
| `control/evidence/cost_stress_status.json` | `bbe231ac7f5e375bf4fa498ac827d22ddfa816d61e98c06008160cec341a9404` | `addd63bd86443b14e474fd826935b9926d0d87e8db1e8e0d6944bd54b2c301db` |
| `control/evidence/current_evidence_status.json` | `c51237d27c4ca56196fc2bb52346a924b7a94ee28be36d38ddf944abd60c979f` | `5ff62ba64fdc4a3766cbfb2c603ac08c6f39b31e1c895d7d42b4b5cdf947c33f` |
| `control/evidence/forward_monitoring_readiness_status.json` | `538fab6de3b6333d74846819f345b632b6043ba9101074fcbef0c1dc2167dc3b` | `753f766c52652e63e927dfced9b65e91b65828222ba5a668c3b54e02a9c88857` |
| `control/evidence/multiple_testing_status.json` | `91a4c04151e862d3e36e567f2b98391f353e7621207666f3da0181ad5a01ffe2` | `e7f54ed1c140f2e1e60049631c6bf8bac456a33b6e1a7bddee025b94a585151d` |
| `control/evidence/paper_monitor_status.json` | `5290a3ad9ad52f8ecacef81214d96095efaaec995519a6bdad6ecb87cb09335d` | `a31f75c1127a5a5027ed710bd5890ecbd7ac12d0792d63d98cb7d16009d96ee1` |
| `control/evidence/robustness_status.json` | `4c219ab56218ea6ec68c454a6c57fad3045fd70b4bba0282978745805af78e45` | `ac0286716b9b119926e23fa4ba8b0fd21a5196d322e1e50f387ecd41f723a708` |
| `control/evidence/shadow_monitor_status.json` | `fb73200c5834713d2e9a9c09791b164778b0d95348f1dcd20113cfed15e59764` | `5e4d720c6c7e01afc6c1d47d0597d3a8e6c8b7ceebe11d0616862d4bccc26dea` |
| `control/last_known_good_state.json` | `f67b37eba2807702f1ffbada01e0f6153046d66a23136e0dc307f01fa4ff9bcc` | `0302205ae55047c0ce4c432d385c1899e9197f355415fa576d6227f53e5d1fd5` |
| `control/promotion_status.json` | `14b8f53f9e95ec03234cbfdf60c9a437db4a4fb3c33dc9fd3146e199901b693a` | `7d1a0076a4aa71577adc6411d4b23d17332b24ac3133feba8102f7f90aba8ab7` |
| `model_output_sp500_pit_t212/background_research_status.json` | `2401c9cd2340d186c98eced96356315cd0c03dab41607c94c60c1df9b5a53d70` | `93b3f6523e04322cbe8f5baabdf29e1c9c1004e59a98c7db5d53c835d18de55f` |
| `model_output_sp500_pit_t212/latest_validated_run.json` | `e5a821da3cae03952cc0bbbad9c43d9f813fa60fb48d58d60fe6947314a9a58d` | `bd8fba0f972984292864562cc13668d5cbb7ff26d7d5edd08e269f07dd927482` |
| `promotion_gate_config.yaml` | `d4c73d780bedcb309869362ff9e90d7189b76acf00d120a317915430bff6210e` | `7d61e57a04c80402149cb4f52c085cbd593d73aad51e8aa15437daa264680882` |

Only `control/p9_shadow_paper_prep_status.json` remains identical among these overlapping paths.

**Finding:** `PRE_G0_PROTECTED_BASELINE_DRIFT_NOT_RECONCILED`.

### 4. The submitted read-only snapshot remains substantively unsafe

`control/review_snapshot/v5r_decision_cockpit_snapshot.json` reports:

```text
active_champion = R5_rank_only_train5
promotion_eligible_display = YES
paper_eligible_display = YES
real_money_eligible_display = YES
```

while the same package represents the state as `BACKTESTED`, `MANUAL_READ_ONLY_ONLY`, and `BLOCKED_FOR_SAFETY`.

Even if operative actions are blocked elsewhere, a review GUI must not visibly present promotion, paper, or real-money eligibility as `YES` under a manually read-only, non-operational terminal state.

**Finding:** `FAIL_CLOSED_COCKPIT_DISPLAY_NOT_ESTABLISHED`.

### 5. G0 is registered but absent from the submitted phase catalog

The package registry contains a G0 review entry; however, `control/vision_automation/phase_catalog.json` does not contain `G0_AUTHORIZATION_SOURCE_CONFLICT_REMEDIATION`.

**Finding:** `G0_PHASE_CATALOG_REGISTRY_MISMATCH`.

### 6. Review package is not an isolated clean remediation checkpoint

`CODEX_G0_GIT_STATUS.txt` lists extensive modified and untracked files, including operational/promotion-related artefacts and scripts such as `control/operational_champion.json`, `control/r5_operational_promotion.json`, `tools/promote_r5_operational.py`, and `OPERATIONAL_DECISION_APPROVAL_ALL.md`.

This is not sufficient evidence of an isolated governance-only remediation from the externally sealed V5R baseline.

**Finding:** `G0_WORKTREE_NOT_CLEANLY_ISOLATED_FOR_EXTERNAL_SEAL`.

### 7. A claimed remediated controller artefact is not included

`CONTROL_AUTHORIZATION_CONFLICT_REPORT.md` states that `control/vision_automation/automation_state.json` was remediated. That file is not included in the submitted G0 ZIP. Its corrected content therefore cannot be externally verified from this package.

**Finding:** `CLAIMED_REMEDIATION_ARTEFACT_OMITTED`.

## Required remediation before resubmission

A replacement G0 submission must:

1. Start from the last externally sealed baseline or explicitly document and externally justify every intervening change.
2. Restore the authoritative Champion status to `R3_w075_q065_noexit`, unless a separately externally sealed approval for a Champion change is supplied. No such approval is accepted by this review.
3. Remove or mark invalid every unapproved R5 operational/promotion lineage assertion from the G0 review state.
4. Ensure all GUI and snapshot outputs show `NO`, `NOT AUTHORIZED`, or `BLOCKED FOR SAFETY` for promotion, paper, real money, and Champion change.
5. Include `control/vision_automation/automation_state.json`, `.cursor/hooks.json`, and every modified authorization/controller source needed to verify the remediation.
6. Add G0 to the phase catalog or otherwise provide a catalog-consistent remediation transition model.
7. Generate the final review ZIP only after the review registry and reports are finalized; record the correct externally observed ZIP hash by detached sidecar in the subsequent approval chain.
8. Provide a clean, isolated Git checkpoint containing only the authorized G0 remediation scope.
9. Re-submit G0 before any G1 approval request is considered.

## Prohibited pending remediation

```text
NO G1 APPROVAL
NO BACKTEST
NO COST-STRESS OR DSR/PBO/CSCV EXECUTION
NO SHADOW OR PAPER ACTIVATION
NO PROMOTION
NO CHAMPION CHANGE
NO REAL-MONEY EXECUTION
NO EXE BUILD OR EXECUTION
```
