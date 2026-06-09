"""V1R2 completion orchestration — bypass removed."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    raise RuntimeError(
        "complete_v1r2_run bypass removed; use tools/complete_v1r3_run.py authorized pipeline"
    )


if __name__ == "__main__":
    main()
