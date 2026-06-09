# CODEX V0R Preflight (final — successful run)

**UTC timestamp:** 2026-05-30T19:13:31+00:00

## Champion

`R3_w075_q065_noexit` — unchanged

## Automation flags (before V0R changes)

| Flag | Before | After V0R |
|------|--------|-----------|
| `auto_research_enabled` | `true` | **`false`** |
| `auto_promote_paper_enabled` | `false` | `false` |
| `auto_promote_signal_enabled` | `false` | `false` |
| `auto_execute_real_money_enabled` | `false` | `false` |

## Hooks

- Before: active autopilot + allow_all
- After: empty `hooks.json`; archive in `hooks.disabled.json`

## P9

`PREEXISTING_UNREVIEWED_PASS` — not re-executed in V0R

## Artifact hashes (unchanged through V0R)

| File | SHA-256 |
|------|---------|
| `latest_validated_run.json` | `e5a821da3cae03952cc0bbbad9c43d9f813fa60fb48d58d60fe6947314a9a58d` |
| `last_known_good_state.json` | `f67b37eba2807702f1ffbada01e0f6153046d66a23136e0dc307f01fa4ff9bcc` |

## Stale status deviation (resolved)

Prior `auto_promotion_status.json` had `all_required_gates_pass: true` — refreshed to `false` with `cost_stress_not_passed`.

## Confirmation

No EXE, backtest, M1, research, shadow, paper, promotion, or trading jobs executed.
