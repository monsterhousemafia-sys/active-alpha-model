#!/usr/bin/env python3
"""Drive M1 to next milestone: R0 PASS, then turbo matrix R3+M1, then seal when 3/3."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "reach_milestone.json"
POLL_SEC = 120
MAX_WAIT_SEC = 7200


def _snapshot(root: Path) -> dict:
    from tools.r0_migration_sla_enforce import canonical_r0_dir
    from tools.run_validation_matrix import _is_pass_complete
    from tools.run_r0_migration_phase_m1 import build_returns_manifest

    r0 = canonical_r0_dir(root)
    m = build_returns_manifest(root)
    passed = sum(
        1
        for vid in ("R0_LEGACY_ENSEMBLE", "R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS")
        if (m.get("variants") or {}).get(vid, {}).get("integrity_pass")
    )
    return {
        "returns_pass": passed,
        "r0_pass": _is_pass_complete(r0),
        "r0_returns": (r0 / "strategy_daily_returns.csv").is_file(),
        "all_pass": bool(m.get("all_m1_variants_integrity_pass")),
    }


def reach_milestone(root: Path, *, max_wait_sec: int = MAX_WAIT_SEC) -> dict:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_sla_enforce import canonical_r0_incomplete, enforce_sla_fast_path
    from tools.run_r0_migration_phase_m1 import build_returns_manifest, launch_validation_matrix, run_m1
    from tools.run_validation_matrix import _is_pass_complete
    from tools.r0_migration_sla_enforce import canonical_r0_dir

    out: dict = {"started": time.time(), "steps": []}
    deadline = time.time() + max_wait_sec

    while time.time() < deadline:
        if is_phase_sealed(root, "M1"):
            out["verdict"] = "M1_ALREADY_SEALED"
            break

        snap = _snapshot(root)
        out["last"] = snap

        if snap.get("all_pass"):
            run_m1(apply_env_fix=False)
            seal = try_seal_phase(root, "M1")
            out["steps"].append({"seal": seal})
            out["verdict"] = "M1_SEALED" if seal.get("status") == "SEALED" else "SEAL_FAILED"
            break

        r0 = canonical_r0_dir(root)
        if canonical_r0_incomplete(root):
            sla = enforce_sla_fast_path(root)
            out["steps"].append({"phase": "R0", "sla": sla.get("verdict")})
            if _is_pass_complete(r0):
                out["steps"].append({"phase": "R0", "note": "r0_pass_complete"})
            time.sleep(POLL_SEC)
            continue

        manifest = build_returns_manifest(root)
        if not manifest.get("all_m1_variants_integrity_pass"):
            relaunch = launch_validation_matrix(
                root,
                no_warm_cache=True,
                cpu_cores=max(1, __import__("os").cpu_count() or 16),
                variants=["R3_w075_q065_noexit", "M1_MOM_BLEND_MATCHED_CONTROLS"],
            )
            out["steps"].append({"phase": "R3_M1", "relaunch": relaunch})
            time.sleep(POLL_SEC)
            continue

        time.sleep(POLL_SEC)

    else:
        out["verdict"] = "TIMEOUT"
    out["finished"] = time.time()
    atomic_write_json(REPORT, out)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--max-wait-min", type=int, default=120)
    args = p.parse_args()
    result = reach_milestone(ROOT, max_wait_sec=max(60, args.max_wait_min * 60))
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("verdict") in ("M1_SEALED", "M1_ALREADY_SEALED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
