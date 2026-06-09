# CODEX G0R3 Preflight

Generated: 2026-05-31T22:04:30+00:00
Branch: remediation/g0r3-final-commit-bound-package
Start HEAD: ad2fcbf4702ef03979ff23df875b6c9e1b077486
Authoritative champion: R3_w075_q065_noexit

## git status --short --branch
## remediation/g0r3-final-commit-bound-package
 M NEXT_CURSOR_PROMPT.md
 M aa_decision_cockpit_readonly_snapshot.py
 M aa_doc_paths.py
 M control/authorization/champion_lineage_status.json
 M control/authorization/current_authorization_status.json
 M control/vision_automation/phase_catalog.json
 M control/vision_automation/review_registry/review_registry.json
?? EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md
?? G0R3-CHANGE_MANIFEST.json
?? control/external_reviews/g0r2_rejection/
?? control/review_snapshot/g0r3_decision_cockpit_snapshot.json
?? docs/integrity/protected_hashes/G0R3/
?? docs/phases/G0R3/
?? tests/test_g0r3_submission_integrity.py
?? tools/complete_g0r3_submission.py

## git log -n 25
ad2fcbf (HEAD -> remediation/g0r3-final-commit-bound-package, remediation/g0r2-clean-checkpoint-evidence-completeness) docs: G0R2 git status and detached review sidecar
da08c5f fix: complete G0R2 checkpoint and protected evidence submission
c5a0fd4 (remediation/g0r-authorization-champion-lineage) fix: remediate rejected G0 authorization and champion-lineage state
13c6e5c (remediation/authorization-source-conflict) docs: document clean-tree hygiene target and refresh workflow
2ad7f0d docs: add V1R3 protected hash baseline snapshot
6e5b3e0 feat: add experimental runtime modules and tooling (non-operative defaults)
a3e4383 refactor: paths, dashboard, and pipeline tooling hardening
fe50143 docs: record R5 operational pointers and refreshed monitoring exports
d5fcd60 feat: V5R evidence manifest, embed snapshots, and verification tools
0e1e9ed docs: G0/G1 governance submission artefacts and authorization policy
719ee85 docs: seal V5R external acceptance and review sidecar hashes
c803920 chore: extend gitignore for operative noise and hygiene refresh tool
189e3cd fix: reconcile champion lineage and governance evidence drift
6840f4a chore: add repo hygiene layout and ignore regenerable evidence
bebce35 Integrate benchmark returns loading and enhance portfolio diagnostics.
b5004d3 docs: prepare G1 submission, G2 preregistration, and matrix diagnosis
d22b733 refactor: consolidate cockpit authorization layer and shared fixtures
d68f7bd fix: complete G0 auth tests, registry hash gate, snapshot remediation
8bae9be fix: block conflicting operational authorization claims fail closed
6c13890 (codex/v5r_runtime_and_riskoff_evidence_repair) Integrate benchmark returns loading and enhance portfolio diagnostics for unknown sectors. Update benchmark return calculations in research functions to utilize verified data, and add checks for unknown sector weights in portfolio diagnostics to ensure compliance with maximum sector limits.
bde017f Fix frozen EXE embedded snapshot resolution and complete V5R resume pipeline.
d75ece5 Add resume script and harden EXE staging/runtime orchestration for V5R remediation.
1eaca4c Add release GUI self-exit evidence hook inside submitted Marktanalyse.exe.
5af5190 Handle orphaned v5r_final directory when recreating isolated worktree.
142fed0 Fix V5R external review blockers for pytest, GUI, fail-closed runtime, and audit ZIP.

## git diff --stat
NEXT_CURSOR_PROMPT.md                              |  6 +--
 aa_decision_cockpit_readonly_snapshot.py           | 29 +++++++++++++++
 aa_doc_paths.py                                    |  9 +++++
 control/authorization/champion_lineage_status.json |  2 +-
 .../current_authorization_status.json              |  2 +-
 control/vision_automation/phase_catalog.json       | 43 ++++++++++++++++++++++
 .../review_registry/review_registry.json           | 22 +++++++++++
 7 files changed, 108 insertions(+), 5 deletions(-)

## git ls-files --others --exclude-standard
EXTERNAL_REVIEW_APPROVAL_G0R3_TEMPLATE.md
G0R3-CHANGE_MANIFEST.json
control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_DECISION_G0R2_REMEDIATION_REQUIRED.md
control/external_reviews/g0r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R2.sha256
control/review_snapshot/g0r3_decision_cockpit_snapshot.json
docs/integrity/protected_hashes/G0R3/CODEX_G0R3_PROTECTED_HASHES_AFTER.json
docs/integrity/protected_hashes/G0R3/CODEX_G0R3_PROTECTED_HASHES_BEFORE.json
docs/phases/G0R3/CODEX_G0R3_EXTERNAL_REJECTION_REMEDIATION_REPORT.md
docs/phases/G0R3/CODEX_G0R3_PACKAGE_INPUT_MANIFEST.json
docs/phases/G0R3/CODEX_G0R3_PREFLIGHT.md
docs/phases/G0R3/CODEX_G0R3_V5R_BASELINE_COMPARISON.json
tests/test_g0r3_submission_integrity.py
tools/complete_g0r3_submission.py
