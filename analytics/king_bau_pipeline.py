"""König-Bau-Pipeline — Plan, Evidence, pytest-Liste (Bash ruft auf)."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/king_bau_pipeline.json")
_EVIDENCE_REL = Path("evidence/king_bau_latest.json")
_MANDATE_REL = Path("evidence/r3_local_build_mandate_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_bau_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL) or {"enabled": True}


def resolve_bau_route(root: Path, topic: str) -> str:
    policy = load_bau_policy(root)
    routes = dict(policy.get("topic_routes") or {})
    key = str(topic or "").strip().lower()
    return str(routes.get(key) or routes.get("") or "r3-bau")


def pytest_targets_from_mandate(root: Path) -> List[str]:
    root = Path(root)
    mandate = _load_json(root / _MANDATE_REL)
    text = str(mandate.get("mandate_de") or "")
    found: List[str] = []
    for m in re.finditer(r"pytest\s+([^\n]+)", text):
        chunk = m.group(1).strip()
        for part in chunk.split():
            if part.startswith("tests/") and part.endswith(".py"):
                found.append(part)
    if found:
        return found
    policy = load_bau_policy(root)
    return list(policy.get("safe_pytest_de") or [])


def run_safe_pytest(root: Path, *, targets: Optional[List[str]] = None) -> Dict[str, Any]:
    root = Path(root)
    paths = list(targets or pytest_targets_from_mandate(root))
    if not paths:
        return {"ok": True, "skipped": True, "message_de": "Keine pytest-Ziele"}
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path("python3")
    cmd = [str(py), "-m", "pytest", *paths, "-q", "--tb=no"]
    try:
        proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=600, check=False)
        tail = (proc.stdout or proc.stderr or "")[-400:]
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "targets": paths,
            "tail_de": tail,
            "message_de": "pytest PASS" if proc.returncode == 0 else f"pytest FAIL ({proc.returncode})",
        }
    except Exception as exc:
        return {"ok": False, "message_de": str(exc)[:200], "targets": paths}


def build_bau_plan(root: Path, *, topic: str = "", prep_stufe_a: bool = False) -> Dict[str, Any]:
    root = Path(root)
    policy = load_bau_policy(root)
    route = resolve_bau_route(root, topic)
    steps = [
        {"id": "verify", "cmd_de": "bash tools/king_ops.sh verify"},
        {"id": "llm_health", "cmd_de": "python3 tools/ai_kernel.py llm-health"},
    ]
    if prep_stufe_a:
        steps.append({"id": "stufe_a", "cmd_de": "bash tools/king_ops.sh stufe-a --force"})
    steps.append({"id": "build", "route": route, "cmd_de": f"bash tools/king_ops.sh {route}"})
    steps.extend(
        [
            {"id": "r3_sync", "cmd_de": "bash tools/r3_sync.sh --repair"},
            {"id": "verify_post", "cmd_de": "bash tools/king_ops.sh verify"},
            {"id": "pytest", "cmd_de": "king_bau_pipeline.run_safe_pytest"},
            {"id": "network", "cmd_de": "bash tools/king_ops.sh network"},
        ]
    )
    return {
        "schema_version": 1,
        "planned_at_utc": _utc_now(),
        "topic": topic,
        "route": route,
        "prep_stufe_a": prep_stufe_a,
        "steps_planned": steps,
        "pytest_targets": pytest_targets_from_mandate(root),
        "headline_de": f"Bau-Plan — {route}" + (" + Stufe A" if prep_stufe_a else ""),
    }


def write_bau_evidence(root: Path, doc: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    out = {**doc, "updated_at_utc": _utc_now()}
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out
