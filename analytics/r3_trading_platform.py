"""R3 Handelsplattform — präsentiert nur Alpha-Model-Ergebnisse (Training im Hintergrund)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_trading_platform_policy.json")
_ROLES_REL = Path("control/r3_product_roles.json")
_PIPELINE_REL = Path("evidence/daily_alpha_h1_pipeline_latest.json")
_READINESS_REL = Path("control/prediction_readiness.json")
_EVIDENCE_REL = Path("evidence/r3_trading_platform_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_trading_platform_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def load_product_roles(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _ROLES_REL)


def _model_training_snapshot(root: Path) -> Dict[str, Any]:
    """Read-only: wann das Modell zuletzt ein Ergebnis geliefert hat (kein Trainings-Trigger)."""
    root = Path(root)
    pipeline = _load_json(root / _PIPELINE_REL)
    readiness = _load_json(root / _READINESS_REL)
    learning = _load_json(root / "control/learning_collection_policy.json")
    return {
        "engine_de": "Active Alpha Model",
        "schedule_de": "Täglich — Ergebnis für R3",
        "profile_used": readiness.get("profile_used"),
        "signal_date": readiness.get("signal_date"),
        "result_at_utc": readiness.get("generated_at_utc"),
        "pipeline_updated_at_utc": pipeline.get("updated_at_utc"),
        "pipeline_ok": bool(pipeline.get("ok")),
        "pipeline_phase": pipeline.get("phase"),
        "training_enabled": bool(learning.get("auto_model_training_enabled")),
        "presentation_only": True,
    }


def build_r3_trading_platform_status(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """R3-Plattform-IST: Handelsergebnis + Modell-Snapshot (nur Anzeige)."""
    root = Path(root)
    policy = load_trading_platform_policy(root)
    roles = load_product_roles(root)
    training = _model_training_snapshot(root)

    prognosis: Dict[str, Any] = {}
    try:
        from analytics.r3_t212_prognosis import build_r3_t212_daily_prognosis

        prognosis = build_r3_t212_daily_prognosis(root, persist=False)
    except Exception:
        pass

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "platform_de": "R3",
        "headline_de": str(policy.get("headline_de") or "R3 — zentrale Handelsplattform"),
        "role_de": str(policy.get("r3_role_de") or ""),
        "alpha_model_de": str(policy.get("alpha_model_role_de") or ""),
        "training_schedule_de": str(policy.get("training_schedule_de") or ""),
        "broker_de": str(policy.get("broker_de") or "Trading212"),
        "presentation_only": True,
        "model_training": training,
        "trading_result": {
            "ok": bool(prognosis.get("ok")),
            "signal_date": prognosis.get("signal_date"),
            "positions": prognosis.get("positions"),
            "investable_eur": prognosis.get("investable_eur"),
            "top_picks": prognosis.get("top_picks"),
            "summary_de": prognosis.get("summary_de"),
            "message_de": prognosis.get("message_de"),
        },
        "message_de": (
            f"R3 Handelsplattform — Ergebnis {prognosis.get('signal_date') or '—'}"
            + (f" · {int(prognosis.get('positions') or 0)} Positionen" if prognosis.get("ok") else "")
        ),
        "safety_de": str(policy.get("safety_de") or ""),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
