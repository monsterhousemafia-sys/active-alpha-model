"""R3 Desktop-Icon — Taskleiste, Alt-Tab, Miniatur (PNG + SVG)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ICON_NAME = "r3-os"
_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)


def icon_source_path(root: Path) -> Path:
    return Path(root) / "assets/r3-os-icon.svg"


def _home_icons() -> Path:
    return Path.home() / ".local/share/icons/hicolor"


def home_dir_owner() -> Optional[Tuple[int, int]]:
    import pwd

    sudo_user = (os.environ.get("SUDO_USER") or "").strip()
    if sudo_user:
        try:
            ent = pwd.getpwnam(sudo_user)
            return int(ent.pw_uid), int(ent.pw_gid)
        except KeyError:
            pass
    home = Path.home()
    parts = home.parts
    if len(parts) >= 3 and parts[1] == "home" and parts[2]:
        try:
            ent = pwd.getpwnam(parts[2])
            return int(ent.pw_uid), int(ent.pw_gid)
        except KeyError:
            pass
    try:
        st = home.stat()
        uid = int(st.st_uid)
        if uid != 0:
            return uid, int(st.st_gid)
    except OSError:
        pass
    return None


def ensure_home_file_owned(path: Path) -> bool:
    """Root-Sandbox-Schreibungen in ~/.local dem Home-User zuweisen."""
    path = Path(path)
    owner = home_dir_owner()
    if owner is None:
        return False
    uid, gid = owner
    if uid == os.getuid():
        return True
    if os.getuid() != 0:
        return os.access(path, os.W_OK) if path.exists() else True
    try:
        targets: List[Path] = []
        if path.is_dir():
            for root, dirs, files in os.walk(path):
                for name in dirs + files:
                    targets.append(Path(root) / name)
            targets.append(path)
        elif path.exists():
            targets.append(path)
        for target in targets:
            os.chown(target, uid, gid)
        return True
    except OSError:
        return False


def _copy_into_home(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not os.access(dest, os.W_OK):
        owner = home_dir_owner()
        if owner and os.getuid() == owner[0]:
            raise PermissionError(
                f"{dest} gehört root — einmalig: "
                f"sudo chown -R {Path.home().name}:{Path.home().name} ~/.local/share/icons ~/.local/share/applications/R3.desktop ~/.config/autostart/r3-os-session.desktop"
            )
    shutil.copy2(src, dest)
    ensure_home_file_owned(dest)


def _png_via_rsvg(svg: Path, dest: Path, size: int) -> bool:
    for cmd in (
        ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(dest), str(svg)],
        ["convert", "-background", "none", "-resize", f"{size}x{size}", str(svg), str(dest)],
    ):
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=15, check=False)
            if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 80:
                return True
        except (OSError, subprocess.TimeoutExpired):
            continue
    return False


def _png_via_qt(svg: Path, dest: Path, size: int) -> bool:
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QGuiApplication, QIcon, QPixmap

        app = QGuiApplication.instance()
        owns_app = False
        if app is None:
            import sys

            app = QGuiApplication(sys.argv)
            owns_app = True
        icon = QIcon(str(svg))
        pix = icon.pixmap(QSize(size, size))
        ok = not pix.isNull() and pix.save(str(dest), "PNG")
        if owns_app:
            app.quit()
        return bool(ok and dest.is_file())
    except Exception:
        return False


def install_r3_desktop_icons(root: Path, *, icon_name: str = _ICON_NAME) -> Dict[str, Any]:
    """SVG + PNG in hicolor — für Taskleiste/Miniatur (nicht nur scalable)."""
    root = Path(root)
    svg = icon_source_path(root)
    if not svg.is_file():
        return {"ok": False, "error_de": f"Icon fehlt: {svg}"}

    installed: List[str] = []
    base = _home_icons()
    scalable = base / "scalable/apps"
    scalable.mkdir(parents=True, exist_ok=True)
    svg_dest = scalable / f"{icon_name}.svg"
    _copy_into_home(svg, svg_dest)
    installed.append(str(svg_dest))

    png_ok = 0
    for size in _SIZES:
        dest_dir = base / f"{size}x{size}/apps"
        dest_dir.mkdir(parents=True, exist_ok=True)
        ensure_home_file_owned(dest_dir)
        dest = dest_dir / f"{icon_name}.png"
        if _png_via_rsvg(svg, dest, size) or _png_via_qt(svg, dest, size):
            ensure_home_file_owned(dest)
            png_ok += 1
            installed.append(str(dest))

    try:
        subprocess.run(["gtk-update-icon-cache", "-f", "-t", str(base)], check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        pass

    apps = Path.home() / ".local/share/applications"
    try:
        subprocess.run(["update-desktop-database", str(apps)], check=False, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass

    return {
        "ok": png_ok >= 4,
        "icon_name": icon_name,
        "png_sizes_ok": png_ok,
        "installed": installed,
        "headline_de": f"R3-Icon installiert ({png_ok}/{len(_SIZES)} PNG)",
    }


def build_qt_window_icon(*, icon_name: str = _ICON_NAME, root: Optional[Path] = None) -> Any:
    """Mehrgrößen-QIcon für Fenster, Taskleiste und Miniatur."""
    try:
        from PySide6.QtGui import QIcon
    except ImportError:
        return None

    icon = QIcon()
    for size in _SIZES:
        p = _home_icons() / f"{size}x{size}/apps" / f"{icon_name}.png"
        if p.is_file():
            icon.addFile(str(p))
    if not icon.isNull():
        return icon
    path = resolve_r3_icon_path(icon_name=icon_name, root=root)
    if path and path.is_file():
        loaded = QIcon(str(path))
        if not loaded.isNull():
            return loaded
    return None


def resolve_r3_icon_path(*, icon_name: str = _ICON_NAME, root: Optional[Path] = None) -> Optional[Path]:
    """Bestes Icon für Qt-Fenster (PNG bevorzugt)."""
    for size in (256, 128, 64, 48, 32, 24, 16):
        p = _home_icons() / f"{size}x{size}/apps" / f"{icon_name}.png"
        if p.is_file():
            return p
    scalable = _home_icons() / "scalable/apps" / f"{icon_name}.svg"
    if scalable.is_file():
        return scalable
    if root is not None:
        src = icon_source_path(root)
        if src.is_file():
            return src
    return None
