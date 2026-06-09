"""Central H1 governance status — single source for gate + dashboard banner."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_STATUS_REL = Path("control/h1_governance_status.json")
_READINESS_REL = Path("control/prediction_readiness.json")


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


def estimate_h1_progress_pct(root: Path, status: Dict[str, Any]) -> int:
    st = str(status.get("status") or "MISSING")
    if st == "COMPLETE":
        return 100
    if st not in ("RUNNING", "FAILED", "ZOMBIE"):
        return 0
    rel = str(status.get("run_dir") or "")
    if not rel:
        return 5
    run = Path(root) / rel
    if (run / "strategy_daily_returns.csv").is_file():
        return 95
    ck_meta = run / "path_sim_checkpoint_meta.json"
    if ck_meta.is_file():
        meta = _load_json(ck_meta)
        last_n = int(meta.get("last_n") or 0)
        n_daily = int(meta.get("n_daily") or 0)
        if n_daily > 0 and last_n > 0:
            return min(99, int(round(100 * last_n / n_daily)))
        if last_n > 0:
            return min(94, 68 + int(27 * last_n / 1867))
    if (run / "features.parquet").is_file():
        from analytics.live_profile_governance import _h1_backtest_process_active

        if _h1_backtest_process_active(root, run):
            return 72
        return 68
    log = run / "validation_run.log"
    if log.is_file():
        size = log.stat().st_size
        if size > 80_000:
            return 45
        if size > 8_000:
            return 22
    return 10


def format_h1_banner_de(doc: Dict[str, Any]) -> str:
    st = str(doc.get("status") or "—")
    sealed = bool(doc.get("sealed"))
    pct = int(doc.get("progress_pct") or 0)
    if sealed:
        return "H1: SEALED — Order-Gate für daily_alpha_h1 freigegeben"
    if st == "RUNNING":
        return f"H1: RUNNING ~{pct}% — Gate öffnet nach Seal"
    if st == "COMPLETE":
        if doc.get("seal_required") is False:
            return str(doc.get("seal_policy_de") or "H1: COMPLETE — Seal optional")
        return "H1: COMPLETE — Evaluate/Seal läuft (h1-watch)"
    if st == "FAILED":
        return "H1: FAILED — ai_kernel h1 --restart"
    if st == "ZOMBIE":
        return "H1: ZOMBIE — ai_kernel h1 --restart"
    return f"H1: {st} — ai_kernel h1-status"


def sync_h1_governance_status(root: Path, *, write_readiness: bool = True) -> Dict[str, Any]:
    root = Path(root)
    from analytics.live_profile_governance import h1_backtest_status, h1_model_evidence, is_h1_backtest_sealed

    bt = h1_backtest_status(root)
    sealed = is_h1_backtest_sealed(root)
    h1_ev = h1_model_evidence(root)
    progress = estimate_h1_progress_pct(root, bt)
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "status": str(bt.get("status") or "MISSING"),
        "run_dir": bt.get("run_dir"),
        "sealed": sealed,
        "progress_pct": progress,
        "banner_de": "",
        "gate_blockers": [],
        "detail_de": bt.get("detail_de"),
        "pass_full_seal": h1_ev.get("pass_full_seal"),
        "operational_ok": h1_ev.get("operational_ok"),
        "metrics_strategy": h1_ev.get("metrics_strategy"),
        "evaluated_at_utc": h1_ev.get("evaluated_at_utc"),
    }
    seal_required = True
    try:
        from analytics.h1_seal_policy import is_h1_seal_required, seal_policy_banner_de

        seal_required = is_h1_seal_required(root)
        if not seal_required:
            doc["seal_required"] = False
            doc["seal_policy_de"] = seal_policy_banner_de(root)
    except Exception:
        pass
    if seal_required and not sealed and doc["status"] in ("RUNNING", "MISSING", "FAILED", "ZOMBIE"):
        doc["gate_blockers"] = ["DAILY_ALPHA_H1_NOT_SEALED"]
    elif not seal_required and doc["status"] == "COMPLETE":
        doc["gate_blockers"] = []
        doc["banner_de"] = doc.get("seal_policy_de") or "H1: COMPLETE — Seal optional"
    doc["banner_de"] = doc.get("banner_de") or format_h1_banner_de(doc)

    path = root / _STATUS_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, doc)

    try:
        from analytics.h1_migration_guard import _sync_pipeline_evidence

        phase = {
            "COMPLETE": "complete",
            "RUNNING": "running",
            "ZOMBIE": "zombie",
            "FAILED": "failed",
        }.get(str(doc.get("status") or ""), "status")
        _sync_pipeline_evidence(
            root,
            phase=phase,
            ok=str(doc.get("status")) in ("RUNNING", "COMPLETE") or sealed,
            detail_de=str(doc.get("detail_de") or doc.get("banner_de") or ""),
            status_doc=bt,
        )
    except Exception:
        pass

    if write_readiness:
        readiness = _load_json(root / _READINESS_REL)
        if readiness:
            readiness["h1_backtest_status"] = {"status": h1_ev["h1_status"], "run_dir": h1_ev.get("run_dir")}
            readiness["h1_backtest_sealed"] = sealed
            readiness["h1_operational_ok"] = h1_ev.get("operational_ok")
            readiness["h1_governance_banner_de"] = doc["banner_de"]
            readiness["h1_evaluation"] = {
                "pass_full_seal": h1_ev.get("pass_full_seal"),
                "evaluated_at_utc": h1_ev.get("evaluated_at_utc"),
                "metrics_strategy": h1_ev.get("metrics_strategy"),
                "message_de": h1_ev.get("message_de"),
                "run_dir": h1_ev.get("run_dir"),
            }
            atomic_write_json(root / _READINESS_REL, readiness)
    return doc


def load_h1_governance_status(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _STATUS_REL)
    if doc:
        return doc
    return sync_h1_governance_status(root, write_readiness=False)
