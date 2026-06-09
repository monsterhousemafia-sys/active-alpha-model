"""König Bash-Orchestrator — Python-Hülle für tools/king_*.sh."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_SCRIPTS = {
    "status": ("tools/king_status.sh", []),
    "maintain": ("tools/king_maintain.sh", []),
    "h1-seal": ("tools/king_h1_seal.sh", []),
    "distribute": ("tools/king_distribute.sh", []),
    "ops": ("tools/king_ops.sh", []),
    "tune": ("tools/king_tune.sh", []),
}


def run_king_tune(root: Path, *, no_watch: bool = False) -> Dict[str, Any]:
    args = ["--no-watch"] if no_watch else []
    doc = run_king_bash(root, "tools/king_tune.sh", args, timeout_s=300.0)
    evidence = root / "evidence/king_tune_latest.json"
    if evidence.is_file():
        try:
            doc["tune"] = json.loads(evidence.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return doc


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_king_bash(
    root: Path,
    script_rel: str,
    args: Optional[List[str]] = None,
    *,
    timeout_s: float = 7200.0,
) -> Dict[str, Any]:
    root = Path(root)
    script = root / script_rel
    if not script.is_file():
        return {"ok": False, "message_de": f"{script_rel} fehlt"}
    env = dict(__import__("os").environ)
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    proc = subprocess.run(
        ["bash", str(script), *(args or [])],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=float(timeout_s),
        check=False,
    )
    return {
        "ok": proc.returncode == 0,
        "schema_version": 1,
        "ran_at_utc": _utc_now(),
        "bash": str(script.relative_to(root)).replace("\\", "/"),
        "args": list(args or []),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-6000:],
        "stderr_tail": (proc.stderr or "")[-3000:] if proc.stderr else None,
    }


def run_king_ops(root: Path, command: str, extra: Optional[List[str]] = None) -> Dict[str, Any]:
    root = Path(root)
    cmd = str(command or "help").strip() or "help"
    doc = run_king_bash(root, "tools/king_ops.sh", [cmd, *(extra or [])], timeout_s=7200.0)
    doc["command"] = cmd
    atomic_write_json(root / "evidence/king_ops_latest.json", doc)
    return doc


def run_king_status(root: Path, *, json_only: bool = False) -> Dict[str, Any]:
    args = ["--json"] if json_only else []
    doc = run_king_bash(root, "tools/king_status.sh", args, timeout_s=120.0)
    evidence = root / "evidence/king_status_latest.json"
    if evidence.is_file():
        try:
            doc["status"] = json.loads(evidence.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return doc


def run_king_maintain(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    args = ["--dry-run"] if dry_run else []
    return run_king_bash(root, "tools/king_maintain.sh", args, timeout_s=300.0)


def run_king_h1_seal(root: Path, mode: str = "run") -> Dict[str, Any]:
    arg_map = {"check": "--check-only", "wait": "--wait", "run": ""}
    flag = arg_map.get(str(mode or "run"), "")
    args = [flag] if flag else []
    return run_king_bash(root, "tools/king_h1_seal.sh", args, timeout_s=7200.0)
