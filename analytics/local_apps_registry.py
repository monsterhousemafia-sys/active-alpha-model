"""Lokale PC-Anwendungen — Inventar, Audit, Desktop-Sichtbarkeit."""
from __future__ import annotations

import html
import json
import os
import shutil
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_MANIFEST_REL = Path("control/local_apps_manifest.json")
_EVIDENCE_REL = Path("evidence/local_apps_audit_latest.json")
_HUB_PORT = 17890


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


def load_local_apps_manifest(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _MANIFEST_REL)


def is_exec_mirror_only(root: Path) -> bool:
    """True wenn nur der R3-Exekutiv-Spiegel aktiv sein soll (control/local_apps_manifest.json)."""
    return str(load_local_apps_manifest(root).get("status") or "").upper() == "EXEC_MIRROR_ONLY"


_EXEC_MIRROR_GET = frozenset(
    {
        "/login",
        "/r3",
        "/desktop",
        "/join",
        "/legion",
        "/api/health",
        "/api/share",
        "/api/federation",
        "/api/compute",
        "/api/legion",
        "/api/h1/dispatch",
        "/api/h1/manifest",
        "/api/h1/asset",
        "/api/h1/artifacts",
        "/api/r3/mirror",
        "/api/r3/operator-readiness",
        "/api/r3/freigabe",
        "/api/system/status",
        "/api/session/status",
    }
)
_EXEC_MIRROR_POST = frozenset(
    {
        "/api/session/start",
        "/api/session/end",
        "/api/r3/order",
        "/api/worker/register",
        "/api/worker/contribute",
        "/api/h1/artifact/upload",
    }
)


def exec_mirror_route_allowed(method: str, path: str) -> bool:
    """Erlaubte Hub-Routen im EXEC_MIRROR_ONLY-Modus — alles andere ist Legacy."""
    p = path if str(path).startswith("/") else f"/{path}"
    m = str(method or "GET").upper()
    if m == "GET":
        return p in _EXEC_MIRROR_GET
    if m == "POST":
        return p in _EXEC_MIRROR_POST
    if m == "OPTIONS":
        return True
    return False


def _hub_probe(path: str, *, port: int = _HUB_PORT) -> bool:
    p = path if str(path).startswith("/") else f"/{path}"
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.2) as sock:
            sock.sendall(
                f"GET {p} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode("ascii")
            )
            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        if b"\r\n\r\n" not in data:
            return False
        head = data.split(b"\r\n\r\n", 1)[0].decode("ascii", errors="ignore")
        return " 200 " in head or " 302 " in head
    except OSError:
        return False


def _desktop_installed(desktop_id: str, *, autostart: bool = False) -> bool:
    if not desktop_id:
        return False
    if autostart or desktop_id in (
        "r3-os-session.desktop",
        "xdg-user-session.desktop",
    ):
        return (Path.home() / ".config/autostart" / desktop_id).is_file()
    return (Path.home() / ".local/share/applications" / desktop_id).is_file()


def _desktop_page_ok(root: Path, *, port: int = _HUB_PORT) -> tuple[bool, str]:
    if not _hub_probe("/api/health", port=port):
        return False, "Hub /api/health nicht erreichbar"
    page_py = Path(root) / "analytics/preview_hub_page.py"
    if not page_py.is_file():
        return False, "preview_hub_page.py fehlt"
    try:
        text = page_py.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        return False, str(exc)[:120]
    needed = (
        "render_desktop_shell_page",
        "r3-desktop",
        "r3-only-mark",
    )
    missing = [n for n in needed if n not in text]
    if missing:
        return False, f"Desktop-Renderer fehlt: {', '.join(missing)}"
    return True, "OK"


def _audit_shell_feature(root: Path, fid: str) -> Dict[str, Any]:
    try:
        from analytics.r3_ubuntu_shell import _feature_available, _feature_map

        spec = _feature_map(root).get(fid) or {}
        ok = bool(spec) and _feature_available(root, spec)
        return {"ok": ok, "detail_de": spec.get("detail_de") or fid}
    except Exception as exc:
        return {"ok": False, "detail_de": str(exc)[:120]}


