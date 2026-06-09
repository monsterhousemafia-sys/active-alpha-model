# CODEX G0R4R Preflight

Generated: 2026-06-01T01:02:36+00:00
Branch: remediation/g0r4r2-verbatim-authoritative-baseline-resubmission
Start HEAD: 3d6b5f886cdf54f988a99c88cf3eca00a232ecf0

## remediation/g0r4r2-verbatim-authoritative-baseline-resubmission
 M NEXT_CURSOR_PROMPT.md
 M aa_decision_cockpit_readonly_snapshot.py
 M aa_doc_paths.py
 M control/authorization/champion_lineage_status.json
 M control/authorization/current_authorization_status.json
 M control/vision_automation/phase_catalog.json
 M control/vision_automation/review_registry/review_registry.json
?? "Daten fuer Reviewer/"
?? EXTERNAL_REVIEW_APPROVAL_G0R4R2_TEMPLATE.md
?? G0R4R2-CHANGE_MANIFEST.json
?? G0R4R2_CURSOR_DROP_IN_PROJECT_ROOT(1).zip
?? G0R4R_SUBMISSION_FOR_REVIEWER/
?? codex_g0r4_detached_package_verification_report.md
?? codex_g0r4_detached_submission_attestation.json
?? codex_g0r4r_detached_package_verification_report.md
?? codex_g0r4r_detached_submission_attestation.json
?? codex_g0r4r_verbatim_external_review_chain_resubmission.zip
?? control/external_reviews/g0r4r2_approval/
?? control/external_reviews/g0r4r_rejection/
?? control/review_snapshot/g0r4r2_decision_cockpit_snapshot.json
?? docs/integrity/protected_hashes/G0R4R2/
?? docs/phases/G0R4R2/
?? docs/review/sidecars/codex_g0r3_final_commit_bound_package_review.zip.sha256
?? docs/review/sidecars/codex_g0r4_detached_attestation_exact_byte_package_review.zip.sha256
?? docs/review/sidecars/codex_g0r4r_verbatim_external_review_chain_resubmission.zip.sha256
?? incoming_external_reviews/
?? tests/test_g0r4r2_submission_integrity.py
?? tests/test_review_submission_delivery.py
?? tools/_g0r4r2_drop_in_bootstrap.py
?? tools/_gen_g0r4r2_orchestrator.py
?? tools/complete_g0r4r2_submission.py
?? tools/review_submission_delivery.py

3d6b5f8 fix: resubmit G0R4R with verbatim external review chain
dbb4c08 fix: generate G0R4 exact-byte detached-attestation review package
cf3fb58 fix: bind G0R3 review package inputs to explicit allowlist checkpoint
ad2fcbf docs: G0R2 git status and detached review sidecar
da08c5f fix: complete G0R2 checkpoint and protected evidence submission
c5a0fd4 fix: remediate rejected G0 authorization and champion-lineage state
13c6e5c docs: document clean-tree hygiene target and refresh workflow
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
6c13890 Integrate benchmark returns loading and enhance portfolio diagnostics for unknown sectors. Update benchmark return calculations in research functions to utilize verified data, and add checks for unknown sector weights in portfolio diagnostics to ensure compliance with maximum sector limits.
bde017f Fix frozen EXE embedded snapshot resolution and complete V5R resume pipeline.
d75ece5 Add resume script and harden EXE staging/runtime orchestration for V5R remediation.
1eaca4c Add release GUI self-exit evidence hook inside submitted Marktanalyse.exe.
5af5190 Handle orphaned v5r_final directory when recreating isolated worktree.
142fed0 Fix V5R external review blockers for pytest, GUI, fail-closed runtime, and audit ZIP.
a828efe Ensure V5R build scripts add project root to sys.path in isolated venv
69a3b4c Fix pytest log capture in isolated pipeline for Windows stdout teardown
