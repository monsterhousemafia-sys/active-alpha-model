"""System update — read-only calibration + operational refinement chain."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/system_update_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_system_update(
    root: Path,
    env: Optional[Mapping[str, str]] = None,
    *,
    force_prices: bool = False,
    refresh_signal: bool = True,
    persist: bool = True,
    log_print: bool = False,
) -> Dict[str, Any]:
    """
    Update operational artifacts: governance, refinement, postmortem, Stufe B, self-calibration.
    No champion change, no auto-execute, no backtest research jobs.
    """
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    messages: List[str] = []

    # 1 — H1 governance + prediction_readiness sync
    try:
        from analytics.h1_governance_status import sync_h1_governance_status

        h1 = sync_h1_governance_status(root, write_readiness=True)
        steps.append({"step": "h1_governance", "ok": True, "status": h1.get("status")})
        messages.append(f"[OK] H1-Governance: {h1.get('status')}")
    except Exception as exc:
        steps.append({"step": "h1_governance", "ok": False, "error": str(exc)[:120]})
        messages.append(f"[WARN] H1-Governance: {exc}")

    # 2 — Operational refinement (prices, signal, cockpit)
    refinement_ok = False
    try:
        from aa_config_env import load_aa_env
        from aa_operational_refinement import load_refinement_config, run_operational_refinement

        if env is None:
            env = load_aa_env(root)
        cfg = load_refinement_config(root)
        if force_prices:
            cfg["force_prices"] = True
        cfg["refresh_signal"] = bool(refresh_signal)
        cfg["run_background_research"] = False
        report = run_operational_refinement(root, env, cfg=cfg, log_print=False)
        refinement_ok = bool(report.ok)
        steps.append(
            {
                "step": "operational_refinement",
                "ok": refinement_ok,
                "r3_regime_match": report.r3_regime_match,
                "signal_refreshed": report.signal_refreshed,
            }
        )
        messages.extend(report.messages[:8])
    except Exception as exc:
        steps.append({"step": "operational_refinement", "ok": False, "error": str(exc)[:120]})
        messages.append(f"[FAIL] Operational refinement: {exc}")

    # 3 — Daily postmortem
    try:
        from analytics.r3_daily_postmortem import run_daily_postmortem

        post = run_daily_postmortem(root, persist=True)
        steps.append({"step": "daily_postmortem", "ok": bool(post.get("ok")), "headline_de": post.get("headline_de")})
    except Exception as exc:
        steps.append({"step": "daily_postmortem", "ok": False, "error": str(exc)[:80]})

    # 4 — Stufe B (idempotent if refinement already ran crosscheck)
    try:
        from analytics.king_stufe_b import run_stufe_b_tick

        stufe_b = run_stufe_b_tick(root, force=True, persist=True)
        steps.append(
            {
                "step": "stufe_b",
                "ok": bool(stufe_b.get("ok") or stufe_b.get("verdict") == "warn"),
                "verdict": stufe_b.get("verdict"),
            }
        )
        messages.extend(list(stufe_b.get("messages_de") or [])[:2])
    except Exception as exc:
        steps.append({"step": "stufe_b", "ok": False, "error": str(exc)[:80]})

    # 5 — Self-calibration evidence
    try:
        from analytics.prediction_self_calibration import run_prediction_self_calibration

        cal = run_prediction_self_calibration(root, persist=True)
        steps.append({"step": "self_calibration", "ok": bool(cal.get("ok")), "headline_de": cal.get("headline_de")})
        messages.append(str(cal.get("headline_de") or "Selbstkalibrierung OK"))
        messages.append(str(cal.get("honesty_de") or ""))
    except Exception as exc:
        steps.append({"step": "self_calibration", "ok": False, "error": str(exc)[:80]})

    failed = [s for s in steps if s.get("ok") is False]
    ok = not failed and (refinement_ok or any(s.get("ok") for s in steps))

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": "System-Update — Governance, Refinement, Stufe B, Selbstkalibrierung",
        "ok": ok,
        "steps": steps,
        "messages_de": [m for m in messages if m],
        "evidence_refs": [
            "evidence/system_update_latest.json",
            "evidence/prediction_self_calibration_latest.json",
            "evidence/price_crosscheck_latest.json",
            "control/prediction_readiness.json",
        ],
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)

    if log_print:
        for line in doc["messages_de"]:
            print(line)
        import json

        print(json.dumps({"ok": ok, "steps": steps}, indent=2, ensure_ascii=False))

    return doc