def audit_local_app(root: Path, app: Dict[str, Any], *, port: int = _HUB_PORT) -> Dict[str, Any]:
    root = Path(root)
    aid = str(app.get("id") or "")
    tier = str(app.get("tier") or "core")
    label = str(app.get("label_de") or aid)
    issues: List[str] = []
    ok = True

    exec_rel = str(app.get("exec_rel") or "").strip()
    if exec_rel:
        path = root / exec_rel
        if not path.is_file():
            ok = False
            issues.append(f"Launcher fehlt: {exec_rel}")
        elif not os.access(path, os.X_OK) and path.suffix in (".sh", ""):
            issues.append(f"Nicht ausführbar: {exec_rel}")

    hub_path = str(app.get("hub_path") or "").strip()
    if hub_path:
        if hub_path == "/desktop":
            page_ok, page_detail = _desktop_page_ok(root, port=port)
            if not page_ok:
                ok = False
                issues.append(page_detail)
        elif tier == "link":
            if not _hub_probe(hub_path, port=port):
                issues.append(f"Hub-Link offline: {hub_path} (Hub starten)")
        elif not _hub_probe(hub_path, port=port):
            ok = False
            issues.append(f"Hub nicht erreichbar: {hub_path}")

    desktop_id = str(app.get("desktop_id") or "").strip()
    autostart = bool(app.get("autostart"))
    if desktop_id and not _desktop_installed(desktop_id, autostart=autostart):
        issues.append(f"Desktop-Eintrag fehlt: {desktop_id}")
        if tier == "core":
            ok = False

    shell_id = str(app.get("shell_id") or "").strip()
    if shell_id:
        sh = _audit_shell_feature(root, shell_id)
        if not sh.get("ok"):
            ok = False
            issues.append(f"Shell-Feature nicht verfügbar: {shell_id}")

    shell_ids = list(app.get("shell_ids") or [])
    if shell_ids:
        bad = []
        for sid in shell_ids:
            sh = _audit_shell_feature(root, str(sid))
            if not sh.get("ok"):
                bad.append(str(sid))
        if bad:
            ok = False
            issues.append(f"System-Panels fehlen: {', '.join(bad)}")

    gui_rel = str(app.get("gui_exec_rel") or "").strip()
    if gui_rel:
        gpath = root / gui_rel
        if not gpath.is_file():
            issues.append(f"GUI-Launcher fehlt: {gui_rel}")

    if tier == "infra":
        if issues:
            issues = [f"[infra] {i}" for i in issues]
        ok = ok and bool(exec_rel or hub_path)

    if tier == "link" and not exec_rel:
        ok = False
        issues.append("Link-Launcher fehlt")

    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if tier == "core" and aid in ("cockpit", "markt", "session") and not display:
        issues.append("Kein Display — GUI nur mit Desktop-Session")

    if aid == "cockpit" and hub_path == "":
        page_ok, page_detail = _desktop_page_ok(root, port=port)
        if not page_ok:
            issues.append(page_detail)

    return {
        "id": aid,
        "tier": tier,
        "label_de": label,
        "ok": ok,
        "issues_de": issues,
        "detail_de": "OK" if ok and not issues else (issues[0] if issues else "Prüfen"),
    }


