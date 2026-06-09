# External Review Decision — G0R3 Final Commit-Bound Package and Manifest Remediation

Review date/time (UTC): `2026-05-31T22:15:38+00:00`  
Review basis: static inspection of the submitted ZIP and detached SHA-256 sidecar; direct byte/hash comparison of in-package artefacts; static inspection of the submitted Git/package evidence and packaging script. No bundled source file, test suite, batch file, EXE, backtest, model job or operational function was executed.

## Reviewed artefacts

| Field | Value |
|---|---|
| Phase submitted | `G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION` |
| Review ZIP | `codex_g0r3_final_commit_bound_package_review.zip` |
| Observed external SHA-256 | `ce8a968ef00b73e0bcb27d6860fdec60386e6223ace7d81b7c0a7b8c97d79e58` |
| Submitted sidecar | `codex_g0r3_final_commit_bound_package_review.zip.sha256` |
| Sidecar verification | `PASS` |
| ZIP entries | `61` |
| ZIP integrity/readability | `PASS` |
| Duplicate ZIP paths | `NONE` |
| Unsafe/traversal ZIP paths | `NONE` |

## External review decision

```text
G0R3_EXTERNAL_REVIEW_DECISION = REJECTED_REMEDIATION_REQUIRED
G0R3_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

G0R3 preserves the substantive R3/read-only/protected-state corrections previously recognized in G0R2 and corrects several prior packaging omissions. It cannot be externally sealed because its central claim of a commit-bound, byte-verifiable final review package is contradicted by the submitted package-input manifest and Git evidence.

## Confirmed positive findings

1. The submitted detached sidecar matches the independently calculated ZIP SHA-256:
   ```text
   ce8a968ef00b73e0bcb27d6860fdec60386e6223ace7d81b7c0a7b8c97d79e58
   ```
2. The ZIP is readable and contains no duplicate or unsafe/traversal paths.
3. The submitted authorization and snapshot artefacts retain `R3_w075_q065_noexit` as authoritative Champion and preserve manual read-only, blocked-for-safety semantics.
4. The submitted current snapshots display:
   ```text
   promotion_eligible_display = NO
   paper_eligible_display = NO
   real_money_eligible_display = NO
   ```
5. `VISION_PROGRESS.json` remains informational-only, states `operational_authorization = NONE`, and sets operative safety flags to `NO`.
6. The Phase Catalog includes G0R3 and expressly prohibits G1 execution, turnover generation, backtest/matrix execution, Cost Stress, statistical validation, Robustness, Shadow, Paper, Promotion, Champion change, real-money activity, EXE build/execution and broker connectivity.
7. The Review Registry represents G0R3 as `AWAITING_EXTERNAL_REVIEW`, with `external_sealed = false`, `g1_authorized = false`, `next_phase_authorized = false` and `review_zip_sha256 = PENDING_EXTERNAL_SEAL`.
8. All four review snapshots required after the G0R2 rejection, including `control/review_snapshot/v5r_decision_cockpit_snapshot.json`, are present in the ZIP.
9. `G0R3-CHANGE_MANIFEST.json` now acknowledges governance/packaging mutations rather than incorrectly describing the work as mutation-free.
10. All `18` protected artefacts listed in `CODEX_G0R3_PROTECTED_HASHES_AFTER.json` are present as actual file contents in the ZIP, match their submitted After hashes, and match the submitted V5R protected baseline.
11. The two previously drifted model-output pointer paths remain documented as prior drift and are present in their V5R-baseline-matching restored state:
    - `model_output_sp500_pit_t212/background_research_status.json`
    - `model_output_sp500_pit_t212/latest_validated_run.json`
12. Static inspection of `tools/complete_g0r3_submission.py` shows an explicit staging allowlist and no operative use of unrestricted `git add -A`, `git add .` or `git commit -a`.

## Material blockers preventing external seal

### 1. The submitted package-input manifest fails byte verification for 32 of 61 ZIP entries

`docs/phases/G0R3/CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json` claims that every submitted entry is a commit-bound input with a stated `sha256_of_included_bytes` and `head_byte_match_verified = true`.

Direct external hashing of the actual submitted ZIP entries produces:

| Test | Result |
|---|---:|
| Manifest entries | `61` |
| Entries whose actual ZIP bytes match the recorded hash | `29` |
| Entries whose actual ZIP bytes do **not** match the recorded hash | `32` |

The mismatches include review-critical materials such as:

- `CODEX_G0R3_PREFLIGHT.md`;
- `CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md`;
- `CODEX_G0R3_GIT_STATUS.txt`;
- `CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json` itself;
- `CODEX_G0R3_TEST_OUTPUT.txt`;
- the G0R, G0R2, G0R3 and V5R cockpit snapshots;
- `control/vision_automation/transition_log.jsonl`;
- `tools/complete_g0r3_submission.py`;
- several test and current governance artefacts.

Because the manifest is the asserted binding between the final submitted ZIP contents and the final input commit, this mismatch invalidates the central external-review proof.

**Finding:** `G0R3_PACKAGE_INPUT_MANIFEST_BYTE_MISMATCH`.

### 2. The submitted packaging script creates in-ZIP byte mutations after reading committed inputs but does not manifest those final bytes

Static inspection of `tools/complete_g0r3_submission.py` shows:

```text
- ZIP entries are read from the stated commit.
- For the package manifest, Git-status report and remediation report,
  the script replaces a commit placeholder after reading committed bytes.
