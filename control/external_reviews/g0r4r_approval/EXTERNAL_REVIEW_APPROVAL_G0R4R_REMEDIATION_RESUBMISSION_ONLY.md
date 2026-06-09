# EXTERNAL REVIEW APPROVAL — G0R4R Remediation Resubmission Only

**Approval ID:** `G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION_ONLY`  
**Issued at (UTC):** `2026-05-31T23:16:09+00:00`  
**Project:** Active Alpha Model / Marktanalyse Decision Cockpit  
**Approval status:** `APPROVED_FOR_LIMITED_REMEDIATION_RESUBMISSION_ONLY`

## 1. Decision

This approval authorizes Codex to execute only the narrowly scoped remediation phase:

```text
G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION
```

The sole purpose of this phase is to correct the remaining chain-of-custody defect in the rejected G0R4 review submission by replacing substituted or reconstructed historical external-review Markdown files with their supplied verbatim originals, then regenerating a technically consistent review submission set.

This approval is **not** an external seal of G0R4 or G0R4R.  
This approval is **not** a G1 approval.  
This approval does **not** authorize any analytical, model, trading, monitoring, promotion, EXE or operational action.

## 2. Controlling review finding

The previously submitted G0R4 package was rejected solely because certain embedded historical external-review Markdown files were not verbatim copies of the authoritative external-review originals.

The validated aspects of G0R4 are to be preserved unchanged:

```text
AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
G1_AUTHORIZED = NO
```

The G0R4 technical package-binding method, protected-state preservation and fail-closed status representation may be reused only insofar as they remain unchanged and verifiably consistent after replacing the non-verbatim external-review inputs.

## 3. Authorized inputs

Codex is authorized to use only the following newly provided external-review inputs for this remediation:

```text
EXTERNAL_REVIEW_DECISION_G0R4_REMEDIATION_REQUIRED.md
EXTERNAL_REVIEW_OBSERVED_HASH_G0R4.sha256
G0R4R_VERBATIM_EXTERNAL_REVIEW_INPUTS.zip
```

All external-review documents contained in `G0R4R_VERBATIM_EXTERNAL_REVIEW_INPUTS.zip` must be handled as immutable external inputs. They must not be summarized, rewritten, shortened, regenerated or substituted under their authoritative filenames.

## 4. Authorized work

Codex may perform only the following actions:

```text
- read the submitted external-review inputs;
- replace the non-verbatim embedded external-review Markdown files with the supplied byte-identical originals;
- include the new G0R4 rejection decision and its observed-hash record verbatim;
- perform byte-identity checks for all external-review input files included in the new submission;
- preserve and re-verify the established R3/read-only/fail-closed/protected-state artefacts;
- update documentation, manifests, phase-catalog and review-registry entries only as required for G0R4R submission status;
- use explicit allowlist Git staging only;
- create a final input commit for the G0R4R submission inputs;
- build a new ZIP exclusively from committed bytes;
- generate a non-self-referential internal committed-payload manifest;
- generate, outside the ZIP, a detached SHA-256 sidecar, detached submission attestation and detached package verification report;
- execute only non-operative integrity/unit tests necessary to verify the submission package.
```

## 5. Required output submission set

If and only if all local G0R4R gates pass, Codex may generate the following submission set for external review:

```text
codex_g0r4r_verbatim_external_review_chain_resubmission.zip
codex_g0r4r_verbatim_external_review_chain_resubmission.zip.sha256
codex_g0r4r_detached_submission_attestation.json
codex_g0r4r_detached_package_verification_report.md
```

All four files must be submitted together for external review.

## 6. Mandatory invariant state

The following state must remain true throughout and after the authorized remediation:

```text
AUTHORITATIVE_CHAMPION = R3_w075_q065_noexit
AUTHORIZED_USAGE = MANUAL_READ_ONLY_REVIEW_ONLY
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY

G0R4R_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
G1_EXECUTION_STARTED = NO

SHADOW_MONITORING_ACTIVATED = NO
PAPER_MONITORING_ACTIVATED = NO
PROMOTION_EXECUTED = NO
CHAMPION_CHANGED = NO
REAL_MONEY_EXECUTED = NO
EXE_EXECUTED = NO
```

## 7. Explicitly prohibited actions

This approval does not authorize:

```text
- G1 execution or G1 approval;
- turnover artefact generation;
- backtest execution or historical revalidation;
- matrix re-run;
- cost-stress calculation;
- DSR, PBO, CSCV or robustness calculation;
- research jobs;
- replay or realtime jobs;
- shadow monitoring or shadow signal generation;
- paper simulation or paper activation;
- promotion;
- Champion change;
- real-money execution;
- broker connectivity;
- EXE build or EXE execution;
- any change to economic model parameters, signal weights, Horizon, Rebalance,
  Exposure, Beta, cost assumptions or Slippage assumptions;
- any automatic next phase.
```

If any prohibited action is required, suggested, initiated or detected, the remediation must terminate with:

```text
G0R4R_STATUS = BLOCKED
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
G1_AUTHORIZED = NO
```

## 8. External-review status after Codex completion

Completion of the authorized Codex work does not produce approval or sealing. At most, a successful local result may state:

```text
G0R4R_LOCAL_REMEDIATION_STATUS = PASS
G0R4R_EXTERNAL_REVIEW_STATUS = AWAITING_EXTERNAL_REVIEW
G0R4R_EXTERNAL_SEALED = NO
G1_AUTHORIZED = NO
OPERATIONAL_STATUS = BLOCKED_FOR_SAFETY
```

Only a subsequent external review of the complete four-file G0R4R submission may decide whether G0R4R is sealed.

## 9. Next possible step after a future seal

Only if G0R4R is subsequently externally reviewed and explicitly sealed may a separate request be made for a narrowly scoped G1 approval.

No G1 approval is issued by this document.
