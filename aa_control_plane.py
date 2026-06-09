"""Self-progressing development pipeline — control plane sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aa_failsafe import is_failsafe_active
from aa_evidence_schema import LOCKED_CHAMPION
from aa_health_check import build_system_health_record, health_is_production_ready
from aa_p0_paths import ensure_p0_directories
from aa_recovery import build_last_known_good_snapshot, save_last_known_good
from aa_safe_io import atomic_write_json, atomic_write_text


def control_dir(root: Path) -> Path:
    return Path(root) / "control"


def pipeline_path(root: Path) -> Path:
    return Path(root) / "DEVELOPMENT_PIPELINE.yaml"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_pipeline(root: Path) -> Dict[str, Any]:
    root = Path(root)
    for name in ("DEVELOPMENT_PIPELINE.json", "DEVELOPMENT_PIPELINE.yaml"):
        path = root / name
        if not path.is_file():
            continue
        if path.suffix.lower() == ".json":
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {"pipeline_version": 0, "phases": [], "current_phase": "unknown"}


def current_phase_id(pipeline: Dict[str, Any]) -> str:
    if pipeline.get("current_phase"):
        return str(pipeline["current_phase"])
    return str(pipeline.get("current_stage", "unknown"))


def phase_by_id(pipeline: Dict[str, Any], phase_id: str) -> Dict[str, Any]:
    for phase in pipeline.get("phases") or []:
        if str(phase.get("id", "")) == phase_id:
            return dict(phase)
    stages = pipeline.get("stages") or {}
    if phase_id in stages:
        return dict(stages[phase_id])
    return {}


def append_incident(control: Path, *, event: str, details: Dict[str, Any]) -> None:
    control = Path(control)
    control.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"at_utc": _utc_now(), "event": event, **details},
        ensure_ascii=False,
        sort_keys=True,
    )
    with (control / "incident_log.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def sync_control_plane(
    root: Path,
    out_dir: Path,
    *,
    run_id: str = "",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Write control/system_health.json and update last_known_good when PASS."""
    root = Path(root)
    out_dir = Path(out_dir)
    ctrl = control_dir(root)
    ctrl.mkdir(parents=True, exist_ok=True)
    ensure_p0_directories(root)

    health = build_system_health_record(root, out_dir)
    pipeline = load_pipeline(root)
    health["pipeline_version"] = pipeline.get("pipeline_version", pipeline.get("version", 0))
    health["current_phase"] = current_phase_id(pipeline)

    atomic_write_json(ctrl / "system_health.json", health)

    if not is_failsafe_active(root) and health_is_production_ready(health):
        snapshot = build_last_known_good_snapshot(out_dir=out_dir, health=health, run_id=run_id)
        save_last_known_good(ctrl, snapshot)
    elif str(health.get("analytical_validity", "")).upper() in {"INVALID", "FAIL"}:
        append_incident(
            ctrl,
            event="analytical_integrity_degraded",
            details={
                "reason": health.get("analytical_reason", ""),
                "run_id": health.get("validated_run_id", run_id),
            },
        )

    return health, pipeline


def write_next_cursor_prompt(root: Path, pipeline: Optional[Dict[str, Any]] = None) -> Path:
    root = Path(root)
    pipeline = pipeline or load_pipeline(root)
    phase_id = current_phase_id(pipeline)
    stage = phase_by_id(pipeline, phase_id)
    title = str(stage.get("title", stage.get("goal", phase_id)))[:120]
    objective = str(stage.get("goal", stage.get("objective", "")))
    blockers = list(stage.get("blockers") or [])
    try:
        from aa_pipeline_orchestration import build_followup_prompt, load_pending

        pending = load_pending(root)
    except Exception:
        pending = {}
    lines = [
        "# Next Cursor Prompt",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"## Current phase: `{phase_id}` — {title}",
        "",
        objective or "_No objective text in pipeline._",
        "",
    ]
    if pending.get("has_work") and str(pending.get("pending_phase", "")):
        lines.extend(
            [
                "## Pending orchestration",
                "",
                f"- **Pending phase:** `{pending.get('pending_phase')}`",
                f"- **Created from:** `{pending.get('created_from_phase', '')}`",
                f"- **Status:** `{pending.get('status', 'PENDING')}`",
                f"- **Reason:** {pending.get('reason', '')}",
                "",
                "### Agent instruction",
                "",
                build_followup_prompt(pending, pipeline),
                "",
            ]
        )
    if phase_id == "P9_CONTROLLED_PAPER_SHADOW_VALIDATION_PREPARATION":
        lines.extend(
            [
                "## P9 safety constraints (mandatory)",
                "",
                f"- Do NOT change the active champion (`{LOCKED_CHAMPION}`).",
                "- Do NOT enable auto-promotion (paper/signal) or real-money order execution.",
                "- Do NOT change economic model parameters (risk-off, horizon, rebalance, exposure, beta, costs, slippage, portfolio).",
                "- Challenger validation is shadow/paper preparation only — no promotion.",
                "",
            ]
        )
    lines.extend(
        [
            "## Rules",
            "- Do not change productive signal weights or auto-promote models.",
            "- Verify IMPLEMENTATION_STATUS.md and control/system_health.json first.",
            "- Run fast unit tests before expensive validation runs.",
            "- Execute exactly one pipeline phase per agent run (`one_new_phase_per_run`).",
            "",
        ]
    )
    if blockers:
        lines.append("## Open blockers")
        lines.extend(f"- {b}" for b in blockers)
        lines.append("")
    deliverables = stage.get("deliverables") or []
    if deliverables:
        lines.append("## Deliverables")
        lines.extend(f"- {d}" for d in deliverables)
        lines.append("")
    return atomic_write_text(root / "NEXT_CURSOR_PROMPT.md", "\n".join(lines))
