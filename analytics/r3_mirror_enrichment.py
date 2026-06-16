"""R3 Mirror — Daytrading-/Operator-Evidenz (vollständig, nicht im Exec-Spiegel-Payload)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_EVIDENCE_POSTMORTEM = Path("evidence/r3_daily_postmortem_latest.json")
_EVIDENCE_STACK = Path("evidence/stack_integrity_latest.json")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_mirror_enrichment(root: Path, *, refresh_scans: bool = False) -> Dict[str, Any]:
    """Pipeline-, Runtime- und Daytrading-Evidenz für den vollen Mirror (nicht /r3 lean)."""
    root = Path(root)
    out: Dict[str, Any] = {
        "runtime_profile": {},
        "runtime_upgrade": {},
        "local_growth": {},
        "local_confirm": "",
        "series_readiness": {},
        "operator_readiness": {},
        "functions_doc": {},
        "postmortem": _load_json(root / _EVIDENCE_POSTMORTEM),
    }

    functions_doc = _load_json(root / Path("evidence/r3_trading_functions_latest.json"))
    if not functions_doc.get("functions"):
        try:
            from analytics.r3_trading_functions import build_r3_trading_functions

            functions_doc = build_r3_trading_functions(root, persist=False)
        except Exception:
            functions_doc = functions_doc or {}
    out["functions_doc"] = functions_doc

    try:
        from analytics.r3_runtime_upgrade import (
            build_upgrade_status,
            load_runtime_profile,
            load_upgrade_evidence,
            scan_runtime_upgrades,
        )

        out["runtime_profile"] = load_runtime_profile(root)
        if refresh_scans:
            upgrade_doc = scan_runtime_upgrades(root, persist=True, force=True)
        else:
            upgrade_doc = load_upgrade_evidence(root)
        runtime_upgrade = build_upgrade_status(root)
        runtime_upgrade["pending"] = upgrade_doc.get("pending")
        runtime_upgrade["has_pending"] = bool(
            upgrade_doc.get("pending") and (upgrade_doc.get("pending") or {}).get("status") == "awaiting_confirmation"
        )
        out["runtime_upgrade"] = runtime_upgrade
    except Exception:
        pass

    try:
        from analytics.r3_local_growth import local_confirmation_de, scan_local_growth

        if refresh_scans:
            stack_ok = bool(_load_json(root / _EVIDENCE_STACK).get("stack_ok"))
            out["local_growth"] = scan_local_growth(root, persist=True, force=True, fast=stack_ok)
        else:
            out["local_growth"] = _load_json(root / Path("evidence/r3_local_growth_latest.json"))
        out["local_confirm"] = local_confirmation_de(root)
    except Exception:
        pass

    try:
        from analytics.series_readiness import scan_series_readiness

        if refresh_scans:
            out["series_readiness"] = scan_series_readiness(root, persist=True, force=True, fast=True)
        else:
            out["series_readiness"] = _load_json(root / Path("evidence/series_readiness_latest.json"))
    except Exception:
        pass

    try:
        from analytics.r3_operator_readiness import sync_r3_operator_readiness

        if refresh_scans:
            out["operator_readiness"] = sync_r3_operator_readiness(root, persist=True)
        else:
            operator_readiness = _load_json(root / Path("evidence/r3_operator_readiness_latest.json"))
            if not operator_readiness:
                operator_readiness = sync_r3_operator_readiness(root, persist=True)
            out["operator_readiness"] = operator_readiness
    except Exception:
        out["operator_readiness"] = _load_json(root / Path("evidence/r3_operator_readiness_latest.json"))

    postmortem = out.get("postmortem") or {}
    if not postmortem.get("as_of_date"):
        try:
            from analytics.r3_daily_postmortem import run_daily_postmortem

            out["postmortem"] = run_daily_postmortem(root, persist=True)
        except Exception:
            pass

    return out
