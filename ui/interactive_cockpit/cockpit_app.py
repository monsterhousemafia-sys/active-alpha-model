"""Launch interactive P16G cockpit."""
from __future__ import annotations

import sys
from pathlib import Path


def main(root: Path | None = None) -> int:
    from aa_paths import project_root
    from aa_live_trading_launch import bootstrap_live_trading_runtime, launch_live_trading_ui

    root = bootstrap_live_trading_runtime(Path(root or project_root()))
    return launch_live_trading_ui(root)


if __name__ == "__main__":
    raise SystemExit(main())
