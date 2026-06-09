# G1 Comparison Logic — Champion, M1, Challenger

Generated: 2026-06-07T20:14:02+00:00

## Variants under identical calendar policy

| Role | Variant ID | Returns artefact | Turnover artefact | Gate eligible |
|------|------------|------------------|-------------------|---------------|
| CHAMPION | `R0_LEGACY_ENSEMBLE` | NO | YES | YES |
| M1_CONTROL | `M1_MOM_BLEND_MATCHED_CONTROLS` | NO | NO | YES |
| CHALLENGER | `MOM_63_TOP12` | NO | NO | NO |

## Cost model (must match across variants)

- Fee model: `trading212_us+fx_0bps+slippage_2bps`
- Baseline costs embedded in return series where documented
- Incremental stress applies extra bps on **variant-specific** rebalance turnover only
- Champion reference: `R0_LEGACY_ENSEMBLE`
- M1 control: `M1_MOM_BLEND_MATCHED_CONTROLS`
- Challenger: `MOM_63_TOP12`

## Comparison rules (read-only preparation)

1. Align daily return calendars; require ≥200 overlapping observations.
2. Cost-stress uses verified turnover per variant; **no champion turnover proxy for challenger gates**.
3. DSR / multiple-testing uses preregistered trial ledger (G2); no post-hoc threshold changes.
4. Robustness subperiod screen is informational; ROBUSTNESS_EVIDENCE gate remains separate.

## Current blockers

- `CHALLENGER_TURNOVER_NOT_VERIFIED`
- `CHALLENGER_RETURNS_MISSING`
- `G1_NOT_EXTERNALLY_APPROVED`

## Explicitly not authorized in G1 preparation

- Shadow / Paper / Promotion / Champion change / Real money
- New backtests without registered G1 approval

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
