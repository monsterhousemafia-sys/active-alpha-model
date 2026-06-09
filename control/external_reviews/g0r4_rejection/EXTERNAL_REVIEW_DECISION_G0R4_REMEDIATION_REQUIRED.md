# External Review Decision — G0R4 Verbatim External-Review Chain Remediation Required

Review date/time (UTC): `2026-05-31T22:52:35+00:00`  
Review basis: static inspection of the submitted ZIP, detached SHA-256 sidecar, detached submission attestation and detached package verification report; direct hashing of ZIP entries and comparison to external review artefacts previously created in this review context. No bundled program, test suite, batch file, EXE, backtest, model job or operational function was executed.

## Reviewed artefacts

| Artefact | Result |
|---|---|
| `codex_g0r4_detached_attestation_exact_byte_package_review.zip` | Received and readable |
| `codex_g0r4_detached_attestation_exact_byte_package_review.zip.sha256` | Received; matches ZIP |
| `codex_g0r4_detached_submission_attestation.json` | Received; entry index matches ZIP |
| `codex_g0r4_detached_package_verification_report.md` | Received; consistent with package verification |

## External review decision

```text
G0R4_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0R4_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

## Confirmed positive findings

1. ZIP SHA-256, detached sidecar, detached attestation and detached verification report agree on:
   ```text
   4d51928423fc05a11a707918e9b4ce84cd42685907a4f1df1bd16b097f4daeb8
   ```
2. The ZIP is readable, with no duplicate or unsafe/traversal paths.
3. The detached attestation provides a complete index of all `65` ZIP entries; all `65/65` entry hashes match the actual submitted ZIP bytes.
4. The ZIP-internal non-self-referential committed-payload manifest lists `64` payload entries excluding itself; all `64/64` listed payload hashes match the actual ZIP bytes.
5. The ZIP-internal manifest correctly avoids embedding its own hash, the final ZIP hash and an external-seal claim.
6. All `18` protected artefacts are included as actual ZIP contents and match the submitted V5R protected baseline.
7. The two previously drifted model-output pointers remain present in their V5R-baseline-matching restored state:
   - `model_output_sp500_pit_t212/background_research_status.json`
   - `model_output_sp500_pit_t212/latest_validated_run.json`
8. The submitted status and snapshot artefacts preserve:
   ```text
   AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
   AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
   OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
   G1_AUTHORIZED = NO
   promotion_eligible_display = NO
   paper_eligible_display = NO
   real_money_eligible_display = NO
   ```
9. Static inspection of the submitted packaging script shows an explicit staging allowlist and no operative `git add -A`, `git add .` or `git commit -a` path.

## Material blocker preventing external seal

### Verbatim chain-of-custody failure for prior external review decisions

The G0R4 ZIP contains files presented under the authoritative external-review filenames and paths. Six submitted Markdown files are not byte-equivalent or text-equivalent to the external review artefacts actually produced in the preceding external reviews. They are shortened/reconstructed summaries.

| Embedded ZIP path | Embedded SHA-256 | Required verbatim external source | Required SHA-256 |
|---|---|---|---|
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md` | `fcc6ce80b10c09c2cbc78c468c2efca996a56f9adf02a250dbf80eefbb77ea2e` | `EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md` | `e4df069142ec7d56091db8593d6c5d3d3ddb51379f0f990eab453b8679346e0b` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md` | `7d400303528cf712e75cc76aacb081e113cbb5b37ec67561100f65a4656dd8a3` | `EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md` | `55b456beffb4871ae27ed0f33bf6f141421f50fe4ece0d2c8cc8e2106846cde2` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_SUMMARY_G0_G1.md` | `7f6d58e92920c2c9da6b4b142dda9f373ca250a6d503ec1f35ac827695d4996e` | `EXTERNAL_REVIEW_SUMMARY_G0_G1.md` | `96d387fbfa281a5aa263120ad07ec5724d53358f5c82a5420b0586228471c1f7` |
| `control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md` | `76b950547d6ea1cda3557071e26e887b382928aca87c5acfc55aa75420583f9c` | `EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md` | `1050df3f8a59836301225cf3342b2f27e644e6d1e86f5577756c5488367d67e5` |
| `control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md` | `2c8bbd091a7c4e7c54057b016251425cbe447e5a7e5d232e98a0da310390cd81` | `EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md` | `f6fa0c3d2b080487441764e07a84360f38e8389923dc5d5b4f3de3d2ada5b689` |
| `control/external_reviews/g0r3_rejection/EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md` | `c8dbf03cd685e3a106f1ddf43c06219424a76b50b7b85c6444603d41ac5ab63e` | `EXTERNAL_REVIEW_DECISION_G0R3_REMEDIATION_REQUIRED.md` | `566dd3f6b5bc8d2305f87e45062ade4e20be21c4b9a890c9d41eec4545451c11` |

The corresponding observed-hash `.sha256` records for G0/G1, G0R, G0R2 and G0R3 match the original external records. The defect is limited to the substituted Markdown review decision/report contents.

This is material because a sealed audit chain must not replace authoritative external review decisions with reconstructed text under the same authoritative filenames. Technical exact-byte consistency of the new package does not authenticate substituted historical review records.

**Finding:** `G0R4_EXTERNAL_REVIEW_INPUTS_NOT_VERBATIM`.

## Required minimal remediation

A replacement G0R4 submission may preserve all technically validated package, R3, fail-closed and protected-state contents. It must make only this narrowly scoped correction:

1. Replace the six embedded substituted Markdown external-review files with the exact verbatim external originals supplied with this rejection decision.
2. Include this G0R4 rejection decision and its observed-hash record verbatim as a new external-review input.
3. Rebuild the non-self-referential payload manifest, ZIP, detached sidecar, detached submission attestation and detached verification report, because the ZIP payload bytes will change.
4. Preserve:
   - `R3_w075_q065_noexit` as authoritative Champion;
   - `BLOCKED_FOR_SAFETY`;
   - `G1_AUTHORIZED = NO`;
   - all `18` V5R-matching protected artefacts;
   - all fail-closed snapshots and prohibited-activity flags.
5. Do not execute any G1, analytical, model or operational task.

## Scope boundary

This review verifies submitted artefact bytes, detached binding, protected-state consistency and fail-closed governance representation. The `final_input_commit` recorded in the detached attestation is part of the submitted claim; the Git object itself was not independently fetched from a repository or Git bundle in this review.

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
