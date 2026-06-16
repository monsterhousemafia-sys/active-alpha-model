# Documentation index

Logical layout for Marktanalyse / Active Alpha audit and phase documentation.

## Public mirror

| Path | Content |
|------|---------|
| [PUBLIC_ACCESS.md](PUBLIC_ACCESS.md) | Clone, ZIP, safety — **for anyone** |
| [SHARE_KIT_EN.md](SHARE_KIT_EN.md) | English copy-paste posts (Reddit, HN, X, LinkedIn) |
| [POST_CLIPBOARD.txt](POST_CLIPBOARD.txt) | Same texts, plain copy-paste |
| [SHARE_TODAY_CHECKLIST.md](SHARE_TODAY_CHECKLIST.md) | What to post today (maintainer) |
| [GITHUB_SYNC_PLAN_B.md](GITHUB_SYNC_PLAN_B.md) | Browser upload when token push fails |

## Live entry points (repository root)

| File | Purpose |
|------|---------|
| `IMPLEMENTATION_STATUS.md` | Current program state (read first) |
| `REPO_HYGIENE.md` | Cleanup rules, allowed vs forbidden edits |
| `AGENTS.md` | Agent/coding governance |
| `NEXT_CURSOR_PROMPT.md` | Next safe steps |
| `EXTERNAL_REVIEW_APPROVAL_*.md` | **Sealed review chain** (do not move — registry hashes) |
| `V5R_EXTERNAL_ACCEPTANCE_REPORT.md` | V5R acceptance evidence summary |

Resolve any legacy basename via `aa_doc_paths.doc_path("CODEX_V5R_…")`.

## `docs/review/`

| Path | Content |
|------|---------|
| `status/` | `G0_EXTERNAL_REVIEW_STATUS.md`, `G1_…`, `P9_…` |
| `sidecars/` | `*.zip.sha256` sidecars for review ZIPs |
| `templates/` | `EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md` |
| `CODEX_EXTERNAL_REVIEW_DECISION_PACKET.md` | V5R decision packet |

Review ZIP binaries stay in **repo root** (gitignored); sidecars live here.

## `docs/` — architecture & phases

| Path | Content |
|------|---------|
| `R3_EXEC_MIRROR_ARCHITECTURE.md` | R3 Exec Mirror — Schichten, T212 Operator-API, Gates, Surface-Version |
| `phases/<PHASE>/` | Historical and active **CODEX phase reports** |

Historical phase reports (preflight, report, audit):

- `P9A`, `V0`, `V0R`, `V1`, `V1R`, `V1R2`, `V1R3`, `V2`, `V2R`, `V3`, `V4`, `V4R`, `V4R2`, `V4R3`, `V5`, `V5R`, `G0`, `G1`, `G2`
- `P10`–`P18` (research → interactive desktop → UX; see `docs/phases/P16G_*`, `P17_*`, `P18_*`)

## `docs/governance/`

Cross-cutting remediation and comparison docs:

- `CONTROL_AUTHORIZATION_CONFLICT_REPORT.md`
- `G1_COMPARISON_LOGIC.md`
- `CODEX_MATRIX_REMEDIATION_DIAGNOSIS.md`
- `CODEX_RISK_OFF_CHALLENGER_EVIDENCE_REPORT.md`

## `docs/integrity/`

| Path | Content |
|------|---------|
| `protected_hashes/<phase>/` | `CODEX_*_PROTECTED_HASHES_{BEFORE,AFTER}.json` |
| `session_logs/<phase>/` | Git status snapshots, build logs, test output (regenerable) |

## `docs/archive/`

- `README.md` — why sealed docs stay referenced from root
- `evidence/archive/` (under `evidence/`) — V5R pipeline dumps (gitignored)

## `control/` (not under docs)

Authoritative **runtime gate JSON** for the Decision Cockpit — not phase reports:

- `control/evidence/*.json`
- `control/champion_lineage_policy.json`
- `control/authorization/`

## Regenerate layout manifest

```text
python tools/reorganize_documentation.py
python tools/patch_doc_path_references.py
```
