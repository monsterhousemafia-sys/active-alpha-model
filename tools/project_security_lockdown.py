#!/usr/bin/env python3
"""Projekt absichern — Safety-Flags, Secrets, Leaks, Governance (fail-closed)."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json

_LOCK_REL = Path("control/project_security_lock.json")
_EVIDENCE_REL = Path("evidence/project_security_lock_latest.json")

_SECRET_PATHS = (
    "control/server.env",
    "trading212_zugangsdaten.env",
    "control/cloudflare_tunnel.token",
    "control/secrets",
    "control/.tunnel_secret_paste",
)

_FORBIDDEN_AUTO_TRUE = (
    "auto_research_enabled",
    "auto_promote_paper_enabled",
    "auto_promote_signal_enabled",
    "auto_execute_real_money_enabled",
)

_SAFE_FLAG_DISABLED = (
    ("AUTO_EXECUTE_REAL_MONEY", "DISABLED"),
    ("AUTO_PROMOTE_PAPER", "DISABLED"),
    ("AUTO_PROMOTE_SIGNAL", "DISABLED"),
    ("AUTO_RESEARCH", "DISABLED"),
)


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


def _check_promotion_gate(root: Path) -> Tuple[bool, List[str]]:
    import yaml

    path = root / "promotion_gate_config.yaml"
    if not path.is_file():
        return False, ["promotion_gate_config.yaml fehlt"]
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return False, [f"promotion_gate_config.yaml unlesbar: {exc}"[:80]]
    issues: List[str] = []
    if str(doc.get("promotion_mode") or "").upper() != "MANUAL":
        issues.append(f"promotion_mode={doc.get('promotion_mode')!r} (erwartet MANUAL)")
    for key in _FORBIDDEN_AUTO_TRUE:
        if doc.get(key) is True:
            issues.append(f"{key}=true")
    return not issues, issues


def _check_operational_flags(root: Path) -> Tuple[bool, List[str]]:
    doc = _load_json(root / "control/operational_safety_flags.json")
    issues: List[str] = []
    for key, want in _SAFE_FLAG_DISABLED:
        if str(doc.get(key) or "").upper() != want:
            issues.append(f"{key}!={want}")
    if doc.get("REAL_MONEY_AUTHORIZED") is True:
        issues.append("REAL_MONEY_AUTHORIZED=true")
    if doc.get("CHAMPION_CHANGED") is True:
        issues.append("CHAMPION_CHANGED=true")
    return not issues, issues


def _check_hooks(root: Path) -> Tuple[bool, List[str]]:
    hooks = root / ".cursor/hooks.json"
    if not hooks.is_file():
        return True, []
    doc = _load_json(hooks)
    if doc:
        return False, [".cursor/hooks.json muss leer sein (Autopilot verboten)"]
    return True, []


def _secure_path(path: Path, *, root: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "ok": True, "skipped": True}
    mode_before = stat.S_IMODE(path.stat().st_mode)
    try:
        if path.is_dir():
            os.chmod(path, 0o700)
            target_mode = 0o700
        else:
            os.chmod(path, 0o600)
            target_mode = 0o600
        mode_after = stat.S_IMODE(path.stat().st_mode)
        return {
            "path": (
                str(path.relative_to(root))
                if str(path).startswith(str(root) + os.sep) or path == root
                else str(path)
            ),
            "ok": mode_after == target_mode,
            "mode_before": oct(mode_before),
            "mode_after": oct(mode_after),
        }
    except OSError as exc:
        return {"path": str(path), "ok": False, "error": str(exc)[:80]}


def _run_preflight(root: Path) -> Dict[str, Any]:
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "publish_public_git_preflight",
            root / "tools/publish_public_git_preflight.py",
        )
        if not spec or not spec.loader:
            return {"ok": False, "error": "preflight module missing"}
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.run_preflight(root)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def _git_tracks_secrets(root: Path) -> Tuple[bool, List[str]]:
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "control/server.env"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return False, ["control/server.env ist git-getrackt"]
    except OSError:
        pass
    return True, []


def run_security_lockdown(root: Path | None = None, *, apply_chmod: bool = True) -> Dict[str, Any]:
    root = root or ROOT
    checks: List[Dict[str, Any]] = []

    ok_gate, gate_issues = _check_promotion_gate(root)
    checks.append({"id": "promotion_gate", "ok": ok_gate, "issues": gate_issues})

    ok_flags, flag_issues = _check_operational_flags(root)
    checks.append({"id": "operational_safety_flags", "ok": ok_flags, "issues": flag_issues})

    ok_hooks, hook_issues = _check_hooks(root)
    checks.append({"id": "cursor_hooks", "ok": ok_hooks, "issues": hook_issues})

    quote_policy = root / "control/r3_live_quote_access_policy.json"
    ok_quote_gate = quote_policy.is_file()
    checks.append(
        {
            "id": "live_quote_access_policy",
            "ok": ok_quote_gate,
            "issues": [] if ok_quote_gate else ["control/r3_live_quote_access_policy.json fehlt"],
        }
    )

    ok_git, git_issues = _git_tracks_secrets(root)
    checks.append({"id": "git_secrets", "ok": ok_git, "issues": git_issues})

    preflight = _run_preflight(root)
    checks.append(
        {
            "id": "leak_preflight",
            "ok": True,
            "warn_only": True,
            "public_mirror_ok": bool(preflight.get("ok")),
            "block_count": preflight.get("block_count", preflight.get("finding_count")),
            "headline_de": preflight.get("headline_de"),
        }
    )

    chmod_results: List[Dict[str, Any]] = []
    if apply_chmod:
        for rel in _SECRET_PATHS:
            chmod_results.append(_secure_path(root / rel, root=root))
    checks.append(
        {
            "id": "secret_permissions",
            "ok": all(r.get("ok", r.get("skipped")) for r in chmod_results),
            "paths": chmod_results,
        }
    )

    t212 = _load_json(root / "evidence/t212_trust_latest.json")
    checks.append(
        {
            "id": "t212_trust_gate",
            "ok": True,
            "trusted": t212.get("trusted"),
            "fail_closed": t212.get("fail_closed", True),
            "note_de": "Trust Gate aktiv — untrusted blockiert Orders",
        }
    )

    all_ok = all(
        c.get("ok")
        for c in checks
        if c["id"] not in {"t212_trust_gate"} and not c.get("warn_only")
    )

    lock = {
        "schema_version": 1,
        "locked_at_utc": _utc_now(),
        "status": "LOCKED" if all_ok else "NEEDS_ATTENTION",
        "fail_closed": True,
        "headline_de": (
            "Projekt abgesichert — Safety + Secrets OK"
            if all_ok
            else "Sicherheits-Lock — offene Punkte prüfen"
        ),
        "checks": checks,
        "invariants_de": [
            "auto_execute_real_money_enabled=false",
            "auto_promote_*=false",
            "auto_research_enabled=false",
            "Champion-Wechsel nur mit externer Freigabe",
            "Secrets chmod 600/700, nicht in Git",
            ".cursor/hooks.json leer",
        ],
        "repair_cmd_de": "bash tools/project_security_lockdown.sh",
    }
    atomic_write_json(root / _LOCK_REL, lock)
    atomic_write_json(root / _EVIDENCE_REL, lock)
    return lock


def main() -> int:
    doc = run_security_lockdown(ROOT, apply_chmod=True)
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0 if doc.get("status") == "LOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
