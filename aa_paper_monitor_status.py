"""Paper monitor status (V3 foundation — blocked, read-only)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_forward_monitor_schema import base_monitoring_fields
from aa_monitoring_readiness import _collect_evidence_blockers
from aa_safe_io import atomic_write_json

STATUS_PATH = Path("control") / "evidence" / "paper_monitor_status.json"

PAPER_BLOCKERS = (
    "PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED",
    "SHADOW_EVIDENCE_NOT_EXTERNALLY_REVIEWED",
    "COST_STRESS_GATE_NOT_PASSED",
    "DSR_BELOW_REQUIRED_CONFIDENCE",
    "P9_NOT_EXTERNALLY_REVIEWED",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_paper_monitor_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    blockers = sorted(set(_collect_evidence_blockers(root)) | set(PAPER_BLOCKERS))
    payload = base_monitoring_fields(observation_type="PAPER_SIMULATION")
    payload.update(
        {
            "generated_at_utc": _utc_now(),
            "activation_status": "BLOCKED",
            "paper_simulation_started": False,
            "paper_eligible": False,
            "active_blockers": blockers,
            "display_messages": [
                "Paper simulation is not activated; V3P external approval required.",
                "No order, fill, broker or portfolio artifacts are created in V3.",
            ],
        }
    )
    return payload


def export_paper_monitor_status(root: Path) -> Path:
    root = Path(root)
    path = root / STATUS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_paper_monitor_status(root))
    return path
