#!/usr/bin/env python3
"""
Active Alpha bootstrap launcher.

Ensures .venv + dependencies, verifies imports, then starts the model or a BAT wrapper.
Designed to be compiled with PyInstaller to Marktanalyse.exe in the project root.
"""
from __future__ import annotations

import multiprocessing as mp
import sys

if getattr(sys, "frozen", False):
    mp.freeze_support()
    from aa_frozen import guard_frozen_worker_exit

    guard_frozen_worker_exit()

import os
import shutil
import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aa_qt_render import bootstrap_qt_native_windows, configure_windows_app_identity

configure_windows_app_identity()
bootstrap_qt_native_windows()

from aa_dashboard_qt import LauncherUI, notify_startup_issue, pump_ui, run_subprocess_with_ui

try:
    import PySide6  # noqa: F401 — ensure PyInstaller bundles Qt
except ImportError:
    pass

REQUIRED_IMPORTS = (
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "yfinance",
    "pyarrow",
    "matplotlib",
    "rich",
    "lxml",
    "bs4",
)

FROZEN_STARTUP_IMPORTS = ("numpy", "pandas")
FROZEN_DEFERRED_IMPORTS = tuple(n for n in REQUIRED_IMPORTS if n not in FROZEN_STARTUP_IMPORTS)
REQ_FILE = "requirements_active_alpha.txt"
STAMP_FILE = Path(".venv") / ".active_alpha_requirements.stamp"
def venv_python(root: Path) -> Path:
    from aa_paths import resolve_venv_python

    return resolve_venv_python(root)

_LAUNCHER_STEPS = (
    ("env", "Python-Umgebung (.venv)"),
    ("libs", "Bibliotheken laden"),
    ("core", "Core-Check"),
    ("ops", "Betriebsdaten aktualisieren"),
    ("paper", "Paper Mark-to-Market"),
    ("run", "Marktanalyse Backtest"),
)


def project_root() -> Path:
    from aa_paths import project_root as _root

    return _root()


_ui: LauncherUI | None = None


def log(msg: str) -> None:
    try:
        from aa_launcher_log import TeeStream, log_line
    except Exception:
        TeeStream = ()  # type: ignore
        log_line = lambda _m: None  # noqa: E731

    if _ui is not None:
        _ui.log(msg)
    stdout = sys.stdout
    if isinstance(stdout, TeeStream):
        stdout.write(msg.rstrip() + "\n")
        if hasattr(stdout, "flush"):
            stdout.flush()
    else:
        log_line(msg)
        if _ui is None and stdout is not None:
            print(msg, flush=True)


