"""P6 behavioral feature research — disabled challenger infrastructure only."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from aa_behavioral_features import FEATURE_GROUPS, build_feature_table, finalize_session_features, is_session_complete
from aa_challenger_eval import resolve_champion_variant
from aa_market_data import ReplayMarketDataProvider, default_replay_root, ensure_sample_replay_data
from aa_realtime_replay import replay_status_summary
from aa_safe_io import atomic_write_json

STATUS_FILE = "behavioral_research_status.json"
FEATURES_FILE = "behavioral_features.parquet"
REPORT_TXT = "behavioral_research_report.txt"

BEHAVIORAL_CHALLENGERS: Dict[str, Dict[str, Any]] = {
    "B0_DAILY_REFERENCE": {
        "feature_groups": [],
        "description": "Validated champion daily reference without behavioral overlay.",
    },
    "B1_REALTIME_EXECUTION_ONLY": {
        "feature_groups": [],
        "description": "Execution-timing scaffold; no alpha overlay in P6.",
    },
    "B2_ATTENTION_CONTINUATION": {
        "feature_groups": ["attention", "continuation"],
        "description": "Attention + continuation intraday features (research only).",
    },
    "B3_LIQUIDITY_STRESS": {
        "feature_groups": ["liquidity_stress"],
        "description": "Liquidity stress intraday features (research only).",
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def status_path(root: Path) -> Path:
    return Path(root) / "control" / STATUS_FILE


def out_status_path(out_dir: Path) -> Path:
    return Path(out_dir) / STATUS_FILE


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _atomic_write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        frame.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
    return path


def _research_entry_metrics(out_dir: Path, variant_id: str) -> Dict[str, Any]:
    research = _read_json(out_dir / "background_research_status.json")
    for entry in research.get("entries") or []:
        if str(entry.get("variant_id")) == variant_id:
            return dict(entry.get("metrics") or {})
    return {}


def _build_challenger_results(
    feature_frame: pd.DataFrame,
    *,
    champion_id: str,
    champion_metrics: Dict[str, Any],
    m1_metrics: Dict[str, Any],
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    feature_summary = {}
    if not feature_frame.empty:
        numeric = feature_frame.select_dtypes(include="number")
        feature_summary = {col: float(numeric[col].mean()) for col in numeric.columns if col in numeric}

    for variant_id, spec in BEHAVIORAL_CHALLENGERS.items():
        groups = list(spec.get("feature_groups") or [])
        status = "RESEARCH_ONLY"
        note = str(spec.get("description", ""))
        if variant_id == "B0_DAILY_REFERENCE":
            comparison = {
                "baseline": champion_id,
                "champion_sharpe": champion_metrics.get("sharpe_0rf"),
                "note": "Daily champion reference — no behavioral overlay.",
            }
        elif variant_id == "B1_REALTIME_EXECUTION_ONLY":
            comparison = {
                "baseline": champion_id,
                "note": "Execution scaffold only; features not applied to alpha.",
            }
        else:
            comparison = {
                "baseline": champion_id,
                "m1_control_variant": "M1_MOM_BLEND_MATCHED_CONTROLS",
                "champion_sharpe": champion_metrics.get("sharpe_0rf"),
                "m1_sharpe": m1_metrics.get("sharpe_0rf"),
                "feature_means": {k: feature_summary.get(k) for k in feature_summary if k in (
                    "relative_volume", "volume_shock", "close_vs_vwap",
                    "relative_intraday_return_vs_spy", "spread_bps", "intraday_realized_volatility",
                )},
                "note": "Research-only overlay; not promoted.",
            }
        results.append(
            {
                "variant_id": variant_id,
                "status": status,
                "production_active": False,
                "enabled": False,
                "feature_groups": groups,
                "comparison": comparison,
                "note": note,
            }
        )
    return results


def update_behavioral_challenger_registry(root: Path, results: List[Dict[str, Any]]) -> None:
    path = Path(root) / "challenger_registry.json"
    reg = _read_json(path)
    existing = {str(c.get("id")): c for c in reg.get("challengers") or []}
    merged: List[Dict[str, Any]] = []
    seen = set()
    for entry in reg.get("challengers") or []:
        vid = str(entry.get("id", ""))
        if vid.startswith("B") and vid in BEHAVIORAL_CHALLENGERS:
            continue
        merged.append(entry)
        seen.add(vid)
    for item in results:
        vid = str(item.get("variant_id"))
        merged.append(
            {
                "id": vid,
                "role": "behavioral_research",
                "status": "research_ready",
                "enabled": False,
                "promoted": False,
                "production_active": False,
                "feature_groups": list(item.get("feature_groups") or []),
                "integrity_pass": True,
            }
        )
        seen.add(vid)
    for vid in BEHAVIORAL_CHALLENGERS:
        if vid not in seen:
            merged.append(
                {
                    "id": vid,
                    "role": "behavioral_research",
                    "status": "planned",
                    "enabled": False,
                    "promoted": False,
                    "production_active": False,
                }
            )
    reg["challengers"] = merged
    reg["updated_at_utc"] = _utc_now()
    reg["auto_promotion"] = "DISABLED"
    atomic_write_json(path, reg)


def format_behavioral_research_report(status: Dict[str, Any]) -> str:
    lines = [
        "Behavioral Feature Research (P6)",
        f"Updated: {status.get('updated_at_utc', '')}",
        f"Research status: {status.get('behavioral_research_status', 'NOT_STARTED')}",
        f"Production active: {status.get('production_active', False)}",
        f"Data quality: {status.get('data_quality_status', 'NOT_VALIDATED')}",
        f"Champion: {status.get('champion_variant_id', '—')} (unchanged)",
        "",
        f"Feature groups available: {', '.join(status.get('feature_groups_available') or [])}",
        "",
        "Behavioral challengers (research only):",
    ]
    for entry in status.get("challenger_results") or []:
        groups = ", ".join(entry.get("feature_groups") or []) or "—"
        lines.append(f"  {entry.get('variant_id')}: {entry.get('status')} groups=[{groups}]")
    lines.extend(
        [
            "",
            "Signal rule: intraday features finalize after session close; earliest use next trading day.",
            "Auto-promotion: DISABLED",
        ]
    )
    return "\n".join(lines) + "\n"


def write_behavioral_research_artifacts(
    root: Path,
    out_dir: Path,
    status: Dict[str, Any],
    feature_frame: Optional[pd.DataFrame] = None,
) -> None:
    root = Path(root)
    out_dir = Path(out_dir)
    ctrl = root / "control"
    ctrl.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_status_path(out_dir), status)
    atomic_write_json(status_path(root), status)
    report = format_behavioral_research_report(status)
    (ctrl / REPORT_TXT).write_text(report, encoding="utf-8")
    (out_dir / REPORT_TXT).write_text(report, encoding="utf-8")
    if feature_frame is not None and not feature_frame.empty:
        _atomic_write_parquet(out_dir / FEATURES_FILE, feature_frame)
        feat_dir = root / "market_data" / "features"
        feat_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_parquet(feat_dir / FEATURES_FILE, feature_frame)


def behavioral_status_summary(out_dir: Path, root: Optional[Path] = None) -> Dict[str, Any]:
    root = root or Path(out_dir).parent
    for candidate in (out_status_path(out_dir), status_path(root)):
        data = _read_json(candidate)
        if data:
            challengers = [c.get("variant_id") for c in data.get("challenger_results") or []]
            return {
                "behavioral_research_status": str(data.get("behavioral_research_status", "NOT_STARTED")),
                "behavioral_production_active": bool(data.get("production_active", False)),
                "behavioral_feature_groups": list(data.get("feature_groups_available") or []),
                "behavioral_challengers": challengers,
                "behavioral_data_quality_status": str(data.get("data_quality_status", "NOT_VALIDATED")),
                "behavioral_updated_at_utc": str(data.get("updated_at_utc", "") or ""),
            }
    return {
        "behavioral_research_status": "NOT_STARTED",
        "behavioral_production_active": False,
        "behavioral_feature_groups": [],
        "behavioral_challengers": [],
        "behavioral_data_quality_status": "NOT_VALIDATED",
        "behavioral_updated_at_utc": "",
    }


def run_behavioral_research_sync(
    root: Path,
    out_dir: Path,
    *,
    tickers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compute behavioral features and research status without changing champion."""
    root = Path(root)
    out_dir = Path(out_dir)
    champion_before = resolve_champion_variant(out_dir)
    pointer_before = _read_json(out_dir / "latest_validated_run.json")

    replay_summary = replay_status_summary(out_dir, root)
    quality_status = str(replay_summary.get("intraday_data_quality_status", "NOT_VALIDATED"))
    if quality_status != "PASS":
        status = {
            "updated_at_utc": _utc_now(),
            "behavioral_research_status": "BLOCKED",
            "production_active": False,
            "data_quality_status": quality_status,
            "feature_groups_available": [],
            "champion_variant_id": champion_before,
            "champion_unchanged": True,
            "challenger_results": [],
            "errors": ["intraday data quality not PASS — behavioral features blocked"],
        }
        write_behavioral_research_artifacts(root, out_dir, status)
        return {
            "status": "QUALITY_BLOCKED",
            "behavioral_research_status": "BLOCKED",
            "data_quality_status": quality_status,
            "champion_unchanged": True,
        }

    ensure_sample_replay_data(root)
    provider = ReplayMarketDataProvider(default_replay_root(root))
    tickers = list(tickers or ["SPY", "AAPL"])
    feature_frame, feat_errors = build_feature_table(provider, tickers)
    if feature_frame.empty:
        status = {
            "updated_at_utc": _utc_now(),
            "behavioral_research_status": "BLOCKED",
            "production_active": False,
            "data_quality_status": quality_status,
            "feature_groups_available": [],
            "champion_variant_id": champion_before,
            "champion_unchanged": True,
            "challenger_results": [],
            "errors": feat_errors or ["no feature rows produced"],
        }
        write_behavioral_research_artifacts(root, out_dir, status)
        return {
            "status": "DATA_BLOCKED",
            "behavioral_research_status": "BLOCKED",
            "data_quality_status": quality_status,
            "champion_unchanged": True,
        }

    champion_metrics = _research_entry_metrics(out_dir, champion_before)
    m1_metrics = _research_entry_metrics(out_dir, "M1_MOM_BLEND_MATCHED_CONTROLS")
    challenger_results = _build_challenger_results(
        feature_frame,
        champion_id=champion_before,
        champion_metrics=champion_metrics,
        m1_metrics=m1_metrics,
    )
    update_behavioral_challenger_registry(root, challenger_results)

    status = {
        "updated_at_utc": _utc_now(),
        "behavioral_research_status": "PASS",
        "production_active": False,
        "data_quality_status": quality_status,
        "feature_groups_available": list(FEATURE_GROUPS.keys()),
        "champion_variant_id": champion_before,
        "champion_unchanged": True,
        "m1_control_variant_id": "M1_MOM_BLEND_MATCHED_CONTROLS",
        "signal_earliest_use_rule": "next_trading_day_after_session_close",
        "challenger_results": challenger_results,
        "feature_row_count": int(len(feature_frame)),
        "session_dates": sorted(feature_frame["session_date"].astype(str).unique().tolist()),
        "errors": feat_errors,
    }
    write_behavioral_research_artifacts(root, out_dir, status, feature_frame)

    champion_after = resolve_champion_variant(out_dir)
    pointer_after = _read_json(out_dir / "latest_validated_run.json")
    unchanged = champion_before == champion_after and pointer_before == pointer_after
    return {
        "status": "OK",
        "behavioral_research_status": "PASS",
        "data_quality_status": quality_status,
        "feature_row_count": len(feature_frame),
        "champion_unchanged": unchanged,
        "production_active": False,
    }


def run_eod_behavioral_finalize(root: Path, out_dir: Path) -> Dict[str, Any]:
    """EOD hook: finalize session features when replay data and quality allow."""
    return run_behavioral_research_sync(root, out_dir)
