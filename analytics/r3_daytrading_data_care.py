"""Daytrading-Datenpflege — delegiert an R3 Ops Kernel (Phase data_care)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_ops_kernel_policy.json")
_EVIDENCE_REL = Path("evidence/r3_daytrading_data_care_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_daytrading_data_care(
    root: Path,
    *,
    force: bool = True,
    persist: bool = True,
) -> Dict[str, Any]:
    """Kurse → Daytrading-Snapshot → Kreislauf → Learning (einheitliche Kernel-Phase)."""
    root = Path(root)
    from analytics.r3_ops_kernel import run_ops_pipeline

    kernel_doc = run_ops_pipeline(
        root,
        phase="data_care",
        force=force,
        persist=False,
        source="daytrading_data_care",
    )

    trust: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=False)
    except Exception:
        pass

    steps = list(kernel_doc.get("steps") or [])
    ok_n = int(kernel_doc.get("steps_ok") or 0)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok_n >= 3,
        "steps_ok": ok_n,
        "steps_total": len(steps),
        "steps": steps,
        "kernel_phase": "data_care",
        "kernel_ref": "evidence/r3_ops_latest.json",
        "t212_trusted": bool(trust.get("trusted")),
        "orders_allowed": bool(trust.get("orders_allowed")),
        "t212_message_de": str(trust.get("message_de") or "")[:160],
        "headline_de": (
            f"Daytrading-Datenpflege — {ok_n}/{len(steps)} OK"
            if ok_n >= 3
            else f"Daytrading-Datenpflege — {ok_n}/{len(steps)} (Blocker prüfen)"
        ),
        "command_de": "bash tools/king_ops.sh daytrading-refresh",
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
