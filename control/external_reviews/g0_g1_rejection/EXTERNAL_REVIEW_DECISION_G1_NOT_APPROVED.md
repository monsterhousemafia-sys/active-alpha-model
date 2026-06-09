# External Review Decision — G1 Read-Only Challenger Cost Evidence Submission

Review date/time (UTC): `2026-05-31T21:12:43+00:00`  
Review basis: static inspection of the submitted archive and consistency review against the final sealed external approval and the contemporaneously reviewed G0 submission. No bundled program, test suite, EXE, batch file, or repository script was executed.

## Reviewed artifact

| Field | Value |
|---|---|
| Phase requested | `G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION` |
| Artifact | `codex_g1_readonly_challenger_cost_evidence_submission.zip` |
| Observed external SHA-256 | `50a26cd8a6a1c36db8d9fc30a82aeb743b241fbb73d51fb0a03d09c5a4644aeb` |
| Archive entries | `10` |
| ZIP readability | `PASS` |
| Duplicate ZIP paths | `NONE` |
| Unsafe ZIP paths | `NONE` |

## Review decision

```text
G1_EXTERNAL_REVIEW_DECISION = NOT_APPROVED
EXTERNAL_REVIEW_APPROVAL_G1_READ_ONLY_CHALLENGER_COST_EVIDENCE.md = NOT ISSUED
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

The G1 request cannot be approved because its required G0 predecessor is not externally sealable in the submitted state and because G1 is built on an unapproved Champion identity.

## Confirmed positive findings

1. The ZIP is structurally readable; no duplicate or traversal paths were identified.
2. The submission explicitly states that it is not itself approval.
3. It correctly retains `CHALLENGER_TURNOVER_NOT_VERIFIED` as an unresolved blocker.
4. It correctly states that no Shadow, Paper, Promotion, Champion change, real-money operation, or new Cost-Stress/DSR/PBO recomputation is authorized by the submission.
5. The G1 ZIP hash recorded in the G0 registry entry matches the externally observed G1 ZIP SHA-256; this does not cure the substantive predecessor and Champion conflicts.

## Material rejection findings

### 1. Required predecessor G0 is rejected

The G1 preflight requires G0 to have passed. The accompanying G0 submission is rejected in this external review and is not sealed.

**Finding:** `G1_PREDECESSOR_G0_NOT_EXTERNALLY_SEALED`.

### 2. G1 uses an unauthorized Champion identity

The final sealed external approval records `R3_w075_q065_noexit` as the unchanged Champion and disallows Champion change.

The G1 submission instead sets:

```text
champion = R5_rank_only_train5
```

in:

- `G1_COMPARISON_LOGIC.md`
- `control/evidence/g1_challenger_cost_preparation_status.json`
- `control/evidence/g1_source_inventory.json`
- `control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml`

Without a separate externally sealed Champion-change authorization, this comparison frame is invalid.

**Finding:** `G1_UNAUTHORIZED_CHAMPION_REFERENCE`.

### 3. G1 comparison logic is not reviewable against the authoritative baseline

Because the comparison reference is switched from sealed Champion `R3_w075_q065_noexit` to unapproved `R5_rank_only_train5`, the submitted inventory cannot establish the intended closure of `CHALLENGER_TURNOVER_NOT_VERIFIED` against the approved lineage.

**Finding:** `G1_COMPARISON_FRAME_NOT_AUTHORIZED`.

### 4. Submission does not provide an externally verifiable detached sidecar

The submission refers to `codex_g1_readonly_challenger_cost_evidence_submission.zip.sha256`, but no detached sidecar was provided with the submitted review materials. The hash has therefore been independently observed in this review, but a claimed sidecar verification cannot be accepted.

**Finding:** `G1_DETACHED_SIDECAR_NOT_SUBMITTED_FOR_VERIFICATION`.

## Required remediation before a new G1 request

A new G1 submission may be considered only after:

1. A corrected G0 review ZIP is externally accepted and sealed.
2. The accepted governance state preserves `R3_w075_q065_noexit` as Champion, unless a separate externally approved change is later provided.
3. The G1 preparation materials use the accepted Champion and approved M1 control consistently.
4. The G1 package includes a verifiable detached SHA-256 sidecar or obtains an external observed-hash record during the approval process.
5. The approved G1 scope remains limited to producing variantspecific turnover/trade/cost evidence for `MOM_63_TOP12`, with no Shadow, Paper, Promotion, Champion change, real-money execution, EXE activity, or unapproved historical reruns.

## Prohibited pending remediation

```text
NO G1 TECHNICAL RUN
NO TURNOVER ARTEFACT GENERATION UNDER THE CURRENT G1 SUBMISSION
NO BACKTEST OR MATRIX RE-RUN
NO COST-STRESS OR STATISTICAL RECOMPUTATION
NO SHADOW OR PAPER
NO PROMOTION OR CHAMPION CHANGE
NO REAL-MONEY EXECUTION
NO EXE BUILD OR EXECUTION
```
