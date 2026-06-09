# External Review Approval — V5R

Review date: 2026-05-31

## Reviewed predecessor artefacts

- Phase: `V5_WINDOWS_EXE_BUILD_AND_VERIFICATION`
- Review ZIP: `codex_v5_exe_build_review.zip`
- Observed external SHA-256: `f4c7d1de3b91f8aff8b6f7ee95a968f21518e2c3a799a78ab380e0fb80355245`
- Review ZIP sidecar verification: PASS
- EXE artefact: `Marktanalyse.exe`
- Observed external EXE SHA-256: `44c84873f38f009c2cae5f504cd0f5644ca5f743fb74e34e5cf20013723d3fad`
- EXE sidecar verification: PASS

## Review decision

V5 is not approved for manual EXE execution or transition to terminal acceptance.

## Confirmed positive findings

- A new AMD64 PE executable was produced.
- Review ZIP and EXE sidecars match the externally observed hashes.
- Hooks remain disabled.
- Automation flags remain disabled.
- Protected before/after hash sets are identical.
- GUI and regression test evidence is present.
- Git commit `92739383048871cee44a695c2555978138a96e5e` exists.

## Critical remediation findings

1. The V5 build is PyInstaller `onedir`, not a standalone single-file EXE.
2. The built entrypoint is `tools/active_alpha_launcher.py`, which contains startup paths for backtest, ops refresh and paper routines.
3. The PyInstaller spec includes operational modules such as `aa_paper_startup`, `paper_trading_engine`, `aa_ops` and `aa_configured_backtest`.
4. The V5 review registry entry states `exe_built: false` although a new EXE was built.
5. The review ZIP omits invoked build-chain scripts required for external verification.
6. The reported final Git working tree is not clean after the V5 commit.

## Authorized execution

Execute only:

`V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR`

## Prohibited

- executing the existing V5 EXE
- executing any new EXE
- research, replay, backtest, validation-matrix, shadow or paper jobs
- promotion, rollback, trading or broker connectivity
- champion change
- automation-flag enablement
- economic-model parameter or productive signal-weight change
- scheduled or background Codex automation
