"""König-Verteilung — Bash-Orchestrator als Python-Hülle."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/king_distribute_latest.json")
_BASH_REL = Path("tools/king_distribute.sh")


def run_king_distribute_bash(root: Path, *, remote_mode: str = "auto") -> Dict[str, Any]:
    root = Path(root)
    script = root / _BASH_REL
    if not script.is_file():
        return {"ok": False, "message_de": f"{_BASH_REL} fehlt"}
    env = dict(__import__("os").environ)
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["AA_REMOTE_MODE"] = str(remote_mode or "auto")
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    proc = subprocess.run(
        ["bash", str(script)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    doc: Dict[str, Any] = {
        "ok": proc.returncode == 0,
        "schema_version": 1,
        "distributed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bash": str(script.relative_to(root)).replace("\\", "/"),
        "returncode": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-2000:] if proc.stderr else None,
    }
    evidence = root / _EVIDENCE_REL
    if evidence.is_file():
        try:
            merged = json.loads(evidence.read_text(encoding="utf-8"))
            if isinstance(merged, dict):
                doc = {**merged, **doc}
        except (json.JSONDecodeError, OSError):
            pass
    atomic_write_json(evidence, doc)
    return doc
