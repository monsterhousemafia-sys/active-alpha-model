"""Unix-Socket JSON-API — maschinenlesbarer Zustand für Agent/Automation."""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

Handler = Callable[[Path, Dict[str, Any]], Dict[str, Any]]

_SOCKET_REL = Path("evidence/.runtime-api.sock")


def _socket_path(root: Path) -> Path:
    return Path(root) / _SOCKET_REL


def _handlers() -> Dict[str, Handler]:
    def h1_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed
        from analytics.h1_governance_status import sync_h1_governance_status

        return {
            "h1_backtest": h1_backtest_status(root),
            "governance": sync_h1_governance_status(root, write_readiness=False),
            "sealed": is_h1_backtest_sealed(root),
        }

    def launch_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.launch_progress_board import build_launch_status

        return build_launch_status(root, refresh_h1=False, persist=False)

    def hub_health(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from tools.preview_hub import _hub_healthy

        from analytics.preview_federation import federation_config

        port = int(federation_config(root).get("hub_port") or 17890)
        return {"ok": _hub_healthy(port), "port": port}

    def remote_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.remote_hub_access import remote_access_status

        return remote_access_status(root)

    def evidence_watch(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.evidence_inotify_watch import run_evidence_watch_once

        return run_evidence_watch_once(root)

    def runtime_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.aa_linux_runtime import build_runtime_status

        return build_runtime_status(root)

    def mandate_alignment(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.agent_mandate import evaluate_mandate_alignment

        return evaluate_mandate_alignment(root, persist=False)

    def system_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.preview_system_status import build_preview_system_status

        return build_preview_system_status(root, refresh_h1=False)

    def cognitive_status(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.cognitive_kernel import cognitive_kernel_status

        return cognitive_kernel_status(root)

    def runtime_profile_cmd(root: Path, _: Dict[str, Any]) -> Dict[str, Any]:
        from analytics.linux_runtime_unified import runtime_profile

        return runtime_profile(root)

    return {
        "h1.status": h1_status,
        "launch.status": launch_status,
        "hub.health": hub_health,
        "remote.status": remote_status,
        "evidence.watch": evidence_watch,
        "runtime.status": runtime_status,
        "mandate.alignment": mandate_alignment,
        "system.status": system_status,
        "cognitive.status": cognitive_status,
        "runtime.profile": runtime_profile_cmd,
        "ping": lambda _r, _p: {"ok": True, "pong": True},
    }


def dispatch(root: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    cmd = str(payload.get("cmd") or payload.get("id") or "").strip().lower()
    handlers = _handlers()
    fn = handlers.get(cmd)
    if fn is None:
        return {"ok": False, "error_de": f"unbekannter Befehl: {cmd}", "commands": sorted(handlers)}
    try:
        result = fn(root, payload)
        return {"ok": True, "cmd": cmd, "result": result}
    except Exception as exc:
        return {"ok": False, "cmd": cmd, "error_de": str(exc)[:300]}


def _handle_client(root: Path, conn: socket.socket) -> None:
    try:
        data = b""
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        line = data.split(b"\n", 1)[0].decode("utf-8", errors="replace").strip()
        payload = json.loads(line or "{}")
        out = dispatch(root, payload if isinstance(payload, dict) else {})
        conn.sendall((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
    except Exception as exc:
        err = json.dumps({"ok": False, "error_de": str(exc)[:200]}, ensure_ascii=False) + "\n"
        try:
            conn.sendall(err.encode("utf-8"))
        except OSError:
            pass
    finally:
        conn.close()


def serve_forever(root: Path, *, host: str = "127.0.0.1") -> None:
    root = _ensure_root_path(Path(root))
    sock_path = _socket_path(root)
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    os.chmod(sock_path, 0o600)
    server.listen(8)
    try:
        from analytics.runtime_structured_log import emit_runtime_log

        emit_runtime_log("runtime-api", "listening", path=str(sock_path.relative_to(root)))
    except Exception:
        pass

    while True:
        conn, _ = server.accept()
        threading.Thread(target=_handle_client, args=(root, conn), daemon=True).start()


def query(root: Path, cmd: str, **params: Any) -> Dict[str, Any]:
    root = Path(root)
    sock_path = _socket_path(root)
    if not sock_path.is_socket():
        return dispatch(root, {"cmd": cmd, **params})
    payload = json.dumps({"cmd": cmd, **params}, ensure_ascii=False) + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(8.0)
        client.connect(str(sock_path))
        client.sendall(payload.encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            block = client.recv(65536)
            if not block:
                break
            buf += block
        line = buf.split(b"\n", 1)[0].decode("utf-8", errors="replace")
        return json.loads(line or "{}")


def _ensure_root_path(root: Path) -> Path:
    root = Path(root)
    entry = str(root)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return root


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Active Alpha Runtime API")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--query", metavar="CMD", help="z.B. h1.status")
    p.add_argument("--root", default=os.environ.get("AA_PROJECT_ROOT", ""))
    args = p.parse_args()
    root = _ensure_root_path(Path(args.root or Path(__file__).resolve().parents[1]))
    if args.serve:
        serve_forever(root)
        return 0
    if args.query:
        print(json.dumps(query(root, args.query), indent=2, ensure_ascii=False))
        return 0
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