- The script separately calculates a manifest object, but the shown
  build path does not write that calculated final-byte manifest back
  into the ZIP.
```

The effect is directly observable in the submitted package: files claimed as `COMMITTED_INPUT` and `head_byte_match_verified = true` do not match their declared included-byte hashes.

This is a packaging integrity defect, not merely a documentation wording issue.

**Finding:** `G0R3_POST_COMMIT_BYTE_SUBSTITUTION_NOT_REPRESENTED_IN_MANIFEST`.

### 3. The submitted Git-status report is not a final clean-checkpoint report

`CODEX_G0R3_GIT_STATUS.txt` states:

```text
g0r3_start_head=ad2fcbf4702ef03979ff23df875b6c9e1b077486
g0r3_final_input_commit=cf3fb58b92b805ce0758f0cd76d807339e488c7e
head_changed=pending_commit
```

It then lists a pre-commit dirty worktree rather than a final clean state. Although a commit identifier is injected into the ZIP content, the report itself does not evidence the claimed final post-commit clean checkpoint and is one of the entries whose byte hash does not match the package-input manifest.

**Finding:** `G0R3_FINAL_CLEAN_CHECKPOINT_REPORT_NOT_ESTABLISHED`.

### 4. Local PASS is unsupported because the package-binding gate failed

The remediation report asserts:

```text
G0R3_LOCAL_REMEDIATION_STATUS: PASS
```

However, the defining objective of G0R3 was a final commit-bound, manifest-verifiable package. The actual package fails that test for 32 entries. Under the stated fail-closed policy, local status must not be `PASS` when the package-input manifest does not verify the submitted bytes.

**Finding:** `G0R3_LOCAL_PASS_ASSERTION_NOT_SUPPORTED`.

## Mismatching package-input-manifest entries

| ZIP path | Manifest SHA-256 | Actual submitted-byte SHA-256 |
|---|---|---|
| `docs/phases/G0R3/CODEX_G0R3_PREFLIGHT.md` | `41a4ecab7a30ef1cd52e91b7a7a34995ad54bd533c5a85c5295744b6df53a0ce` | `88ba7a368d1b13364df8af09d87bdc22f39f113360ef4ebefffdf77c2966606d` |
| `docs/phases/G0R3/CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md` | `83943dcb5a6bebd20486db63d5501e176f6c3a69349c4919b46f77080ef6ca98` | `21afc037ed433850491b82f03f243d79b5389422638129e62ce9eab835bbdc8e` |
| `docs/integrity/session_logs/G0R3/CODEX_G0R3_GIT_STATUS.txt` | `648f97b74db3626d9a57b6bcedf4b0df9b9f011f78ff7530f1b460ccdeab7b3c` | `0122457a8286adaf1444eca35e4cccb50dbc6c93af43bb1bb4eb9627efee6392` |
| `docs/phases/G0R3/CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json` | `523f433f6889c90798c50232b163b86246708bac85a515980711e3deb377dc0c` | `61553e89457196e2175d4fe0f4d061acef809b97441783372234a5fa57f395a0` |
| `docs/integrity/session_logs/G0R3/CODEX_G0R3_TEST_OUTPUT.txt` | `657c32b8765569e24c30779bb655877d8a7abe9a52b0aa1421d7c88112c2efa1` | `b0185f7354a2f92ad9f99f9fda5d1bc05db361b92c56120568a3f56acd2874c3` |
| `control/review_snapshot/g0r_decision_cockpit_snapshot.json` | `941c4691fb9d1c2826dd4c3e7b987eb25f4f68ebb8c67d1f505ce21f5570cfa4` | `fb7bade6305ad3a007b5c0f63240842b3708830c3d8ea71483bc48b012546cf0` |
| `control/review_snapshot/g0r2_decision_cockpit_snapshot.json` | `f5ae8b5beb5d95db040f4067e81dba4fac2ffb0c6b3441080a53fc74fe03140f` | `7267a10dd69fe921412e483d9ef2299bb8ff22596d0ec26834b3ee9109a6a1db` |
| `control/review_snapshot/g0r3_decision_cockpit_snapshot.json` | `f086a26e34971ed16587789c1979b8fe11c113fcc6b904ae46434c24c892dd15` | `2c54d609e2ec3e6305d6be95a8f64708f085e1045d2b6553dc6742976535fb7f` |
| `control/review_snapshot/v5r_decision_cockpit_snapshot.json` | `4055d919b70dbf2340ed8e487679234b2aee2d93c5ee8f9624e0f3816e0db7d7` | `97cce59119b8ce2747121c5bf4214ad8913d0585baa4843b5d272b57d90f77dc` |
| `control/vision_automation/transition_log.jsonl` | `ea3a7feb038bb3beba72b2ff0750dd88749c5664466cb2b1c6ab16d9ae822cd4` | `2877ea91512462dab3e7fdddafa3bcbc4c4f9b239da7dbf8187950a30bf077c2` |
| `control/system_health.json` | `e6aa5e4cb1ba1083551259adaa7f09922065897c9702d5bce0c3d4b09d757baa` | `e4cd2bed595506a23180d1363de645a9befafc7b9a5b55e51fb78d564b8161cc` |
| `.cursor/hooks.json` | `21d21d4fab45e66f97501a390d866f0b6c801cfd8f2b6656a252d1a50b692827` | `887820009578e8dc55e174da5873b4025cde40c5b0c33e750b69238b3c158079` |
| `EXTERNAL_REVIEW_APPROVAL_FINAL.md` | `efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3` | `017d0bc59df4bea2b5773ef1cfaf47e6c93f4036b96d5d14b30fcb6fe7940e6a` |
| `V5R_EXTERNAL_ACCEPTANCE_REPORT.md` | `08a18385f8e6498b0c63437c372ec4d43980e70e8ad32e5ca6220e9a30b1c97f` | `6d65847e9d4aff0295498087e2810c24fdee272262071c2e11b60047936de276` |
| `docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json` | `291b1d75d0774dff20db4cd2efc113239254adfcd3a0193b7a5d1bb4180abd17` | `255f9a7db48d517f9f023dfbe2f7475c36839f599d191331d03f3c7c8c57c7de` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G0_REMEDIATION_REQUIRED.md` | `93780d13c7803053b29c468b97fae8d45d3eca3c345d3839f47c070510e82cd8` | `fcc6ce80b10c09c2cbc78c468c2efca996a56f9adf02a250dbf80eefbb77ea2e` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_DECISION_G1_NOT_APPROVED.md` | `fa903323562a830816c1cf236462b2104f2f447b4e68db04fc0d1e508b8759b9` | `7d400303528cf712e75cc76aacb081e113cbb5b37ec67561100f65a4656dd8a3` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_SUMMARY_G0_G1.md` | `9659c55f2ab80f834c9d7ce22707f7169b14309e85c801528d8eae976751650a` | `7f6d58e92920c2c9da6b4b142dda9f373ca250a6d503ec1f35ac827695d4996e` |
| `control/external_reviews/g0_g1_rejection/EXTERNAL_REVIEW_OBSERVED_HASHES_G0_G1.sha256` | `ce7308cbd9522db9b70b8b191d6b6a4673e21023584ed9a63adc50d39db082cf` | `13c4c9956e133920771e7b6f5e25e5ac904148a83f5a2d1b0c2542008c59f1d2` |
| `control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_DECISION_G0R_REMEDIATION_REQUIRED.md` | `1db90a39c646dd4b47cc823d6620e11e3ce34f079160d2afabe09a9f00bb2cc0` | `76b950547d6ea1cda3557071e26e887b382928aca87c5acfc55aa75420583f9c` |
| `control/external_reviews/g0r_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R.sha256` | `d0ff3869f2519ade06717c6f7eea03d3c60e0a005a9ee4a8ad34bfa5bbd70175` | `bf6190427a676b8c7fea86438e0e069b03c89568190d71c931b4f4455b7cce20` |
| `control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md` | `676bde1933a828e7bd4353080d53889b555c523d5b0456ac1f55849317d510c5` | `2c8bbd091a7c4e7c54057b016251425cbe447e5a7e5d232e98a0da310390cd81` |
| `control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256` | `2f1a2b13a6e8b9ff34152daa49c57c8ff3fa1450d23b5c70a6c9b0abd7968860` | `4eed9790abd179861d7fd6187fd6cac92c0c8c382c52ffdb273e72b42a1f1e6e` |
| `NEXT_CURSOR_PROMPT.md` | `4679bbbdd247a4fe5c9477de4269311b70f1ba11097413f26e3bb453785bf15e` | `313ff16bdcc99786f5463cd3b785061c6177f4a70fe51d2071271441ca4b59a9` |
| `EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md` | `17e1f15e45a96310f07b15ed3ca9973232b78aa312ff8791d0423eb1230727d0` | `aac8f83abf88b554c4202ae8029139661ea92eecab759adcf7fdadd10d468781` |
| `tools/complete_g0r3_submission.py` | `621fb135c76ced8f54e42331c274f9efbdd109c9b3aba595c5432eadcabb64ca` | `94446ef6130d70364cb182dd2b14fc7ae9db4ed32f7dd9105c27b83e55e2f45d` |
| `tests/test_g0r3_submission_integrity.py` | `971fe5c2b2dd73fb5f70674ec1fe181b7192d0d8fa699bdb88b73311ec11950f` | `c8c30f945d770605350a898487323d0f7fbaee8014551c8e31bdb5e124998e46` |
| `tests/test_authorization_conflict_fail_closed.py` | `f695ed67fd98f302085060217647a13fb29bc186e27253074918b2d57dddecdf` | `c87ccf4a9a34a28843f34ed472eb86c3dd38df8eb65b583ee538ebb0abb5685b` |
| `tests/test_g0r_remediation.py` | `c6227edb77d2942279846ebc790881fc374e9e8c6544204b58817eb1cb78b41e` | `8bdd56bc5f5a4f18c4c3377c272b92eea6b32600fa31c7f743d7cf08d777b2b4` |
| `tests/test_g0r2_remediation.py` | `9a0ceddd8ed5b7359778c2293947fdd8dfa77a4009f21c903b457e8e35cfda47` | `21f585164b973129a38577bc1ccf3737a5ae55cc43214a88c396fb94a90851d6` |
| `aa_decision_cockpit_readonly_snapshot.py` | `cf3f833ff9d7d84fd9d63a0c3dceb3dc7d03d9afd41b9c022fef29d858e23afc` | `bf06ce4f307834186954e187ff3daedfa9853b8f636210fdfbf82905507478a5` |
| `aa_doc_paths.py` | `ffc51feb697398a00109af0e8220993b83ef6ebb07aead6f6a4daaca497c30e9` | `a579c70361fce2bf7104ffbc1a3fda696e459e9ff522e2bd150d9f83a95f1588` |

