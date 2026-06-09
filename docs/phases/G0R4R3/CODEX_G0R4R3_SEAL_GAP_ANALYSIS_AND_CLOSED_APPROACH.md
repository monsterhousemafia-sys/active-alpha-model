# G0R4R3 Seal Gap Analysis — Closed Approach

Generated as part of the zero-gap sealing strategy for external review.

## Root cause: why G0R4R2 would fail external seal

Pre-submission audit (`tools/g0r4r3_seal_readiness.py`) confirmed **10 gaps** in the current G0R4R2 ZIP:

| Gap class | Finding |
|-----------|---------|
| CRLF → LF normalization | All 3 authoritative baseline files in ZIP have **LF-only** bytes; required CRLF hashes differ |
| Missing G0R4R2 approval audit | `g0r4r2_approval/*` not packaged |
| Missing G0R4R2 rejection audit | `g0r4r2_rejection/*` not packaged (only legacy `g0r4r_rejection/*`) |
| Missing G0R4R3 approval audit | `g0r4r3_approval/*` not packaged |
| Missing `.gitattributes` | Byte-preservation rules not in ZIP |

**Conclusion:** Do not submit G0R4R2. G0R4R3 is the only valid path.

## Six-layer closed approach (G0R4R3)

```text
Layer 1  Transport gate     — drop-in SHA + inner bundle SHA + extracted manifest
Layer 2  Git attribute gate — .gitattributes -text for 9 immutable paths; git check-attr before staging
Layer 3  Worktree gate      — binary copy only; CRLF hashes verified on disk before commit
Layer 4  Git blob gate      — cat-file blob SHA == source SHA (hard block before ZIP build)
Layer 5  ZIP entry gate     — zip entry bytes == git blob == source (hard block before PASS)
Layer 6  Detached attestation — only post-build report may claim final ZIP PASS
```

## Artefacts implementing the approach

| File | Role |
|------|------|
| `tools/g0r4r3_seal_readiness.py` | Pre-flight auditor; documents gaps in any candidate ZIP |
| `tools/complete_g0r4r3_submission.py` | Full orchestrator with all six layers |
| `docs/phases/G0R4R3/CODEX_G0R4R3_EXPECTED_VERBATIM_INPUTS.json` | Committed payload: **no false ZIP-PASS** |
| `codex_g0r4r3_detached_package_verification_report.md` | **Only** artefact that claims final verification |

## Resume/rebuild rule

Every resume path re-runs Layer 4 + Layer 5 before delivery. No shortcut on existing commit.

## Blocker until drop-in installed

```text
G0R4R3_CURSOR_DROP_IN_PROJECT_ROOT.zip
SHA-256: 02b1d97f845d5d666ef852bf3c4cd725bfe54efb05f73cc47663e772c3b879c7
```

After drop-in:

```text
.venv\Scripts\python.exe tools\_g0r4r3_drop_in_bootstrap.py
.venv\Scripts\python.exe tools\complete_g0r4r3_submission.py
.venv\Scripts\python.exe tools\g0r4r3_seal_readiness.py
```

Last line must report `seal_readiness_summary: PASS` before sending to external reviewer.
