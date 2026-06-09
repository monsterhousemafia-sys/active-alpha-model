"""Evidence-Verzeichnis beobachten — Zustandsänderungen für Agent/Timer."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

from aa_safe_io import atomic_write_json

_WATCH_REL = Path("evidence/runtime_watch_latest.json")
_KEY_FILES = (
    "launch_readiness_latest.json",
    "launch_progress_latest.json",
    "daily_alpha_h1_pipeline_latest.json",
    "daily_alpha_h1_evaluation_latest.json",
    "remote_hub_tunnel.json",
    "preview_hub.json",
    "gui_preview_latest.json",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    files: Dict[str, Any] = {}
    for name in _KEY_FILES:
        path = root / "evidence" / name
        if path.is_file():
            files[name] = {
                "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat(),
                "size": path.stat().st_size,
            }
    ck_dirs = sorted((root / "validation_runs").glob("*_DAILY_ALPHA_H1"), reverse=True)[:3]
    for run in ck_dirs:
        ck = run / "path_sim_checkpoint_meta.json"
        if ck.is_file():
            try:
                meta = json.loads(ck.read_text(encoding="utf-8"))
                files[f"checkpoint/{run.name}"] = meta
            except (json.JSONDecodeError, OSError):
                pass
    return {"files": files, "snapshotted_at_utc": _utc_now()}


def run_evidence_watch_once(root: Path) -> Dict[str, Any]:
    """Ein Durchlauf — diff gegen letzte Snapshots, Events schreiben."""
    root = Path(root)
    prev_path = root / _WATCH_REL
    prev: Dict[str, Any] = {}
    if prev_path.is_file():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}

    cur = _snapshot(root)
    prev_files = (prev.get("snapshot") or {}).get("files") or {}
    cur_files = cur.get("files") or {}
    events: List[Dict[str, Any]] = []

    all_names: Set[str] = set(prev_files) | set(cur_files)
    for name in sorted(all_names):
        before = prev_files.get(name)
        after = cur_files.get(name)
        if before == after:
            continue
        events.append(
            {
                "path": name,
                "before": before,
                "after": after,
                "at_utc": _utc_now(),
            }
        )

    try:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

        h1 = h1_backtest_status(root)
        sealed = is_h1_backtest_sealed(root)
    except Exception:
        h1, sealed = {}, False

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "events": events[-40:],
        "event_count": len(events),
        "snapshot": cur,
        "h1": h1,
        "h1_sealed": sealed,
    }
    atomic_write_json(prev_path, doc)

    if events:
        try:
            from analytics.runtime_structured_log import emit_runtime_log

            emit_runtime_log(
                "evidence-watch",
                "state_change",
                root=root,
                persist=True,
                changes=len(events),
                h1_status=h1.get("status"),
            )
        except Exception:
            pass
    return doc


def run_evidence_watch_loop(root: Path, *, interval_s: float = 30.0, max_cycles: int = 0) -> None:
    root = Path(root)
    cycles = 0
    while True:
        run_evidence_watch_once(root)
        cycles += 1
        if max_cycles and cycles >= max_cycles:
            break
        time.sleep(max(5.0, interval_s))
