"""Shadow monitor status (V3 foundation — blocked, read-only)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_forward_monitor_schema import base_monitoring_fields
from aa_monitoring_readiness import _collect_evidence_blockers
from aa_safe_io import atomic_write_json

STATUS_PATH = Path("control") / "evidence" / "shadow_monitor_status.json"

SHADOW_BLOCKERS = (
    "SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED",
    "P9_NOT_EXTERNALLY_REVIEWED",
    "CHALLENGER_TURNOVER_NOT_VERIFIED",
    "DSR_BELOW_REQUIRED_CONFIDENCE",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_shadow_monitor_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    blockers = sorted(set(_collect_evidence_blockers(root)) | set(SHADOW_BLOCKERS))
    payload = base_monitoring_fields(observation_type="SHADOW_OBSERVATION")
    payload.update(
        {
            "generated_at_utc": _utc_now(),
            "activation_status": "BLOCKED",
            "shadow_collection_started": False,
            "active_blockers": blockers,
            "display_messages": [
                "Shadow observation is not activated; V3S external approval required.",
                "No prediction, outcome or order artifacts are created in V3.",
            ],
        }
    )
    return payload


def export_shadow_monitor_status(root: Path) -> Path:
    root = Path(root)
    path = root / STATUS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_shadow_monitor_status(root))
    return path