def build_local_apps_audit(
    root: Path,
    *,
    port: int = _HUB_PORT,
    persist: bool = True,
    probe_hub: bool = True,
    include_runtime: bool = False,
) -> Dict[str, Any]:
    root = Path(root)
    manifest = load_local_apps_manifest(root)
    apps_in = list(manifest.get("apps") or [])
    audited = []
    for row in apps_in:
        if not isinstance(row, dict):
            continue
        if not probe_hub and str(row.get("hub_path") or "").strip():
            audited.append(
                {
                    **audit_local_app(root, {**row, "hub_path": ""}, port=port),
                    "id": str(row.get("id") or ""),
                    "label_de": str(row.get("label_de") or ""),
                    "tier": str(row.get("tier") or "core"),
                    "ok": True,
                    "issues_de": [],
                    "detail_de": "Hub (Anzeige)",
                }
            )
        else:
            audited.append(audit_local_app(root, row, port=port))
    runtime_doc: Dict[str, Any] = {}
    if include_runtime:
        try:
            from analytics.local_apps_runtime import build_runtime_audit

            runtime_doc = build_runtime_audit(root, apps_in, port=port)
            rt_map = {str(r.get("id")): r for r in (runtime_doc.get("apps") or [])}
            for row in audited:
                rt = rt_map.get(str(row.get("id"))) or {}
                row["runtime_ok"] = bool(rt.get("runtime_ok"))
                row["runtime_detail_de"] = rt.get("runtime_detail_de")
                row["start_cmd_de"] = rt.get("start_cmd_de")
                try:
                    from analytics.local_app_urls import app_start_display_de

                    row["local_start_de"] = app_start_display_de(root, row, port=port)
                except Exception:
                    row["local_start_de"] = row.get("start_cmd_de") or ""
                if rt and not rt.get("runtime_ok"):
                    row["ok"] = False
                    issues = list(row.get("issues_de") or [])
                    issues.append(f"Laufzeit: {rt.get('runtime_detail_de')}")
                    row["issues_de"] = issues
                    row["detail_de"] = issues[0]
        except Exception as exc:
            runtime_doc = {"error_de": str(exc)[:120], "all_ok": False}
    ok_n = sum(1 for a in audited if a.get("ok"))
    rt_ok = int(runtime_doc.get("ok_count") or ok_n) if include_runtime else ok_n
    all_ok = ok_n == len(audited) and len(audited) > 0
    if include_runtime and runtime_doc:
        all_ok = all_ok and bool(runtime_doc.get("all_ok"))
    doc = {
        "schema_version": 2 if include_runtime else 1,
        "updated_at_utc": _utc_now(),
        "headline_de": manifest.get("headline_de"),
        "display_available": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "hub_port": int(port),
        "total": len(audited),
        "ok_count": ok_n,
        "runtime_ok_count": rt_ok,
        "fail_count": len(audited) - ok_n,
        "all_ok": all_ok,
        "runtime": runtime_doc if include_runtime else None,
        "apps": audited,
        "next_de": "bash tools/king_ops.sh apps-run",
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def build_32b_apps_mandate(root: Path) -> str:
    audit = build_local_apps_audit(root, persist=True, include_runtime=True)
    failing = [a for a in (audit.get("apps") or []) if not a.get("ok")]
    lines = [
        "König-Mandat: Alle Anwendungen für den User prüfen und LAUFFÄHIG machen.",
        f"Datei-Audit: {audit.get('ok_count')}/{audit.get('total')}.",
        f"Laufzeit: {audit.get('runtime_ok_count', '—')}/{audit.get('total')}.",
        "Lies control/local_apps_manifest.json, evidence/local_apps_audit_latest.json, evidence/local_apps_runtime_latest.json.",
        "Ziel: Jede App startbar — Cockpit, Hub, Desktop, Bash, GPT-4o, Aktien, Shell-Kacheln, Agent.",
        "Repariere nur analytics/, tools/, control/, tests/ — Safety fail-closed, keine Orders.",
    ]
    for app in failing[:14]:
        start = app.get("start_cmd_de") or ""
        lines.append(
            f"- {app.get('id')}: {app.get('label_de')} — {', '.join(app.get('issues_de') or [])} Start: {start}"
        )
    if not failing:
        lines.append(
            "Alle Smoke-Tests grün — verifiziere trotzdem: bash tools/r3_desktop_health.sh, "
            "bash tools/marktanalyse_bash.sh start, bash tools/bash_gpt4o.sh status, Hub /desktop Cache."
        )
    lines.extend(
        [
            "Pflicht: tools/r3_desktop_os.py ptyxis, desktop_shell_cache fast render, bash_gpt4o.sh.",
            "Nach jedem write_file: .venv/bin/python -m pytest tests/test_local_apps_runtime.py tests/test_local_apps_registry.py -q.",
            "Dann: bash tools/setup_r3_desktop_os.sh und bash tools/r3_desktop_health.sh.",
            "finish wenn Laufzeit-Audit all_ok und User kann alle Apps aus local_apps_manifest starten.",
        ]
    )
    return " ".join(lines)


def render_local_apps_section(
    root: Path,
    audit: Optional[Dict[str, Any]] = None,
    *,
    probe_hub: bool = False,
) -> str:
    root = Path(root)
    doc = audit or build_local_apps_audit(root, persist=False, probe_hub=probe_hub)
    apps = list(doc.get("apps") or [])
    rows = []
    try:
        from analytics.local_app_urls import app_start_display_de
    except Exception:
        app_start_display_de = None  # type: ignore
    for app in apps:
        cls = "ok" if app.get("ok") else "fail"
        issues = app.get("issues_de") or []
        start_de = str(app.get("local_start_de") or "")
        if not start_de and app_start_display_de:
            start_de = app_start_display_de(root, app)
        detail = start_de or app.get("detail_de") or (issues[0] if issues else "—")
        rows.append(
            f'<div class="la-tile {cls}">'
            f'<div class="la-label">{html.escape(str(app.get("label_de") or ""))}</div>'
            f'<div class="la-tier">{html.escape(str(app.get("tier") or ""))}</div>'
            f'<div class="la-detail">{html.escape(str(detail)[:120])}</div>'
            f"</div>"
        )
    ok_n = int(doc.get("ok_count") or 0)
    total = int(doc.get("total") or 0)
    return f"""
<section class="desktop-extra local-apps" id="local-apps" aria-label="Lokale Anwendungen">
  <h2>Lokale Anwendungen ({ok_n}/{total})</h2>
  <div class="la-grid">{''.join(rows)}</div>
  <p class="desktop-kv-detail">32B fertigstellen: <code>bash tools/king_ops.sh local-apps</code></p>
</section>"""


LOCAL_APPS_CSS = """
.la-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 8px; }
@media (max-width: 900px) { .la-grid { grid-template-columns: repeat(2, 1fr); } }
.la-tile {
  padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line);
  background: rgba(127,127,127,.06);
}
.la-tile.ok { border-color: rgba(52,199,89,.35); background: rgba(52,199,89,.07); }
.la-tile.fail { border-color: rgba(255,59,48,.35); background: rgba(255,59,48,.06); }
.la-label { font-size: 13px; font-weight: 600; }
.la-tier { font-size: 10px; text-transform: uppercase; color: var(--muted); margin-top: 2px; }
.la-detail { font-size: 10px; color: var(--muted); margin-top: 4px; line-height: 1.3; }
"""
