# Next Cursor Prompt

Generated: 2026-06-09T18:48:14+00:00

## Current phase: `P16G_READONLY_REAL_ACCOUNT_CONFIGURATION_AND_MANUAL_TICKET_GENERATION` — Readonly account and ticket generation.

Readonly account and ticket generation.

## Rules
- Do not change productive signal weights or auto-promote models.
- Verify IMPLEMENTATION_STATUS.md and control/system_health.json first.
- Run fast unit tests before expensive validation runs.
- Execute exactly one pipeline phase per agent run (`one_new_phase_per_run`).
