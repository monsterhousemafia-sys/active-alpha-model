# External Review Approval — V5

Review date: 2026-05-31

## Reviewed predecessor artifact

- Predecessor phase: `V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE`
- Artifact: `codex_v4r3_final_build_gate_review.zip`
- Observed external SHA-256: `ea345927f370bd8cf0807b77addd7a2413025af8cf89ebb32e3b3b828b070999`
- Sidecar verification: PASS

## Review decision

V4R3 is approved for transition to `V5_WINDOWS_EXE_BUILD_AND_VERIFICATION`, subject to all mandatory V5 preflight checks.

## Confirmed positive findings

- ZIP and sidecar integrity passed.
- The reviewed GUI validates the Cursor hook schema fail-closed.
- The reviewed GUI dynamically reads controller state.
- The reviewed GUI validates the experiment panel fail-closed.
- The reviewed GUI keeps Evidence Stage at `BACKTESTED`.
- Monitoring remains blocked.
- Automation flags remain disabled.
- Protected before/after hash sets supplied in V4R3 are complete and unchanged.
- V5 was not previously started.

## Mandatory V5 preflight requirements

1. Establish a Git checkpoint for the exact externally reviewed V4R3 file state before any V5 code or build change.
2. Confirm that the local files to be committed match the externally reviewed V4R3 ZIP for all V4R3-reviewed source, test, controller and protected artefacts.
3. Extend or verify the read-only GUI so it safely represents the V5 build lifecycle and the post-build state `AWAITING_EXTERNAL_REVIEW`.
4. Run mandatory PySide6/offscreen GUI smoke tests in the V5 build environment before accepting the build.
5. Inspect build and verification scripts before execution; no script may launch the EXE or trigger operative jobs.

## Authorized execution

Execute only:

`V5_WINDOWS_EXE_BUILD_AND_VERIFICATION`

## Authorized V5 actions

- Seal the V4R3 review through the approved controller path.
- Inspect and, only if necessary, minimally update read-only GUI/build integration required for a correct V5 artefact.
- Run targeted unit and offscreen GUI smoke tests.
- Build one new Windows EXE.
- Perform static verification of the built EXE without launching it.
- Create hashes, build logs, reports and review artefacts.

## Prohibited

- Executing `Marktanalyse.exe` or any generated EXE
- V3S or V3P activation
- research, replay, market-data collection, shadow collection or paper simulation
- promotion, rollback, trading or broker connectivity
- champion change
- automation-flag enablement
- economic-model parameter or productive signal-weight changes
- scheduled or background Codex automation
