"""R3 — natives lokales Cockpit-Fenster (Qt, kein Browser, nur 127.0.0.1)."""
from __future__ import annotations

import html
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from analytics.r3_crash_guard import clamp_wait_sec

_LOG = logging.getLogger(__name__)

from analytics.r3_shell_brand import loading_html as _loading_html

_LOADING_HTML = _loading_html()


def _error_html(url: str, detail: str) -> str:
    safe_url = html.escape(url, quote=True)
    safe_detail = html.escape(detail, quote=True)
    return (
        f"<!DOCTYPE html><html lang='de'><head><meta charset='utf-8'/>"
        "<style>body{margin:0;padding:32px;background:#f5f5f7;color:#1d1d1f;"
        "font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif}"
        "h1{color:#ff3b30;font-size:22px;font-weight:600}a{color:#0071e3}</style></head><body>"
        "<h1>R3 — Hub nicht erreichbar</h1>"
        f"<p>URL: <a href='{safe_url}'>{safe_url}</a></p>"
        f"<pre>{safe_detail}</pre>"
        "<p>Neustart: <code>bash tools/r3_cockpit.sh</code></p></body></html>"
    )


def _session_cfg(root: Path) -> Dict[str, Any]:
    try:
        from analytics.r3_os_supremacy import load_supremacy

        return dict(load_supremacy(root).get("session") or {})
    except Exception:
        return {}


def _qt_available() -> bool:
    try:
        import PySide6.QtWebEngineWidgets  # noqa: F401
        import PySide6.QtWidgets  # noqa: F401

        return True
    except ImportError:
        return False


def prefer_native_shell(root: Path) -> bool:
    if os.environ.get("R3_NATIVE_SHELL") == "1" or os.environ.get("R3_SESSION") == "1":
        return True
    cfg = _session_cfg(root)
    shell = str(cfg.get("shell") or "native").strip().lower()
    if shell in ("browser", "web"):
        return False
    if shell in ("native", "local", "qt"):
        return True
    return not bool(cfg.get("browser_app_mode", False))


def run_native_cockpit_app(
    root: Path,
    *,
    hub_path: str = "/",
    port: int = 17890,
    fullscreen: Optional[bool] = None,
) -> int:
    """Qt-Hauptschleife — lädt nur den lokalen Hub (127.0.0.1)."""
    root = Path(root).resolve()

    def _cleanup_pid() -> None:
        try:
            from analytics.r3_cockpit_lock import clear_cockpit_pid_if_self

            clear_cockpit_pid_if_self()
        except Exception:
            pass

    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        print('{"ok": false, "error_de": "Keine grafische Sitzung."}', file=sys.stderr)
        return 1

    try:
        from analytics.r3_ubuntu_stability import apply_ubuntu_qt_env, resolve_fullscreen
        from analytics.r3_session_browser import _hub_url, wait_hub_page
        from analytics.stack_integrity import ensure_hub_reliable

        for key, val in apply_ubuntu_qt_env().items():
            if val:
                os.environ[key] = val

        cfg = _session_cfg(root)
        if fullscreen is None:
            fullscreen = resolve_fullscreen(cfg)
        wm_class = str(cfg.get("wm_class") or "R3")[:64]
        wait_sec = clamp_wait_sec(cfg.get("startup_delay_sec"), default=60.0)
        fast_wait = min(wait_sec, 12.0)

        try:
            port = int(ensure_hub_reliable(root, port=port))
        except Exception as exc:
            print(f'{{"ok": false, "error_de": "Hub nicht erreichbar: {exc}"}}', file=sys.stderr)
            return 1

        path = hub_path if str(hub_path).startswith("/") else f"/{hub_path}"
        if path.startswith("/#"):
            path = "/desktop"
        url = _hub_url(root, path, port=port)

        from PySide6.QtCore import Qt, QTimer, QUrl
        from PySide6.QtGui import QGuiApplication
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWidgets import QApplication, QMainWindow, QSizePolicy

        app = QApplication.instance() or QApplication(sys.argv)
        app.setOrganizationName("R3")
        app.setApplicationName("R3")
        app.setApplicationDisplayName("R3")
        try:
            QGuiApplication.setDesktopFileName("R3")
        except Exception:
            pass
        try:
            from analytics.r3_cockpit_lock import clear_cockpit_pid_if_self, register_cockpit_pid_at_start

            register_cockpit_pid_at_start()
            app.aboutToQuit.connect(clear_cockpit_pid_if_self)
        except Exception:
            pass

        def _signal_quit(_signum: int, _frame: object) -> None:
            _cleanup_pid()
            app.quit()

        try:
            signal.signal(signal.SIGTERM, _signal_quit)
            signal.signal(signal.SIGINT, _signal_quit)
        except (OSError, ValueError):
            pass

        try:
            from analytics.r3_desktop_icon import build_qt_window_icon, install_r3_desktop_icons

            install_r3_desktop_icons(root)
            app_icon = build_qt_window_icon(root=root)
        except Exception:
            app_icon = None

        win = QMainWindow()
        win.setWindowTitle("R3")
        if app_icon is not None and not app_icon.isNull():
            try:
                app.setWindowIcon(app_icon)
                win.setWindowIcon(app_icon)
            except Exception:
                pass
        view = QWebEngineView(win)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setHtml(_LOADING_HTML, QUrl("http://127.0.0.1/"))
        win.setCentralWidget(view)
        win.setProperty("wmClass", wm_class or "R3")

        def _apply_fullscreen() -> None:
            if not fullscreen:
                return
            try:
                screen = app.primaryScreen()
                if screen is not None:
                    win.setGeometry(screen.geometry())
                win.setWindowState(Qt.WindowState.WindowFullScreen)
                win.showFullScreen()
            except Exception as exc:
                _LOG.warning("fullscreen apply failed: %s", exc)

        if fullscreen:
            _apply_fullscreen()
        else:
            win.resize(1440, 900)
            win.show()

        hub_port = [port]

        def _load_target(retry: int = 0) -> None:
            try:
                from analytics.r3_runtime import is_surface_page_ready

                if is_surface_page_ready(int(hub_port[0]), path=path.split("#", 1)[0]):
                    view.setUrl(QUrl(url))
                    return
                if wait_hub_page(url, timeout=min(fast_wait if retry == 0 else wait_sec, 90.0)):
                    view.setUrl(QUrl(url))
                    return
                if retry < 1:
                    try:
                        hub_port[0] = int(ensure_hub_reliable(root, port=hub_port[0]))
                    except Exception:
                        pass
                    QTimer.singleShot(800, lambda: _load_target(retry + 1))
                    return
                view.setHtml(
                    _error_html(url, "Hub-Seite antwortet nicht rechtzeitig."),
                    QUrl("http://127.0.0.1/"),
                )
            except Exception as exc:
                _LOG.exception("hub load failed: %s", exc)
                view.setHtml(_error_html(url, str(exc)[:200]), QUrl("http://127.0.0.1/"))

        def _on_load_finished(ok: bool) -> None:
            try:
                _apply_fullscreen()
                if ok:
                    return
                if wait_hub_page(url, timeout=20.0):
                    view.setUrl(QUrl(url))
            except Exception as exc:
                _LOG.warning("load_finished handler: %s", exc)

        view.loadFinished.connect(_on_load_finished)
        QTimer.singleShot(50, _load_target)
        try:
            return int(app.exec())
        finally:
            _cleanup_pid()
    except Exception as exc:
        _LOG.exception("run_native_cockpit_app crashed: %s", exc)
        _cleanup_pid()
        print(f'{{"ok": false, "error_de": "Cockpit-Absturz: {exc}"}}', file=sys.stderr)
        return 1


