"""R3 Session-Browser — Cockpit als primäre Oberfläche (App-Modus)."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _hub_url(root: Path, path: str = "/", *, port: int = 17890) -> str:
    p = path if str(path).startswith("/") else f"/{path}"
    return f"http://127.0.0.1:{port}{p}"


def wait_hub_page(
    url: str,
    *,
    timeout: float = 90.0,
    min_bytes: int = 200,
    poll_sec: float = 0.5,
) -> bool:
    """Wartet bis der Hub HTML liefert (Health allein reicht für WebEngine nicht)."""
    import time
    import urllib.error
    import urllib.request

    base = str(url or "").split("#", 1)[0]
    if not base:
        return False
    deadline = time.time() + max(5.0, float(timeout))
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base, timeout=8) as resp:
                body = resp.read(8192)
            if int(getattr(resp, "status", 0) or 0) == 200 and len(body) >= int(min_bytes):
                return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(max(0.2, float(poll_sec)))
    return False


def ensure_hub(root: Path, *, port: int = 17890) -> int:
    from analytics.stack_integrity import ensure_hub_reliable

    return int(ensure_hub_reliable(Path(root), port=int(port)))


def _browser_candidates(url: str, *, fullscreen: bool, wm_class: str) -> List[List[str]]:
    fs = ["--start-fullscreen"] if fullscreen else []
    cls = ["--class=" + wm_class, "--window-name=" + wm_class]
    return [
        ["chromium-browser", f"--app={url}", *fs, *cls, "--disable-translate", "--no-first-run"],
        ["chromium", f"--app={url}", *fs, *cls, "--disable-translate", "--no-first-run"],
        ["google-chrome", f"--app={url}", *fs, *cls, "--disable-translate", "--no-first-run"],
        ["microsoft-edge", f"--app={url}", *fs, *cls],
        ["firefox", "-kiosk", url] if fullscreen else ["firefox", "-new-window", url],
    ]


def resolve_browser_cmd(
    url: str,
    *,
    fullscreen: bool = True,
    wm_class: str = "R3",
) -> Optional[List[str]]:
    for parts in _browser_candidates(url, fullscreen=fullscreen, wm_class=wm_class):
        if parts and shutil.which(str(parts[0])):
            return parts
    return None


def launch_session_browser(
    root: Path,
    *,
    hub_path: str = "/",
    port: int = 17890,
    fullscreen: bool = True,
) -> Dict[str, Any]:
    root = Path(root)
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "error_de": "Keine grafische Sitzung."}
    try:
        port = ensure_hub(root, port=port)
    except Exception as exc:
        return {"ok": False, "error_de": f"Hub nicht erreichbar: {exc}"[:200]}
    url = _hub_url(root, hub_path, port=port)
    cmd = resolve_browser_cmd(url, fullscreen=fullscreen, wm_class="R3")
    if not cmd:
        return {"ok": False, "error_de": "Kein Browser (chromium/firefox) gefunden.", "url": url}
    env = os.environ.copy()
    env["AA_PROJECT_ROOT"] = str(root.resolve())
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["R3_SESSION"] = "1"
    try:
        subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "ok": True,
            "url": url,
            "browser": cmd[0],
            "message_de": "R3-Sitzung gestartet — Ubuntu läuft im Cockpit.",
        }
    except OSError as exc:
        return {"ok": False, "error_de": str(exc)[:200], "url": url}


def launch_session_cockpit(
    root: Path,
    *,
    hub_path: str = "/",
    port: int = 17890,
    fullscreen: bool = True,
    block: bool = False,
) -> Dict[str, Any]:
    from analytics.r3_local_cockpit import launch_session_cockpit as _launch

    return _launch(
        root,
        hub_path=hub_path,
        port=port,
        fullscreen=fullscreen,
        block=block,
    )


def session_hub_path(root: Path) -> str:
    try:
        from analytics.r3_session_manager import resolve_hub_entry_path

        return resolve_hub_entry_path(root)
    except Exception:
        pass
    try:
        from analytics.r3_desktop_update import desktop_hub_path

        return desktop_hub_path(root)
    except Exception:
        pass
    try:
        from analytics.linux_runtime_unified import kernel_is_authoritative

        if kernel_is_authoritative(root):
            from analytics.r3_os_supremacy import load_supremacy

            cfg = load_supremacy(root)
            return str((cfg.get("session") or {}).get("hub_path_kernel_ok") or "/launch")
    except Exception:
        pass
    try:
        from analytics.r3_os_supremacy import load_supremacy

        cfg = load_supremacy(root)
        return str((cfg.get("session") or {}).get("hub_path_fallback") or "/")
    except Exception:
        return "/"
