# CODEX V5R Final Runtime and Integrity Report

Generated: 2026-05-31T00:16:04+00:00

## FACTS
- dist/Marktanalyse.exe SHA-256: `54b617f8c480260b8f2e4abbdc6e8031f5eb5f87acd20d2d80a3e8a47fb150bc`
- EXE executed: True
- Runtime outcome: `EXPECTED_GUI_TEST_TEARDOWN`
- Git HEAD (approx): `8c2ec10ad0ad3da257d3333c4bd4b92a00a4b24e`

## TESTS EXECUTED
- tools/complete_v5r_runtime_riskoff_evidence.py orchestrator
- pytest cockpit + risk-off suites (see evidence/test_summary.txt)

## TEST RESULTS
- V5R runtime smoke: PASS
- V5R static import audit: PASS

## ARTIFACT HASHES
- codex_v5r_final_review.zip: `869efbcaf1d2207bcf2c8e83b2f8c9845cb86d2582eb39629645b934a16a4afa`
- codex_v5r_standalone_exe_review.zip: `4f310c1f0e6d45692d2140c974c7bda179f31b64ef502264c7632128c2c955c7`

## CHANGES MADE
- Legacy risk-off defaults restored in BacktestConfig
- Runtime smoke test via AA_DECISION_COCKPIT_SMOKE_TEST
- evidence/ audit artefacts and review ZIPs

## NOT VERIFIED
- External reviewer acceptance

## REMAINING BLOCKERS
- CHALLENGER_TURNOVER_NOT_VERIFIED
- COST_STRESS_GATE_NOT_PASSED
- DSR_BELOW_REQUIRED_CONFIDENCE
- ROBUSTNESS_NOT_PASSED
- P9_NOT_EXTERNALLY_REVIEWED

## GATE DECISIONS
- V5R_RUNTIME_VERIFICATION_STATUS: PASS
- V5R_INTEGRITY_STATUS: PASS

## NO-ACTIVATION CONFIRMATION
- SHADOW_MONITORING_ACTIVATED: NO
- PAPER_MONITORING_ACTIVATED: NO
- PROMOTION_EXECUTED: NO
- REAL_MONEY_EXECUTED: NO
- OPERATIVE_JOBS_EXECUTED: NO

## EXTERNAL REVIEW REQUIRED
- V5R standalone EXE acceptance
- Shadow/Paper activation approval