def launch_native_cockpit(
    root: Path,
    *,
    hub_path: str = "/",
    port: int = 17890,
    fullscreen: Optional[bool] = None,
    block: bool = False,
) -> Dict[str, Any]:
    """Startet natives R3-Fenster — nur lokaler Hub, kein öffentliches Web."""
    root = Path(root).resolve()
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return {"ok": False, "error_de": "Keine grafische Sitzung."}

    from analytics.r3_session_browser import _hub_url
    from analytics.stack_integrity import ensure_hub_reliable

    try:
        port = ensure_hub_reliable(root, port=port)
    except Exception as exc:
        return {"ok": False, "error_de": f"Hub nicht erreichbar: {exc}"[:200]}

    path = hub_path if str(hub_path).startswith("/") else f"/{hub_path}"
    url = _hub_url(root, path, port=port)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)

    root_s = str(root)
    cmd = [
        str(py),
        "-c",
        (
            "import sys; from pathlib import Path; "
            "from analytics.r3_local_cockpit import run_native_cockpit_app; "
            f"sys.exit(run_native_cockpit_app(Path({root_s!r}), hub_path={path!r}, port={int(port)}))"
        ),
    ]
    from analytics.r3_ubuntu_stability import apply_ubuntu_qt_env

    env = apply_ubuntu_qt_env(os.environ.copy())
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["R3_SESSION"] = "1"
    env["R3_NATIVE_SHELL"] = "1"

    if block:
        code = subprocess.call(cmd, env=env, cwd=str(root))
        return {
            "ok": code == 0,
            "url": url,
            "shell": "native",
            "message_de": "R3 Cockpit beendet." if code == 0 else "R3 Cockpit Fehler.",
            "exit_code": code,
        }

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        if proc.poll() is not None:
            return {
                "ok": False,
                "error_de": "Cockpit-Prozess sofort beendet — Qt/Display prüfen.",
                "url": url,
                "exit_code": proc.returncode,
            }
        return {
            "ok": True,
            "url": url,
            "shell": "native",
            "pid": proc.pid,
            "message_de": "R3 Cockpit lokal gestartet — nur 127.0.0.1, kein Web.",
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
    """Nur natives Qt-Fenster — kein Browser-Fallback."""
    root = Path(root)
    if not prefer_native_shell(root):
        return {
            "ok": False,
            "shell": "native",
            "error_de": "R3 läuft nur lokal (Qt). Browser-Modus ist deaktiviert — bash tools/r3_cockpit.sh",
        }
    if not _qt_available():
        return {
            "ok": False,
            "shell": "native",
            "error_de": "PySide6 fehlt — .venv/bin/pip install PySide6 PySide6-Addons",
        }
    return launch_native_cockpit(
        root,
        hub_path=hub_path,
        port=port,
        fullscreen=fullscreen,
        block=block,
    )
