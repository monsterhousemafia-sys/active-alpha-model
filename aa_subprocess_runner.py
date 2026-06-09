"""Non-interactive subprocess helpers for research/tuning batch runners."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping, Optional

CompleteFn = Callable[[Path], bool]


def noninteractive_env(extra: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    env = dict(os.environ)
    env["AA_GUI"] = "0"
    env["AA_NONINTERACTIVE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    if extra:
        env.update(dict(extra))
    return env


def terminate_proc_tree(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


def run_logged_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    out_dir: Path,
    log_path: Optional[Path] = None,
    is_complete: Optional[CompleteFn] = None,
    grace_seconds: int = 45,
    env: Optional[Mapping[str, str]] = None,
) -> int:
    """Run a command with live log streaming and optional hang recovery."""
    out_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_path or (out_dir / "run.log")
    log_path.write_text("", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=noninteractive_env(env),
        bufsize=1,
    )
    assert proc.stdout is not None
    complete = is_complete or (lambda _p: False)
    with proc.stdout:
        for line in proc.stdout:
            with log_path.open("a", encoding="utf-8", errors="ignore") as fh:
                fh.write(line)
            if complete(out_dir):
                try:
                    rc = proc.wait(timeout=grace_seconds)
                    return 0 if complete(out_dir) else int(rc)
                except subprocess.TimeoutExpired:
                    terminate_proc_tree(proc)
                    return 0 if complete(out_dir) else 1
    rc = int(proc.wait())
    if rc != 0 and complete(out_dir):
        return 0
    return rc
