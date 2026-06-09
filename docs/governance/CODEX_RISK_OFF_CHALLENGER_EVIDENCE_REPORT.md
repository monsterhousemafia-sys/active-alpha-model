# CODEX Risk-Off Challenger Evidence Report

Generated: 2026-05-31T00:16:04+00:00

## FACTS
- Risk-off challenger parameters implemented in aa_config / aa_portfolio / aa_risk_off
- Frozen validation_runs used for comparison (reproducibility_mode=strict)
- Primary challenger: R3_w075_q065_noexit (mom_blend_blend + momentum_rescue q=0.65 w=0.75)

## TESTS EXECUTED
- tests/test_risk_off_selection.py
- tests/test_integrity.py (partial)

## TEST RESULTS
- Implementation tests: see evidence/test_summary.txt

## GATE DECISIONS
- COST_STRESS_GATE: FAIL
- DSR_CONFIDENCE_GATE: FAIL_OR_POLICY_MISSING
- ROBUSTNESS_GATE: FAIL
- CHALLENGER_TURNOVER_VERIFIED: NO

## NO-ACTIVATION CONFIRMATION
- CHAMPION_CHANGED: NO
- PROMOTION_ALLOWED: FALSE

## EXTERNAL REVIEW REQUIRED
- Challenger promotion decision blocked pending gate passes
