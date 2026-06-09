"""V1 completion orchestration — bypass removed."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    raise RuntimeError(
        "complete_v1_run bypass removed; use authorized controller state machine via run_authorized_phase_pipeline"
    )


if __name__ == "__main__":
    main()
