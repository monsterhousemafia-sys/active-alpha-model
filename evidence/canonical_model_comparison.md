# Canonical Model Comparison (Phase C)

Generated: 2026-06-05T17:44:36+00:00
Authoritative champion: `R0_LEGACY_ENSEMBLE`
Alignment mode: **INTERSECTION_RECOMPUTED**

## Headline

- Matrix embedded Sharpe leader: **R2_MOM_BLEND_REPLACE** (champion rank: None)
- Aligned intersection Sharpe leader (MOM/research CSVs): **MOM_63_TOP12**
- **Warning:** Do not compare matrix-embedded Sharpe to intersection-aligned MOM Sharpe directly.
- Aligned calendar: {"status": "OK", "n_aligned": 1859, "start_date": "2019-01-03 00:00:00", "end_date": "2026-05-28 00:00:00", "variants_included": ["R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS", "R0_LEGACY_ENSEMBLE", "MOM_63_TOP12", "MOM_63_TOP12_STRICT", "MOM_63_TOP15_RECONSTRUCTED"], "raw_n_days": {"R3_w075_q065_noexit": 1860, "M1_MOM_BLEND_MATCHED_CONTROLS": 1860, "R0_LEGACY_ENSEMBLE": 1860, "MOM_63_TOP12": 1860, "MOM_63_TOP12_STRICT": 1859, "MOM_63_TOP15_RECONSTRUCTED": 1860}, "calendar_delta_days": {"R3_w075_q065_noexit": 1, "M1_MOM_BLEND_MATCHED_CONTROLS": 1, "R0_LEGACY_ENSEMBLE": 1, "MOM_63_TOP12": 1, "MOM_63_TOP12_STRICT": 0, "MOM_63_TOP15_RECONSTRUCTED": 1}, "calendar_warning": false}

## Rankings — matrix embedded (1860d governance frame)

1. `R2_MOM_BLEND_REPLACE` (SIBLING_MATRIX) — Sharpe 0.9734
2. `R3_w070_q070_noexit` (SIBLING_MATRIX) — Sharpe 0.9119
3. `R4_w070_q070_forceexit` (SIBLING_MATRIX) — Sharpe 0.9055
4. `R1_GATE_BASE_ONLY` (SIBLING_MATRIX) — Sharpe 0.8501

## Rankings — aligned intersection (return CSV overlap)

1. `MOM_63_TOP12` (RESEARCH_CANDIDATE) — Sharpe 1.0311
2. `MOM_63_TOP12_STRICT` (RESEARCH_CANDIDATE) — Sharpe 0.9983
3. `MOM_63_TOP15_RECONSTRUCTED` (RESEARCH_CANDIDATE) — Sharpe 0.9938
4. `R0_LEGACY_ENSEMBLE` (SIBLING_MATRIX) — Sharpe 0.8946 [CHAMPION]
5. `M1_MOM_BLEND_MATCHED_CONTROLS` (M1_CONTROL) — Sharpe 0.8904
6. `R3_w075_q065_noexit` (CHAMPION) — Sharpe 0.8621

## Cost stress gate

- Status: PASS pass=True

## Quarantined (excluded from main rankings)

- `R5_rank_only_train5`: Excluded from main rankings; unauthorized operational champion claim.
