#!/usr/bin/env python3
"""One-shot recovery: dedupe processes, prune junk, restart canonical R0 path-only turbo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "evidence" / "r0_migration" / "recover_canonical_r0.json"


def recover(root: Path) -> dict:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_killer_pack import apply_killer_pack
    from tools.r0_migration_prune_validation_junk import prune_validation_junk
    from tools.r0_migration_sla_enforce import enforce_sla_fast_path

    out = {
        "prune": prune_validation_junk(root),
        "sla_enforce": enforce_sla_fast_path(root),
        "killer_pack": apply_killer_pack(root),
    }
    atomic_write_json(REPORT, out)
    return out


def main() -> int:
    result = recover(ROOT)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
