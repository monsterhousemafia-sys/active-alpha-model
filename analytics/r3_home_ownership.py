"""Post-Login — ~/.local-Besitz nach Cursor-Root-Sandbox korrigieren."""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from analytics.r3_desktop_icon import home_dir_owner


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def r3_home_ownership_targets() -> List[Path]:
    home = Path.home()
    return [
        home / ".local/share/icons/hicolor",
        home / ".local/share/applications/R3.desktop",
        home / ".config/autostart/r3-os-session.desktop",
        home / ".config/autostart/xdg-user-session.desktop",
        home / ".config/systemd/user/xdg-user-session.service",
        home / ".local/bin/r3",
        home / ".config/systemd/user/active-alpha-preview-hub.service",
        home / ".config/systemd/user/aa-hub.slice",
    ]


def _path_owner_uid(path: Path) -> Optional[int]:
    try:
        return int(path.stat().st_uid)
    except OSError:
        return None


def _needs_fix(path: Path, target_uid: int) -> bool:
    if not path.exists():
        return False
    owner = _path_owner_uid(path)
    return owner is not None and owner != target_uid


def _chown_as_root(path: Path, uid: int, gid: int) -> bool:
    try:
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                for name in dirs + files:
                    os.chown(Path(root) / name, uid, gid)
            os.chown(path, uid, gid)
        else:
            os.chown(path, uid, gid)
        return True
    except OSError:
        return False


def _chown_via_sudo(path: Path, uid: int, gid: int) -> bool:
    try:
        proc = subprocess.run(
            ["sudo", "-n", "chown", "-R", f"{uid}:{gid}", str(path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
        return proc.returncode == 0 and not _needs_fix(path, uid)
    except (OSError, subprocess.TimeoutExpired):
        return False


def _resolve_home_owner() -> Optional[Tuple[int, int]]:
    owner = home_dir_owner()
    if owner is not None:
        return owner
    if os.getuid() != 0:
        return os.getuid(), os.getgid()
    return None


def fix_r3_home_ownership(root: Optional[Path] = None) -> Dict[str, Any]:
    """Besitz auf Home-User — idempotent, fail-closed bei fehlendem sudo."""
    root = Path(root or Path.cwd()).resolve()
    owner = _resolve_home_owner()
    if owner is None:
        return {
            "ok": False,
            "error_de": "Home-User nicht ermittelbar",
            "fixed": [],
            "pending": [],
        }
    uid, gid = owner
    fixed: List[str] = []
    pending: List[str] = []
    for target in r3_home_ownership_targets():
        if not _needs_fix(target, uid):
            continue
        ok = False
        if os.getuid() == 0:
            ok = _chown_as_root(target, uid, gid)
        elif os.getuid() == uid:
            ok = _chown_via_sudo(target, uid, gid)
        if ok and not _needs_fix(target, uid):
            fixed.append(str(target))
        else:
            pending.append(str(target))

    doc: Dict[str, Any] = {
        "ok": not pending,
        "updated_at_utc": _utc_now(),
        "home_uid": uid,
        "fixed": fixed,
        "fixed_count": len(fixed),
        "pending": pending,
        "pending_count": len(pending),
        "headline_de": (
            f"Besitz OK ({len(fixed)} korrigiert)"
            if not pending
            else f"Besitz — {len(pending)} Pfad(e) brauchen sudo"
        ),
        "message_de": (
            "R3 ~/.local gehört dem Benutzer."
            if not pending
            else "bash tools/fix_r3_home_ownership.sh (ggf. mit sudo)"
        ),
    }
    try:
        share = Path.home() / ".local/share/r3-os"
        share.mkdir(parents=True, exist_ok=True)
        (share / "post_login_ownership_latest.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if root.is_dir():
            ev = root / "evidence/r3_home_ownership_latest.json"
            ev.parent.mkdir(parents=True, exist_ok=True)
            ev.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return doc


def run_post_login_hook(root: Path) -> Dict[str, Any]:
    """Einmal pro Login — Besitz, dann Desktop-DB."""
    doc = fix_r3_home_ownership(root)
    if doc.get("ok") or doc.get("fixed"):
        try:
            apps = Path.home() / ".local/share/applications"
            subprocess.run(
                ["update-desktop-database", str(apps)],
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    return doc
