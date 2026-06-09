"""Launch-Readiness — alle Setup-Schritte bündeln."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/launch_readiness_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _py(root: Path) -> Path:
    p = root / ".venv/bin/python3"
    return p if p.is_file() else Path(sys.executable)


def _run_kernel(
    root: Path, cmd: str, *, timeout: int = 300, env: Dict[str, str] | None = None
) -> Dict[str, Any]:
    root = Path(root)
    proc = subprocess.run(
        [str(_py(root)), str(root / "tools/ai_kernel.py"), cmd],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        env=env,
    )
    doc: Dict[str, Any] = {"cmd": cmd, "rc": proc.returncode}
    raw = (proc.stdout or "").strip()
    if raw:
        try:
            doc["result"] = json.loads(raw)
        except json.JSONDecodeError:
            doc["stdout_tail"] = raw[-1500:]
    if proc.stderr:
        doc["stderr_tail"] = (proc.stderr or "")[-500:]
    return doc


def _restart_hub(root: Path) -> Dict[str, Any]:
    root = Path(root)
    proc = subprocess.run(
        [str(_py(root)), str(root / "tools/preview_hub.py"), "--ensure", "--restart"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
        check=False,
    )
    return {"cmd": "hub-restart", "rc": proc.returncode}


def run_launch_setup(root: Path) -> Dict[str, Any]:
    """Alle automatisierbaren Launch-Schritte ausführen."""
    root = Path(root)
    steps: List[Dict[str, Any]] = []
    remaining: List[str] = []

    try:
        steps.append(_restart_hub(root))
    except subprocess.TimeoutExpired:
        steps.append({"cmd": "hub-restart", "rc": -1, "error_de": "Timeout"})

    for cmd, timeout in (
        ("server-bootstrap", 180),
        ("spread-prelaunch", 120),
        ("spread-remote", 90),
        ("spread-secure", 60),
        ("spread-timers", 30),
        ("spread-tick", 120),
        ("h1-watch", 60),
        ("legion", 30),
    ):
        try:
            steps.append(_run_kernel(root, cmd, timeout=timeout))
        except subprocess.TimeoutExpired:
            steps.append({"cmd": cmd, "rc": -1, "error_de": "Timeout"})

    import os

    tunnel_env = os.environ.copy()
    tunnel_env["AA_TUNNEL_LOGIN_WAIT_S"] = "10"
    try:
        steps.append(
            _run_kernel(root, "spread-tunnel-secure", timeout=25, env=tunnel_env)
        )
    except subprocess.TimeoutExpired:
        steps.append({"cmd": "spread-tunnel-secure", "rc": -1, "error_de": "Timeout"})

    plan = _run_kernel(root, "spread-plan", timeout=90)
    steps.append(plan)
    status = (plan.get("result") or {}).get("status") or {}
    h1 = _run_kernel(root, "h1-status", timeout=30)
    steps.append(h1)

    public_ready = bool(status.get("public_launch_ready"))
    blockers = list(status.get("blockers_de") or [])
    remote = {}
    for s in steps:
        if s.get("cmd") == "server-bootstrap":
            remote = (s.get("result") or {}).get("health", {}).get("status") or {}
            break

    if not remote.get("tunnel_token_set"):
        remaining.append(
            "Tunnel-Token: ai_kernel spread-tunnel-secure (Browser-Login — Passwort nur im Browser, nie im Chat)"
        )
    if any("h1_sealed" in b for b in blockers):
        remaining.append("H1 sealed abwarten — ai_kernel h1-watch (läuft per Timer)")

    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(public_ready) or (len(blockers) == 1 and "h1_sealed" in str(blockers[0])),
        "public_launch_ready": public_ready,
        "blockers_de": blockers,
        "remaining_de": remaining,
        "remote": {
            "public_base_url": remote.get("public_base_url"),
            "remote_ready": remote.get("remote_ready"),
            "stable": remote.get("stable"),
            "tunnel_token_set": remote.get("tunnel_token_set"),
        },
        "h1": (h1.get("result") or {}).get("governance") or {},
        "steps": [{"cmd": s.get("cmd"), "rc": s.get("rc")} for s in steps],
        "headline_de": (
            "Launch bereit — nur noch H1 sealed, dann öffentlich posten"
            if len(remaining) == 1 and "H1" in remaining[0]
            else (
                "Launch-Setup abgeschlossen — siehe remaining_de"
                if remaining
                else "Launch freigegeben — spread-tick + Forum-Post"
            )
        ),
    }
    if not remote.get("tunnel_token_set"):
        try:
            from analytics.vault_auto_open import enrich_with_vault_portal

            doc = enrich_with_vault_portal(doc, root, context="launch_setup", always_try=True)
        except Exception:
            pass

    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
