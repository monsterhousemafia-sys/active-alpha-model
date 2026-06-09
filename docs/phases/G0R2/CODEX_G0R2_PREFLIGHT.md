# CODEX G0R2 Preflight

Generated: 2026-05-31T21:34:43+00:00
Branch: remediation/g0r2-clean-checkpoint-evidence-completeness
Start HEAD: c5a0fd45c366faf61f2337e02f39b92d12813040
Authoritative champion: R3_w075_q065_noexit

## git status --short --branch
## remediation/g0r2-clean-checkpoint-evidence-completeness
 M aa_decision_cockpit_readonly_snapshot.py
 M aa_doc_paths.py
 M control/authorization/champion_lineage_status.json
 M control/authorization/current_authorization_status.json
 M control/review_snapshot/v5r_decision_cockpit_snapshot.json
 M control/vision_automation/phase_catalog.json
 M control/vision_automation/review_registry/review_registry.json
?? EXTERNAL_REVIEW_APPROVAL_G0R2_TEMPLATE.md
?? G0R2-BACKUP_MANIFEST.json
?? control/external_reviews/g0r_rejection/
?? control/review_snapshot/g0r2_decision_cockpit_snapshot.json
?? docs/integrity/protected_hashes/G0R2/
?? docs/phases/G0R2/
?? tests/test_g0r2_remediation.py
?? tools/complete_g0r2_remediation.py

## git log -n 20
c5a0fd4 (HEAD -> remediation/g0r2-clean-checkpoint-evidence-completeness, remediation/g0r-authorization-champion-lineage) fix: remediate rejected G0 authorization and champion-lineage state
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

## git diff --stat
aa_decision_cockpit_readonly_snapshot.py           | 42 ++++++++++++++++++++++
 aa_doc_paths.py                                    |  8 +++++
 control/authorization/champion_lineage_status.json |  2 +-
 .../current_authorization_status.json              |  2 +-
 .../v5r_decision_cockpit_snapshot.json             | 25 ++++++-------
 control/vision_automation/phase_catalog.json       | 39 ++++++++++++++++++++
 .../review_registry/review_registry.json           | 21 +++++++++++
 7 files changed, 125 insertions(+), 14 deletions(-)