## Required remediation before a replacement submission

A replacement submission may preserve all already verified R3/read-only/protected-state corrections and focus solely on final package-binding correctness. It must:

1. Build a manifest over the **exact final ZIP entry bytes**. Every `sha256_of_included_bytes` value must equal the hash of the corresponding entry in the submitted ZIP.
2. Eliminate post-commit placeholder replacement inside ZIP entries, or represent such transformed entries honestly as generated package metadata rather than `COMMITTED_INPUT` with false `head_byte_match_verified = true`.
3. Avoid self-referential claims. A package manifest may either:
   - exclude its own entry from byte-binding claims; or
   - use a clearly documented non-self-referential sealing design whose verification can be externally reproduced.
4. Provide a final Git checkpoint report that reflects the state **after** the final input commit, including:
   - final input commit SHA;
   - `head_changed = true`;
   - clean relevant worktree status after commit;
   - explicit allowlist used;
   - confirmation that package metadata generated outside the commit is separately classified.
5. Mark generated ZIP metadata accurately, for example as `GENERATED_PACKAGE_METADATA`, not as commit-identical inputs unless the bytes actually match the commit.
6. Re-run only non-operative package-integrity/unit tests and ensure they verify the final produced ZIP, not merely pre-package placeholders.
7. Generate a new ZIP and detached sidecar and submit both for external review.
8. Keep G1 unauthorized and retain all existing operative prohibitions.

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
