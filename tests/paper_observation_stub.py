"""Copy or seed outgoing_cursor_observation folders for paper phase engine tests."""
from __future__ import annotations

import shutil
from pathlib import Path


def ensure_observation_dir(tmp_path: Path, repo_root: Path, obs_rel: str) -> Path:
    """Ensure tmp_path/outgoing_cursor_observation/<obs_rel> exists (copy or stub)."""
    dst = tmp_path / "outgoing_cursor_observation" / obs_rel
    src = repo_root / "outgoing_cursor_observation" / obs_rel
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        for item in src.iterdir():
            target = dst / item.name
            if item.is_file():
                shutil.copy2(item, target)
            elif item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
    else:
        stub = dst / "CURSOR_STUB_EXECUTION_REPORT.md"
        if not stub.is_file():
            stub.write_text("# Stub observation artefact (local dev)\nStatus: PASS\n", encoding="utf-8")
    return dst
