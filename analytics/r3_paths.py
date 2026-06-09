"""R3 native paths — einheitliche Ablage, kein active-alpha in der Sitzung."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

SHARE_REL = Path(".local/share/r3-os")
LEGACY_SHARE_REL = Path(".local/share/active-alpha")


def r3_share_dir() -> Path:
    return Path.home() / SHARE_REL


def legacy_share_dir() -> Path:
    return Path.home() / LEGACY_SHARE_REL


def migrate_legacy_share() -> Dict[str, Any]:
    """active-alpha → r3-os (Kopie fehlender Dateien, Symlink für Kompatibilität)."""
    r3 = r3_share_dir()
    leg = legacy_share_dir()
    r3.mkdir(parents=True, exist_ok=True)
    copied: List[str] = []
    if leg.is_dir():
        for item in leg.iterdir():
            dest = r3 / item.name
            if dest.exists():
                continue
            try:
                if item.is_symlink():
                    dest.symlink_to(item.resolve())
                else:
                    shutil.copy2(item, dest)
                copied.append(item.name)
            except OSError:
                pass
    link_ok = False
    if not leg.exists() and r3.is_dir():
        try:
            leg.symlink_to(r3)
            link_ok = True
        except OSError:
            pass
    elif leg.is_dir() and not leg.is_symlink():
        try:
            backup = Path.home() / ".local/share/active-alpha.bak-r3"
            if not backup.exists():
                leg.rename(backup)
                leg.symlink_to(r3)
                link_ok = True
        except OSError:
            pass
    return {
        "r3_share": str(r3),
        "legacy_share": str(leg),
        "copied": copied,
        "legacy_symlinked": link_ok,
    }


def public_status_paths(root: Path) -> Dict[str, str]:
    share = r3_share_dir()
    return {
        "user_json": str(share / "operator_latest.json"),
        "user_txt": str(share / "operator_latest.txt"),
        "project_json": str(Path(root) / "evidence/operator_public_latest.json"),
        "preview_html": str(share / "gui_preview_latest.html"),
        "h1_secure": str(share / "h1_secure_latest.json"),
        "trading_day_txt": str(share / "trading_day_latest.txt"),
    }


def is_r3_native_session() -> bool:
    if os.environ.get("R3_SESSION") == "1":
        return True
    marker = r3_share_dir() / "session_supremacy.json"
    return marker.is_file()


def r3_cli_hint() -> str:
    return "r3-cockpit · r3-show · r3-welt"
