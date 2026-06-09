"""R3 sichtbar machen — Cache neu rendern, König-32B-Handoff, Abgleich."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_apply_visible_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _py(root: Path) -> Path:
    p = root / ".venv/bin/python3"
    return p if p.is_file() else Path(sys.executable)


def apply_r3_visible_changes(root: Path, *, king_handoff: bool = True) -> Dict[str, Any]:
    """Neues UI in Cache schreiben und 32B-Bau-Pfad dokumentieren."""
    root = Path(root)
    steps: list[Dict[str, Any]] = []

    mandate: Dict[str, Any] = {}
    if king_handoff:
        try:
            from analytics.r3_build_mandate import build_r3_local_mandate, notify_king_build_handoff

            mandate = build_r3_local_mandate(root, topic="gui")
            handoff = notify_king_build_handoff(root, mandate)
            steps.append({"step": "king_32b_mandate", "ok": True, "headline_de": mandate.get("headline_de")})
            steps.append({"step": "king_handoff", "ok": bool(handoff.get("ok", True)), "detail": handoff})
        except Exception as exc:
            steps.append({"step": "king_handoff", "ok": False, "error_de": str(exc)[:160]})

    try:
        from analytics.r3_runtime_upgrade import align_r3_surface

        align = align_r3_surface(root, scan_upgrades=False, warm_cache=False, persist=True)
        steps.append({"step": "align", "ok": bool(align.get("ok", True))})
    except Exception as exc:
        steps.append({"step": "align", "ok": False, "error_de": str(exc)[:160]})

    try:
        from analytics.r3_build_mandate import post_build_r3_align

        post = post_build_r3_align(root, mandate_de=mandate.get("mandate_de", ""), build_ok=True)
        steps.append({"step": "post_build_align", "ok": bool(post.get("ok"))})
    except Exception as exc:
        steps.append({"step": "post_build_align", "ok": False, "error_de": str(exc)[:160]})

    try:
        from analytics.r3_home_ownership import run_post_login_hook

        own_doc = run_post_login_hook(root)
        steps.append(
            {
                "step": "post_login_ownership",
                "ok": bool(own_doc.get("ok")),
                "fixed": own_doc.get("fixed_count"),
            }
        )
    except Exception as exc:
        steps.append({"step": "post_login_ownership", "ok": False, "error_de": str(exc)[:160]})

    try:
        from analytics.r3_desktop_os import install_r3_exec_mirror_app
        from analytics.r3_desktop_icon import install_r3_desktop_icons

        icon_doc = install_r3_desktop_icons(root)
        app_doc = install_r3_exec_mirror_app(root, session_autostart=False)
        steps.append(
            {
                "step": "desktop_icon",
                "ok": bool(icon_doc.get("ok")),
                "png": icon_doc.get("png_sizes_ok"),
                "desktop": bool(app_doc.get("ok")),
            }
        )
    except Exception as exc:
        steps.append({"step": "desktop_icon", "ok": False, "error_de": str(exc)[:160]})

    body = b""
    try:
        from analytics.r3_exec_mirror import render_r3_exec_mirror_page
        from analytics.desktop_shell_cache import write_desktop_cache

        body = render_r3_exec_mirror_page(root)
        write_desktop_cache(root, body, fast=False)
        ok_ui = b"--r3-orange" in body and b"r3-stack" in body
        steps.append({"step": "render_cache", "ok": ok_ui, "bytes": len(body)})
    except Exception as exc:
        steps.append({"step": "render_cache", "ok": False, "error_de": str(exc)[:160]})

    try:
        proc = subprocess.run(
            [str(_py(root)), str(root / "tools/preview_hub.py"), "--ensure", "--restart"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        steps.append({"step": "hub_restart", "ok": proc.returncode == 0, "rc": proc.returncode})
    except Exception as exc:
        steps.append({"step": "hub_restart", "ok": False, "error_de": str(exc)[:120]})

    ok = all(s.get("ok", False) for s in steps if s.get("step") == "render_cache")
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": ok,
        "visible_ui": b"--r3-orange" in body,
        "bytes": len(body),
        "steps": steps,
        "headline_de": "R3 UI sichtbar" if ok else "R3 UI — Cache prüfen",
        "surface_de": "http://127.0.0.1:17890/r3",
        "king_path_de": "bash tools/king_ops.sh r3-bau gui",
        "reload_de": "Browser: Strg+Shift+R auf /r3",
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