def find_system_python() -> list[str]:
    candidates: list[str] = []
    for ver in ("3.14", "3.13", "3.12", "3.11"):
        candidates.append(f"py -{ver}")
    candidates.append("python")
    for cmd in candidates:
        pump_ui(force=True)
        try:
            proc = run_subprocess_with_ui(
                cmd.split()
                + [
                    "-c",
                    "import sys; raise SystemExit(0 if sys.version_info[:2]>=(3,11) and sys.maxsize>2**32 else 1)",
                ],
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                return cmd.split()
        except FileNotFoundError:
            continue
    return []


def run_cmd(cmd: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    log(f"[CMD] {' '.join(cmd)}")
    return run_subprocess_with_ui(
        cmd,
        cwd=str(cwd),
        check=check,
        on_wait=lambda: log("[INFO] Befehl läuft noch …"),
    )


def cleanup_broken_scipy(root: Path) -> None:
    site = root / ".venv" / "Lib" / "site-packages"
    if not site.is_dir():
        return
    for path in site.glob("~cipy*"):
        log(f"[INFO] Entferne kaputten SciPy-Rest: {path.name}")
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink(missing_ok=True)


def imports_ok(python: Path) -> bool:
    code = "; ".join(f"import {name}" for name in REQUIRED_IMPORTS)
    proc = run_subprocess_with_ui([str(python), "-c", code], capture_output=True, check=False)
    return proc.returncode == 0


def stamp_ok(root: Path) -> bool:
    req = root / REQ_FILE
    stamp = root / STAMP_FILE
    if not req.is_file() or not stamp.is_file():
        return False
    return stamp.stat().st_mtime >= req.stat().st_mtime


def write_stamp(root: Path) -> None:
    stamp = root / STAMP_FILE
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.write_text("ok\n", encoding="utf-8")


def ensure_frozen_environment(root: Path) -> Path:
    """EXE uses bundled runtime; skip pip/venv setup when possible."""
    global _ui
    os.chdir(root)
    if _ui is not None:
        _ui.activate("env")
    log(f"Arbeitsordner: {root}")
    log("[OK] EXE-Modus: eingebettete Python-Laufzeit")
    if _ui is not None:
        _ui.done("env")
        _ui.activate("libs")
    for name in FROZEN_STARTUP_IMPORTS:
        try:
            __import__(name)
        except ImportError as exc:
            raise RuntimeError(f"Eingebettete Bibliothek fehlt: {name} ({exc})") from exc
    log("[OK] Bibliotheken (Startup): " + ", ".join(FROZEN_STARTUP_IMPORTS))
    if _ui is not None:
        _ui.done("libs")
    skip_venv = os.environ.get("AA_SKIP_VENV_PROBE", "1").strip().lower() in {"1", "true", "yes", "on"}
    venv_py = venv_python(root)
    if not skip_venv and venv_py.is_file() and imports_ok(venv_py):
        log("[OK] Lokale .venv vorhanden (optional)")
        return venv_py
    log("[INFO] Keine lokale .venv — EXE nutzt eingebettete Module")
    return Path(sys.executable)


def ensure_frozen_full_imports() -> None:
    """Load heavy bundled libs before backtest (skipped on Fast-Path startup)."""
    for name in FROZEN_DEFERRED_IMPORTS:
        __import__(name)


def _env_flag(env: dict[str, str], key: str, default: str = "1") -> bool:
    return str(env.get(key, default) or default).strip().lower() not in {"0", "false", "no", "off"}


def ensure_environment(root: Path) -> Path:
    frozen = getattr(sys, "frozen", False)
    if frozen and os.environ.get("AA_FROZEN_LIGHT_ENV", "1").strip() == "1":
        return ensure_frozen_environment(root)
    global _ui
    os.chdir(root)
    if _ui is not None:
        _ui.activate("env")
    log(f"Arbeitsordner: {root}")

    if not (root / REQ_FILE).is_file():
        raise FileNotFoundError(f"{REQ_FILE} fehlt in {root}")

    venv_py = venv_python(root)
    recreate = not venv_py.is_file() or os.environ.get("AA_RECREATE_ENV", "").strip() == "1"
    if venv_py.is_file() and not recreate:
        proc = run_subprocess_with_ui(
            [str(venv_py), "-c", "import sys; raise SystemExit(0 if sys.maxsize>2**32 else 1)"],
            check=False,
        )
        if proc.returncode != 0:
            recreate = True

    py_launch: list[str] = []
    if recreate:
        py_launch = find_system_python()
        if not py_launch:
            raise RuntimeError(
                "Keine geeignete 64-bit Python 3.11+ Installation gefunden (py -3.14, py -3.13 oder python)."
            )

    if recreate:
        log("[INFO] Erstelle/Repariere lokale .venv …")
        if (root / ".venv").exists():
            shutil.rmtree(root / ".venv", ignore_errors=True)
        run_cmd(py_launch + ["-m", "venv", ".venv"], cwd=root)

    cleanup_broken_scipy(root)

    install_needed = recreate or not imports_ok(venv_py) or os.environ.get("AA_FORCE_INSTALL", "").strip() == "1"
    if not install_needed and not stamp_ok(root):
        log("[INFO] requirements_active_alpha.txt wurde geaendert.")
        install_needed = True

    if install_needed:
        log("[INFO] Installiere/aktualisiere Pakete …")
        run_cmd([str(venv_py), "-m", "pip", "install", "--upgrade", "pip"], cwd=root)
        run_cmd([str(venv_py), "-m", "pip", "install", "-r", REQ_FILE], cwd=root)
        proc = run_subprocess_with_ui(
            [str(venv_py), "-c", "import matplotlib"],
            cwd=str(root),
            check=False,
        )
        if proc.returncode != 0:
            run_cmd([str(venv_py), "-m", "pip", "install", "matplotlib"], cwd=root)
        write_stamp(root)
    else:
        log("[OK] Lokale .venv ist bereit.")

    if not imports_ok(venv_py):
        log("[WARN] Import-Test fehlgeschlagen. Repariere scipy/sklearn/matplotlib …")
        run_cmd(
            [str(venv_py), "-m", "pip", "install", "--upgrade", "--force-reinstall", "scipy", "scikit-learn", "matplotlib"],
            cwd=root,
        )
        if not imports_ok(venv_py):
            raise RuntimeError("Python-Umgebung konnte nicht repariert werden.")

    versions = run_subprocess_with_ui(
        [str(venv_py), "-c", "import numpy; print(numpy.__version__)"],
        cwd=str(root),
        capture_output=True,
        check=True,
    ).stdout.strip()
    log(f"[OK] Python-Umgebung bereit (numpy {versions})")
    if _ui is not None:
        _ui.done("env")
        _ui.activate("libs")
    log("[OK] Bibliotheken: " + ", ".join(REQUIRED_IMPORTS))
    if _ui is not None:
        _ui.done("libs")
    return venv_py


def run_frozen_core_check(root: Path) -> None:
    """Lightweight compatibility gate for Marktanalyse.exe (no subprocess --help)."""
    import check_active_alpha_core as cac

    missing = [name for name in cac.REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise RuntimeError("Core-Check: fehlende Dateien — " + ", ".join(missing[:5]))
    for mod in ("aa_config", "aa_runtime", "paper_trading_engine"):
        __import__(mod)


def verify_project(root: Path, venv_py: Path) -> tuple[dict[str, str], object, object]:
    if _ui is not None:
        _ui.activate("core")
    log("[INFO] Core-Check …")
    frozen = getattr(sys, "frozen", False)
    if frozen:
        run_frozen_core_check(root)
    else:
        checker = root / "check_active_alpha_core.py"
        if not checker.is_file():
            raise FileNotFoundError(f"{checker} fehlt")
        run_cmd([str(venv_py), str(checker)], cwd=root)
    log("[OK] Core-Check bestanden")
    from aa_config_env import resolve_launcher_env
    from aa_data_freshness import apply_stale_data_env, assess_daily_data
    from aa_ops import run_preflight_step
    from aa_system_status import health_from_parts, health_label

    env = resolve_launcher_env(root, frozen=frozen)
    report = assess_daily_data(root, env)
    for line in report.log_lines:
        log(line)
    if not report.price_current:
        env.update(apply_stale_data_env(dict(env), report))
    preflight = run_preflight_step(root, env, log=log, data_report=report)
    if preflight.blocking:
        raise RuntimeError("Preflight fehlgeschlagen — siehe Log")
    os.environ.update(env)
    health = health_from_parts(preflight=preflight.status, data_ok=report.ok)
    if _ui is not None and hasattr(_ui, "set_health_status"):
        _ui.set_health_status(health, health_label(health))
    if _ui is not None:
        _ui.done("core")
    return env, report, preflight


def run_ops_refresh_step(
    root: Path,
    env: dict[str, str],
    report,
    *,
    include_signal: bool = False,
    force: bool = False,
) -> tuple[dict[str, str], object]:
    from aa_ops_refresh import run_ops_refresh

    if _ui is not None:
        _ui.activate("ops")
    pump_ui(force=True)
    result = run_ops_refresh(
        root,
        env,
        log=log,
        pump_ui_fn=pump_ui,
        include_signal=include_signal,
        force=force,
        data_report=report,
    )
    env.update(result.env_updates)
    os.environ.update(env)
    pump_ui(force=True)
    if _ui is not None:
        _ui.done("ops")
    return env, result


def run_paper_routine(root: Path, venv_py: Path, env: dict | None = None) -> dict:
    from aa_config_env import resolve_launcher_env
    from aa_paper_startup import run_paper_startup

    if _ui is not None:
        _ui.activate("paper")
    pump_ui(force=True)
    if env is None:
        env = resolve_launcher_env(root, frozen=getattr(sys, "frozen", False))
    os.environ.update(env)
    status = run_paper_startup(
        root,
        venv_py,
        env,
        log=log,
        inprocess=True,
        pump_ui_fn=pump_ui,
    )
    pump_ui(force=True)
    if _ui is not None:
        _ui.done("paper")
    return dict(status or {})


def launch_results_only(root: Path, env: dict[str, str], *, preflight, data_report=None) -> int:
    from aa_data_freshness import assess_daily_data
    from aa_ops import decide_run_plan, load_cached_run_result, update_system_status

    if _ui is not None:
        _ui.activate("run")
    log("[OK] Fast-Path: gespeicherte Analyse wird angezeigt (kein Voll-Backtest)")
    pump_ui(force=True)
    if data_report is None:
        data_report = assess_daily_data(root, env)
    plan = decide_run_plan(root, env, data_report=data_report, preflight=preflight)
    result = load_cached_run_result(root, env)
    if not result.success:
        log(f"[WARN] Fast-Path abgebrochen — {result.error or 'Analyse unvollständig'}")
        return launch_backtest(root, env, preflight=preflight)
    update_system_status(
        root,
        phase="results",
        preflight=preflight,
        data_report=data_report,
        run_plan=plan,
        exit_code=0,
        message="Fast-Path — Ergebnisse aus Cache",
        out_dir=result.out_dir,
        details={
            "analytical_validity": "PASS" if result.success else "INVALID",
            "validated_run_id": "",
        },
    )
    if _ui is not None:
        dash = _ui.handoff_to_backtest()
        dash._core.out_dir = str(result.out_dir)
        _ui.done("run")
        _ui.finalize(success=True, result=result)
    return 0


def launch_backtest(root: Path, env: dict[str, str], *, preflight) -> int:
    if _ui is not None:
        _ui.activate("run")
    log("[INFO] Starte Backtest …")
    if getattr(sys, "frozen", False):
        ensure_frozen_full_imports()
        skip = os.environ.get("AA_SKIP_DOWNLOAD_IF_CACHED", "1").strip() == "1"
        if skip:
            log("[INFO] EXE-Modus: Preis-Cache wird genutzt, falls tagesaktuell.")
        else:
            log("[INFO] EXE-Modus: frische Marktkurse werden geladen.")
        log("[INFO] EXE-Modus: ein Fenster, Thread-Parallelismus.")
    try:
        dashboard = _ui.handoff_to_backtest() if _ui is not None else None
        from aa_configured_backtest import run_configured_backtest
        from aa_data_freshness import assess_daily_data
        from aa_ops import decide_run_plan, update_system_status
        from aa_qt_render import configure_cpu_compute_env

        configure_cpu_compute_env()
        result = run_configured_backtest(root, dashboard=dashboard)
        if _ui is not None:
            _ui.done("run")
        rc = 0 if result.success else 1
        data_report = assess_daily_data(root, env)
        plan = decide_run_plan(root, env, data_report=data_report, preflight=preflight)
        update_system_status(
            root,
            phase="analyze",
            preflight=preflight,
            data_report=data_report,
            run_plan=plan,
            exit_code=rc,
            message="Analyse abgeschlossen" if rc == 0 else "Analyse fehlgeschlagen",
            out_dir=result.out_dir if result else None,
        )
        if _ui is not None:
            _ui.finalize(success=(rc == 0), result=result)
        return rc
    except KeyboardInterrupt:
        log("[WARN] Backtest abgebrochen.")
        if _ui is not None:
            _ui.done("run")
            _ui.finalize(success=False)
        return 130
    except Exception as exc:
        log(f"[ERROR] Backtest fehlgeschlagen: {exc}")
        if _ui is not None:
            _ui.done("run")
            if _ui._dashboard is not None:
                _ui._dashboard._core.last_error = str(exc)
            _ui.finalize(success=False)
        return 1


def main(argv: list[str] | None = None) -> int:
    global _ui
    _ = argv
    from aa_ops import decide_run_plan, update_system_status
    from aa_qt_render import bootstrap_qt_native_windows, configure_cpu_compute_env

    bootstrap_qt_native_windows()
    configure_cpu_compute_env(launcher=True)
    mp.freeze_support()
    if getattr(sys, "frozen", False) and mp.current_process().name != "MainProcess":
        return 0
    root = project_root()
    os.chdir(root)

    from aa_single_instance import acquire_single_instance

    _instance_guard = acquire_single_instance(root)
    if _instance_guard is None:
        return 0

    from aa_launcher_log import close_run_log, install_log_tee, start_run_log
    from aa_version import APP_TITLE

    log_path = start_run_log(root)
    install_log_tee()
    log(f"[INFO] {APP_TITLE}")
    log(f"[INFO] Log-Datei: {log_path}")
    rc = 1
    frozen = getattr(sys, "frozen", False)
    _instance_guard = None
    try:
        from aa_dashboard_qt import qt_available

        if frozen and not qt_available():
            notify_startup_issue(
                "Die grafische Oberfläche konnte nicht geladen werden (PySide6 fehlt).\n\n"
                "Bitte build_active_alpha_launcher.bat erneut ausführen\n"
                "oder Marktanalyse über run_active_alpha_model.bat starten."
            )
            return 1
        with LauncherUI() as ui:
            _ui = ui
            pump_ui(force=True)
            venv_py = ensure_environment(root)
            env, report, preflight = verify_project(root, venv_py)
            plan = decide_run_plan(root, env, data_report=report, preflight=preflight)
            for reason in plan.reasons:
                log(f"[INFO] Laufplan ({plan.mode}): {reason}")

            update_system_status(
                root,
                phase="plan",
                preflight=preflight,
                data_report=report,
                run_plan=plan,
                exit_code=0,
                message="; ".join(plan.reasons),
            )

            status_details: dict[str, object] = {}

            if plan.show_results_only:
                env, ops_result = run_ops_refresh_step(root, env, report)
                if getattr(ops_result, "lock_contended", False):
                    status_details["ops_lock_contended"] = True
                    log("[WARN] Ops-Refresh blockiert — paralleler Lauf aktiv")
                defer_paper = _env_flag(env, "AA_DEFER_PAPER_ON_FAST_PATH", "1")
                if defer_paper:
                    if _ui is not None and _ui._session is not None:

                        def _deferred_paper() -> None:
                            run_paper_routine(root, venv_py, env)

                        _ui._session.window.register_deferred_startup(_deferred_paper)
                        _ui.done("paper")
                    log("[INFO] Paper Mark-to-Market nach UI-Anzeige (Hintergrund).")
                else:
                    paper_status = run_paper_routine(root, venv_py, env)
                    if paper_status.get("paper_mark_ok") is False:
                        status_details["paper_mark_failed"] = True
                rc = launch_results_only(root, env, preflight=preflight, data_report=report)
            elif plan.needs_signal_refresh:
                log("[INFO] Signal-Refresh (Integrität PASS) — überspringe Voll-Backtest.")
                env, ops_result = run_ops_refresh_step(
                    root, env, report, include_signal=True, force=True
                )
                if getattr(ops_result, "lock_contended", False):
                    status_details["ops_lock_contended"] = True
                    log("[WARN] Ops-Refresh blockiert — paralleler Lauf aktiv")
                defer_paper = _env_flag(env, "AA_DEFER_PAPER_ON_FAST_PATH", "1")
                if defer_paper:
                    if _ui is not None and _ui._session is not None:

                        def _deferred_paper_signal() -> None:
                            run_paper_routine(root, venv_py, env)

                        _ui._session.window.register_deferred_startup(_deferred_paper_signal)
                        _ui.done("paper")
                else:
                    paper_status = run_paper_routine(root, venv_py, env)
                    if paper_status.get("paper_mark_ok") is False:
                        status_details["paper_mark_failed"] = True
                from aa_data_freshness import assess_daily_data

                report = assess_daily_data(root, env)
                rc = launch_results_only(root, env, preflight=preflight, data_report=report)
            else:
                env, ops_result = run_ops_refresh_step(root, env, report)
                if getattr(ops_result, "lock_contended", False):
                    status_details["ops_lock_contended"] = True
                paper_status = run_paper_routine(root, venv_py, env)
                if paper_status.get("paper_mark_ok") is False:
                    status_details["paper_mark_failed"] = True
                rc = launch_backtest(root, env, preflight=preflight)
            if status_details:
                phase = "results" if (plan.show_results_only or plan.needs_signal_refresh) and rc == 0 else "analyze"
                update_system_status(
                    root,
                    phase=phase,
                    preflight=preflight,
                    data_report=report,
                    run_plan=plan,
                    exit_code=rc,
                    message="; ".join(plan.reasons),
                    details=status_details,
                )
            if rc == 0:
                log("[OK] Marktanalyse abgeschlossen.")
            elif rc != 130:
                log(f"[ERROR] Backtest beendet mit Code {rc}.")
            return rc
    except Exception as exc:
        log(f"[ERROR] {exc}")
        pump_ui(force=True)
        try:
            from aa_config_env import resolve_launcher_env
            from aa_data_freshness import assess_daily_data
            from aa_preflight import PreflightReport

            env = resolve_launcher_env(root, frozen=frozen)
            pf = PreflightReport(status="ERROR")
            dr = assess_daily_data(root, env)
            plan = decide_run_plan(root, env, data_report=dr, preflight=pf)
            update_system_status(
                root,
                phase="error",
                preflight=pf,
                data_report=dr,
                run_plan=plan,
                exit_code=1,
                message=str(exc),
            )
        except Exception:
            pass
        if frozen:
            notify_startup_issue(f"Start fehlgeschlagen:\n\n{exc}")
        return 1
    finally:
        log(f"[INFO] Beendet mit Code {rc}")
        close_run_log()
        if _instance_guard is not None:
            _instance_guard.release()
        _ui = None


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
