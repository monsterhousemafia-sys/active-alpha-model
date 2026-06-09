#!/usr/bin/env python3
"""Remove failed/duplicate M1 validation_runs dirs that confuse status and waste disk."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

M1_VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)
RUN_DIR_RE = re.compile(
    r"^(\d{8}T\d{6}Z)_(R0_LEGACY_ENSEMBLE|R3_w075_q065_noexit|M1_MOM_BLEND_MATCHED_CONTROLS)$"
)
REPORT = ROOT / "evidence" / "r0_migration" / "prune_validation_junk.json"
MIN_INTEGRITY_DAYS = 1800


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical_r0_stamp(root: Path) -> str | None:
    sla = root / "control" / "r0_migration" / "m1_sla_6h.json"
    if not sla.is_file():
        return None
    try:
        data = json.loads(sla.read_text(encoding="utf-8"))
    except Exception:
        return None
    stamp = str(data.get("canonical_r0_stamp") or "").strip()
    return stamp or None


def _dir_size_bytes(path: Path) -> int:
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                continue
    return total


def _returns_pass(run_dir: Path) -> bool:
    ret = run_dir / "strategy_daily_returns.csv"
    if not ret.is_file():
        return False
    try:
        import pandas as pd

        df = pd.read_csv(ret, index_col=0, parse_dates=True)
        return int(len(df)) >= MIN_INTEGRITY_DAYS
    except Exception:
        return False


def plan_prune(root: Path) -> Dict[str, Any]:
    vr = root / "validation_runs"
    keep: Set[str] = set()
    remove: List[Dict[str, Any]] = []
    canon = _canonical_r0_stamp(root)
    if canon:
        keep.add(f"{canon}_R0_LEGACY_ENSEMBLE")

    if not vr.is_dir():
        return {
            "at_utc": _utc_now(),
            "canonical_r0_stamp": canon,
            "keep": sorted(keep),
            "remove": [],
            "bytes_freed": 0,
        }

    for d in sorted(vr.iterdir()):
        if not d.is_dir():
            continue
        m = RUN_DIR_RE.match(d.name)
        if not m:
            continue
        if d.name in keep or _returns_pass(d):
            keep.add(d.name)
            continue
        remove.append(
            {
                "dir": d.name,
                "bytes": _dir_size_bytes(d),
            }
        )

    return {
        "at_utc": _utc_now(),
        "canonical_r0_stamp": canon,
        "keep": sorted(keep),
        "remove": remove,
        "bytes_freed": sum(r["bytes"] for r in remove),
    }


def prune_validation_junk(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json

    plan = plan_prune(root)
    deleted: List[str] = []
    errors: List[Dict[str, str]] = []
    vr = root / "validation_runs"

    for entry in plan["remove"]:
        name = entry["dir"]
        path = vr / name
        if not path.is_dir():
            continue
        if dry_run:
            deleted.append(name)
            continue
        try:
            shutil.rmtree(path)
            deleted.append(name)
        except OSError as exc:
            errors.append({"dir": name, "error": str(exc)})

    out = {
        **plan,
        "dry_run": dry_run,
        "deleted": deleted,
        "errors": errors,
    }
    if not dry_run:
        atomic_write_json(REPORT, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = prune_validation_junk(ROOT, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
