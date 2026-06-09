from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

from aa_dashboard import RunDashboard
from aa_dashboard_core import DashboardCore


def qt_available() -> bool:
    try:
        from PySide6 import QtCore  # noqa: F401
        return True
    except ImportError:
        return False


from aa_version import APP_TITLE


def configure_native_app(app: Any) -> None:
    from aa_qt_render import apply_app_icon, bootstrap_qt_native_windows, configure_native_app_font

    bootstrap_qt_native_windows()
    configure_native_app_font(app)
    if sys.platform == "win32":
        try:
            from PySide6.QtWidgets import QStyleFactory

            keys = QStyleFactory.keys()
            if "Windows11" in keys:
                app.setStyle("Windows11")
            elif "windowsvista" in keys:
                app.setStyle("windowsvista")
        except Exception:
            pass
    apply_app_icon(app)
    app.setApplicationName(APP_TITLE)
    app.setOrganizationName("Alpha Model")
    app.setApplicationDisplayName(APP_TITLE)


def run_qt_event_loop(app: Any, *, auto_close_ms: int = 0) -> None:
    """Block until the window closes; optionally quit automatically after success."""
    if auto_close_ms > 0:
        try:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(auto_close_ms, app.quit)
        except Exception:
            pass
    app.exec()


def pump_ui(*, force: bool = True) -> None:
    """Keep the UI responsive during long blocking work on the main thread."""
    from aa_ui_pump import pump_ui as _pump

    _pump(force=force)


def run_subprocess_with_ui(
    args,
    *,
    cwd=None,
    check: bool = True,
    capture_output: bool = False,
    text: bool = True,
    shell: bool = False,
    on_wait=None,
    **kwargs,
):
    """Run a subprocess while pumping the Qt UI so the window stays responsive."""
    import subprocess
    import time
    from time import monotonic

    pump_ui(force=True)
    from aa_subprocess_win import hidden_subprocess_kwargs

    popen_kw = {"cwd": cwd, "text": text, "shell": shell, **hidden_subprocess_kwargs(), **kwargs}
    if capture_output:
        popen_kw["stdout"] = subprocess.PIPE
        popen_kw["stderr"] = subprocess.PIPE
    cmd = args if shell or isinstance(args, str) else list(args)
    proc = subprocess.Popen(cmd, **popen_kw)
    next_wait_ping = monotonic()
    while proc.poll() is None:
        pump_ui(force=True)
        now = monotonic()
        if on_wait is not None and now >= next_wait_ping:
            on_wait()
            next_wait_ping = now + 2.0
        time.sleep(0.02)
    pump_ui(force=True)
    stdout = stderr = None
    if capture_output:
        stdout, stderr = proc.communicate()
    if check and proc.returncode != 0:
        cmd_txt = args if isinstance(args, str) else " ".join(str(a) for a in args)
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd_txt}")
    stored_args = args if isinstance(args, (list, tuple)) else [args]
    return subprocess.CompletedProcess(stored_args, proc.returncode, stdout, stderr)


def notify_startup_issue(message: str, *, title: str | None = None) -> None:
    """Visible feedback when the GUI cannot start (e.g. windowed .exe without Qt)."""
    notify_user_dialog(message, title=title or APP_TITLE, warning=True)


