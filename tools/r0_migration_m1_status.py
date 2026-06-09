#!/usr/bin/env python3
"""One-screen M1 progress (no governance noise)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VARIANTS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)


def main() -> int:
    from aa_runtime_profile import is_batch_work_active

    root = ROOT
    lines: list[str] = []
    done = 0
    for v in VARIANTS:
        hits = sorted(
            root.glob(f"validation_runs/*{v}*/strategy_daily_returns.csv"),
            key=lambda p: -p.stat().st_mtime,
        )
        if hits:
            done += 1
            lines.append(f"  [OK] {v}")
        else:
            from tools.r0_migration_runtime import newest_run_dir_for_variant

            d = newest_run_dir_for_variant(root, v)
            if d:
                log = d / "validation_run.log"
                turbo = d / "validation_run_path_turbo.log"
                if turbo.is_file() and (
                    not log.is_file() or turbo.stat().st_mtime >= log.stat().st_mtime
                ):
                    log = turbo
                idle = (
                    round((time.time() - log.stat().st_mtime) / 60, 1)
                    if log.is_file()
                    else None
                )
                log_tag = "path_turbo" if log.name == "validation_run_path_turbo.log" else "run"
                lines.append(f"  [..] {v}  run={d.name}  {log_tag}_idle_min={idle}")
            else:
                lines.append(f"  [ ] {v}  not started")

    lock = root / ".active_alpha_batch.lock"
    lines.insert(0, f"M1 returns: {done}/3")
    lines.append(f"batch_active: {is_batch_work_active(root)}")
    if lock.is_file():
        lines.append(f"lock: {lock.read_text(encoding='utf-8').strip()}")

    if done == 3:
        from tools.r0_migration_m1_control import M1_FINISH

        lines.append(f"next: {M1_FINISH}")
    elif is_batch_work_active(root):
        from tools.r0_migration_m1_control import M1_STATUS

        lines.append(f"next: wait (PC on) — or {M1_STATUS}")
    else:
        from tools.r0_migration_sla_enforce import canonical_r0_incomplete

        if canonical_r0_incomplete(ROOT):
            lines.append("next: progress_guard active — do not start duplicate matrix")
        else:
            from tools.r0_migration_m1_control import M1_ENTRY

            lines.append(f"next: {M1_ENTRY}")

    text = "\n".join(lines)
    print(text)
    out = root / "evidence" / "r0_migration" / "m1_status_latest.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return 0 if done == 3 else 1


if __name__ == "__main__":
    raise SystemExit(main())
