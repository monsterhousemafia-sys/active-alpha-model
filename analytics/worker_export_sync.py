"""Worker-Export nur bei URL/Token-Änderung — ZIP bleibt stabil."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

_MARKER_REL = Path("evidence/community_spread_export.json")

# Never rsync these into a worker bundle (recursive copy / bloat traps).
WORKER_BUNDLE_RSYNC_EXCLUDES: Tuple[str, ...] = (
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    "validation_runs/",
    "model_output_sp500_pit_t212/",
    "runs/",
    "build/",
    "active_alpha_worker_FULL/",
    "active_alpha_worker_LITE/",
    "active_alpha_model_worker_*/",
    ".venv/",
)


def validate_worker_export_dest(root: Path, dest: Path) -> Path:
    """Fail closed: export target must live outside the project tree."""
    root = Path(root).resolve()
    dest = Path(dest).resolve()
    if dest == root or root in dest.parents:
        raise ValueError(
            f"Worker export dest must be outside project root ({root}); got {dest} "
            "(recursive rsync would nest active_alpha_worker_FULL and blow disk usage)."
        )
    return dest


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


def export_fingerprint(root: Path) -> str:
    from analytics.preview_federation import federation_config, prepare_worker_bundle_config

    cfg = prepare_worker_bundle_config(root)
    fed = federation_config(root)
    payload = {
        "hub_join_url": cfg.get("hub_join_url"),
        "join_token": cfg.get("join_token"),
        "join_token_locked": fed.get("join_token_locked"),
        "public_base_url_locked": fed.get("public_base_url_locked"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_export_marker(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _MARKER_REL)


def export_is_current(root: Path) -> Tuple[bool, str]:
    root = Path(root)
    marker = load_export_marker(root)
    fp = export_fingerprint(root)
    lite_zip = Path(str(marker.get("lite_zip") or root.parent / "active_alpha_worker_LITE.zip"))
    if marker.get("fingerprint") == fp and lite_zip.is_file():
        join = _load_json(lite_zip.parent / "active_alpha_worker_LITE" / "preview_worker_join.json")
        if not join:
            join_path = lite_zip.parent / "active_alpha_worker_LITE" / "preview_worker_join.json"
            if join_path.is_file():
                join = _load_json(join_path)
        if join.get("hub_join_url") and join.get("join_token"):
            return True, f"Export aktuell ({fp})"
    return False, f"Export veraltet oder fehlt ({fp})"


def ensure_lite_export(root: Path, *, force: bool = False) -> Dict[str, Any]:
    root = Path(root)
    current, detail = export_is_current(root)
    if current and not force:
        marker = load_export_marker(root)
        return {
            "ok": True,
            "skipped": True,
            "detail_de": detail,
            "lite_zip": str(marker.get("lite_zip") or root.parent / "active_alpha_worker_LITE.zip"),
            "fingerprint": marker.get("fingerprint"),
        }

    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    proc = subprocess.run(
        [str(py), str(root / "tools/ai_kernel.py"), "preview-export-lite"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    fp = export_fingerprint(root)
    lite_dest = str(root.parent / "active_alpha_worker_LITE")
    lite_zip = str(root.parent / "active_alpha_worker_LITE.zip")
    from analytics.preview_federation import build_share_package

    pkg = build_share_package(root)
    marker = {
        "lite_dest": lite_dest,
        "lite_zip": lite_zip,
        "join_url": pkg.get("share_url"),
        "fingerprint": fp,
        "updated_at_utc": _utc_now(),
        "export_rc": proc.returncode,
    }
    if proc.returncode == 0:
        marker["lite_dest"] = str(Path(marker["lite_dest"]).resolve())
        marker["lite_zip"] = str(Path(marker["lite_zip"]).resolve())
        path = root / _MARKER_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": proc.returncode == 0,
        "skipped": False,
        "export_rc": proc.returncode,
        "lite_zip": lite_zip,
        "fingerprint": fp,
        "detail_de": "Lite-ZIP neu exportiert" if proc.returncode == 0 else f"Export rc={proc.returncode}",
    }


def build_worker_stability_status(root: Path) -> Dict[str, Any]:
    """Langzeit-Status: Tunnel, Join-URL, ZIP-Sync, Federation-Worker."""
    root = Path(root)
    from analytics.preview_federation import build_share_package, federation_config

    try:
        from analytics.remote_hub_access import remote_access_status
    except Exception:
        remote_access_status = None  # type: ignore[assignment]

    fed = federation_config(root)
    pkg = build_share_package(root)
    current, export_detail = export_is_current(root)
    remote: Dict[str, Any] = {}
    if remote_access_status is not None:
        try:
            remote = remote_access_status(root)
        except Exception as exc:
            remote = {"error_de": str(exc)[:120]}

    workers_n = 0
    king_registered = False
    try:
        workers_doc = _load_json(root / "evidence/preview_federation.json")
        workers = workers_doc.get("workers") or {}
        if isinstance(workers, dict):
            workers_n = len(workers)
            king_id = str(fed.get("king_worker_id") or "king")
            king_registered = king_id in workers or any(
                str(w.get("role") or "").lower() == "king"
                for w in workers.values()
                if isinstance(w, dict)
            )
        elif isinstance(workers, list):
            workers_n = len(workers)
            king_registered = any(
                str(w.get("worker_id") or "") == str(fed.get("king_worker_id") or "king")
                for w in workers
                if isinstance(w, dict)
            )
    except Exception:
        pass

    join_url = str(pkg.get("share_url") or fed.get("public_base_url") or "").rstrip("/")
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(remote.get("remote_ready")) and bool(join_url),
        "join_url": join_url,
        "join_token_set": bool(fed.get("join_token")),
        "tunnel_stable": bool(remote.get("stable")),
        "tunnel_token_set": bool(remote.get("tunnel_token_set")),
        "tunnel_pid_alive": bool(remote.get("tunnel_pid_alive")),
        "public_base_url": str(fed.get("public_base_url") or "").rstrip("/"),
        "export_current": current,
        "export_detail_de": export_detail,
        "workers_online": workers_n,
        "king_registered": king_registered,
        "headline_de": (
            f"Worker-Stabilität — Join {join_url or 'n/a'}"
            if remote.get("tunnel_pid_alive")
            else "Worker-Stabilität — Tunnel/Hub prüfen"
        ),
        "manual_step_de": (
            "bash tools/king_ops.sh tunnel-stable setup"
            if not remote.get("tunnel_token_set")
            else None
        ),
    }
    from aa_safe_io import atomic_write_json

    atomic_write_json(root / "evidence/worker_stability_latest.json", doc)
    return doc
