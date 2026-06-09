"""One-shot seed: write sector_reference.csv from aa_constants.SECTOR_MAP (PIT baseline)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_constants import SECTOR_MAP
from aa_sector_reference import resolve_reference_path, update_sector_reference_from_records


def main() -> int:
    p = argparse.ArgumentParser(description="Seed sector_reference.csv from SECTOR_MAP.")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--valid-from", default="2012-01-01")
    args = p.parse_args()
    root = args.root.resolve()
    path = resolve_reference_path(root)
    records = [
        {
            "ticker": tk,
            "sector_coarse": sec,
            "sector_gics": sec,
            "source": "legacy_map_seed",
        }
        for tk, sec in sorted(SECTOR_MAP.items())
    ]
    result = update_sector_reference_from_records(
        records,
        path,
        valid_from=args.valid_from,
        source_detail="legacy_map_seed",
        root=root,
    )
    print(f"[OK] Seeded {result['row_count']} rows -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
