# External Review Decision — G0R4R Authoritative Baseline Verbatim Remediation Required

Review date/time (UTC): `2026-05-31T23:54:52+00:00`  
Review basis: static inspection of the submitted ZIP, detached SHA-256 sidecar, detached submission attestation and detached package verification report; direct byte/hash comparison against the supplied prior review-chain artefacts and the package's own authoritative-hash claims. No bundled program, test suite, batch file, EXE, backtest, model job or operational function was executed.

## Reviewed submission

| Field | Result |
|---|---|
| Phase submitted | `G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION` |
| ZIP | `codex_g0r4r_verbatim_external_review_chain_resubmission.zip` |
| Observed ZIP SHA-256 | `a03d793e9a73107addaa1385dbc1029f1a506d264b0ee4925b7da3de64bc8e01` |
| Sidecar match | `PASS` |
| ZIP integrity/readability | `PASS` |
| ZIP entries | `74` |
| Duplicate/unsafe ZIP paths | `NONE` |

## External review decision

```text
G0R4R_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0R4R_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

## Confirmed positive findings

1. ZIP and detached sidecar agree exactly on SHA-256:
   ```text
   a03d793e9a73107addaa1385dbc1029f1a506d264b0ee4925b7da3de64bc8e01
   ```
2. The ZIP is readable and contains no duplicate or unsafe/traversal paths.
3. The detached attestation covers all `74/74` ZIP entries and every entry hash matches the actual submitted ZIP byte content.
4. The internal non-self-referential committed-payload manifest verifies all `73/73` listed payload entries, excludes itself from its internal byte list and contains no final ZIP hash or external-seal assertion.
5. The defect identified in G0R4 is corrected: all `14/14` checked external review and G0R4R approval input files embedded in the ZIP are byte-identical to the externally supplied originals.
6. The ZIP contains all `18` protected artefacts listed by the submitted G0R4R protected-hash map; their actual entry bytes match the submitted hash values. The parsed G0R4R protected-hash mapping equals the submitted V5R protected-hash mapping.
7. The submitted state retains:
   ```text
   AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
   AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
   OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
   G1_AUTHORIZED = NO
   promotion_eligible_display = NO
   paper_eligible_display = NO
   real_money_eligible_display = NO
   ```

## Material blocker preventing external seal

### Authoritative baseline artefacts are not byte-identical to the package's own referenced prior authority chain

The package's current authorization state declares:

```text
authoritative_source = EXTERNAL_REVIEW_APPROVAL_FINAL.md
authoritative_source_sha256 = efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3
```

and the submitted automation state also declares:

```text
last_external_approval_sha256 = efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3
```

However, the submitted ZIP contains:

```text
EXTERNAL_REVIEW_APPROVAL_FINAL.md actual ZIP SHA-256 = 017d0bc59df4bea2b5773ef1cfaf47e6c93f4036b96d5d14b30fcb6fe7940e6a
```

The actual embedded authoritative approval file therefore does not match the SHA-256 the package itself treats as authoritative.

Direct comparison against the corresponding byte versions present in the earlier supplied review-chain package shows that three baseline artefacts have been line-ending-normalized from `CRLF` to `LF`. Their text is newline-normalization-equivalent, but their bytes and SHA-256 values are not identical:

| Baseline artefact | Prior-chain / required SHA-256 | Submitted ZIP SHA-256 | Equal after newline normalization only |
|---|---|---|---|
| `EXTERNAL_REVIEW_APPROVAL_FINAL.md` | `efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3` | `017d0bc59df4bea2b5773ef1cfaf47e6c93f4036b96d5d14b30fcb6fe7940e6a` | `YES` |
| `V5R_EXTERNAL_ACCEPTANCE_REPORT.md` | `08a18385f8e6498b0c63437c372ec4d43980e70e8ad32e5ca6220e9a30b1c97f` | `6d65847e9d4aff0295498087e2810c24fdee272262071c2e11b60047936de276` | `YES` |
| `docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json` | `291b1d75d0774dff20db4cd2efc113239254adfcd3a0193b7a5d1bb4180abd17` | `255f9a7db48d517f9f023dfbe2f7475c36839f599d191331d03f3c7c8c57c7de` | `YES` |

This is material for sealing because G0R4R is a chain-of-custody remediation. It cannot be sealed while it includes a non-byteidentical copy of the document designated as its authoritative final external approval, especially where its own status artefacts reference the prior byte hash.

**Finding:** `G0R4R_AUTHORITATIVE_BASELINE_INPUTS_NOT_VERBATIM`.

## Required minimal remediation

A replacement submission may preserve all technical package-binding, external-review-chain, R3, fail-closed and protected-content corrections already verified above. It must make only this narrowly scoped correction:

1. Replace the submitted LF-normalized copies of:
   ```text
   EXTERNAL_REVIEW_APPROVAL_FINAL.md
   V5R_EXTERNAL_ACCEPTANCE_REPORT.md
   docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json
   ```
   with the byte-identical prior-chain versions supplied for remediation.
2. Include this G0R4R rejection decision and its observed-hash record verbatim as new external review inputs.
3. Rebuild the internal committed-payload manifest, final ZIP, detached sidecar, detached attestation and detached verification report because the payload bytes will change.
4. Preserve:
   ```text
   AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
   AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
   OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
   G1_AUTHORIZED = NO
   ```
5. Do not execute G1 or any analytical, model or operational activity.

## Scope boundary

This review independently verifies the submitted ZIP bytes, detached binding, embedded external review originals available in the review environment, submitted protected file contents and fail-closed representation. The `final_input_commit` declared in the detached attestation was not independently fetched from a Git repository or Git bundle.

## Prohibited pending corrected external seal

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
