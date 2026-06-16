#!/usr/bin/env python3
"""Preview Command Center — lokaler Hub (HTTP) für Cockpit + Operator-Aktionen."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 17890
_META_REL = Path("evidence/preview_hub.json")
_LOG_REL = Path("evidence/preview_hub.log")


def _project_root() -> Path:
    return Path(os.environ.get("AA_PROJECT_ROOT", "").strip() or ROOT)


def _ensure_import_path(root: Path) -> Path:
    root = Path(root)
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return root


def _py(root: Path) -> str:
    v = root / ".venv/bin/python3"
    return str(v) if v.is_file() else sys.executable


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _http_probe(port: int, path: str = "/api/health", *, host: str = "127.0.0.1", timeout: float = 2.0) -> bytes:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            req = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            sock.sendall(req)
            chunks: list[bytes] = []
            while True:
                block = sock.recv(65536)
                if not block:
                    break
                chunks.append(block)
        return b"".join(chunks)
    except OSError:
        return b""


def _hub_healthy(port: int, *, host: str = "127.0.0.1") -> bool:
    """Leichtgewichtiger Health-Check — delegiert an hub_runtime (Schema v2)."""
    try:
        from analytics.hub_runtime import is_healthy

        return bool(is_healthy(int(port), host=host, timeout=0.8))
    except Exception:
        return False


def _hub_route_ready(port: int, path: str = "/login", *, host: str = "127.0.0.1") -> bool:
    """Prüft ob Hub-Routen existieren (kein R3-Mirror — siehe r3_runtime)."""
    raw = _http_probe(port, path, host=host, timeout=2.0)
    if not raw:
        return False
    status = raw.split(b"\r\n", 1)[0]
    if b" 404 " in status:
        return False
    return b" 200 " in status or b" 302 " in status


def _safe_write(handler: BaseHTTPRequestHandler, body: bytes) -> None:
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


def _hub_log_path(root: Path) -> Path:
    return Path(root) / _LOG_REL


def _append_hub_log(root: Path, message: str) -> None:
    path = _hub_log_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{stamp}] {message}\n")
    if "failed" in message.lower() or "error" in message.lower():
        try:
            from analytics.runtime_structured_log import emit_runtime_log

            emit_runtime_log("aa-hub", "hub_log", level="error", root=root, message=message[:500])
        except Exception:
            pass


def _load_meta_pid(root: Path) -> Optional[int]:
    path = Path(root) / _META_REL
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        pid = int(doc.get("pid") or 0)
        return pid if pid > 0 else None
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _hub_process_root(pid: int) -> Optional[Path]:
    try:
        cwd = Path(f"/proc/{pid}/cwd").resolve()
    except OSError:
        return None
    return cwd if (cwd / "tools" / "preview_hub.py").is_file() else None


def _kill_foreign_hubs(
    root: Path,
    port: int,
    *,
    keep_pid: Optional[int] = None,
    keep_meta: bool = True,
) -> None:
    """Beendet fremde und doppelte preview_hub-Prozesse."""
    root = Path(root).resolve()
    king = str(root)
    me = os.getpid()
    king_meta_pid = _load_meta_pid(root) if keep_meta else None
    keeper = keep_pid if keep_pid is not None else (
        king_meta_pid if king_meta_pid and king_meta_pid != me else None
    )
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "preview_hub.py"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            if "pgrep" in line:
                continue
            parts = line.strip().split(None, 1)
            if not parts:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            if pid == me or (keeper and pid == keeper):
                continue
            proc_root = _hub_process_root(pid)
            same_project = proc_root == root or king in line
            if same_project or proc_root is None:
                try:
                    os.kill(pid, 15)
                    time.sleep(0.15)
                    os.kill(pid, 9)
                    label = "doppelten" if same_project else "fremden"
                    _append_hub_log(root, f"{label} Hub beendet: {pid} ({proc_root or '?'})")
                except OSError:
                    pass
                continue
            try:
                os.kill(pid, 9)
                _append_hub_log(root, f"fremden Hub beendet: {pid} ({proc_root or '?'})")
            except OSError:
                pass
    except (subprocess.TimeoutExpired, OSError):
        pass


def _release_hub_daemon_lock(root: Path) -> None:
    """Stale flock nach Zombie-Daemon entfernen."""
    lock_path = Path(root) / "evidence/preview_hub_daemon.lock"
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _stop_hub(root: Path, port: int) -> None:
    root = Path(root)
    _kill_foreign_hubs(root, port, keep_meta=False)
    _release_hub_daemon_lock(root)
    if _port_listening(port):
        _append_hub_log(root, f"Port :{port} noch belegt — warte auf Freigabe")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _port_listening(port):
            time.sleep(0.2)


def _write_meta(root: Path, port: int, pid: int) -> None:
    from aa_safe_io import atomic_write_json

    root = Path(root)
    path = root / _META_REL
    uptime_path = root / "evidence/preview_hub_uptime.json"
    try:
        from analytics.preview_federation import hub_public_base_url

        share = hub_public_base_url(root, port=port)
    except Exception:
        share = f"http://127.0.0.1:{port}/"
    uptime_doc = {}
    if uptime_path.is_file():
        try:
            uptime_doc = json.loads(uptime_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            uptime_doc = {}
    if not uptime_doc.get("first_started_utc"):
        uptime_doc["first_started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    uptime_doc["last_started_utc"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    atomic_write_json(uptime_path, uptime_doc)
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "port": port,
            "pid": pid,
            "url": f"http://127.0.0.1:{port}/",
            "share_url": share,
        },
    )


def _load_report(root: Path) -> Dict[str, Any]:
    path = root / "evidence/gui_preview_latest.json"
    if not path.is_file():
        return {"overall_pass": False, "passed": 0, "total": 0, "report_de": "Noch kein Preview-Lauf."}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _render_page(root: Path, *, port: int, request_host: Optional[str] = None) -> str:
    """Launch + vollständiges Preview-Abbild (einheitliche Hub-Seite)."""
    root = _ensure_import_path(Path(root))
    from analytics.preview_hub_page import render_hub_launch_page

    return render_hub_launch_page(root, port=port, request_host=request_host).decode("utf-8")


def _error_html(title: str, detail: str) -> str:
    safe_title = title.replace("<", "&lt;")
    safe_detail = detail.replace("<", "&lt;")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{safe_title}</title></head><body>"
        f"<h1>{safe_title}</h1><pre>{safe_detail}</pre>"
        "<p>Neustart: <code>r3-cockpit</code> oder "
        "<code>python3 tools/preview_hub.py --ensure --restart</code></p>"
        "</body></html>"
    )


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    _safe_write(handler, body)


def _run_action(root: Path, action_id: str) -> Dict[str, Any]:
    action_id = str(action_id or "").strip().lower()
    if not action_id:
        return {"ok": False, "message_de": "Keine Aktion angegeben."}

    try:
        if action_id == "refresh-snap":
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = _refresh_snapshot_impl(root, force_quotes=False, force_sync=True)
            return {"ok": True, "message_de": f"Konto {float((snap.get('broker') or {}).get('cash_eur') or 0):,.2f} €", "snap_traffic": snap.get("traffic")}

        if action_id == "daily-mark":
            from ui.live_trading_dashboard.service import action_daily_mark

            out = action_daily_mark(root)
            return {"ok": bool(out.get("ok", True)), "message_de": str(out.get("message_de") or out.get("summary_de") or "Mark fertig")[:400]}

        if action_id == "signal":
            from ui.live_trading_dashboard.service import action_signal_update

            out = action_signal_update(root)
            return {"ok": bool(out.get("ok", True)), "message_de": str(out.get("message_de") or out.get("summary_de") or "Signal fertig")[:400]}

        if action_id == "plan-orders":
            from ui.live_trading_dashboard.service import _refresh_snapshot_impl

            snap = _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
            po = snap.get("portfolio_orders") or {}
            return {
                "ok": True,
                "message_de": str(po.get("summary_de") or "Keine Orders")[:400],
                "portfolio_orders": po,
            }

        if action_id == "order-desk":
            launcher = root / "run_marktanalyse_linux.sh"
            if not launcher.is_file():
                return {"ok": False, "message_de": "Order-Desk Launcher fehlt."}
            env = os.environ.copy()
            env["AA_LINUX_NATIVE_APP"] = "1"
            env["AA_PROJECT_ROOT"] = str(root)
            subprocess.Popen(
                [str(launcher)],
                cwd=str(root),
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"ok": True, "message_de": "Order-Desk öffnet — Rebalance & Orders mit GUI-Bestätigung."}

        if action_id == "trading-day":
            from analytics.trading_day_orchestrator import run_trading_day_orchestrator

            out = run_trading_day_orchestrator(root, phase="full", force=True)
            return {"ok": bool(out.get("ok", True)), "message_de": str(out.get("summary_de") or "Trading-Day fertig")[:400]}

        if action_id == "learn":
            from analytics.post_order_learning import run_post_order_learning

            out = run_post_order_learning(root)
            return {"ok": bool(out.get("ok", True)), "message_de": str(out.get("summary_de") or "Lernen fertig")[:400]}

        if action_id == "circle":
            from analytics.closed_loop_score import refresh_closed_loop_score

            doc = refresh_closed_loop_score(root)
            return {"ok": True, "message_de": str(doc.get("headline_de") or "Kreis aktualisiert")[:400]}

        if action_id == "refresh-preview":
            from ui.live_trading_dashboard.gui_preview_harness import run_full_gui_preview

            report = run_full_gui_preview(root, refresh_snap=False, mode="stable")
            try:
                from analytics.preview_freshness import mark_gui_preview_done

                if report.get("overall_pass"):
                    mark_gui_preview_done(root, mode="stable")
            except Exception:
                pass
            return {
                "ok": bool(report.get("overall_pass")),
                "message_de": f"Preview {report.get('passed')}/{report.get('total')} OK",
                "reload": True,
            }

        if action_id == "share-preview":
            from analytics.preview_federation import build_share_package

            pkg = build_share_package(root)
            return {
                "ok": True,
                "message_de": f"Teilen: {pkg.get('join_url')}",
                "share": pkg,
            }

        if action_id == "sync-broker":
            from ui.live_trading_dashboard.service import action_sync_broker

            out = action_sync_broker(root)
            return {"ok": bool(out.get("ok")), "message_de": str(out.get("message_de") or "Sync")[:400]}

        return {"ok": False, "message_de": f"Unbekannte Aktion: {action_id}"}
    except Exception as exc:
        return {
            "ok": False,
            "message_de": str(exc)[:300],
            "error_type": type(exc).__name__,
            "traceback": traceback.format_exc()[-500:],
        }


def _request_host(handler: BaseHTTPRequestHandler) -> Optional[str]:
    host = str(handler.headers.get("Host") or "").strip()
    return host or None


def _request_client_ip(handler: BaseHTTPRequestHandler) -> str:
    return str(handler.client_address[0] or "127.0.0.1")


def _serve_vault(
    handler: BaseHTTPRequestHandler,
    root: Path,
    *,
    method: str,
    path: str,
    query: str,
    content_type: str,
    body: bytes,
) -> bool:
    """Vault-Bridge — True wenn Anfrage bedient wurde."""
    if not path.startswith("/local/vault"):
        return False
    _ensure_import_path(root)
    from analytics.vault_hub_bridge import handle_vault_request

    status, ctype, payload = handle_vault_request(
        root,
        method=method,
        path=path,
        query=query,
        client_ip=_request_client_ip(handler),
        content_type=content_type,
        body=body,
    )
    handler.send_response(status)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.end_headers()
    _safe_write(handler, payload)
    return True


def _exec_mirror_route_blocked(
    handler: BaseHTTPRequestHandler,
    root: Path,
    *,
    method: str,
    path: str,
) -> bool:
    """Fail-closed: Legacy-Routen im Spiegel-Modus mit 410 beantworten."""
    from analytics.local_apps_registry import exec_mirror_route_allowed, is_exec_mirror_only

    if not is_exec_mirror_only(root):
        return False
    if exec_mirror_route_allowed(method, path):
        return False
    msg = {
        "ok": False,
        "error": "EXEC_MIRROR_ONLY",
        "message_de": (
            f"Route {path} ist im Spiegel-Modus deaktiviert. "
            "Nutze r3 → /r3 (Ergebnisse + Auftrag)."
        ),
    }
    body = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    handler.send_response(410)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    _safe_write(handler, body)
    return True


def make_handler(root: Path, port: int):
    class PreviewHubHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-AA-Join-Token, X-AA-Chunk-Id, X-AA-Worker-Id, X-AA-Run-Dir",
            )
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            req_host = _request_host(self)
            try:
                if path.startswith("/local/vault"):
                    if _serve_vault(
                        self,
                        root,
                        method="GET",
                        path=path,
                        query=parsed.query,
                        content_type="",
                        body=b"",
                    ):
                        return
                if path in ("/favicon.ico", "/assets/r3-icon.svg", "/assets/r3-favicon.svg"):
                    icon_file = root / "assets/r3-os-icon.svg"
                    if icon_file.is_file():
                        body = icon_file.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Cache-Control", "public, max-age=86400")
                        self.end_headers()
                        _safe_write(self, body)
                        return
                if path in ("/", "/index.html"):
                    from analytics.local_apps_registry import is_exec_mirror_only

                    if is_exec_mirror_only(root):
                        from analytics.r3_session_manager import is_r3_session_active

                        dest = "/r3" if is_r3_session_active(root) else "/login"
                        self.send_response(302)
                        self.send_header("Location", dest)
                        self.end_headers()
                        return
                    body = _render_page(root, port=port, request_host=req_host).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if _exec_mirror_route_blocked(self, root, method="GET", path=path):
                    return
                if path == "/legion":
                    from analytics.federation_legion import render_legion_html
                    from analytics.preview_federation import hub_public_base_url

                    base = hub_public_base_url(root, port=port, request_host=req_host)
                    body = render_legion_html(root, hub_base=base).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/login":
                    _ensure_import_path(root)
                    from analytics.r3_login_shell import render_login_page

                    body = render_login_page(root, port=port)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/agent":
                    _ensure_import_path(root)
                    from analytics.alpha_model_agent_home import (
                        chamber_local_only,
                        is_loopback_client,
                        render_chamber_local_gate_html,
                    )

                    remote = chamber_local_only(root) and not is_loopback_client(
                        _request_client_ip(self)
                    )
                    body = render_chamber_local_gate_html(root, remote=remote).encode("utf-8")
                    self.send_response(403 if remote else 200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path in ("/r3", "/desktop"):
                    _ensure_import_path(root)
                    from analytics.r3_session_manager import is_r3_session_active
                    from analytics.r3_surface import (
                        CANONICAL_SURFACE_PATH,
                        is_exec_mirror_surface,
                    )

                    if not is_r3_session_active(root):
                        self.send_response(302)
                        self.send_header("Location", "/login")
                        self.end_headers()
                        return
                    if is_exec_mirror_surface(root) and path == "/desktop":
                        self.send_response(302)
                        self.send_header("Location", CANONICAL_SURFACE_PATH)
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        return
                    from analytics.desktop_shell_cache import get_desktop_html_for_hub, warm_desktop_cache

                    body = get_desktop_html_for_hub(
                        root, port=port, fast=True, live_prep=False
                    )
                    warm_desktop_cache(
                        root, port=port, fast=True, block=False, live_prep=True
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/launch":
                    _ensure_import_path(root)
                    from analytics.preview_hub_page import render_world_launch_hub_page

                    body = render_world_launch_hub_page(root, port=port)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/join":
                    from analytics.preview_federation import hub_public_base_url, render_join_html

                    base = hub_public_base_url(root, port=port, request_host=req_host)
                    body = render_join_html(root, hub_base=base).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/download":
                    _ensure_import_path(root)
                    from analytics.preview_federation import hub_public_base_url
                    from analytics.ulwo_launch import render_download_page

                    base = hub_public_base_url(root, port=port, request_host=req_host)
                    body = render_download_page(root, hub=base)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/api/ulwo/bundle.zip":
                    _ensure_import_path(root)
                    zpath = root / "evidence/exports/Universal_Lite_Worker_OS.zip"
                    if not zpath.is_file():
                        from analytics.ulwo_launch import build_ulwo_bundle

                        build_ulwo_bundle(root)
                    if not zpath.is_file():
                        self.send_error(404)
                        return
                    data = zpath.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", 'attachment; filename="Universal_Lite_Worker_OS.zip"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    _safe_write(self, data)
                    return
                if path == "/api/ulwo/install.sh":
                    _ensure_import_path(root)
                    from analytics.preview_federation import hub_public_base_url
                    from analytics.ulwo_launch import build_install_script

                    base = hub_public_base_url(root, port=port, request_host=req_host)
                    body = build_install_script(root, hub=base).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/x-shellscript; charset=utf-8")
                    self.send_header("Content-Disposition", 'attachment; filename="ulwo-install.sh"')
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    _safe_write(self, body)
                    return
                if path == "/api/ulwo/launch":
                    _ensure_import_path(root)
                    from analytics.ulwo_launch import MANIFEST_REL, _load_json

                    doc = _load_json(root / MANIFEST_REL)
                    if not doc:
                        from analytics.ulwo_launch import launch_ulwo

                        doc = launch_ulwo(root)
                    _json_response(self, 200, doc)
                    return
                if path == "/api/federation":
                    _ensure_import_path(root)
                    from analytics.preview_federation import build_federation_summary

                    _json_response(self, 200, build_federation_summary(root, request_host=req_host))
                    return
                if path == "/api/compute":
                    _ensure_import_path(root)
                    from analytics.federation_assignments import build_assignment_status
                    from analytics.federation_compute import build_utilization_summary, load_compute_queue

                    qs = parse_qs(parsed.query)
                    if (qs.get("assignments") or [""])[0] in ("1", "true", "yes"):
                        _json_response(self, 200, build_assignment_status(root))
                        return
                    _json_response(
                        self,
                        200,
                        {"utilization": build_utilization_summary(root), "queue": load_compute_queue(root)},
                    )
                    return
                if path == "/api/legion":
                    _ensure_import_path(root)
                    from analytics.federation_legion import build_legion_summary

                    _json_response(self, 200, build_legion_summary(root))
                    return
                if path == "/api/h1/dispatch":
                    _ensure_import_path(root)
                    from analytics.h1_federation_dispatch import load_dispatch_plan

                    _json_response(self, 200, load_dispatch_plan(root))
                    return
                if path == "/api/h1/manifest":
                    _ensure_import_path(root)
                    from analytics.h1_federation_dispatch import build_h1_asset_manifest, inspect_h1_run

                    inspect = inspect_h1_run(root)
                    run_dir = str(inspect.get("run_dir") or "")
                    if not run_dir:
                        _json_response(self, 404, {"ok": False, "message_de": "Kein H1-Lauf"})
                        return
                    _json_response(self, 200, build_h1_asset_manifest(root, run_dir))
                    return
                if path == "/api/h1/asset":
                    _ensure_import_path(root)
                    from analytics.h1_artifact_transport import serve_h1_asset

                    qs = parse_qs(parsed.query)
                    run_dir = str((qs.get("run_dir") or [""])[0] or "")
                    filename = str((qs.get("file") or [""])[0] or "")
                    join_token = str((qs.get("join_token") or [""])[0] or "")
                    asset_path, mime, err = serve_h1_asset(
                        root, run_rel=run_dir, filename=filename, join_token=join_token
                    )
                    if err or asset_path is None:
                        _json_response(self, 403 if err == "join_token ungültig" else 404, {"ok": False, "message_de": err or "—"})
                        return
                    data = asset_path.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", mime or "application/octet-stream")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Content-Disposition", f'attachment; filename="{asset_path.name}"')
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    _safe_write(self, data)
                    return
                if path == "/api/h1/artifacts":
                    _ensure_import_path(root)
                    from analytics.h1_artifact_transport import list_prep_artifacts

                    _json_response(self, 200, list_prep_artifacts(root))
                    return
                if path == "/api/manifest":
                    _ensure_import_path(root)
                    from analytics.preview_manifest import load_preview_manifest

                    _json_response(self, 200, load_preview_manifest(root))
                    return
                if path == "/api/share":
                    _ensure_import_path(root)
                    from analytics.preview_federation import build_share_package

                    _json_response(self, 200, build_share_package(root, port=port, request_host=req_host))
                    return
                if path == "/api/cockpit":
                    _ensure_import_path(root)
                    from analytics.preview_cockpit import build_preview_cockpit

                    snap = None
                    try:
                        from ui.live_trading_dashboard.gui_preview_harness import _load_snap_for_gui

                        snap = _load_snap_for_gui(root, None, allow_refresh=False)
                    except Exception:
                        pass
                    _json_response(self, 200, build_preview_cockpit(root, snap=snap))
                    return
                if path == "/api/prognose/secrets":
                    _ensure_import_path(root)
                    from analytics.r3_prognose_secrets import build_prognose_secrets_doc

                    _json_response(self, 200, build_prognose_secrets_doc(root))
                    return
                if path == "/api/forschungszweig":
                    _ensure_import_path(root)
                    from analytics.r3_forschungszweig import build_forschungszweig_status

                    _json_response(self, 200, build_forschungszweig_status(root))
                    return
                if path == "/api/pilot/board":
                    _ensure_import_path(root)
                    from analytics.r3_pilot_central import build_pilot_board

                    _json_response(self, 200, build_pilot_board(root))
                    return
                if path == "/api/r3/central":
                    _ensure_import_path(root)
                    from analytics.r3_central_registry import build_r3_central_status

                    _json_response(self, 200, build_r3_central_status(root, persist=True))
                    return
                if path == "/api/r3/flow":
                    _ensure_import_path(root)
                    from analytics.r3_flow_orchestrator import sync_r3_flow

                    refresh = str((parse_qs(urlparse(self.path).query).get("sync") or [""])[0]).lower()
                    if refresh in {"1", "true", "yes"}:
                        _json_response(self, 200, sync_r3_flow(root, warm_cache=True, persist=True))
                    else:
                        from analytics.r3_flow_orchestrator import build_r3_flow_status

                        _json_response(self, 200, build_r3_flow_status(root, persist=True))
                    return
                if path == "/api/r3/platform":
                    _ensure_import_path(root)
                    from analytics.r3_trading_platform import build_r3_trading_platform_status

                    _json_response(self, 200, build_r3_trading_platform_status(root, persist=True))
                    return
                if path == "/api/r3/cycle":
                    _ensure_import_path(root)
                    from analytics.r3_trading_cycle import load_trading_cycle_status, run_trading_cycle

                    qs = parse_qs(urlparse(self.path).query)
                    if (qs.get("run") or [""])[0] in ("1", "true", "yes"):
                        _json_response(self, 200, run_trading_cycle(root))
                    else:
                        _json_response(self, 200, load_trading_cycle_status(root))
                    return
                if path == "/api/r3/engine":
                    _ensure_import_path(root)
                    refresh = str((parse_qs(urlparse(self.path).query).get("tick") or [""])[0]).lower()
                    if refresh in {"1", "true", "yes"}:
                        from analytics.r3_trading_cycle import run_trading_cycle

                        _json_response(self, 200, run_trading_cycle(root))
                    else:
                        from analytics.alpha_model_background_engine import build_engine_status

                        _json_response(self, 200, build_engine_status(root, persist=False))
                    return
                if path == "/api/r3/local":
                    _ensure_import_path(root)
                    refresh = str((parse_qs(urlparse(self.path).query).get("apply") or [""])[0]).lower()
                    if refresh in {"1", "true", "yes"}:
                        from analytics.r3_local_first import apply_r3_local_first

                        _json_response(self, 200, apply_r3_local_first(root))
                    else:
                        from analytics.r3_local_first import verify_r3_local_first

                        _json_response(self, 200, verify_r3_local_first(root))
                    return
                if path == "/api/r3/t212":
                    _ensure_import_path(root)
                    q = parse_qs(urlparse(self.path).query)
                    confirm_acct = str((q.get("confirm_account") or ["0"])[0]).lower() in {
                        "1",
                        "true",
                        "yes",
                    }
                    refresh = str((q.get("sync") or [""])[0]).lower()
                    from analytics.r3_t212_operator_api import resolve_operator_api_state

                    api_state = resolve_operator_api_state(root)
                    if api_state.get("needs_api_setup") and not confirm_acct:
                        _json_response(self, 200, api_state)
                        return
                    if confirm_acct:
                        from analytics.r3_t212_account_identity import confirm_t212_account

                        _json_response(self, 200, confirm_t212_account(root))
                        return
                    if refresh in {"1", "true", "yes"}:
                        from analytics.r3_t212_api_bond import sync_r3_t212_api_bond

                        out = sync_r3_t212_api_bond(root, force=True, persist=True)
                        out = {**out, **resolve_operator_api_state(root)}
                        _json_response(self, 200, out)
                    else:
                        from analytics.r3_t212_api_bond import build_r3_t212_api_bond

                        out = build_r3_t212_api_bond(root, persist=True)
                        out = {**out, **resolve_operator_api_state(root)}
                        _json_response(self, 200, out)
                    return
                if path == "/api/r3/start":
                    _ensure_import_path(root)
                    from analytics.r3_one_click_start import run_one_click_start

                    _json_response(self, 200, run_one_click_start(root, persist=True))
                    return
                if path == "/api/r3/prognosis":
                    _ensure_import_path(root)
                    from analytics.r3_t212_prognosis import build_r3_t212_daily_prognosis

                    q = parse_qs(urlparse(self.path).query)
                    refresh = str((q.get("refresh") or [""])[0]).lower()
                    force = str((q.get("force") or [""])[0]).lower() in {"1", "true", "yes"}
                    if refresh in {"1", "true", "yes"}:
                        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

                        out = ensure_r3_prognosis_fresh(root, force=force, persist=True)
                        doc = out.get("prognosis") or build_r3_t212_daily_prognosis(root, persist=False)
                        _json_response(
                            self,
                            200,
                            {
                                "ok": bool(doc.get("ok")),
                                "refreshed": not out.get("skipped"),
                                "skipped": bool(out.get("skipped")),
                                "prognosis": doc,
                                "worthwhile_buy_count": doc.get("worthwhile_buy_count"),
                                "updated_at_utc": doc.get("updated_at_utc"),
                            },
                        )
                        return
                    _json_response(self, 200, build_r3_t212_daily_prognosis(root, persist=True))
                    return
                if path == "/api/r3/functions":
                    _ensure_import_path(root)
                    from analytics.r3_trading_functions import build_r3_trading_functions

                    _json_response(self, 200, build_r3_trading_functions(root, persist=True))
                    return
                if path == "/api/r3/operator-readiness":
                    _ensure_import_path(root)
                    from analytics.r3_operator_readiness import sync_r3_operator_readiness

                    q = parse_qs(urlparse(self.path).query)
                    do_repair = str((q.get("repair") or ["0"])[0]).lower() in {"1", "true", "yes"}
                    _json_response(
                        self,
                        200,
                        sync_r3_operator_readiness(root, persist=True, repair=do_repair),
                    )
                    return
                if path == "/api/r3/mirror":
                    _ensure_import_path(root)
                    from analytics.r3_exec_mirror import build_exec_mirror_state
                    from analytics.r3_surface import exec_mirror_mode

                    exec_lean = exec_mirror_mode(root)
                    q = parse_qs(urlparse(self.path).query)
                    do_scan = str((q.get("scan") or ["0"])[0]).lower() in {"1", "true", "yes"}
                    force_refresh = str((q.get("refresh") or ["0"])[0]).lower() in {"1", "true", "yes"}
                    if not exec_lean:
                        try:
                            from analytics.r3_quote_keepalive import (
                                load_quote_keepalive_policy,
                                tick_quote_keepalive,
                            )

                            qpol = load_quote_keepalive_policy(root)
                            keepalive_doc = None
                            if force_refresh or qpol.get("refresh_on_mirror_poll", False):
                                keepalive_doc = tick_quote_keepalive(
                                    root,
                                    force=force_refresh,
                                    owner="R3_COCKPIT",
                                    persist=True,
                                )
                                if keepalive_doc and not keepalive_doc.get("skipped"):
                                    assess = keepalive_doc.get("assess_after") or keepalive_doc.get("assess") or {}
                                    quote_status = str(
                                        assess.get("quote_status") or keepalive_doc.get("quote_status") or ""
                                    ).upper()
                                    if quote_status == "FRESH" or keepalive_doc.get("ok"):
                                        try:
                                            from analytics.pilot_portfolio_reevaluation import (
                                                run_periodic_reevaluation,
                                            )

                                            run_periodic_reevaluation(root, force=False)
                                        except Exception:
                                            pass
                        except Exception:
                            pass
                        if do_scan or force_refresh:
                            try:
                                from analytics.r3_prognosis_pipeline import (
                                    ensure_r3_prognosis_fresh,
                                    load_automation_policy,
                                )

                                policy = load_automation_policy(root)
                                if force_refresh or policy.get("refresh_on_mirror_poll", False):
                                    ensure_r3_prognosis_fresh(root, force=force_refresh, persist=True)
                            except Exception:
                                pass
                    _json_response(
                        self,
                        200,
                        build_exec_mirror_state(root, refresh_scans=do_scan),
                    )
                    return
                if path == "/api/r3/mirror/panel":
                    _ensure_import_path(root)
                    from analytics.r3_exec_mirror import build_mirror_panel_payload

                    _json_response(self, 200, build_mirror_panel_payload(root))
                    return
                if path == "/api/r3/upgrade":
                    _ensure_import_path(root)
                    from analytics.r3_runtime_upgrade import build_upgrade_status, scan_runtime_upgrades

                    q = parse_qs(urlparse(self.path).query)
                    if str((q.get("scan") or ["1"])[0]).lower() in {"1", "true", "yes"}:
                        scan_runtime_upgrades(root, persist=True)
                    _json_response(self, 200, build_upgrade_status(root))
                    return
                if path == "/api/r3/freigabe":
                    _ensure_import_path(root)
                    from analytics.r3_freigabe import (
                        auto_prepare_freigabe_for_desktop,
                        load_freigabe,
                    )

                    q = parse_qs(urlparse(self.path).query)
                    refresh = str((q.get("prepare") or ["1"])[0]).lower()
                    if refresh in {"1", "true", "yes"}:
                        _json_response(self, 200, auto_prepare_freigabe_for_desktop(root))
                    else:
                        _json_response(self, 200, load_freigabe(root))
                    return
                if path == "/api/r3/ingest":
                    _ensure_import_path(root)
                    from analytics.r3_browser_data import ingest_prognosis_data_from_internet, load_ingest_status

                    refresh = str((parse_qs(urlparse(self.path).query).get("refresh") or ["1"])[0]).lower()
                    if refresh in {"1", "true", "yes"}:
                        full = str((parse_qs(urlparse(self.path).query).get("full") or [""])[0]).lower()
                        _json_response(
                            self,
                            200,
                            ingest_prognosis_data_from_internet(
                                root, fast=full not in {"1", "true", "yes"}, force=full in {"1", "true", "yes"}
                            ),
                        )
                    else:
                        _json_response(self, 200, load_ingest_status(root))
                    return
                if path == "/api/build":
                    _ensure_import_path(root)
                    from analytics.r3_build_channel import apply_queue, build_channel_status, handle_build_command

                    if self.command == "GET":
                        _json_response(self, 200, build_channel_status(root))
                        return
                    msg = str(payload.get("message") or payload.get("text") or "").strip()
                    if payload.get("apply"):
                        _json_response(self, 200, apply_queue(root))
                        return
                    if not msg:
                        self.send_error(400)
                        return
                    _json_response(self, 200, handle_build_command(root, msg))
                    return
                if path == "/api/kernel-roles":
                    _ensure_import_path(root)
                    from analytics.r3_kernel_roles import build_kernel_roles_status

                    _json_response(self, 200, build_kernel_roles_status(root))
                    return
                if path == "/api/continuity":
                    _ensure_import_path(root)
                    from analytics.r3_conversation_continuity import continuity_status

                    _json_response(self, 200, continuity_status(root))
                    return
                if path == "/api/ki/status":
                    _ensure_import_path(root)
                    from analytics.r3_ki_console import ki_health

                    _json_response(self, 200, ki_health(root))
                    return
                if path == "/api/ki/history":
                    _ensure_import_path(root)
                    from analytics.r3_ki_storage import ensure_ki_boot, history_for_ui

                    ensure_ki_boot(root)
                    _json_response(self, 200, {"ok": True, "messages": history_for_ui(root)})
                    return
                if path == "/api/ki/storage":
                    _ensure_import_path(root)
                    from analytics.r3_ki_storage import storage_status

                    _json_response(self, 200, storage_status(root))
                    return
                if path in ("/api/r3/unified", "/api/r3/power"):
                    _ensure_import_path(root)
                    from analytics.r3_unified import build_power_status

                    _json_response(self, 200, build_power_status(root))
                    return
                if path == "/api/ki/advisors":
                    _ensure_import_path(root)
                    from analytics.r3_external_advisor import advisor_status

                    _json_response(self, 200, advisor_status(root))
                    return
                if path == "/api/ki/internet":
                    _ensure_import_path(root)
                    from analytics.r3_ki_web import probe_internet_generic

                    ok = probe_internet_generic()
                    _json_response(
                        self,
                        200,
                        {"ok": True, "internet_ok": ok, "headline_de": "Internet OK" if ok else "Internet offline"},
                    )
                    return
                if path == "/api/ki/guidance":
                    _ensure_import_path(root)
                    from analytics.r3_ki_guidance import guidance_payload, starter_prompts

                    qs = parse_qs(urlparse(self.path).query)
                    voice = (qs.get("voice") or [""])[0] in ("1", "true", "yes")
                    out = guidance_payload(root, voice=voice)
                    out["starters"] = starter_prompts(root)
                    _json_response(self, 200, out)
                    return
                if path == "/api/ki/attachments":
                    _ensure_import_path(root)
                    from analytics.r3_ki_attachments import list_recent_attachments

                    _json_response(self, 200, {"ok": True, "attachments": list_recent_attachments()})
                    return
                if path == "/api/system/status":
                    _ensure_import_path(root)
                    from analytics.preview_system_status import build_preview_system_status

                    doc = build_preview_system_status(root, refresh_h1=False)
                    try:
                        from analytics.r3_surface_theme import friendly_status

                        doc = friendly_status(doc, root)
                    except Exception:
                        pass
                    _json_response(self, 200, doc)
                    return
                if path == "/api/visibility":
                    _ensure_import_path(root)
                    from analytics.operator_visibility import build_visibility_snapshot

                    _json_response(self, 200, build_visibility_snapshot(root))
                    return
                if path == "/api/screenshot":
                    shot = root / "evidence/gui_preview_screenshot.png"
                    if not shot.is_file():
                        prev = _load_report(root).get("screenshot")
                        if prev:
                            shot = Path(str(prev))
                    if not shot.is_file():
                        self.send_error(404)
                        return
                    data = shot.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    _safe_write(self, data)
                    return
                if path == "/api/report":
                    _json_response(self, 200, _load_report(root))
                    return
                if path == "/api/launch/status":
                    _ensure_import_path(root)
                    from analytics.preview_hub_page import _launch_doc_enriched

                    _json_response(self, 200, _launch_doc_enriched(root))
                    return
                if path == "/api/desktop/shell":
                    _ensure_import_path(root)
                    from analytics.r3_ubuntu_shell import build_shell_status

                    _json_response(self, 200, build_shell_status(root))
                    return
                if path.startswith("/api/desktop/launch"):
                    _ensure_import_path(root)
                    from analytics.r3_ubuntu_shell import launch_shell_feature

                    qs = parse_qs(urlparse(self.path).query)
                    feature = (qs.get("feature") or [""])[0]
                    _json_response(self, 200, launch_shell_feature(root, str(feature)))
                    return
                if path.startswith("/api/desktop/power"):
                    _ensure_import_path(root)
                    from analytics.r3_desktop_fusion import launch_power_action

                    qs = parse_qs(urlparse(self.path).query)
                    action = (qs.get("action") or [""])[0]
                    _json_response(self, 200, launch_power_action(root, str(action)))
                    return
                if path.startswith("/api/desktop/search"):
                    _ensure_import_path(root)
                    from analytics.r3_desktop_fusion import fusion_search

                    qs = parse_qs(urlparse(self.path).query)
                    query = (qs.get("q") or [""])[0]
                    _json_response(self, 200, fusion_search(root, str(query)))
                    return
                if path.startswith("/api/desktop/native"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import launch_native_app

                    qs = parse_qs(urlparse(self.path).query)
                    app = (qs.get("app") or [""])[0]
                    _json_response(self, 200, launch_native_app(root, str(app)))
                    return
                if path.startswith("/api/desktop/files"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import list_files

                    qs = parse_qs(urlparse(self.path).query)
                    sub = (qs.get("path") or [""])[0]
                    _json_response(self, 200, list_files(root, subpath=str(sub)))
                    return
                if path.startswith("/api/desktop/project-files"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import list_project_files

                    qs = parse_qs(urlparse(self.path).query)
                    sub = (qs.get("path") or [""])[0]
                    _json_response(self, 200, list_project_files(root, subpath=str(sub)))
                    return
                if path.startswith("/api/desktop/open"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import open_path

                    qs = parse_qs(urlparse(self.path).query)
                    fpath = (qs.get("path") or [""])[0]
                    _json_response(self, 200, open_path(str(fpath)))
                    return
                if path.startswith("/api/desktop/terminal"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import open_system_terminal, run_terminal_action

                    qs = parse_qs(urlparse(self.path).query)
                    action = (qs.get("action") or [""])[0]
                    if action == "system":
                        _json_response(self, 200, open_system_terminal(root))
                    else:
                        _json_response(self, 200, run_terminal_action(root, str(action)))
                    return
                if path == "/api/desktop/settings":
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import native_settings

                    doc = native_settings(root)
                    _json_response(self, 200, {"ok": True, "settings": doc})
                    return
                if path == "/api/desktop/step-a":
                    _ensure_import_path(root)
                    from analytics.r3_step_a import evaluate_step_a

                    _json_response(self, 200, evaluate_step_a(root))
                    return
                if path == "/api/session/status":
                    _ensure_import_path(root)
                    from analytics.r3_session_manager import session_status_doc

                    _json_response(self, 200, session_status_doc(root))
                    return
                if path == "/api/desktop/step-b":
                    _ensure_import_path(root)
                    from analytics.r3_step_b import evaluate_step_b

                    _json_response(self, 200, evaluate_step_b(root))
                    return
                if path == "/api/desktop/quality":
                    _ensure_import_path(root)
                    from analytics.r3_quality_scores import evaluate_quality_scores

                    _json_response(self, 200, evaluate_quality_scores(root))
                    return
                if path == "/api/desktop/h1-health":
                    _ensure_import_path(root)
                    from analytics.h1_migration_guard import ensure_h1_migration_healthy

                    _json_response(self, 200, ensure_h1_migration_healthy(root, auto_fix=False))
                    return
                if path == "/api/desktop/closure":
                    _ensure_import_path(root)
                    from analytics.r3_ubuntu_closure import evaluate_ubuntu_closure

                    _json_response(self, 200, evaluate_ubuntu_closure(root))
                    return
                if path.startswith("/api/desktop/plane"):
                    _ensure_import_path(root)
                    from analytics.r3_system_plane import plane_status

                    qs = parse_qs(urlparse(self.path).query)
                    domain = (qs.get("domain") or [""])[0]
                    _json_response(self, 200, plane_status(root, domain=str(domain) or None))
                    return
                if path.startswith("/api/desktop/panel"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import native_panel

                    qs = parse_qs(urlparse(self.path).query)
                    panel = (qs.get("panel") or [""])[0]
                    _json_response(self, 200, native_panel(root, str(panel)))
                    return
                if path.startswith("/api/desktop/preview"):
                    _ensure_import_path(root)
                    from analytics.r3_native_apps import preview_file

                    qs = parse_qs(urlparse(self.path).query)
                    fpath = (qs.get("path") or [""])[0]
                    _json_response(self, 200, preview_file(str(fpath)))
                    return
                if path == "/api/health":
                    uptime_path = root / "evidence/preview_hub_uptime.json"
                    uptime = {}
                    if uptime_path.is_file():
                        try:
                            uptime = json.loads(uptime_path.read_text(encoding="utf-8"))
                        except (json.JSONDecodeError, OSError):
                            uptime = {}
                    from analytics.hub_runtime import HUB_PRODUCT, HUB_SCHEMA_VERSION

                    _json_response(
                        self,
                        200,
                        {
                            "ok": True,
                            "port": port,
                            "product": HUB_PRODUCT,
                            "hub_schema_version": HUB_SCHEMA_VERSION,
                            "first_started_utc": uptime.get("first_started_utc"),
                        },
                    )
                    return
                self.send_error(404)
            except (BrokenPipeError, ConnectionResetError):
                return
            except Exception as exc:
                _append_hub_log(root, f"GET {path} failed: {exc}\n{traceback.format_exc()}")
                body = _error_html("Preview-Hub Fehler", str(exc)).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                _safe_write(self, body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            content_type = str(self.headers.get("Content-Type") or "")

            if _exec_mirror_route_blocked(self, root, method="POST", path=path):
                return

            if path == "/api/r3/start":
                _ensure_import_path(root)
                from analytics.r3_one_click_start import run_one_click_start

                _json_response(self, 200, run_one_click_start(root, persist=True))
                return

            if path == "/api/r3/t212/credentials":
                _ensure_import_path(root)
                from analytics.r3_t212_operator_api import save_t212_credentials_from_web

                try:
                    payload = json.loads(raw.decode("utf-8") if raw else "{}")
                except json.JSONDecodeError:
                    payload = {}
                if not isinstance(payload, dict):
                    payload = {}
                out = save_t212_credentials_from_web(
                    root,
                    api_key=str(payload.get("api_key") or ""),
                    api_secret=str(payload.get("api_secret") or ""),
                )
                _json_response(self, 200 if out.get("ok") else 400, out)
                return

            if path == "/api/r3/upgrade":
                _ensure_import_path(root)
                from analytics.r3_runtime_upgrade import (
                    confirm_runtime_upgrade,
                    dismiss_runtime_upgrade,
                )

                q = parse_qs(urlparse(self.path).query)
                action = str((q.get("action") or [""])[0]).lower()
                proposal_id = str((q.get("proposal_id") or [""])[0]).strip()
                if action == "confirm":
                    _json_response(self, 200, confirm_runtime_upgrade(root, proposal_id=proposal_id))
                elif action == "dismiss":
                    _json_response(self, 200, dismiss_runtime_upgrade(root, proposal_id=proposal_id))
                else:
                    _json_response(self, 400, {"ok": False, "message_de": "action=confirm oder dismiss erforderlich"})
                return

            if path == "/api/h1/artifact/upload":
                _ensure_import_path(root)
                from analytics.h1_artifact_transport import ingest_prep_artifact_from_request

                out = ingest_prep_artifact_from_request(
                    root, headers=self.headers, body=raw, query=parse_qs(parsed.query)
                )
                _json_response(self, 200 if out.get("ok") else 400, out)
                return

            if path.startswith("/local/vault"):
                try:
                    if _serve_vault(
                        self,
                        root,
                        method="POST",
                        path=path,
                        query=parsed.query,
                        content_type=content_type,
                        body=raw,
                    ):
                        return
                except Exception as exc:
                    _append_hub_log(root, f"POST {path} vault failed: {exc}\n{traceback.format_exc()}")
                    body = _error_html("Schlüssel-Tresor Fehler", str(exc)).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    _safe_write(self, body)
                    return

            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except (json.JSONDecodeError, ValueError):
                _json_response(self, 400, {"ok": False, "message_de": "Ungültiges JSON"})
                return

            if path == "/api/worker/pull":
                _ensure_import_path(root)
                from analytics.federation_compute import pull_task_for_worker
                from analytics.federation_compute import worker_capabilities

                wid = str(payload.get("worker_id") or "").strip()
                caps = list(payload.get("capabilities") or [])
                if not caps:
                    caps = worker_capabilities(root, bundle_kind=str(payload.get("bundle_kind") or "lite"))
                task = pull_task_for_worker(
                    root,
                    worker_id=wid,
                    capabilities=caps,
                    cpus=int(payload.get("cpus") or 1),
                )
                _json_response(self, 200, {"ok": True, "task": task})
                return

            if path == "/api/worker/complete":
                _ensure_import_path(root)
                from analytics.federation_compute import complete_task

                out = complete_task(
                    root,
                    task_id=str(payload.get("task_id") or ""),
                    worker_id=str(payload.get("worker_id") or ""),
                    ok=bool(payload.get("ok")),
                    result=dict(payload.get("result") or {}),
                )
                _json_response(self, 200 if out.get("ok") else 400, out)
                return

            if path in ("/api/worker/register", "/api/worker/contribute"):
                _ensure_import_path(root)
                from analytics.federation_compute import sync_compute_demand
                from analytics.preview_federation import upsert_worker

                if path == "/api/worker/register":
                    wid = str(payload.get("worker_id") or "").strip()
                    if not wid:
                        _json_response(self, 400, {"ok": False, "message_de": "worker_id fehlt"})
                        return
                    payload.setdefault("role", "compute")
                    payload["last_seen_utc"] = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
                    out = upsert_worker(root, payload)
                    _json_response(self, 200 if out.get("ok") else 500, out)
                    return
                out = upsert_worker(root, payload)
                if out.get("ok"):
                    try:
                        sync_compute_demand(root)
                    except Exception:
                        pass
                _json_response(self, 200 if out.get("ok") else 500, out)
                return

            if path == "/api/dev/trail":
                _ensure_import_path(root)
                from analytics.r3_dev_trail import record_dev_change, set_next_changes

                if payload.get("next_de"):
                    doc = set_next_changes(root, list(payload.get("next_de") or []))
                    _json_response(self, 200, {"ok": True, "trail": doc})
                    return
                title = str(payload.get("title_de") or payload.get("title") or "").strip()
                if not title:
                    _json_response(self, 400, {"ok": False, "message_de": "title_de fehlt"})
                    return
                entry = record_dev_change(
                    root,
                    title_de=title,
                    detail_de=str(payload.get("detail_de") or payload.get("detail") or ""),
                    status=str(payload.get("status") or "active"),
                )
                _json_response(self, 200, {"ok": True, "entry": entry})
                return

            if path == "/api/pilot/contribute":
                _ensure_import_path(root)
                from analytics.r3_pilot_central import implement_and_test_contribution, submit_contribution

                msg = str(payload.get("message") or payload.get("mandate_de") or "").strip()
                author = str(payload.get("author_de") or "Mitwirkende")
                if not msg:
                    self.send_error(400)
                    return
                sub = submit_contribution(
                    root, msg, author_de=author, author_id=str(payload.get("author_id") or author)
                )
                out = (
                    implement_and_test_contribution(root, (sub.get("item") or {}).get("id"))
                    if sub.get("ok")
                    else sub
                )
                _json_response(self, 200 if out.get("ok", sub.get("ok")) else 503, out)
                return

            if path in ("/api/pilot/approve", "/api/pilot/reject"):
                _ensure_import_path(root)
                from analytics.r3_pilot_central import king_approve, king_reject

                iid = str(payload.get("id") or "").strip() or None
                out = king_approve(root, iid) if path.endswith("/approve") else king_reject(root, iid)
                _json_response(self, 200 if out.get("ok") else 403, out)
                return

            if path == "/api/desktop/screenshot":
                _ensure_import_path(root)
                from analytics.r3_native_apps import take_screenshot

                _json_response(self, 200, take_screenshot(root))
                return

            if path == "/api/desktop/lock":
                _ensure_import_path(root)
                from analytics.r3_native_apps import lock_session

                _json_response(self, 200, lock_session())
                return

            if path == "/api/desktop/run":
                _ensure_import_path(root)
                from analytics.r3_native_apps import run_console_command

                cmd = str(payload.get("command") or "").strip()
                _json_response(self, 200, run_console_command(root, cmd))
                return

            if path == "/api/desktop/plane":
                _ensure_import_path(root)
                from analytics.r3_system_plane import plane_action

                _json_response(self, 200, plane_action(root, payload))
                return

            if path == "/api/ki/upload":
                _ensure_import_path(root)
                from analytics.r3_ki_attachments import save_upload_b64

                out = save_upload_b64(
                    root,
                    filename=str(payload.get("filename") or "upload.txt"),
                    content_b64=str(payload.get("content_b64") or payload.get("data_b64") or ""),
                    mime=str(payload.get("mime") or payload.get("content_type") or "text/plain"),
                )
                _json_response(self, 200 if out.get("ok") else 400, out)
                return

            if path == "/api/ki/import":
                _ensure_import_path(root)
                from analytics.r3_ki_console import import_chat_to_ki_storage

                out = import_chat_to_ki_storage(root)
                n = int(out.get("session_messages") or 0)
                out = {
                    **out,
                    "ok": True,
                    "reply_de": f"R3-Archiv geladen — {n} Nachrichten in der Sitzung.",
                    "route_de": "Archiv",
                }
                _json_response(self, 200, out)
                return

            if path == "/api/session/start":
                _ensure_import_path(root)
                from analytics.r3_login_shell import handle_session_start

                _json_response(self, 200, handle_session_start(root))
                return
            if path == "/api/session/end":
                _ensure_import_path(root)
                from analytics.r3_login_shell import handle_session_end

                _json_response(self, 200, handle_session_end(root))
                return
            if path == "/api/ki/chat":
                _ensure_import_path(root)
                from analytics.r3_ki_console import handle_ki_message

                msg = str(payload.get("message") or payload.get("text") or "").strip()
                reset = bool(payload.get("reset"))
                voice = bool(payload.get("voice"))
                att = list(payload.get("attachment_ids") or payload.get("attachments") or [])
                out = handle_ki_message(root, msg, reset=reset, attachment_ids=att, voice=voice)
                code = 200 if out.get("ok") or out.get("prognose") or out.get("web") else 503
                _json_response(self, code, out)
                return

            if path == "/api/r3/order":
                _ensure_import_path(root)
                from analytics.r3_stock_orders import handle_r3_order_request

                out = handle_r3_order_request(root, payload)
                _json_response(self, 200 if out.get("ok") else 400, out)
                return

            if path != "/api/action":
                self.send_error(404)
                return
            action_id = str(payload.get("action") or payload.get("id") or "")
            result = _run_action(root, action_id)
            code = 200 if result.get("ok") else 500
            _json_response(self, code, result)

    return PreviewHubHandler


@contextmanager
def _hub_daemon_lock(root: Path):
    root = Path(root)
    lock_path = root / "evidence/preview_hub_daemon.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("w", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        raise SystemExit("Preview-Hub läuft bereits (Daemon-Lock)")
    try:
        fh.write(str(os.getpid()) + "\n")
        fh.flush()
        yield
    finally:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def _start_quote_keepalive_daemon(root: Path) -> None:
    """Hintergrund-Keepalive — R3-Kurse auch ohne Browser-Fokus (~60s)."""

    def _loop() -> None:
        while True:
            time.sleep(60)
            try:
                from analytics.r3_quote_keepalive import tick_quote_keepalive

                tick_quote_keepalive(root, force=False, owner="r3_quote_keepalive", persist=True)
            except Exception:
                pass

    threading.Thread(target=_loop, name="r3-quote-keepalive", daemon=True).start()


def run_server(root: Path, port: int) -> None:
    root = _ensure_import_path(Path(root))
    _kill_foreign_hubs(root, port)
    os.environ.setdefault("AA_LINUX_NATIVE_APP", "1")
    os.environ["AA_PROJECT_ROOT"] = str(root)
    from analytics.preview_federation import hub_bind_host, hub_public_base_url, sync_king_contribution

    bind = hub_bind_host(root)
    handler = make_handler(root, port)
    server = ThreadingHTTPServer((bind, port), handler)
    with _hub_daemon_lock(root):
        try:
            sync_king_contribution(root)
        except Exception:
            pass
        _write_meta(root, port, os.getpid())
        public = hub_public_base_url(root, port=port)
        print(f"[preview-hub] bind={bind} local=http://127.0.0.1:{port}/ share={public}/", flush=True)
        _start_quote_keepalive_daemon(root)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


def _spawn_hub_daemon(root: Path, port: int) -> None:
    root = Path(root)
    env = os.environ.copy()
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    log_path = _hub_log_path(root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("a", encoding="utf-8")
    subprocess.Popen(
        [_py(root), str(root / "tools/preview_hub.py"), "--daemon", "--port", str(port)],
        cwd=str(root),
        env=env,
        start_new_session=True,
        stdout=log_fh,
        stderr=log_fh,
    )


def ensure_hub_running(
    root: Path,
    *,
    port: int = DEFAULT_PORT,
    wait_s: float = 8.0,
    restart: bool = False,
) -> int:
    root = Path(root)
    if restart:
        _stop_hub(root, port)
    elif _port_listening(port) and _hub_healthy(port) and _hub_route_ready(port, "/login"):
        _kill_foreign_hubs(root, port, keep_meta=True)
        return port
    elif _port_listening(port) and _hub_healthy(port):
        _append_hub_log(root, "Hub veraltet (/login fehlt oder 404) — Neustart")
        _stop_hub(root, port)
    elif _port_listening(port):
        _append_hub_log(root, f"Hub auf :{port} antwortet leer/kaputt — Neustart")
        _stop_hub(root, port)
    else:
        _kill_foreign_hubs(root, port, keep_meta=False)
        _release_hub_daemon_lock(root)

    for attempt in range(2):
        _spawn_hub_daemon(root, port)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if _hub_healthy(port):
                return port
            time.sleep(0.2)
        if attempt == 0:
            _append_hub_log(root, f"Hub-Start Versuch {attempt + 1} fehlgeschlagen — Lock bereinigen")
            _kill_foreign_hubs(root, port, keep_meta=False)
            _release_hub_daemon_lock(root)
    raise RuntimeError(f"Preview-Hub startete nicht gesund auf Port {port}")


def main() -> int:
    p = argparse.ArgumentParser(description="R3 Preview Hub — Cockpit")
    p.add_argument("--daemon", action="store_true", help="Server im Hintergrund (Autostart)")
    p.add_argument("--ensure", action="store_true", help="Hub starten falls nicht aktiv")
    p.add_argument("--stop", action="store_true", help="Alle Hub-Instanzen dieses Projekts beenden")
    p.add_argument("--restart", action="store_true", help="Mit --ensure: kaputten Hub ersetzen")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = p.parse_args()
    root = _project_root()

    if args.stop:
        _stop_hub(root, args.port)
        print("stopped")
        return 0

    if args.ensure:
        try:
            port = ensure_hub_running(root, port=args.port, restart=args.restart)
            print(port)
            return 0
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    if args.daemon:
        root = _ensure_import_path(root)
        from analytics.preview_federation import is_worker_bundle, resolve_worker_hub_url

        if is_worker_bundle(root):
            king = resolve_worker_hub_url(root) or "König-Hub"
            print(f"[FEHLER] Worker-Bundle startet keinen lokalen Hub — nutze {king}", file=sys.stderr)
            return 1
        run_server(root, args.port)
        return 0

    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