def notify_user_dialog(message: str, *, title: str = "Active Alpha", warning: bool = False) -> None:
    """Show a modal notice, or log only in unattended/auto-run mode."""
    from aa_qt_render import is_auto_run_mode

    if is_auto_run_mode():
        pump_ui(force=True)
        print(f"[{title}] {message}", flush=True)
        return
    pump_ui(force=True)
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is not None:
            box = QMessageBox()
            box.setWindowTitle(title)
            box.setText(message)
            box.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
            box.setWindowModality(Qt.WindowModality.ApplicationModal)
            parent = app.activeWindow()
            if parent is not None:
                box.setWindowFlags(box.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            box.raise_()
            box.activateWindow()
            box.exec()
            pump_ui(force=True)
            return
    except Exception:
        pass
    if sys.platform != "win32":
        print(f"{title}: {message}", flush=True)
        return
    try:
        import ctypes

        icon = 0x00000030 if warning else 0x00000040
        ctypes.windll.user32.MessageBoxW(None, message, title, icon)
    except Exception:
        print(f"{title}: {message}", flush=True)


class MainThreadDashboard:
    """Queue dashboard mutations onto the Qt main thread (GPU/UI thread)."""

    def __init__(self, inner: "RunDashboardQt") -> None:
        self._inner = inner

    def _invoke(self, name: str, /, *args, **kwargs) -> None:
        from PySide6.QtCore import QThread, QTimer
        from PySide6.QtWidgets import QApplication

        def run() -> None:
            getattr(self._inner, name)(*args, **kwargs)

        app = QApplication.instance()
        if app is None or QThread.currentThread() is app.thread():
            run()
            return
        QTimer.singleShot(0, run)

    def start(self, *, total_phases: int, out_dir: Any, title: Optional[str] = None) -> None:
        self._invoke("start", total_phases=total_phases, out_dir=out_dir, title=title)

    def start_phase(self, name: str, *, total: int = 1, step: str = "") -> None:
        self._invoke("start_phase", name, total=total, step=step)

    def advance_phase(self, advance: int = 1, **kwargs: Any) -> None:
        self._invoke("advance_phase", advance, **kwargs)

    def finish_phase(self) -> None:
        self._invoke("finish_phase")

    def complete_pipeline_step(self, key: str) -> None:
        self._invoke("complete_pipeline_step", key)

    def set_status(self, **kwargs: Any) -> None:
        self._invoke("set_status", **kwargs)

    def ok(self, message: str) -> None:
        self._invoke("ok", message)

    def warn(self, message: str) -> None:
        self._invoke("warn", message)

    def error(self, message: str) -> None:
        self._invoke("error", message)

    def stop(self) -> None:
        self._invoke("stop")

    @property
    def inner(self) -> "RunDashboardQt":
        return self._inner


class RunDashboardQt:
    """Native Windows dashboard backed by PySide6."""

    PAINT_MIN_INTERVAL_S = 0.04

    def __init__(self, *, enabled: bool = True, title: Optional[str] = None, session: Any = None) -> None:
        self.enabled = enabled
        self.rich = False
        self.console = None
        self.live = None
        self._core = DashboardCore(title=title)
        self._session = session
        self._active = enabled and qt_available()
        self._last_paint_at = 0.0

    @property
    def title(self) -> str:
        return self._core.title

    @title.setter
    def title(self, value: str) -> None:
        self._core.title = value

    def _ensure_ui(self) -> None:
        if not self._active:
            return
        if self._session is None:
            from aa_dashboard_qt_window import AppSession

            self._session = AppSession.get()
            self._session.window.set_mode("backtest")
            self._session.start(self._paint)
        elif self._session._sync_fn is not self._paint:
            self._session.window.set_mode("backtest")
            self._session._sync_fn = self._paint
            self._session.mark_dirty()
            self._session.flush(force=True)

    def _paint(self, *, force: bool = False, heartbeat: bool = False) -> None:
        if self._session is not None:
            self._session.window.sync_backtest(self._core, force=force, heartbeat=heartbeat)

    def refresh(self, *, force: bool = False) -> None:
        if not self._active or self._session is None:
            return
        from time import monotonic

        now = monotonic()
        if force:
            self._session.flush(force=True)
            self._last_paint_at = now
            return
        if (now - self._last_paint_at) >= self.PAINT_MIN_INTERVAL_S:
            self._session.flush(force=False)
            self._last_paint_at = now
        else:
            self._session.mark_dirty()
            self._session._tick()

    def start(self, *, total_phases: int, out_dir: Any, title: Optional[str] = None) -> None:
        _ = total_phases
        if title:
            self._core.title = title
        self._core.out_dir = str(out_dir)
        self._core.reset_timer()
        from aa_cancellation import clear_cancel

        clear_cancel()
        self._core._activity = "Marktanalyse startet …"
        self._core.log("INFO", "Programm gestartet — bereite Umgebung vor …")
        if self._active:
            self._ensure_ui()
        self._core.log("INFO", "Marktanalyse Backtest wird initialisiert …")
        self.refresh(force=True)

    def stop(self) -> None:
        try:
            self._core.mark_complete()
            self.refresh(force=True)
        except Exception:
            pass

    def start_phase(self, name: str, *, total: int = 1, step: str = "") -> None:
        from aa_cancellation import check_cancelled

        check_cancelled(name)
        self._core.start_phase(name, total=total, step=step)
        self.refresh(force=True)

    def set_status(self, **kwargs: Any) -> None:
        self._core.set_status(**kwargs)
        self.refresh()

    def advance_phase(self, advance: int = 1, **kwargs: Any) -> None:
        from aa_cancellation import check_cancelled

        check_cancelled(self._core._sub_step or "Fortschritt")
        self._core.advance_phase(advance, **kwargs)
        self.refresh(force=True)

    def finish_phase(self) -> None:
        self._core.finish_phase()
        self.refresh(force=True)

    def complete_pipeline_step(self, key: str) -> None:
        self._core.complete_pipeline_step(key)
        self.refresh(force=True)

    def ok(self, message: str) -> None:
        self._core.ok(message)
        self.refresh(force=True)

    def warn(self, message: str) -> None:
        self._core.warn(message)
        self.refresh(force=True)

    def error(self, message: str) -> None:
        self._core.error(message)
        self.refresh(force=True)

    @property
    def phase_index(self) -> int:
        return self._core.phase_index

    @property
    def total_phases(self) -> int:
        return self._core.total_phases

    @total_phases.setter
    def total_phases(self, value: int) -> None:
        self._core.total_phases = value

    @property
    def phase_name(self) -> str:
        return self._core.phase_name

    @phase_name.setter
    def phase_name(self, value: str) -> None:
        self._core.phase_name = value

    @property
    def phase_step(self) -> str:
        return self._core.phase_step

    @phase_step.setter
    def phase_step(self, value: str) -> None:
        self._core.phase_step = value

    @property
    def phase_total(self) -> int:
        return self._core.phase_total

    @phase_total.setter
    def phase_total(self, value: int) -> None:
        self._core.phase_total = value

    @property
    def phase_completed(self) -> int:
        return self._core.phase_completed

    @phase_completed.setter
    def phase_completed(self, value: int) -> None:
        self._core.phase_completed = value

    def finalize_app(
        self,
        *,
        success: bool,
        keep_open_ms: int = 0,
        result: Any = None,
    ) -> None:
        _ = keep_open_ms
        if not self._active or self._session is None:
            return
        self._session.stop_timer()
        metrics: Dict[str, Any] = {}
        signal_date = "n/a"
        output_files = None
        out_dir = self._core.out_dir
        error = self._core.last_error
        if result is not None:
            metrics = getattr(result, "metrics", {}) or {}
            signal_date = getattr(result, "signal_date", "n/a")
            output_files = getattr(result, "output_files", None)
            out_dir = str(getattr(result, "out_dir", out_dir))
        try:
            self._session.window.show_result(
                success=success,
                out_dir=out_dir,
                metrics=metrics,
                signal_date=signal_date,
                output_files=output_files,
                error=error,
            )
        except Exception:
            if not success and error:
                self._core.last_error = str(error)
            self.error(str(error or "Lauf fehlgeschlagen")[:500])
        self._session.flush(force=True)

        if os.environ.get("AA_GUI", "").strip() == "0" or os.environ.get("AA_NONINTERACTIVE", "").strip() == "1":
            return
        run_qt_event_loop(self._session.app, auto_close_ms=0)


class LauncherUI:
    """Native Windows launcher UI with text fallback."""

    def __init__(self) -> None:
        from aa_dashboard_core import LauncherDashboardCore

        self._core = LauncherDashboardCore()
        self._use_qt = qt_available()
        self._session: Any = None
        self._dashboard: Any = None
        self._finalized = False

    def _paint(self, *, force: bool = False, heartbeat: bool = False) -> None:
        if self._session is not None:
            self._session.window.sync_launcher(self._core, force=force, heartbeat=heartbeat)

    def __enter__(self):
        from aa_cancellation import clear_cancel

        clear_cancel()
        self._core._activity = "Marktanalyse startet …"
        self._core.log("[INFO] Programm gestartet — bereite Umgebung vor …")
        if self._use_qt:
            from aa_dashboard_qt_window import AppSession

            self._session = AppSession.get()
            self._session.window.set_mode("launcher")
            self._session.start(self._paint)
            self._refresh(force=True)
        else:
            print("Marktanalyse — Setup wird gestartet …", flush=True)
        return self

    def __exit__(self, exc_type, exc, tb):
        self._core.mark_complete()
        if not self._use_qt or self._session is None:
            return
        if self._finalized:
            return
        if self._dashboard is None:
            self._refresh(force=True)
            return
        self._session.stop_timer()
        if exc_type is None:
            return
        err = str(exc) if exc is not None else "Lauf unvollständig beendet"
        self._session.window.show_result(
            success=False,
            out_dir="",
            metrics={},
            error=err,
        )
        run_qt_event_loop(self._session.app)

    def handoff_to_backtest(self) -> "RunDashboardQt":
        """Reuse the same window for the backtest phase."""
        dash = RunDashboardQt(title=APP_TITLE, session=self._session)
        self._dashboard = dash
        if self._session is not None:
            self._session.window.set_mode("backtest")
            self._session._sync_fn = dash._paint
            self._session.mark_dirty()
            self._session.flush(force=True)
        return dash

    def activate(self, key: str) -> None:
        self._core.activate(key)
        self._refresh(force=True)

    def done(self, key: str) -> None:
        self._core.done(key)
        self._refresh(force=True)

    def log(self, msg: str) -> None:
        self._core.log(msg)
        if not self._use_qt:
            print(msg, flush=True)
        self._refresh(force=True)

    def set_health_status(self, health: str, message: str = "") -> None:
        if self._use_qt and self._session is not None:
            self._session.window.set_health_status(health, message)
        self._refresh(force=True)

    def _refresh(self, *, force: bool = False) -> None:
        if not self._use_qt or self._session is None:
            return
        if force:
            self._session.flush(force=True)
        else:
            self._session.mark_dirty()
            self._session._tick()

    def finalize(
        self,
        *,
        success: bool,
        result: Any = None,
        keep_open_ms: int = 0,
    ) -> None:
        _ = keep_open_ms
        if not self._use_qt or self._session is None:
            return
        self._finalized = True
        if self._dashboard is not None and result is not None:
            self._dashboard.finalize_app(success=success, result=result)
            return
        if self._dashboard is not None and not success:
            err = self._dashboard._core.last_error or "Analyse fehlgeschlagen"
            self._session.stop_timer()
            self._session.window.show_result(
                success=False,
                out_dir=str(self._dashboard._core.out_dir or ""),
                metrics={},
                error=err,
            )
            if os.environ.get("AA_GUI", "").strip() == "0" or os.environ.get("AA_NONINTERACTIVE", "").strip() == "1":
                return
            run_qt_event_loop(self._session.app, auto_close_ms=0)
            return
        self._session.stop_timer()
        out_dir = ""
        metrics: Dict[str, Any] = {}
        signal_date = "n/a"
        if result is not None:
            metrics = getattr(result, "metrics", {}) or {}
            out_dir = str(getattr(result, "out_dir", "") or "")
            signal_date = str(getattr(result, "signal_date", "n/a") or "n/a")
        self._session.window.show_result(
            success=success,
            out_dir=out_dir,
            metrics=metrics,
            signal_date=signal_date,
            error="" if success else "Setup fehlgeschlagen",
        )
        if os.environ.get("AA_GUI", "").strip() == "0" or os.environ.get("AA_NONINTERACTIVE", "").strip() == "1":
            return
        run_qt_event_loop(self._session.app, auto_close_ms=0)


def create_dashboard(
    *,
    enabled: bool = True,
    title: Optional[str] = None,
    prefer_gui: bool = True,
    plain: bool = False,
    session: Any = None,
):
    if not enabled or plain:
        return RunDashboard(enabled=False, title=title)
    if prefer_gui and qt_available():
        return RunDashboardQt(enabled=True, title=title, session=session)
    return RunDashboard(enabled=True, title=title, use_rich=False)


def should_use_gui(args: Any) -> bool:
    if getattr(args, "plain_progress", False) or getattr(args, "no_gui", False):
        return False
    if os.environ.get("AA_GUI", "").strip() == "0":
        return False
    if os.environ.get("AA_NONINTERACTIVE", "").strip() == "1":
        return False
    stdout = sys.stdout
    if stdout is None or not stdout.isatty():
        return False
    if getattr(args, "gui", False) or os.environ.get("AA_GUI", "").strip() == "1":
        return qt_available()
    return sys.platform == "win32" and qt_available()
