#!/usr/bin/env python3
"""Headless periodic refresh for prices, universe, signal and paper MTM."""
from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

os.environ.setdefault("AA_GUI", "0")
os.environ.setdefault("AA_NO_PLOT", "1")
os.environ.setdefault("AA_NONINTERACTIVE", "1")


def main() -> int:
    from aa_config_env import resolve_launcher_env
    from aa_ops_refresh import run_ops_refresh
    from aa_paper_startup import run_paper_startup

    root = _ROOT
    env = resolve_launcher_env(root, frozen=False)
    os.environ.update(env)

    def log(msg: str) -> None:
        print(msg, flush=True)

    result = run_ops_refresh(root, env, log=log, force="--force" in sys.argv, include_signal=True)
    env.update(result.env_updates)
    os.environ.update(env)

    from aa_data_freshness import assess_daily_data
    from aa_ops import decide_run_plan, update_system_status
    from aa_preflight import run_launcher_preflight

    preflight = run_launcher_preflight(root, env, log=log)
    data_report = assess_daily_data(root, env)
    plan = decide_run_plan(root, env, data_report=data_report, preflight=preflight)
    update_system_status(
        root,
        phase="refresh",
        preflight=preflight,
        data_report=data_report,
        run_plan=plan,
        exit_code=0 if data_report.ok else 1,
        message="Scheduled refresh",
    )

    from aa_subprocess_win import prefer_pythonw

    venv_py = prefer_pythonw(root / ".venv" / "Scripts" / "python.exe")
    if venv_py.is_file():
        run_paper_startup(root, venv_py, env, log=log, inprocess=True)

    return 0 if (result.data_report is None or result.data_report.ok or result.signal_refreshed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
