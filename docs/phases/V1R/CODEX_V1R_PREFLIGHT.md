# CODEX V1R Preflight Report

UTC timestamp: 2026-05-30T20:15:00+00:00

## External SHA-256 finding

- Approval file observed hash: `403c9a5c3660db6c6ae5b7d1582f6029add22b7fd2569c7c6e81dd997bb6d283`
- Internal `CODEX_V1_REVIEW_ZIP_SHA256.txt`: `403c9a5c3660db6c6ae5b7d1582f6029add22b7fd2569c7c6e81dd997bb6d283`
- Deviation: none (hashes match; V1R replaces self-referential in-ZIP hash with sidecar mechanism)

## Git

- Version: git 2.54.0.windows.1
- Branch before V1R: `codex/v1-evidence-and-gated-cascade`
- Commits before V1R: none
- Target branch: `codex/v1r-evidence-controller-hardening`

## Hooks

- `.cursor/hooks.json`: empty — no active hooks

## Safety flags (`promotion_gate_config.yaml`)

All four automation flags: `false`

## Champion evidence sources

- `control/auto_promotion_status.json`: `R3_w075_q065_noexit`
- `control/last_known_good_state.json`: `validated_variant_id` / `variant_id` = `R3_w075_q065_noexit`

## Protected artifact hashes (before V1R)

See `CODEX_V1R_PROTECTED_HASHES_BEFORE.json`

## Operative activity

No research, replay, shadow, paper, promotion, rollback, backtest, M1, trading, EXE build or execution performed.
