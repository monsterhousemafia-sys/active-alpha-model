"""R3 Exec Mirror — öffentliche API.

Architektur: docs/R3_EXEC_MIRROR_ARCHITECTURE.md

Schichten:
  1. State   analytics.r3_mirror_state   — Evidence → dict
  2. View    analytics.r3_mirror_view    — dict → HTML
  3. Hub     GET /r3, GET /api/r3/mirror — preview_hub (HTTP, hub_runtime)
  4. Operator analytics.r3_t212_operator_api — T212-Zugangsdaten, Gates (Domain SSoT)
  5. Bond    analytics.r3_t212_api_bond  — Live-Sync, Bond-Lock
  Qt-Cockpit lädt Hub-URL — stack_integrity / r3_cockpit_lock
"""
from __future__ import annotations

from analytics.r3_mirror_state import (
    EVIDENCE_BATCH,
    EVIDENCE_BOND,
    EVIDENCE_ORDERS,
    EVIDENCE_PLAN,
    EVIDENCE_PREP,
    EVIDENCE_REEVAL,
    EVIDENCE_SNAP,
    build_exec_mirror_state,
    display_headline,
    resolve_submission_mode,
)
from analytics.r3_mirror_view import (
    MIRROR_POLL_MS,
    MIRROR_PREP_EVERY_N_POLLS,
    build_mirror_panel_payload,
    format_stand_de,
    render_mirror_body_html,
    render_r3_exec_mirror_page,
    render_results_panel,
)

__all__ = [
    "build_exec_mirror_state",
    "render_results_panel",
    "render_mirror_body_html",
    "build_mirror_panel_payload",
    "render_r3_exec_mirror_page",
    "format_stand_de",
    "display_headline",
    "resolve_submission_mode",
    "EVIDENCE_ORDERS",
    "EVIDENCE_PLAN",
    "EVIDENCE_BATCH",
    "EVIDENCE_BOND",
    "EVIDENCE_PREP",
    "EVIDENCE_REEVAL",
    "EVIDENCE_SNAP",
    "MIRROR_POLL_MS",
    "MIRROR_PREP_EVERY_N_POLLS",
]
