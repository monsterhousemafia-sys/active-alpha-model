"""Laufzeit-Prüfung lokaler Anwendungen — lauffähig für den User."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_EVIDENCE_REL = Path("evidence/local_apps_runtime_latest.json")


def _run(cmd: List[str], *, cwd: Path, timeout: float = 25.0) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "AA_PROJECT_ROOT": str(cwd)},
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, out.strip()[:200]
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, str(exc)[:200]


def runtime_check_app(root: Path, app: Dict[str, Any], *, port: int = 17890) -> Dict[str, Any]:
    """Smoke-Test: kann der User die App starten/nutzen?"""
    root = Path(root)
    aid = str(app.get("id") or "")
    label = str(app.get("label_de") or aid)
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)

    ok = True
    detail = "OK"
    cmd_de = ""

    if aid == "hub":
        ok, detail = _run([str(py), str(root / "tools/preview_hub.py"), "--ensure"], cwd=root, timeout=15)
        cmd_de = "python tools/preview_hub.py --ensure"

    elif aid == "bash_gpt4o":
        ok, detail = _run(["bash", str(root / "tools/bash_gpt4o.sh"), "status"], cwd=root, timeout=30)
        cmd_de = "bash tools/bash_gpt4o.sh menu"

    elif aid in ("markt", "order_desk", "marktanalyse_bash"):
        sh = root / "tools/marktanalyse_bash.sh"
        ok, detail = _run(["bash", str(sh), "help"], cwd=root) if sh.is_file() else (False, "fehlt")
        cmd_de = "bash tools/marktanalyse_bash.sh menu"
        if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
            gui = root / "run_marktanalyse_linux.sh"
            if gui.is_file():
                cmd_de = "bash run_marktanalyse_linux.sh (GUI) · bash tools/marktanalyse_bash.sh menu (Bash)"

    elif aid == "agent":
        sh = root / "tools/alpha_model_agent.sh"
        ok = sh.is_file() and os.access(sh, os.X_OK)
        try:
            from analytics.local_llm_bridge import health_report

            if not health_report(root).get("ready"):
                detail = "Launcher OK — Ollama Setup empfohlen"
            else:
                detail = "Launcher + Ollama OK"
        except Exception as exc:
            detail = f"Launcher OK — {exc}"[:80]
        cmd_de = "bash tools/alpha_model_agent.sh"

    elif aid == "cockpit":
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        sh = root / "tools/r3_cockpit.sh"
        ok = sh.is_file() and os.access(sh, os.X_OK) and has_display
        try:
            from analytics.desktop_shell_cache import get_desktop_html_for_hub

            body = get_desktop_html_for_hub(root, port=port, fast=True)
            ok = ok and len(body) > 500 and b"r3-desktop-shell" in body
            detail = "Single-Instance + /desktop Cache OK" if ok else "Cockpit/Cache"
        except Exception as exc:
            detail = str(exc)[:120]
            ok = False
        cmd_de = "bash tools/r3_cockpit.sh → /desktop"

    elif aid == "welt":
        sh = root / "tools/r3_welt.sh"
        ok = sh.is_file() and os.access(sh, os.X_OK)
        detail = "Launcher OK — öffnet /launch im Cockpit" if ok else "r3_welt.sh fehlt"
        cmd_de = "bash tools/r3_welt.sh → /launch"

    elif aid in ("session",):
        sh = root / "tools/r3_session_autostart.sh"
        auto = Path.home() / ".config/autostart/r3-os-session.desktop"
        ok = sh.is_file() and auto.is_file()
        detail = "Autostart OK" if ok else "Session-Autostart fehlt"
        cmd_de = "tools/r3_session_autostart.sh (Login)"

    elif app.get("shell_ids"):
        ids = [str(x) for x in (app.get("shell_ids") or [])]
        try:
            from analytics.r3_ubuntu_shell import _feature_available, _feature_map

            fmap = _feature_map(root)
            bad = [fid for fid in ids if not (fmap.get(fid) and _feature_available(root, fmap[fid]))]
            ok = not bad
            detail = f"{len(ids) - len(bad)}/{len(ids)} Panels OK" if ok else f"fehlt: {', '.join(bad)}"
        except Exception as exc:
            ok = False
            detail = str(exc)[:120]
        cmd_de = "gnome-control-center (settings/network/…)"

    elif app.get("shell_id"):
        fid = str(app.get("shell_id"))
        try:
            from analytics.r3_ubuntu_shell import _feature_available, _feature_map

            spec = _feature_map(root).get(fid) or {}
            ok = bool(spec) and _feature_available(root, spec)
            detail = str(spec.get("detail_de") or fid) if ok else f"Feature {fid} nicht startbar"
        except Exception as exc:
            ok = False
            detail = str(exc)[:120]
        cmd_de = f"bash tools/r3_shell_launch.sh {fid}"

    elif app.get("hub_path"):
        from analytics.local_apps_registry import _hub_probe

        path = str(app.get("hub_path"))
        ok = _hub_probe(path, port=port)
        detail = path if ok else f"Hub {path} down"

    elif app.get("exec_rel"):
        p = root / str(app.get("exec_rel"))
        ok = p.is_file() and (p.suffix != ".sh" or os.access(p, os.X_OK))
        detail = "OK" if ok else f"Fehlt: {app.get('exec_rel')}"
        cmd_de = f"bash {app.get('exec_rel')}"

    return {
        "runtime_ok": ok,
        "runtime_detail_de": detail,
        "start_cmd_de": cmd_de,
        "id": aid,
        "label_de": label,
    }


def build_runtime_audit(root: Path, apps: List[Dict[str, Any]], *, port: int = 17890) -> Dict[str, Any]:
    root = Path(root)
    rows = [runtime_check_app(root, app, port=port) for app in apps if isinstance(app, dict)]
    ok_n = sum(1 for r in rows if r.get("runtime_ok"))
    from datetime import datetime, timezone

    from aa_safe_io import atomic_write_json

    doc = {
        "schema_version": 1,
        "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "total": len(rows),
        "ok_count": ok_n,
        "fail_count": len(rows) - ok_n,
        "all_ok": ok_n == len(rows) and len(rows) > 0,
        "apps": rows,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
