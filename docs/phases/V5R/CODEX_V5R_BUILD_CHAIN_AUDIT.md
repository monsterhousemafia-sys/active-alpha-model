# CODEX V5R Build Chain Audit

Generated: 20260530T225731Z

ENTRYPOINT = tools/decision_cockpit_readonly_launcher.py
DISTRIBUTION_TYPE = ONEFILE_STANDALONE
OPERATIVE_IMPORT_PATH_FOUND = NO
OPERATIVE_JOB_EXECUTION_PATH_FOUND = NO
EXE_EXECUTION_PATH_FOUND = NO
REQUIRES_COMPANION_INTERNAL_FOLDER = NO
SAFE_TO_BUILD = YES

## Invoked build scripts

- tools/build_v5r_standalone_exe.py — PyInstaller onefile, writes snapshot, no EXE launch
- tools/static_verify_v5r_standalone_exe.py — static PE/string scan only

## Excluded

- tools/verify_exe_integration.py — launches EXE
- tools/smoke_test_launcher.py — onedir bundle checks only
- tools/active_alpha_launcher.py — operative entrypoint (not used)
