# CODEX V5 Orchestrator Audit

Generated: 2026-05-30 (recovery preflight)

## Scope

Static audit of `tools/complete_v5_run.py` and all subprocess targets for resumed V5 build.

## `tools/complete_v5_run.py` — commands invoked

| Step | Command / callee | Purpose |
|------|------------------|---------|
| Preflight | `audit_helper_scripts` | Bypass audit |
| Preflight | `verify_v4r3_baseline.main` | ZIP vs git checkpoint |
| Preflight | `register_external_approval` | **NOT permitted on resume** |
| Preflight | `begin_authorized_phase` | **NOT permitted on resume** |
| Tests | `python -m pytest` (21 test modules) | Pre/post build |
| Build | `tools/build_v5_exe.main` | PyInstaller pipeline |
| Verify | `tools/static_verify_marktanalyse_exe.main` | Static EXE check |
| Complete | `record_phase_test_pass`, `complete_authorized_phase` | State machine |
| Package | `tools/build_v5_review_zip.main` | Review ZIP |
| Git | `git add`, `git commit` | V5 commit |

## Build scripts invoked (`tools/build_v5_exe.py`)

| Command | EXE launch? |
|---------|-------------|
| `pip install pyinstaller PySide6` | NO |
| `python tools/generate_r3_icon.py` | NO |
| `python -m PyInstaller ... Marktanalyse.spec` | NO (build only) |
| `python tools/post_build_marktanalyse.py` | NO |
| `python tools/smoke_test_launcher.py` | NO — file/bundle checks only |

## Verifier scripts

| Script | Invoked by V5? | Executes EXE? |
|--------|----------------|-------------|
| `tools/static_verify_marktanalyse_exe.py` | YES | NO |
| `tools/smoke_test_launcher.py` | YES (post-build) | NO |
| `tools/verify_exe_integration.py` | **NO** | YES (`run_exe_once`, `Popen`) |

## `tools/verify_exe_integration.py` (excluded)

- Contains `run_exe_once()` launching `Marktanalyse.exe` via `subprocess.Popen`
- Not called by V5 resume path

## `build_active_alpha_launcher.bat` (not used by resume)

- Uses PyInstaller + post_build + smoke_test; `taskkill` only, no EXE start

## Resume path: `tools/resume_v5_run.py`

- Validates `RUNNING_AUTHORIZED_PHASE` without re-register/re-begin
- Does **not** call `register_external_approval` or `begin_authorized_phase`
- Does **not** call `verify_exe_integration.py`
- Requires new EXE hash ≠ pre-existing baseline
- Completes only after build + static verify + tests

## Audit verdict

| Check | Result |
|-------|--------|
| EXE_EXECUTION_PATH_FOUND | **NO** (in resume path and build_v5_exe chain) |
| OPERATIVE_JOB_PATH_FOUND | **NO** |
| Pre-existing EXE treated as new output | **NO** (hash/timestamp check in resume) |
| GUI tests skippable without fail | **NO** (exit 99 → BLOCKED) |
| Complete before build possible | **NO** (resume orders build before complete) |
| SAFE_TO_RESUME_V5_BUILD | **YES** via `tools/resume_v5_run.py` |
| `complete_v5_run.py` safe to run as-is | **NO** — re-registers V5; use resume script only |
