# CODEX V5 EXE Build Report

Phase: `V5_WINDOWS_EXE_BUILD_AND_VERIFICATION` (resumed after interrupted run)

## Recovery

- Interrupted run recovered: YES
- V4R3 sealed: YES
- Pre-existing EXE baseline preserved: YES

## Git traceability

- V4R3 baseline checkpoint commit: `50d6cfbced22032012db499c0756427b121597d4`
- V5 build/evidence commit: `9273938` — `build: create read-only Marktanalyse Decision Cockpit EXE for external review`
- GIT_V5_BUILD_COMMIT_CREATED: YES
- GIT_V5_BUILD_COMMIT_SHA: `92739383048871cee44a695c2555978138a96e5e`
- EXE excluded from Git; supplied separately with `Marktanalyse.exe.sha256`
- EXE_REBUILT_DURING_GIT_SEAL_STEP: NO
- EXE_EXECUTED: NO

## Pre-existing EXE (not V5 build evidence)

- SHA-256: `eb93e3af18ed175cd8ce8b919b90088dd85cbcfc92a318f65c452afde42f8debe`
- LastWriteTimeUtc: `2026-05-30T13:31:39.9000678Z`

## New V5 build EXE

- Path: `E:\active_alpha_model\Marktanalyse.exe`
- Size bytes: 27856626
- SHA-256: `44c84873f38f009c2cae5f504cd0f5644ca5f743fb74e34e5cf20013723d3fad`
- Distinct from pre-existing: True

## Tests

- GUI prebuild: see CODEX_V5_GUI_PREBUILD_TEST.log
- Full prebuild exit: 0
- Postbuild exit: 0

## Static verification

PASS

## Protected hashes

See CODEX_V5_PROTECTED_HASHES_BEFORE.json and AFTER.json

## Confirmations

- EXE executed: NO
- Pre-existing EXE reused as build evidence: NO
- No operative jobs: YES

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
