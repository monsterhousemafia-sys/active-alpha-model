"""Snapshot freshness stamp — avoid duplicate T212/quote refresh."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_STAMP_REL = Path("evidence/snapshot_stamp.json")
_DEFAULT_MAX_AGE_S = 120


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_stamp(root: Path) -> Dict[str, Any]:
    path = Path(root) / _STAMP_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def mark_snapshot_fresh(root: Path, *, source: str = "unknown") -> Dict[str, Any]:
    root = Path(root)
    doc = {
        "schema_version": 1,
        "at_utc": _utc_now(),
        "source": str(source)[:80],
    }
    path = root / _STAMP_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def snapshot_age_seconds(root: Path) -> Optional[float]:
    stamp = _load_stamp(root)
    at = stamp.get("at_utc")
    if not at:
        return None
    try:
        ts = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except (TypeError, ValueError):
        return None


def is_snapshot_fresh(root: Path, *, max_age_s: int = _DEFAULT_MAX_AGE_S) -> bool:
    age = snapshot_age_seconds(root)
    return age is not None and age < float(max_age_s)


def is_dashboard_process_running() -> bool:
    patterns = (
        "run_marktanalyse_linux",
        "aa_pilot_launch",
        "live_trading_dashboard",
        "Marktanalyse",
    )
    try:
        proc = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=3)
        blob = proc.stdout or ""
        return any(p in blob for p in patterns)
    except Exception:
        return False


def should_skip_headless_refresh(
    root: Path,
    *,
    mode: str,
    force: bool = False,
    max_age_s: int = _DEFAULT_MAX_AGE_S,
) -> Tuple[bool, str]:
    """Return (skip, reason_de). Boot/orchestrator/pre-us/us-open may bypass."""
    if force:
        return False, ""
    mode = str(mode or "snapshot").lower()
    if mode in ("boot", "orchestrator", "full", "pre-us", "us-open", "daily-mark"):
        return False, ""
    if is_snapshot_fresh(root, max_age_s=max_age_s):
        if is_dashboard_process_running():
            return True, "Snapshot frisch (<2 min) und Dashboard aktiv"
        return True, f"Snapshot frisch (<{max_age_s}s)"
    return False, ""
