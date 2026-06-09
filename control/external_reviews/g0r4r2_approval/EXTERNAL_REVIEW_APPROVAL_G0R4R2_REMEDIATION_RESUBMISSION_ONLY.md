# EXTERNAL REVIEW APPROVAL — G0R4R2 Authoritative Baseline Verbatim Remediation Resubmission Only

**Approval ID:** `G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION_ONLY`  
**Issued at (UTC):** `2026-05-31T23:58:47+00:00`  
**Project:** Active Alpha Model / Marktanalyse Decision Cockpit  
**Approval status:** `APPROVED_FOR_LIMITED_REMEDIATION_RESUBMISSION_ONLY`

## 1. Decision

This document authorizes Codex to execute only the narrowly scoped remediation phase:

```text
G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION
```

The sole purpose of this phase is to correct the remaining byte-level chain-of-custody defect found in the rejected G0R4R submission: three authoritative baseline artefacts were embedded as line-ending-normalized copies rather than as the byte-identical prior-chain versions to which the project's own authoritative status refers.

This approval is **not** an external seal of G0R4R or G0R4R2.  
This approval is **not** a G1 approval.  
This approval authorizes **no** analytical, model, trading, monitoring, promotion, EXE or operational action.

## 2. Controlling external-review finding

The submitted G0R4R package passed the following technical checks:

```text
- ZIP / sidecar binding passed.
- Detached attestation verified all ZIP entries.
- Internal non-self-referential payload-manifest verification passed.
- The previously required external review verbatim replacement passed.
- Protected-state and fail-closed state representation remained intact.
```

It was rejected solely because these authoritative baseline artefacts were not byte-identical to the prior-chain versions referenced by the package's own authorization state:

```text
EXTERNAL_REVIEW_APPROVAL_FINAL.md
V5R_EXTERNAL_ACCEPTANCE_REPORT.md
docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json
```

The required byte-identical replacement versions are supplied in:

```text
G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip
```

## 3. Mandatory invariant state

Throughout and after this authorized remediation, the following state must remain true:

```text
AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY

G0R4R2_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
G1_EXECUTION_STARTED = NO

SHADOW_MONITORING_ACTIVATED = NO
PAPER_MONITORING_ACTIVATED = NO
PROMOTION_EXECUTED = NO
CHAMPION_CHANGED = NO
REAL_MONEY_EXECUTED = NO
EXE_EXECUTED = NO
```

## 4. Authorized inputs

Codex is authorized to use only the following newly provided external-review inputs for this phase:

```text
EXTERNAL_REVIEW_DECISION_G0R4R_REMEDIATION_REQUIRED.md
EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R.sha256
G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip
G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_INPUTS.zip.sha256
G0R4R2_REQUIRED_VERBATIM_AUTHORITY_BASELINE_MANIFEST.json
EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md
EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256
```

All supplied external-review and baseline artefacts are immutable inputs. They must not be normalized, rewritten, shortened, reconstructed, reformatted or regenerated.

## 5. Authorized work

Codex may perform only:

```text
- verify the input bundle and this approval document by SHA-256;
- replace the three identified non-byteidentical baseline artefacts with the supplied exact-byte originals;
- include this G0R4R rejection decision and its observed-hash record verbatim;
- include this approval document and its SHA-256 sidecar verbatim;
- preserve and re-verify the already validated R3/read-only/fail-closed/protected-state representation;
- update phase-catalog, review-registry, submission documentation, manifests, tests and snapshot state only as strictly required for the G0R4R2 submission status;
- use explicit allowlist Git staging only;
- create a final input commit for the G0R4R2 submission inputs;
- build a new review ZIP exclusively from committed bytes;
- generate a non-self-referential internal committed-payload manifest;
- generate, outside the ZIP, a detached ZIP SHA-256 sidecar, detached submission attestation and detached package verification report;
- execute only non-operative integrity/unit tests needed to validate this submission package.
```

## 6. Explicitly prohibited actions

This approval does not authorize:

```text
- G1 execution or G1 approval;
- Challenger turnover artefact generation;
- backtest execution or historical revalidation;
- matrix re-run;
- cost-stress calculation;
- DSR, PBO, CSCV or robustness calculation;
- research jobs, replay jobs or realtime jobs;
- shadow monitoring or shadow signal generation;
- paper simulation or paper activation;
- promotion or Champion change;
- real-money execution;
- broker connectivity;
- EXE build or EXE execution;
- changes to economic model parameters, signal weights, horizon, rebalance,
  exposure, beta, cost assumptions or slippage assumptions;
- any automatic subsequent phase.
```

If any prohibited activity is required, initiated or detected:

```text
G0R4R2_STATUS = BLOCKED
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
G1_AUTHORIZED = NO
```

## 7. Required output submission set

If and only if every local G0R4R2 integrity gate passes, Codex may create the following four artefacts for external review:

```text
codex_g0r4r2_verbatim_authoritative_baseline_resubmission.zip
codex_g0r4r2_verbatim_authoritative_baseline_resubmission.zip.sha256
codex_g0r4r2_detached_submission_attestation.json
codex_g0r4r2_detached_package_verification_report.md
```

All four files must be submitted together for external review.

Completion of Codex work produces no seal and no G1 approval. At most, the local status may be:

```text
G0R4R2_LOCAL_REMEDIATION_STATUS = PASS
G0R4R2_EXTERNAL_REVIEW_STATUS = AWAITING_EXTERNAL_REVIEW
G0R4R2_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```
