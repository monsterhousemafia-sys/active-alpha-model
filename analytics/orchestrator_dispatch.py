"""Cognitive Orchestrator — pending Modell-/Evidence-Befehle zügig umsetzen."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_CONFIG_REL = Path("control/cognitive_orchestrator.json")
_EVIDENCE_REL = Path("evidence/orchestrator_dispatch_latest.json")
_CMD_RE = re.compile(r"python3\s+tools/ai_kernel\.py\s+([a-z0-9-]+)")
_COOLDOWN_MIN: Dict[str, int] = {
    "learn": 30,
    "warnings": 15,
    "h1-status": 5,
    "launch-status": 10,
    "spread-remote-status": 10,
    "lean-max": 60,
    "lean-turbo": 60,
    "lean-on": 60,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_orchestrator_config(root: Path) -> Dict[str, Any]:
    path = Path(root) / _CONFIG_REL
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            return doc if isinstance(doc, dict) else {}
        except (json.JSONDecodeError, OSError):
            pass
    return {"fast_mode": True, "dispatch_allowlist": ["learn", "warnings", "h1-status"]}


def _collect_pending_commands(root: Path, cfg: Dict[str, Any]) -> List[str]:
    pending: List[str] = []
    keys = list(cfg.get("pending_json_keys") or ["commands_pending_de"])
    for rel in cfg.get("evidence_pending_sources") or []:
        path = Path(root) / str(rel)
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for key in keys:
            val = doc.get(key)
            if isinstance(val, list):
                pending.extend(str(x) for x in val if x)
            elif isinstance(val, str) and val.strip():
                pending.append(val.strip())
    # step_b monday checklist from control
    step_b = Path(root) / "control/r3_step_b.json"
    if step_b.is_file():
        try:
            sb = json.loads(step_b.read_text(encoding="utf-8"))
            for item in sb.get("monday_checklist_de") or []:
                pending.append(str(item))
        except (json.JSONDecodeError, OSError):
            pass
    return pending


def _parse_ai_kernel_cmd(line: str) -> str | None:
    m = _CMD_RE.search(line)
    return m.group(1) if m else None


def _load_last_cmd_utc(root: Path) -> Dict[str, str]:
    path = Path(root) / _EVIDENCE_REL
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        raw = doc.get("last_cmd_utc")
        return {str(k): str(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {}


def _cooldown_active(cmd: str, last_cmd_utc: Dict[str, str]) -> str | None:
    mins = _COOLDOWN_MIN.get(cmd)
    if not mins:
        return None
    stamp = last_cmd_utc.get(cmd)
    if not stamp:
        return None
    try:
        prev = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        age_min = (datetime.now(timezone.utc) - prev).total_seconds() / 60.0
        if age_min < mins:
            return f"Cooldown {mins}min ({age_min:.0f}min seit letztem Lauf)"
    except (TypeError, ValueError):
        return None
    return None


def run_orchestrator_dispatch(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = load_orchestrator_config(root)
    allow = {str(x).strip() for x in (cfg.get("dispatch_allowlist") or []) if x}
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)

    executed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    seen_cmds: set[str] = set()
    last_cmd_utc = _load_last_cmd_utc(root)
    now = _utc_now()

    for raw in _collect_pending_commands(root, cfg):
        cmd = _parse_ai_kernel_cmd(raw)
        if not cmd:
            continue
        if cmd not in allow:
            skipped.append({"cmd": cmd, "reason_de": "nicht in dispatch_allowlist"})
            continue
        if cmd in seen_cmds:
            continue
        seen_cmds.add(cmd)
        cd = _cooldown_active(cmd, last_cmd_utc)
        if cd:
            skipped.append({"cmd": cmd, "reason_de": cd})
            continue
        # h1-status / launch-status: read-only sync
        timeout = 120 if cmd in ("learn", "warnings") else 45
        try:
            proc = subprocess.run(
                [str(py), str(root / "tools/ai_kernel.py"), cmd],
                cwd=str(root),
                env={**os.environ, "AA_PROJECT_ROOT": str(root), "AA_LINUX_NATIVE_APP": "1"},
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            ok = proc.returncode == 0
            executed.append(
                {
                    "cmd": cmd,
                    "exit_code": proc.returncode,
                    "ok": ok,
                    "stdout_tail": (proc.stdout or "")[-400:],
                }
            )
            if ok:
                last_cmd_utc[cmd] = now
        except subprocess.TimeoutExpired:
            executed.append({"cmd": cmd, "ok": False, "error_de": "timeout"})
        except OSError as exc:
            executed.append({"cmd": cmd, "ok": False, "error_de": str(exc)[:120]})

    doc = {
        "schema_version": 1,
        "ran_at_utc": _utc_now(),
        "fast_mode": bool(cfg.get("fast_mode")),
        "allowlist": sorted(allow),
        "executed": executed,
        "skipped": skipped[:20],
        "last_cmd_utc": last_cmd_utc,
        "headline_de": f"Orchestrator-Dispatch: {sum(1 for e in executed if e.get('ok'))}/{len(executed)} OK",
        "ok": True,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
